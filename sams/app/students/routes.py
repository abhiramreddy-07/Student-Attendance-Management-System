"""Student management (admin only)."""
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import ROLE_STUDENT, Attendance, Student, User
from ..services import attendance_stats, student_summary
from ..utils import (EMAIL_RE, MOBILE_RE, delete_photo, generate_password, parse_date,
                     roles_required, save_photo, validate_password)

bp = Blueprint("students", __name__, url_prefix="/students")
FIELDS = ("student_code", "full_name", "roll_number", "email", "mobile", "department",
          "section", "password")


def _read_form():
    data = {k: (request.form.get(k) or "").strip() for k in FIELDS}
    data["student_code"] = data["student_code"].upper()
    data["email"] = data["email"].lower()
    data["year"] = request.form.get("year", type=int)
    return data


def _validate(data, student=None):
    cfg = current_app.config
    errors = []
    if not student:
        if not data["student_code"]:
            errors.append("Student ID is required.")
        elif Student.query.filter_by(student_code=data["student_code"]).first() or \
                User.query.filter(func.lower(User.username) == data["student_code"].lower()).first():
            errors.append(f"Student ID {data['student_code']} already exists.")
    if not data["full_name"]:
        errors.append("Full name is required.")
    if not data["roll_number"]:
        errors.append("Roll number is required.")
    else:
        dup = Student.query.filter(Student.roll_number == data["roll_number"])
        if student:
            dup = dup.filter(Student.id != student.id)
        if dup.first():
            errors.append(f"Roll number {data['roll_number']} is already assigned to another student.")
    if not EMAIL_RE.match(data["email"]):
        errors.append("Enter a valid email address.")
    else:
        dup = User.query.filter(func.lower(User.email) == data["email"])
        if student:
            dup = dup.filter(User.id != student.user_id)
        if dup.first():
            errors.append(f"Email {data['email']} is already registered.")
    if data["mobile"] and not MOBILE_RE.match(data["mobile"]):
        errors.append("Mobile number must contain 10-15 digits (optional leading +).")
    if data["department"] not in cfg["DEPARTMENTS"]:
        errors.append("Choose a valid department.")
    if data["year"] not in cfg["YEARS"]:
        errors.append("Choose a valid academic year.")
    if data["section"] not in cfg["SECTIONS"]:
        errors.append("Choose a valid section.")
    if not student and data["password"]:
        pw_err = validate_password(data["password"])
        if pw_err:
            errors.append(pw_err)
    return errors


def _next_code():
    last = Student.query.order_by(Student.id.desc()).first()
    return f"STU{(last.id + 1 if last else 1):04d}"


@bp.route("/")
@roles_required("admin")
def list_students():
    q = (request.args.get("q") or "").strip()
    dept = request.args.get("department", "")
    year = request.args.get("year", type=int)
    section = request.args.get("section", "")
    query = Student.query.join(User, Student.user_id == User.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.full_name.like(like), Student.roll_number.like(like),
                                 Student.student_code.like(like)))
    if dept:
        query = query.filter(Student.department == dept)
    if year:
        query = query.filter(Student.year == year)
    if section:
        query = query.filter(Student.section == section)
    page = request.args.get("page", 1, type=int)
    pagination = query.order_by(Student.department, Student.year, Student.section,
                                Student.roll_number).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    stats = attendance_stats([s.id for s in pagination.items])
    return render_template("students/list.html", pagination=pagination, stats=stats,
                           q=q, dept=dept, year=year, section=section)


@bp.route("/add", methods=["GET", "POST"])
@roles_required("admin")
def add_student():
    data = {"student_code": _next_code(), "year": 1}
    if request.method == "POST":
        data = _read_form()
        errors = _validate(data)
        filename, photo_err = save_photo(request.files.get("photo"))
        if photo_err:
            errors.append(photo_err)
        if errors:
            delete_photo(filename)
            for e in errors:
                flash(e, "danger")
        else:
            password = data["password"] or generate_password()
            user = User(username=data["student_code"].lower(), email=data["email"],
                        role=ROLE_STUDENT, full_name=data["full_name"],
                        mobile=data["mobile"] or None, photo=filename)
            user.set_password(password)
            student = Student(user=user, student_code=data["student_code"],
                              roll_number=data["roll_number"], department=data["department"],
                              year=data["year"], section=data["section"])
            db.session.add(student)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                delete_photo(filename)
                flash("A student with the same ID, roll number or email already exists.", "danger")
            else:
                flash(f"Student created. Login username: {user.username} | "
                      f"password: {password} (shown only once - note it down).", "success")
                return redirect(url_for("students.view_student", student_id=student.id))
    return render_template("students/form.html", student=None, data=data)


@bp.route("/<int:student_id>")
@roles_required("admin")
def view_student(student_id):
    student = db.get_or_404(Student, student_id)
    start, end = parse_date(request.args.get("start")), parse_date(request.args.get("end"))
    summary = student_summary(student.id, start, end)
    records = (Attendance.query.filter_by(student_id=student.id)
               .order_by(Attendance.attendance_date.desc()).limit(15).all())
    return render_template("students/detail.html", student=student, summary=summary,
                           records=records, start=start, end=end)


@bp.route("/<int:student_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def edit_student(student_id):
    student = db.get_or_404(Student, student_id)
    data = {"student_code": student.student_code, "full_name": student.full_name,
            "roll_number": student.roll_number, "email": student.email,
            "mobile": student.mobile or "", "department": student.department,
            "year": student.year, "section": student.section}
    if request.method == "POST":
        data = _read_form()
        data["student_code"] = student.student_code  # the ID is protected
        errors = _validate(data, student)
        filename, photo_err = save_photo(request.files.get("photo"), student.user.photo)
        if photo_err:
            errors.append(photo_err)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            student.user.full_name, student.user.email = data["full_name"], data["email"]
            student.user.mobile = data["mobile"] or None
            if filename:
                student.user.photo = filename
            student.roll_number, student.department = data["roll_number"], data["department"]
            student.year, student.section = data["year"], data["section"]
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Another student already uses that roll number or email.", "danger")
            else:
                flash("Student details updated.", "success")
                return redirect(url_for("students.view_student", student_id=student.id))
    return render_template("students/form.html", student=student, data=data)


@bp.route("/<int:student_id>/toggle", methods=["POST"])
@roles_required("admin")
def toggle_status(student_id):
    student = db.get_or_404(Student, student_id)
    student.user.active = not student.user.active
    db.session.commit()
    flash(f"{student.full_name} is now {'active' if student.user.active else 'deactivated'}.",
          "success" if student.user.active else "warning")
    return redirect(request.referrer or url_for("students.list_students"))


@bp.route("/<int:student_id>/reset-password", methods=["POST"])
@roles_required("admin")
def reset_password(student_id):
    student = db.get_or_404(Student, student_id)
    password = generate_password()
    student.user.set_password(password)
    db.session.commit()
    flash(f"New password for {student.user.username}: {password} (shown only once).", "success")
    return redirect(url_for("students.view_student", student_id=student.id))


@bp.route("/<int:student_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_student(student_id):
    student = db.get_or_404(Student, student_id)
    name, photo = student.full_name, student.user.photo
    db.session.delete(student.user)  # cascades to the student + all of their records
    db.session.commit()
    delete_photo(photo)
    flash(f"{name} and all of their attendance records were permanently deleted.", "success")
    return redirect(url_for("students.list_students"))
