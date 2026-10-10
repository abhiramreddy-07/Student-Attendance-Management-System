"""SQLAlchemy models for SAMS.

users 1--1 students 1--* attendance
students 1--* notification_reads *--1 notifications
users 1--* qr_sessions, users 1--* attendance (marked_by)
"""
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, and_, or_
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager

ROLE_ADMIN = "admin"
ROLE_STUDENT = "student"
PRESENT = "Present"
ABSENT = "Absent"


def now():
    return datetime.now()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    mobile = db.Column(db.String(20))
    photo = db.Column(db.String(255))
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    last_login = db.Column(db.DateTime)

    student = db.relationship("Student", back_populates="user", uselist=False,
                              cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("role IN ('admin','student')", name="ck_users_role"),)

    @property
    def is_active(self):  # used by Flask-Login
        return bool(self.active)

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        unique=True, nullable=False)
    student_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    roll_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    department = db.Column(db.String(60), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    user = db.relationship("User", back_populates="student")
    attendance_records = db.relationship("Attendance", back_populates="student",
                                         cascade="all, delete-orphan")
    audit_logs = db.relationship("AttendanceAuditLog", back_populates="student",
                                 cascade="all, delete-orphan")
    reads = db.relationship("NotificationRead", back_populates="student",
                            cascade="all, delete-orphan")
    direct_notifications = db.relationship("Notification", back_populates="student",
                                           cascade="all, delete-orphan")

    __table_args__ = (Index("ix_students_class", "department", "year", "section"),)

    # convenience proxies to the login account
    full_name = property(lambda self: self.user.full_name)
    email = property(lambda self: self.user.email)
    mobile = property(lambda self: self.user.mobile)
    photo = property(lambda self: self.user.photo)
    active = property(lambda self: self.user.active)

    @property
    def class_label(self):
        return f"{self.department} · Year {self.year} · Sec {self.section}"

    def notifications_query(self):
        """Notifications addressed to this student (all / their class / them)."""
        return Notification.query.filter(or_(
            Notification.target_type == "all",
            and_(Notification.target_type == "student", Notification.student_id == self.id),
            and_(Notification.target_type == "class",
                 Notification.department == self.department,
                 or_(Notification.year.is_(None), Notification.year == self.year),
                 or_(Notification.section.is_(None), Notification.section == self.section)),
        ))

    def read_ids(self):
        return {r for (r,) in db.session.query(NotificationRead.notification_id)
                .filter(NotificationRead.student_id == self.id)}

    def unread_count(self):
        read_ids = db.session.query(NotificationRead.notification_id).filter(
            NotificationRead.student_id == self.id)
        return self.notifications_query().filter(~Notification.id.in_(read_ids)).count()


class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    attendance_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False)
    marked_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    source = db.Column(db.String(10), nullable=False, default="manual")  # manual | qr
    qr_session_id = db.Column(db.Integer, db.ForeignKey("qr_sessions.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    updated_at = db.Column(db.DateTime, nullable=False, default=now, onupdate=now)

    student = db.relationship("Student", back_populates="attendance_records")
    marker = db.relationship("User", foreign_keys=[marked_by])

    __table_args__ = (
        UniqueConstraint("student_id", "attendance_date", name="uq_attendance_student_date"),
        CheckConstraint("status IN ('Present','Absent')", name="ck_attendance_status"),
    )


class Holiday(db.Model):
    """Non-working days. Attendance cannot be recorded on them and they are never counted."""
    __tablename__ = "holidays"

    id = db.Column(db.Integer, primary_key=True)
    holiday_date = db.Column(db.Date, unique=True, nullable=False, index=True)
    reason = db.Column(db.String(120), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=now)


class AttendanceAuditLog(db.Model):
    __tablename__ = "attendance_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    attendance_date = db.Column(db.Date, nullable=False)
    old_status = db.Column(db.String(10))  # NULL when the record was created
    new_status = db.Column(db.String(10), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    changed_at = db.Column(db.DateTime, nullable=False, default=now, index=True)
    note = db.Column(db.String(200))

    student = db.relationship("Student", back_populates="audit_logs")
    user = db.relationship("User", foreign_keys=[changed_by])


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    target_type = db.Column(db.String(10), nullable=False, default="all")  # all|class|student
    department = db.Column(db.String(60))
    year = db.Column(db.Integer)       # NULL = every year of the department
    section = db.Column(db.String(10))  # NULL = every section
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, nullable=False, default=now, index=True)

    student = db.relationship("Student", back_populates="direct_notifications")
    author = db.relationship("User", foreign_keys=[created_by])
    reads = db.relationship("NotificationRead", back_populates="notification",
                            cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint("target_type IN ('all','class','student')",
                                      name="ck_notification_target"),)

    @property
    def target_label(self):
        if self.target_type == "all":
            return "Everyone"
        if self.target_type == "student":
            return f"{self.student.full_name} ({self.student.student_code})" if self.student else "Student"
        parts = [self.department or "", f"Year {self.year}" if self.year else "All years",
                 f"Sec {self.section}" if self.section else "All sections"]
        return " · ".join(parts)


class NotificationRead(db.Model):
    """Per-student read receipt (a notification to a class has many recipients)."""
    __tablename__ = "notification_reads"

    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(db.Integer, db.ForeignKey("notifications.id", ondelete="CASCADE"),
                                nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=False, default=now)

    notification = db.relationship("Notification", back_populates="reads")
    student = db.relationship("Student", back_populates="reads")

    __table_args__ = (UniqueConstraint("notification_id", "student_id", name="uq_read_once"),)


class QRAttendanceSession(db.Model):
    __tablename__ = "qr_sessions"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    department = db.Column(db.String(60), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(10), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    session_name = db.Column(db.String(60), nullable=False, default="Daily")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    closed_at = db.Column(db.DateTime)

    creator = db.relationship("User", foreign_keys=[created_by])

    @property
    def is_open(self):
        return self.is_active and now() < self.expires_at

    @property
    def state(self):
        if not self.is_active:
            return "Closed"
        return "Open" if now() < self.expires_at else "Expired"

    @property
    def class_label(self):
        return f"{self.department} · Year {self.year} · Sec {self.section}"
