"""QR attendance. The QR code only carries a random session token; identity always
comes from the logged-in student's session, never from the QR code."""
import io
import secrets
from datetime import date, timedelta

import qrcode
from flask import (Blueprint, current_app, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user

from ..attendance.routes import record_attendance
from ..extensions import db
from ..models import ABSENT, PRESENT, Attendance, QRAttendanceSession, now
from ..services import class_students, is_holiday
from ..utils import parse_date, roles_required

bp = Blueprint("qr_attendance", __name__, url_prefix="/qr")
PREFIX = "SAMS:"


@bp.route("/")
@roles_required("admin")
def sessions():
    page = request.args.get("page", 1, type=int)
    pagination = QRAttendanceSession.query.order_by(QRAttendanceSession.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False)
    return render_template("qr_attendance/sessions.html", pagination=pagination)


@bp.route("/new", methods=["GET", "POST"])
@roles_required("admin")
def new_session():
    cfg = current_app.config
    if request.method == "POST":
        dept = request.form.get("department", "")
        year = request.form.get("year", type=int)
        section = request.form.get("section", "")
        day = parse_date(request.form.get("date")) or date.today()
        name = (request.form.get("session_name") or "Daily").strip()[:60] or "Daily"
        minutes = request.form.get("minutes", type=int) or cfg["QR_SESSION_MINUTES"]
        error = None
        if dept not in cfg["DEPARTMENTS"] or year not in cfg["YEARS"] or section not in cfg["SECTIONS"]:
            error = "Select a valid department, year and section."
        elif not 1 <= minutes <= 180:
            error = "Validity must be between 1 and 180 minutes."
        elif day > date.today():
            error = "QR sessions cannot be created for a future date."
        elif is_holiday(day):
            error = "That date is a holiday."
        elif not class_students(dept, year, section):
            error = "There are no active students in that class."
        if error:
            flash(error, "danger")
        else:
            s = QRAttendanceSession(token=secrets.token_urlsafe(32), department=dept, year=year,
                                    section=section, session_date=day, session_name=name,
                                    created_by=current_user.id,
                                    expires_at=now() + timedelta(minutes=minutes))
            db.session.add(s)
            db.session.commit()
            flash("QR session created. Ask students to scan the code.", "success")
            return redirect(url_for("qr_attendance.show_session", session_id=s.id))
    return render_template("qr_attendance/new.html", today=date.today(),
                           default_minutes=cfg["QR_SESSION_MINUTES"])


def _stats(s):
    students = class_students(s.department, s.year, s.section)
    present = Attendance.query.filter_by(qr_session_id=s.id, status=PRESENT).count()
    return {"state": s.state, "marked": present, "total": len(students),
            "seconds_left": max(0, int((s.expires_at - now()).total_seconds())) if s.is_open else 0}


@bp.route("/<int:session_id>")
@roles_required("admin")
def show_session(session_id):
    s = db.get_or_404(QRAttendanceSession, session_id)
    marked = (Attendance.query.filter_by(qr_session_id=s.id).order_by(Attendance.created_at.desc()).all())
    return render_template("qr_attendance/show.html", s=s, stats=_stats(s), marked=marked)


@bp.route("/<int:session_id>/status")
@roles_required("admin")
def session_status(session_id):
    return jsonify(_stats(db.get_or_404(QRAttendanceSession, session_id)))


@bp.route("/<int:session_id>/image.png")
@roles_required("admin")
def session_image(session_id):
    s = db.get_or_404(QRAttendanceSession, session_id)
    img = qrcode.make(PREFIX + s.token, box_size=9, border=3)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/<int:session_id>/close", methods=["POST"])
@roles_required("admin")
def close_session(session_id):
    s = db.get_or_404(QRAttendanceSession, session_id)
    if s.is_active:
        s.is_active, s.closed_at = False, now()
        msg = "QR session closed."
        if request.form.get("mark_absent") and not is_holiday(s.session_date):
            n = 0
            for st in class_students(s.department, s.year, s.section):
                if not Attendance.query.filter_by(student_id=st.id, attendance_date=s.session_date).first():
                    record_attendance(st, s.session_date, ABSENT, current_user.id, source="qr",
                                      qr_session_id=s.id, note="Absent - did not scan QR")
                    n += 1
            msg += f" {n} student(s) who did not scan were marked Absent."
        db.session.commit()
        flash(msg, "success")
    return redirect(url_for("qr_attendance.show_session", session_id=s.id))


@bp.route("/scan")
@roles_required("student")
def scan():
    return render_template("qr_attendance/scan.html")


@bp.route("/mark", methods=["POST"])
@roles_required("student")
def mark():
    """Student submits a scanned token. Returns JSON {ok, message}."""
    payload = request.get_json(silent=True) or request.form
    token = (payload.get("token") or "").strip()
    if token.startswith(PREFIX):
        token = token[len(PREFIX):]
    me = current_user.student
    if not token or me is None:
        return jsonify(ok=False, message="Invalid QR code."), 400
    s = QRAttendanceSession.query.filter_by(token=token).first()
    if s is None:
        return jsonify(ok=False, message="This QR code is not recognised."), 404
    if not s.is_active:
        return jsonify(ok=False, message="This QR session has been closed by the faculty."), 400
    if not s.is_open:
        return jsonify(ok=False, message="This QR session has expired."), 400
    if (me.department, me.year, me.section) != (s.department, s.year, s.section):
        return jsonify(ok=False, message="This QR code is for a different class."), 403
    if is_holiday(s.session_date):
        return jsonify(ok=False, message="Today is a non-working day."), 400
    existing = Attendance.query.filter_by(student_id=me.id, attendance_date=s.session_date).first()
    if existing is not None:
        if existing.status == PRESENT:
            return jsonify(ok=True, duplicate=True,
                           message="Your attendance is already recorded as Present."), 200
        return jsonify(ok=False, message="You are marked Absent for this date. "
                       "Please contact your faculty - QR cannot overwrite it."), 409
    try:
        record_attendance(me, s.session_date, PRESENT, s.created_by, source="qr",
                          qr_session_id=s.id, note=f"QR scan ({s.session_name})")
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify(ok=False, message="Could not save attendance. Try again."), 500
    return jsonify(ok=True, message=f"Attendance marked Present for {s.session_date:%d %b %Y}.")
