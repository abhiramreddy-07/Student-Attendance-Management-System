"""Application factory."""
import os

from flask import Flask, jsonify, render_template, request
from flask_login import current_user

from config import Config

from .extensions import csrf, db, login_manager


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "warning"

    from .admin.routes import bp as admin_bp
    from .attendance.routes import bp as attendance_bp
    from .auth.routes import bp as auth_bp
    from .notifications.routes import bp as notifications_bp
    from .portal.routes import bp as portal_bp
    from .qr_attendance.routes import bp as qr_bp
    from .reports.routes import bp as reports_bp
    from .students.routes import bp as students_bp
    for bp in (auth_bp, admin_bp, portal_bp, students_bp, attendance_bp, qr_bp,
               reports_bp, notifications_bp):
        app.register_blueprint(bp)

    @app.context_processor
    def inject_globals():
        unread = 0
        if current_user.is_authenticated and current_user.role == "student" and current_user.student:
            unread = current_user.student.unread_count()
        return {"APP_NAME": "SAMS", "unread_count": unread,
                "DEPARTMENTS": app.config["DEPARTMENTS"], "YEARS": app.config["YEARS"],
                "SECTIONS": app.config["SECTIONS"]}

    def wants_json():
        return request.path.startswith("/qr/mark") or request.is_json

    @app.errorhandler(403)
    def forbidden(e):
        if wants_json():
            return jsonify(ok=False, message="You are not allowed to do that."), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        if wants_json():
            return jsonify(ok=False, message="Not found."), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/413.html"), 413

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        if wants_json():
            return jsonify(ok=False, message="Server error. Please try again."), 500
        return render_template("errors/500.html"), 500

    return app
