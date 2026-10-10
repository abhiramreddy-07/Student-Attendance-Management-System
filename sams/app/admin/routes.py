"""Admin dashboard (all numbers come from the database)."""
from flask import Blueprint, render_template

from ..models import AttendanceAuditLog, Notification
from ..services import attendance_trend, department_stats, is_holiday, today_overview
from ..utils import roles_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/dashboard")
@roles_required("admin")
def dashboard():
    from datetime import date
    today = date.today()
    return render_template(
        "admin/dashboard.html",
        overview=today_overview(today),
        today=today,
        holiday_today=is_holiday(today),
        trend=attendance_trend(14),
        departments=department_stats(),
        recent=AttendanceAuditLog.query.order_by(AttendanceAuditLog.changed_at.desc(),
                                                 AttendanceAuditLog.id.desc()).limit(8).all(),
        notifications=Notification.query.order_by(Notification.created_at.desc()).limit(5).all(),
    )
