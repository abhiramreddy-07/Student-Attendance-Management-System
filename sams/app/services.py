"""Business rules shared by every module (one place => consistent numbers).

Attendance % = present days / total recorded working days * 100
Holidays (non-working days) are excluded from every count.
"""
from dataclasses import dataclass
from datetime import date, timedelta

from flask import current_app
from sqlalchemy import case, func, select

from .extensions import db
from .models import ABSENT, PRESENT, Attendance, Holiday, Student, User


@dataclass
class Summary:
    present: int = 0
    absent: int = 0

    @property
    def total(self):
        return self.present + self.absent

    @property
    def percentage(self):
        return calc_percentage(self.present, self.total)

    @property
    def is_low(self):
        return self.total > 0 and self.percentage < current_app.config["LOW_ATTENDANCE_THRESHOLD"]


def calc_percentage(present, total):
    """Zero records => 0.0 (never a ZeroDivisionError)."""
    return round(present * 100.0 / total, 2) if total else 0.0


def _working_day_filter(q):
    return q.filter(~Attendance.attendance_date.in_(select(Holiday.holiday_date)))


def attendance_stats(student_ids=None, start=None, end=None):
    """Return {student_id: Summary} for working days inside [start, end]."""
    q = db.session.query(
        Attendance.student_id,
        func.sum(case((Attendance.status == PRESENT, 1), else_=0)),
        func.sum(case((Attendance.status == ABSENT, 1), else_=0)),
    )
    q = _working_day_filter(q)
    if student_ids is not None:
        if not student_ids:
            return {}
        q = q.filter(Attendance.student_id.in_(list(student_ids)))
    if start:
        q = q.filter(Attendance.attendance_date >= start)
    if end:
        q = q.filter(Attendance.attendance_date <= end)
    return {sid: Summary(int(p or 0), int(a or 0)) for sid, p, a in q.group_by(Attendance.student_id)}


def student_summary(student_id, start=None, end=None):
    return attendance_stats([student_id], start, end).get(student_id, Summary())


def is_holiday(day):
    return Holiday.query.filter_by(holiday_date=day).first() is not None


def active_students_query():
    return Student.query.join(User, Student.user_id == User.id).filter(User.active.is_(True))


def class_students(department, year, section):
    return (active_students_query()
            .filter(Student.department == department, Student.year == year,
                    Student.section == section)
            .order_by(Student.roll_number).all())


def today_overview(day=None):
    day = day or date.today()
    total = active_students_query().count()
    q = db.session.query(Attendance.status, func.count(Attendance.id)).filter(
        Attendance.attendance_date == day)
    counts = dict(q.group_by(Attendance.status).all())
    present, absent = counts.get(PRESENT, 0), counts.get(ABSENT, 0)
    return {"total_students": total, "present": present, "absent": absent,
            "percentage": calc_percentage(present, present + absent)}


def attendance_trend(days=14, end=None):
    """Daily class-wide attendance % for the last `days` calendar days (working days only)."""
    end = end or date.today()
    start = end - timedelta(days=days - 1)
    q = db.session.query(
        Attendance.attendance_date,
        func.sum(case((Attendance.status == PRESENT, 1), else_=0)),
        func.count(Attendance.id),
    ).filter(Attendance.attendance_date.between(start, end))
    q = _working_day_filter(q).group_by(Attendance.attendance_date).order_by(Attendance.attendance_date)
    return [{"date": d.strftime("%d %b"), "percentage": calc_percentage(int(p or 0), int(t))}
            for d, p, t in q]


def department_stats():
    rows = (db.session.query(Student.department, func.count(Student.id))
            .join(User, Student.user_id == User.id).filter(User.active.is_(True))
            .group_by(Student.department).order_by(Student.department).all())
    return [{"department": d, "students": n} for d, n in rows]
