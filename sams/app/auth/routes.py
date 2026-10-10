"""Login, logout, profile and password change (shared by both roles)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, or_

from ..extensions import db
from ..models import User, now
from ..utils import EMAIL_RE, MOBILE_RE, safe_next, save_photo, validate_password

bp = Blueprint("auth", __name__)


def home_for(user):
    return url_for("admin.dashboard" if user.is_admin else "portal.dashboard")


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    role = request.form.get("role", "student")
    if request.method == "POST":
        ident = (request.form.get("identifier") or "").strip().lower()
        password = request.form.get("password") or ""
        errors = []
        if not ident:
            errors.append("Enter your username or email.")
        if not password:
            errors.append("Enter your password.")
        if role not in ("admin", "student"):
            errors.append("Choose a valid role.")
        if not errors:
            user = User.query.filter(or_(func.lower(User.username) == ident,
                                         func.lower(User.email) == ident)).first()
            # One generic message so attackers cannot tell which part was wrong.
            if not user or not user.check_password(password) or user.role != role:
                errors.append("Invalid credentials for the selected role.")
            elif not user.active:
                errors.append("This account has been deactivated. Contact the administrator.")
            else:
                login_user(user, remember=bool(request.form.get("remember")))
                user.last_login = now()
                db.session.commit()
                flash(f"Welcome back, {user.full_name}!", "success")
                return redirect(safe_next(request.args.get("next")) or home_for(user))
        for e in errors:
            flash(e, "danger")
    return render_template("auth/login.html", role=role)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user
    if request.method == "POST":
        mobile = (request.form.get("mobile") or "").strip()
        errors = []
        if mobile and not MOBILE_RE.match(mobile):
            errors.append("Mobile number must contain 10-15 digits.")
        # Role / student ID / privileges are never read from the form.
        # Students may only change mobile + photo; admins may also change name + email.
        if user.is_admin:
            name = (request.form.get("full_name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            if not name:
                errors.append("Full name is required.")
            if not EMAIL_RE.match(email):
                errors.append("Enter a valid email address.")
            elif User.query.filter(func.lower(User.email) == email, User.id != user.id).first():
                errors.append("That email address is already used by another account.")
        filename, photo_err = save_photo(request.files.get("photo"), user.photo)
        if photo_err:
            errors.append(photo_err)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            if user.is_admin:
                user.full_name, user.email = name, email
            user.mobile = mobile or None
            if filename:
                user.photo = filename
            db.session.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("auth.profile"))
    return render_template("auth/profile.html")


@bp.route("/profile/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password") or ""
        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        error = None
        if not current_user.check_password(current):
            error = "Your current password is incorrect."
        elif new != confirm:
            error = "New password and confirmation do not match."
        elif new == current:
            error = "The new password must be different from the current one."
        else:
            error = validate_password(new)
        if error:
            flash(error, "danger")
        else:
            current_user.set_password(new)
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("auth.profile"))
    return render_template("auth/change_password.html")
