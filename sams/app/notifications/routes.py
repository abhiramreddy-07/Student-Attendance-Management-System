"""In-app notifications. Admin sends; students read their own."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import Notification, NotificationRead, Student
from ..services import active_students_query
from ..utils import roles_required

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@bp.route("/")
@roles_required("admin", "student")
def index():
    page = request.args.get("page", 1, type=int)
    per = current_app.config["PER_PAGE"]
    if current_user.is_admin:
        q = Notification.query
        read_ids = set()
    else:
        q = current_user.student.notifications_query()
        read_ids = current_user.student.read_ids()
        if request.args.get("filter") == "unread":
            q = q.filter(~Notification.id.in_(read_ids or {0}))
    pagination = q.order_by(Notification.created_at.desc()).paginate(page=page, per_page=per, error_out=False)
    return render_template("notifications/list.html", pagination=pagination, read_ids=read_ids,
                           only_unread=request.args.get("filter") == "unread")


@bp.route("/new", methods=["GET", "POST"])
@roles_required("admin")
def create():
    cfg = current_app.config
    data = {"target_type": "all"}
    if request.method == "POST":
        data = {k: (request.form.get(k) or "").strip() for k in
                ("title", "message", "target_type", "department", "section")}
        data["year"] = request.form.get("year", type=int)
        data["student_id"] = request.form.get("student_id", type=int)
        errors = []
        if not data["title"] or len(data["title"]) > 150:
            errors.append("Title is required (max 150 characters).")
        if not data["message"]:
            errors.append("Message is required.")
        t = data["target_type"]
        n = Notification(title=data["title"], message=data["message"], target_type=t,
                         created_by=current_user.id)
        if t == "class":
            if data["department"] not in cfg["DEPARTMENTS"]:
                errors.append("Choose the department to notify.")
            n.department = data["department"]
            n.year = data["year"] if data["year"] in cfg["YEARS"] else None
            n.section = data["section"] if data["section"] in cfg["SECTIONS"] else None
        elif t == "student":
            student = db.session.get(Student, data["student_id"]) if data["student_id"] else None
            if student is None:
                errors.append("Choose the student to notify.")
            n.student_id = student.id if student else None
        elif t != "all":
            errors.append("Choose who should receive the notification.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            db.session.add(n)
            db.session.commit()
            flash("Notification sent.", "success")
            return redirect(url_for("notifications.index"))
    students = active_students_query().order_by(Student.roll_number).all()
    return render_template("notifications/create.html", data=data, students=students)


@bp.route("/<int:notification_id>")
@roles_required("admin", "student")
def detail(notification_id):
    n = db.get_or_404(Notification, notification_id)
    if current_user.is_admin:
        return render_template("notifications/detail.html", n=n, is_read=None)
    me = current_user.student
    # Students may only open notifications addressed to them.
    if not me.notifications_query().filter(Notification.id == n.id).first():
        abort(404)
    if not NotificationRead.query.filter_by(notification_id=n.id, student_id=me.id).first():
        db.session.add(NotificationRead(notification_id=n.id, student_id=me.id))
        db.session.commit()
    return render_template("notifications/detail.html", n=n, is_read=True)


@bp.route("/<int:notification_id>/read", methods=["POST"])
@roles_required("student")
def mark_read(notification_id):
    me = current_user.student
    n = me.notifications_query().filter(Notification.id == notification_id).first_or_404()
    if not NotificationRead.query.filter_by(notification_id=n.id, student_id=me.id).first():
        db.session.add(NotificationRead(notification_id=n.id, student_id=me.id))
        db.session.commit()
    return redirect(request.referrer or url_for("notifications.index"))


@bp.route("/read-all", methods=["POST"])
@roles_required("student")
def mark_all_read():
    me = current_user.student
    done = me.read_ids()
    for n in me.notifications_query().all():
        if n.id not in done:
            db.session.add(NotificationRead(notification_id=n.id, student_id=me.id))
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("notifications.index"))


@bp.route("/<int:notification_id>/delete", methods=["POST"])
@roles_required("admin")
def delete(notification_id):
    db.session.delete(db.get_or_404(Notification, notification_id))
    db.session.commit()
    flash("Notification deleted.", "success")
    return redirect(url_for("notifications.index"))
