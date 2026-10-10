"""Student portal. Every query is bound to current_user.student - no IDs in URLs."""
from flask import Blueprint, abort, current_app, render_template, request
from flask_login import current_user

from ..models import Attendance, Notification
from ..services import student_summary
from ..utils import parse_date, roles_required

bp = Blueprint("portal", __name__, url_prefix="/student")


def _me():
    if not current_user.student:
        abort(403)
    return current_user.student


@bp.route("/dashboard")
@roles_required("student")
def dashboard():
    me = _me()
    recent = (Attendance.query.filter_by(student_id=me.id)
              .order_by(Attendance.attendance_date.desc()).limit(5).all())
    notes = me.notifications_query().order_by(Notification.created_at.desc()).limit(4).all()
    return render_template("portal/dashboard.html", me=me, summary=student_summary(me.id),
                           recent=recent, notes=notes, read_ids=me.read_ids(),
                           threshold=current_app.config["LOW_ATTENDANCE_THRESHOLD"])


@bp.route("/attendance")
@roles_required("student")
def history():
    me = _me()
    start, end = parse_date(request.args.get("start")), parse_date(request.args.get("end"))
    q = Attendance.query.filter_by(student_id=me.id)
    if start:
        q = q.filter(Attendance.attendance_date >= start)
    if end:
        q = q.filter(Attendance.attendance_date <= end)
    page = request.args.get("page", 1, type=int)
    pagination = q.order_by(Attendance.attendance_date.desc()).paginate(
        page=page, per_page=15, error_out=False)
    return render_template("portal/history.html", me=me, pagination=pagination,
                           summary=student_summary(me.id, start, end), start=start, end=end)
