"""Daily attendance, history, audit trail and holidays (admin/faculty only)."""
from datetime import date

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import ABSENT, PRESENT, Attendance, AttendanceAuditLog, Holiday, Student, User
from ..services import class_students, is_holiday
from ..utils import parse_date, roles_required

bp = Blueprint("attendance", __name__, url_prefix="/attendance")


def record_attendance(student, day, status, user_id, source="manual", qr_session_id=None, note=None):
    """Create or update ONE record + write the audit log. Returns 'created'|'updated'|'unchanged'.

    The caller commits. Existing records are only changed through this function,
    so every change is traceable.
    """
    rec = Attendance.query.filter_by(student_id=student.id, attendance_date=day).first()
    if rec is None:
        db.session.add(Attendance(student_id=student.id, attendance_date=day, status=status,
                                  marked_by=user_id, source=source, qr_session_id=qr_session_id))
        db.session.add(AttendanceAuditLog(student_id=student.id, attendance_date=day,
                                          old_status=None, new_status=status,
                                          changed_by=user_id, note=note or f"Marked ({source})"))
        return "created"
    if rec.status == status:
        return "unchanged"
    db.session.add(AttendanceAuditLog(student_id=student.id, attendance_date=day,
                                      old_status=rec.status, new_status=status,
                                      changed_by=user_id, note=note or "Edited"))
    rec.status, rec.marked_by, rec.source = status, user_id, source
    return "updated"


def _class_args(source):
    return (source.get("department", ""), source.get("year", type=int),
            source.get("section", ""))


def _valid_class(dept, year, section):
    cfg = current_app.config
    return dept in cfg["DEPARTMENTS"] and year in cfg["YEARS"] and section in cfg["SECTIONS"]


@bp.route("/mark", methods=["GET", "POST"])
@roles_required("admin")
def mark():
    source = request.form if request.method == "POST" else request.args
    dept, year, section = _class_args(source)
    day = parse_date(source.get("date")) or date.today()
    selected = _valid_class(dept, year, section)
    students = class_students(dept, year, section) if selected else []
    existing = {}
    if students:
        existing = {r.student_id: r for r in Attendance.query.filter(
            Attendance.attendance_date == day,
            Attendance.student_id.in_([s.id for s in students]))}
    holiday = Holiday.query.filter_by(holiday_date=day).first()

    if request.method == "POST":
        back = url_for("attendance.mark", department=dept, year=year, section=section,
                       date=day.isoformat())
        if not selected:
            flash("Select a department, year and section first.", "danger")
            return redirect(url_for("attendance.mark"))
        if day > date.today():
            flash("Attendance cannot be marked for a future date.", "danger")
            return redirect(back)
        if holiday:
            flash(f"{day:%d %b %Y} is a holiday ({holiday.reason}); attendance cannot be marked.", "danger")
            return redirect(back)
        if not students:
            flash("There are no active students in this class.", "warning")
            return redirect(back)
        # Only students that really belong to the selected class are accepted.
        wanted = {}
        for s in students:
            status = request.form.get(f"status_{s.id}")
            if status not in (PRESENT, ABSENT):
                flash(f"Please choose Present or Absent for {s.full_name}.", "danger")
                return redirect(back)
            wanted[s.id] = status
        changes = [s for s in students if s.id in existing and existing[s.id].status != wanted[s.id]]
        if changes and not request.form.get("confirm_edit"):
            flash("Saved attendance already exists for this date. Tick 'I want to edit saved "
                  "attendance' to confirm the change.", "warning")
            return redirect(back)
        note = (request.form.get("note") or "").strip()[:200] or None
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        try:
            for s in students:
                counts[record_attendance(s, day, wanted[s.id], current_user.id, note=note)] += 1
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Attendance was saved by someone else at the same time. Please reload and review.", "danger")
            return redirect(back)
        flash(f"Attendance saved for {day:%d %b %Y}: {counts['created']} new, "
              f"{counts['updated']} edited, {counts['unchanged']} unchanged.", "success")
        return redirect(back)

    return render_template("attendance/mark.html", dept=dept, year=year, section=section,
                           day=day, selected=selected, students=students, existing=existing,
                           holiday=holiday, today=date.today())


@bp.route("/history")
@roles_required("admin")
def history():
    dept = request.args.get("department", "")
    year = request.args.get("year", type=int)
    section = request.args.get("section", "")
    status = request.args.get("status", "")
    q = (request.args.get("q") or "").strip()
    start, end = parse_date(request.args.get("start")), parse_date(request.args.get("end"))
    query = (Attendance.query.join(Student, Attendance.student_id == Student.id)
             .join(User, Student.user_id == User.id))
    if dept:
        query = query.filter(Student.department == dept)
    if year:
        query = query.filter(Student.year == year)
    if section:
        query = query.filter(Student.section == section)
    if status in (PRESENT, ABSENT):
        query = query.filter(Attendance.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(User.full_name.like(like) | Student.roll_number.like(like))
    if start:
        query = query.filter(Attendance.attendance_date >= start)
    if end:
        query = query.filter(Attendance.attendance_date <= end)
    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(Attendance.attendance_date.desc(), Student.roll_number).paginate(
        page=page, per_page=current_app.config["PER_PAGE"] + 5, error_out=False)
    return render_template("attendance/history.html", pagination=pagination, dept=dept,
                           year=year, section=section, status=status, q=q, start=start, end=end)


@bp.route("/<int:record_id>/edit", methods=["POST"])
@roles_required("admin")
def edit_record(record_id):
    rec = db.get_or_404(Attendance, record_id)
    new_status = request.form.get("status")
    note = (request.form.get("note") or "").strip()[:200]
    if new_status not in (PRESENT, ABSENT):
        flash("Invalid status.", "danger")
    elif not note:
        flash("Please give a short reason for editing saved attendance.", "danger")
    else:
        result = record_attendance(rec.student, rec.attendance_date, new_status,
                                   current_user.id, note=note)
        db.session.commit()
        flash("Attendance updated." if result == "updated" else "No change - status was already "
              f"{new_status}.", "success" if result == "updated" else "info")
    return redirect(request.referrer or url_for("attendance.history"))


@bp.route("/audit")
@roles_required("admin")
def audit():
    page = request.args.get("page", 1, type=int)
    pagination = AttendanceAuditLog.query.order_by(
        AttendanceAuditLog.changed_at.desc(), AttendanceAuditLog.id.desc()).paginate(
        page=page, per_page=20, error_out=False)
    return render_template("attendance/audit.html", pagination=pagination)


@bp.route("/holidays", methods=["GET", "POST"])
@roles_required("admin")
def holidays():
    if request.method == "POST":
        day = parse_date(request.form.get("date"))
        reason = (request.form.get("reason") or "").strip()
        if not day or not reason:
            flash("Enter a date and a reason.", "danger")
        elif is_holiday(day):
            flash("That date is already marked as a holiday.", "warning")
        elif Attendance.query.filter_by(attendance_date=day).first():
            flash("Attendance has already been recorded on that date, so it cannot be a holiday.", "danger")
        else:
            db.session.add(Holiday(holiday_date=day, reason=reason[:120], created_by=current_user.id))
            db.session.commit()
            flash(f"{day:%d %b %Y} marked as a non-working day.", "success")
        return redirect(url_for("attendance.holidays"))
    return render_template("attendance/holidays.html",
                           items=Holiday.query.order_by(Holiday.holiday_date.desc()).all())


@bp.route("/holidays/<int:holiday_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_holiday(holiday_id):
    db.session.delete(db.get_or_404(Holiday, holiday_id))
    db.session.commit()
    flash("Holiday removed.", "success")
    return redirect(url_for("attendance.holidays"))
