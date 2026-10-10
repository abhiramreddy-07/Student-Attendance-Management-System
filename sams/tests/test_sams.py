import json
from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (ABSENT, PRESENT, Attendance, AttendanceAuditLog, Notification,
                        QRAttendanceSession, Student, User)
from app.services import attendance_stats, calc_percentage, student_summary
from conftest import login, make_student


# ---------------------------------------------------------------- authentication
def test_admin_login_logout(client, admin):
    r = login(client, "admin", "Admin@123", "admin")
    assert b"Dashboard" in r.data
    r = client.post("/logout", follow_redirects=True)
    assert b"logged out" in r.data
    assert client.get("/admin/dashboard").status_code == 302  # back to login


def test_student_login_logout(client, app):
    make_student("S1")
    r = login(client, "s1", "Student@123", "student")
    assert b"My Dashboard" in r.data or b"Hello" in r.data
    client.post("/logout")
    assert client.get("/student/dashboard").status_code == 302


def test_login_by_email_and_wrong_password_and_wrong_role(client, admin):
    assert b"Dashboard" in login(client, "admin@t.example.edu", "Admin@123", "admin").data
    client.post("/logout")
    assert b"Invalid credentials" in login(client, "admin", "wrong", "admin").data
    assert b"Invalid credentials" in login(client, "admin", "Admin@123", "student").data


def test_passwords_are_hashed(admin):
    assert admin.password_hash != "Admin@123" and admin.password_hash.startswith(("scrypt", "pbkdf2"))


def test_deactivated_student_cannot_login(client, app):
    s = make_student("S1")
    s.user.active = False
    db.session.commit()
    assert b"deactivated" in login(client, "s1", "Student@123", "student").data


def test_open_redirect_blocked(client, admin):
    r = client.post("/login?next=//evil.com", data={"identifier": "admin", "password": "Admin@123",
                                                    "role": "admin"})
    assert "evil.com" not in r.headers["Location"]


# ---------------------------------------------------------------- authorization
def test_student_cannot_open_admin_pages(client, app):
    make_student("S1")
    login(client, "s1", "Student@123", "student")
    for url in ["/admin/dashboard", "/students/", "/attendance/mark", "/reports/",
                "/reports/export.csv", "/qr/new", "/notifications/new", "/attendance/history"]:
        assert client.get(url).status_code == 403, url
    assert b"Unauthorized Access" in client.get("/students/").data


def test_admin_cannot_use_student_portal(admin_client):
    assert admin_client.get("/student/dashboard").status_code == 403
    assert admin_client.get("/qr/scan").status_code == 403


def test_student_cannot_see_other_students_notification(client, app, admin):
    a, b = make_student("A1"), make_student("B1")
    n = Notification(title="Private", message="x", target_type="student", student_id=b.id,
                     created_by=admin.id)
    db.session.add(n)
    db.session.commit()
    login(client, "a1", "Student@123", "student")
    assert client.get(f"/notifications/{n.id}").status_code == 404
    assert client.post(f"/notifications/{n.id}/read").status_code == 404


def test_student_pages_only_show_own_data(client, app, admin, weekday):
    a, b = make_student("A1"), make_student("B1")
    db.session.add_all([Attendance(student_id=a.id, attendance_date=weekday, status=PRESENT),
                        Attendance(student_id=b.id, attendance_date=weekday, status=ABSENT)])
    db.session.commit()
    login(client, "a1", "Student@123", "student")
    r = client.get("/student/attendance?student_id=%d" % b.id)  # tampering has no effect
    assert b"Present" in r.data and b"Absent</span>" not in r.data
    assert client.get(f"/students/{b.id}").status_code == 403


# ---------------------------------------------------------------- student management
def student_form(**kw):
    d = dict(student_code="NEW001", full_name="New Student", roll_number="N-1",
             email="new@t.example.edu", mobile="9876543210", department="Computer Science",
             year="2", section="A", password="")
    d.update(kw)
    return d


def test_create_edit_search_deactivate_delete_student(admin_client):
    r = admin_client.post("/students/add", data=student_form(), follow_redirects=True)
    assert b"Student created" in r.data and b"temporary" not in r.data
    s = Student.query.filter_by(student_code="NEW001").first()
    assert s and s.user.check_password("x") is False
    assert b"New Student" in admin_client.get("/students/?q=N-1").data
    assert b"No students found" in admin_client.get("/students/?q=zzzz").data
    r = admin_client.post(f"/students/{s.id}/edit", data=student_form(full_name="Renamed"),
                          follow_redirects=True)
    assert b"Renamed" in r.data
    admin_client.post(f"/students/{s.id}/toggle")
    assert db.session.get(Student, s.id).user.active is False
    admin_client.post(f"/students/{s.id}/delete")
    assert Student.query.count() == 0 and User.query.filter_by(username="new001").first() is None


def test_duplicate_roll_and_email_rejected(admin_client):
    admin_client.post("/students/add", data=student_form())
    r = admin_client.post("/students/add", data=student_form(student_code="NEW002"),
                          follow_redirects=True)
    assert b"already assigned" in r.data and b"already registered" in r.data
    assert Student.query.count() == 1


def test_invalid_student_form_rejected(admin_client):
    r = admin_client.post("/students/add", data=student_form(email="bad", mobile="12", year="9",
                                                             department="Nope"), follow_redirects=True)
    assert b"valid email" in r.data and b"Mobile number" in r.data and b"valid department" in r.data
    assert Student.query.count() == 0


def test_student_list_pagination(admin_client):
    for i in range(23):
        make_student(f"P{i:02d}")
    assert b"Showing 1" in admin_client.get("/students/").data
    assert b"Showing 21" in admin_client.get("/students/?page=3").data


def test_empty_database_pages(admin_client):
    for url in ["/admin/dashboard", "/students/", "/attendance/history", "/reports/",
                "/notifications/", "/qr/", "/attendance/audit", "/attendance/holidays",
                "/attendance/mark", "/qr/new", "/notifications/new"]:
        assert admin_client.get(url).status_code == 200, url


# ---------------------------------------------------------------- attendance + percentage
def test_percentage_formula_45_of_50(app):
    s = make_student("S1")
    start = date(2024, 1, 1)
    for i in range(50):
        db.session.add(Attendance(student_id=s.id, attendance_date=start + timedelta(days=i),
                                  status=PRESENT if i < 45 else ABSENT))
    db.session.commit()
    m = student_summary(s.id)
    assert (m.present, m.absent, m.total, m.percentage) == (45, 5, 50, 90.0)


def test_zero_records_no_division_error(app):
    s = make_student("S1")
    m = student_summary(s.id)
    assert m.total == 0 and m.percentage == 0.0 and calc_percentage(0, 0) == 0.0


def test_date_range_filter(app):
    s = make_student("S1")
    for i, st in enumerate([PRESENT, PRESENT, ABSENT, ABSENT]):
        db.session.add(Attendance(student_id=s.id, attendance_date=date(2024, 3, 1 + i), status=st))
    db.session.commit()
    assert student_summary(s.id, date(2024, 3, 1), date(2024, 3, 2)).percentage == 100.0
    assert student_summary(s.id, date(2024, 3, 3)).percentage == 0.0


def test_holidays_not_counted_and_block_marking(admin_client, app, weekday):
    s = make_student("S1")
    r = admin_client.post("/attendance/holidays", data={"date": weekday.isoformat(), "reason": "Fest"},
                          follow_redirects=True)
    assert b"non-working day" in r.data
    r = admin_client.post("/attendance/mark", data={"department": s.department, "year": 2, "section": "A",
                          "date": weekday.isoformat(), f"status_{s.id}": PRESENT}, follow_redirects=True)
    assert b"holiday" in r.data and Attendance.query.count() == 0
    db.session.add(Attendance(student_id=s.id, attendance_date=weekday - timedelta(days=100), status=PRESENT))
    db.session.commit()
    assert student_summary(s.id).total == 1


def mark_payload(day, students, status, **extra):
    d = {"department": "Computer Science", "year": 2, "section": "A", "date": day.isoformat()}
    d.update({f"status_{s.id}": status for s in students})
    d.update(extra)
    return d


def test_mark_attendance_and_edit_requires_confirmation(admin_client, app, weekday):
    a, b = make_student("A1"), make_student("B1")
    r = admin_client.post("/attendance/mark", data=mark_payload(weekday, [a, b], PRESENT), follow_redirects=True)
    assert b"2 new" in r.data and Attendance.query.count() == 2
    # editing without confirmation must NOT silently overwrite
    r = admin_client.post("/attendance/mark", data=mark_payload(weekday, [a, b], ABSENT), follow_redirects=True)
    assert b"confirm" in r.data.lower() and Attendance.query.filter_by(status=ABSENT).count() == 0
    # with confirmation it updates, and writes an audit log
    r = admin_client.post("/attendance/mark", data=mark_payload(weekday, [a, b], ABSENT, confirm_edit="1",
                                                               note="fix"), follow_redirects=True)
    assert b"2 edited" in r.data and Attendance.query.filter_by(status=ABSENT).count() == 2
    logs = AttendanceAuditLog.query.filter(AttendanceAuditLog.old_status == PRESENT).all()
    assert len(logs) == 2 and logs[0].new_status == ABSENT and logs[0].changed_by is not None
    assert Attendance.query.count() == 2  # no duplicates


def test_cannot_mark_students_of_other_class_or_future(admin_client, app, weekday):
    a = make_student("A1")
    other = make_student("O1", section="B")
    admin_client.post("/attendance/mark", data=mark_payload(weekday, [a, other], PRESENT))
    assert Attendance.query.filter_by(student_id=other.id).count() == 0
    r = admin_client.post("/attendance/mark", data=mark_payload(date.today() + timedelta(days=2), [a], PRESENT),
                          follow_redirects=True)
    assert b"future" in r.data


def test_missing_status_rejected(admin_client, app, weekday):
    a, b = make_student("A1"), make_student("B1")
    r = admin_client.post("/attendance/mark", data=mark_payload(weekday, [a], PRESENT), follow_redirects=True)
    assert b"Please choose Present or Absent" in r.data and Attendance.query.count() == 0


def test_database_blocks_duplicate_attendance(app, weekday):
    s = make_student("S1")
    db.session.add(Attendance(student_id=s.id, attendance_date=weekday, status=PRESENT))
    db.session.commit()
    db.session.add(Attendance(student_id=s.id, attendance_date=weekday, status=ABSENT))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_history_edit_requires_reason(admin_client, app, weekday):
    s = make_student("S1")
    rec = Attendance(student_id=s.id, attendance_date=weekday, status=PRESENT)
    db.session.add(rec)
    db.session.commit()
    admin_client.post(f"/attendance/{rec.id}/edit", data={"status": ABSENT, "note": ""})
    assert db.session.get(Attendance, rec.id).status == PRESENT
    admin_client.post(f"/attendance/{rec.id}/edit", data={"status": ABSENT, "note": "Late proof"})
    assert db.session.get(Attendance, rec.id).status == ABSENT
    assert b"Late proof" in admin_client.get("/attendance/audit").data


# ---------------------------------------------------------------- QR attendance
def qr_session(admin, minutes=10, **kw):
    cfg = dict(token="tok-" + "x" * 30, department="Computer Science", year=2, section="A",
               session_date=date.today(), created_by=admin.id,
               expires_at=__import__("datetime").datetime.now() + timedelta(minutes=minutes))
    cfg.update(kw)
    s = QRAttendanceSession(**cfg)
    db.session.add(s)
    db.session.commit()
    return s


def scan(client, token):
    r = client.post("/qr/mark", data=json.dumps({"token": token}), content_type="application/json")
    return r.status_code, r.get_json()


def test_admin_creates_qr_session_and_image(admin_client, app, weekday):
    make_student("S1")
    r = admin_client.post("/qr/new", data={"department": "Computer Science", "year": 2, "section": "A",
                                          "date": date.today().isoformat(), "session_name": "P1",
                                          "minutes": 5}, follow_redirects=True)
    s = QRAttendanceSession.query.one()
    assert len(s.token) >= 40 and b"QR session created" in r.data
    img = admin_client.get(f"/qr/{s.id}/image.png")
    assert img.status_code == 200 and img.data[:4] == b"\x89PNG"
    assert admin_client.get(f"/qr/{s.id}/status").get_json()["state"] == "Open"


def test_qr_happy_path_and_duplicate(client, app, admin):
    st = make_student("S1")
    s = qr_session(admin)
    login(client, "s1", "Student@123", "student")
    code, body = scan(client, "SAMS:" + s.token)
    assert code == 200 and body["ok"]
    assert Attendance.query.filter_by(student_id=st.id, status=PRESENT, source="qr").count() == 1
    code, body = scan(client, s.token)  # second scan
    assert body["ok"] and body.get("duplicate") and Attendance.query.count() == 1


def test_qr_rejections(client, app, admin):
    make_student("S1")
    make_student("OTHER", section="B")
    expired = qr_session(admin, minutes=-1, token="expired-" + "y" * 30)
    closed = qr_session(admin, token="closed-" + "z" * 30, is_active=False)
    other_class = qr_session(admin, token="other-" + "w" * 30, section="B")
    login(client, "s1", "Student@123", "student")
    assert scan(client, "nonsense")[0] == 404
    assert "expired" in scan(client, expired.token)[1]["message"]
    assert "closed" in scan(client, closed.token)[1]["message"]
    assert scan(client, other_class.token)[0] == 403
    assert scan(client, "")[0] == 400
    assert Attendance.query.count() == 0


def test_qr_does_not_overwrite_absent_and_admin_cannot_scan(client, app, admin, weekday):
    st = make_student("S1")
    s = qr_session(admin)
    db.session.add(Attendance(student_id=st.id, attendance_date=s.session_date, status=ABSENT))
    db.session.commit()
    login(client, "s1", "Student@123", "student")
    code, body = scan(client, s.token)
    assert code == 409 and Attendance.query.one().status == ABSENT


def test_admin_cannot_post_qr_mark(admin_client):
    assert admin_client.post("/qr/mark", json={"token": "x"}).status_code == 403


def test_close_session_marks_absentees(admin_client, app, admin):
    a, b = make_student("A1"), make_student("B1")
    s = qr_session(admin)
    db.session.add(Attendance(student_id=a.id, attendance_date=s.session_date, status=PRESENT,
                              qr_session_id=s.id, source="qr"))
    db.session.commit()
    admin_client.post(f"/qr/{s.id}/close", data={"mark_absent": "1"})
    assert db.session.get(QRAttendanceSession, s.id).state == "Closed"
    assert Attendance.query.filter_by(student_id=b.id).one().status == ABSENT
    assert Attendance.query.filter_by(student_id=a.id).one().status == PRESENT


# ---------------------------------------------------------------- reports
def seed_report(weekday):
    a, b = make_student("A1"), make_student("B1", dept="Electronics", year=1)
    for i in range(4):
        db.session.add(Attendance(student_id=a.id, attendance_date=weekday - timedelta(days=i),
                                  status=PRESENT if i < 3 else ABSENT))
        db.session.add(Attendance(student_id=b.id, attendance_date=weekday - timedelta(days=i), status=ABSENT))
    db.session.commit()
    return a, b


def test_reports_filters_and_totals(admin_client, app, weekday):
    seed_report(weekday)
    html = admin_client.get("/reports/").data.decode()
    assert "75.00%" in html and "0.00%" in html and "Present: 3" in html
    html = admin_client.get("/reports/?department=Electronics").data.decode()
    assert "Student A1" not in html and "Student B1" in html
    assert "Electronics" in admin_client.get("/reports/?view=department").data.decode()
    assert b"Year" in admin_client.get("/reports/?view=class").data


def test_csv_export(admin_client, app, weekday):
    seed_report(weekday)
    r = admin_client.get("/reports/export.csv?view=student&department=Computer+Science")
    assert r.mimetype == "text/csv" and "attachment" in r.headers["Content-Disposition"]
    text = r.data.decode()
    assert "Roll No" in text and "R-A1" in text and "R-B1" not in text and "TOTAL" in text


def test_csv_formula_injection_neutralised(admin_client, app):
    s = make_student("S1")
    s.user.full_name = "=HYPERLINK(\"http://evil\")"
    db.session.commit()
    assert "'=HYPERLINK" in admin_client.get("/reports/export.csv").data.decode()


# ---------------------------------------------------------------- notifications
def test_notifications_targeting_and_read_status(client, app, admin):
    a = make_student("A1")                                   # CS year 2 A
    b = make_student("B1", dept="Electronics", year=1)
    db.session.add_all([
        Notification(title="All", message="m", target_type="all", created_by=admin.id),
        Notification(title="CS2", message="m", target_type="class", department="Computer Science", year=2, created_by=admin.id),
        Notification(title="Direct", message="m", target_type="student", student_id=b.id, created_by=admin.id)])
    db.session.commit()
    assert a.unread_count() == 2 and b.unread_count() == 2
    login(client, "a1", "Student@123", "student")
    html = client.get("/notifications/").data.decode()
    assert "CS2" in html and "Direct" not in html
    n = Notification.query.filter_by(title="CS2").one()
    assert "CS2" in client.get(f"/notifications/{n.id}").data.decode()
    assert a.unread_count() == 1
    client.post("/notifications/read-all")
    assert a.unread_count() == 0


def test_admin_sends_notification(admin_client, app):
    s = make_student("S1")
    r = admin_client.post("/notifications/new", data={"title": "Hi", "message": "Body",
                          "target_type": "student", "student_id": s.id}, follow_redirects=True)
    assert b"Notification sent" in r.data and s.unread_count() == 1
    r = admin_client.post("/notifications/new", data={"title": "", "message": "", "target_type": "all"},
                          follow_redirects=True)
    assert b"Title is required" in r.data


# ---------------------------------------------------------------- profile / password
def test_change_password_rules(client, app):
    make_student("S1")
    login(client, "s1", "Student@123", "student")
    assert b"incorrect" in client.post("/profile/password", data={"current_password": "bad",
        "new_password": "NewPass123", "confirm_password": "NewPass123"}, follow_redirects=True).data
    assert b"at least 8" in client.post("/profile/password", data={"current_password": "Student@123",
        "new_password": "ab1", "confirm_password": "ab1"}, follow_redirects=True).data
    assert b"changed successfully" in client.post("/profile/password", data={"current_password": "Student@123",
        "new_password": "NewPass123", "confirm_password": "NewPass123"}, follow_redirects=True).data
    client.post("/logout")
    assert b"Hello" in login(client, "s1", "NewPass123", "student").data


def test_student_cannot_change_protected_fields(client, app):
    s = make_student("S1")
    login(client, "s1", "Student@123", "student")
    client.post("/profile", data={"mobile": "9876543210", "full_name": "Hacker", "email": "h@x.com",
                                  "role": "admin", "student_code": "HACK"})
    db.session.refresh(s)
    u = db.session.get(User, s.user_id)
    assert u.mobile == "9876543210" and u.role == "student" and u.full_name == "Student S1"
    assert s.student_code == "S1" and u.email == "s1@t.example.edu"


def test_photo_upload_validation(client, app):
    import io
    from PIL import Image
    make_student("S1")
    login(client, "s1", "Student@123", "student")
    bad = client.post("/profile", data={"mobile": "", "photo": (io.BytesIO(b"<?php evil ?>"), "x.php")},
                      content_type="multipart/form-data", follow_redirects=True)
    assert b"PNG, JPG or GIF" in bad.data
    fake = client.post("/profile", data={"mobile": "", "photo": (io.BytesIO(b"not an image"), "x.png")},
                       content_type="multipart/form-data", follow_redirects=True)
    assert b"not a valid image" in fake.data
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "red").save(buf, "PNG")
    buf.seek(0)
    ok = client.post("/profile", data={"mobile": "", "photo": (buf, "me.png")},
                     content_type="multipart/form-data", follow_redirects=True)
    assert b"Profile updated" in ok.data and User.query.filter_by(username="s1").one().photo.endswith(".jpg")


# ---------------------------------------------------------------- misc
def test_error_pages(client, admin_client):
    r = admin_client.get("/does-not-exist")
    assert r.status_code == 404 and b"Page Not Found" in r.data


def _fixtures_for_pages(admin, weekday):
    a, _ = seed_report(weekday)  # students A1 and B1 + attendance
    qr = qr_session(admin)
    n = Notification(title="T", message="M", target_type="all", created_by=admin.id)
    db.session.add(n)
    db.session.commit()
    return a, qr, n


def test_every_admin_page_renders(admin_client, app, admin, weekday):
    a, qr, n = _fixtures_for_pages(admin, weekday)
    for url in ["/admin/dashboard", "/students/", f"/students/{a.id}", f"/students/{a.id}/edit",
                "/students/add", "/attendance/mark?department=Computer+Science&year=2&section=A&date=" + weekday.isoformat(),
                "/attendance/history", "/attendance/audit", "/attendance/holidays", "/qr/", f"/qr/{qr.id}",
                "/qr/new", "/reports/?view=class", "/notifications/", f"/notifications/{n.id}",
                "/notifications/new", "/profile", "/profile/password"]:
        assert admin_client.get(url).status_code == 200, url


def test_every_student_page_renders(client, app, admin, weekday):
    _fixtures_for_pages(admin, weekday)
    n = Notification.query.first()
    login(client, "a1", "Student@123", "student")
    for url in ["/student/dashboard", "/student/attendance", "/qr/scan", "/notifications/",
                f"/notifications/{n.id}", "/profile", "/profile/password"]:
        assert client.get(url).status_code == 200, url
