"""Create tables and insert FICTIONAL demo data. Safe to run repeatedly.

    python seed.py            # create tables + demo data (skips what already exists)
    python seed.py --reset    # DROP all tables first (asks for confirmation)
"""
import random
import sys
from datetime import date, timedelta

from app import create_app
from app.extensions import db
from app.models import (ABSENT, PRESENT, Attendance, AttendanceAuditLog, Holiday, Notification,
                        Student, User)

# DEVELOPMENT-ONLY credentials - change or delete these accounts before real use.
ADMIN = {"username": "admin", "email": "admin@sams.example.edu", "password": "Admin@123",
         "full_name": "Dr. Meera Iyer (Demo Faculty)", "mobile": "9000000001"}
STUDENT_PASSWORD = "Student@123"

STUDENTS = [  # code, name, roll, department, year, section
    ("CS2024001", "Aarav Sharma", "CS21001", "Computer Science", 2, "A"),
    ("CS2024002", "Diya Patel", "CS21002", "Computer Science", 2, "A"),
    ("CS2024003", "Kabir Nair", "CS21003", "Computer Science", 2, "A"),
    ("CS2024004", "Ananya Reddy", "CS21004", "Computer Science", 2, "B"),
    ("CS2024005", "Rohan Gupta", "CS21005", "Computer Science", 2, "B"),
    ("IT2024001", "Ishita Menon", "IT21001", "Information Technology", 3, "A"),
    ("IT2024002", "Vihaan Das", "IT21002", "Information Technology", 3, "A"),
    ("IT2024003", "Saanvi Joshi", "IT21003", "Information Technology", 3, "A"),
    ("IT2024004", "Arjun Kulkarni", "IT21004", "Information Technology", 1, "B"),
    ("EC2024001", "Myra Bose", "EC21001", "Electronics", 1, "A"),
    ("EC2024002", "Reyansh Verma", "EC21002", "Electronics", 1, "A"),
    ("EC2024003", "Tara Banerjee", "EC21003", "Electronics", 1, "A"),
]
NOTIFICATIONS = [
    ("Welcome to SAMS", "Your attendance portal is live. Check your attendance regularly and "
     "scan the QR code shown by your faculty during class.", "all", {}),
    ("CS Year 2 - Lab Schedule", "Lab sessions for Computer Science Year 2 move to Friday 2 PM this week.",
     "class", {"department": "Computer Science", "year": 2}),
    ("Attendance warning", "Your attendance is close to the 75% minimum. Please meet your class "
     "coordinator.", "student", {"student_code": "IT2024004"}),
]


def last_working_days(n):
    days, d = [], date.today()
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def seed():
    created = {"users": 0, "attendance": 0, "notifications": 0, "holidays": 0}
    admin = User.query.filter_by(username=ADMIN["username"]).first()
    if not admin:
        admin = User(username=ADMIN["username"], email=ADMIN["email"], role="admin",
                     full_name=ADMIN["full_name"], mobile=ADMIN["mobile"])
        admin.set_password(ADMIN["password"])
        db.session.add(admin)
        created["users"] += 1

    students = []
    for code, name, roll, dept, year, sec in STUDENTS:
        st = Student.query.filter_by(student_code=code).first()
        if not st:
            first = name.split()[0].lower()
            user = User(username=code.lower(), email=f"{first}.{roll.lower()}@sams.example.edu",
                        role="student", full_name=name, mobile=f"98765{len(students):05d}")
            user.set_password(STUDENT_PASSWORD)
            st = Student(user=user, student_code=code, roll_number=roll, department=dept,
                         year=year, section=sec)
            db.session.add(st)
            created["users"] += 1
        students.append(st)
    db.session.commit()

    days = last_working_days(15)
    holiday = days[5]  # one demo non-working day in the middle of the range
    if not Holiday.query.filter_by(holiday_date=holiday).first():
        db.session.add(Holiday(holiday_date=holiday, reason="Demo holiday", created_by=admin.id))
        created["holidays"] += 1
    rng = random.Random(42)  # deterministic demo data
    for st in students:
        # IT2024004 is deliberately low so the "low attendance" warning can be demonstrated
        p_present = 0.55 if st.student_code == "IT2024004" else 0.88
        for d in days:
            if d == holiday:
                continue
            status = PRESENT if rng.random() < p_present else ABSENT
            if not Attendance.query.filter_by(student_id=st.id, attendance_date=d).first():
                db.session.add(Attendance(student_id=st.id, attendance_date=d, status=status,
                                          marked_by=admin.id, source="manual"))
                db.session.add(AttendanceAuditLog(student_id=st.id, attendance_date=d,
                                                  new_status=status, changed_by=admin.id,
                                                  note="Seed data"))
                created["attendance"] += 1
    db.session.commit()

    for title, msg, target, extra in NOTIFICATIONS:
        if Notification.query.filter_by(title=title).first():
            continue
        n = Notification(title=title, message=msg, target_type=target, created_by=admin.id,
                         department=extra.get("department"), year=extra.get("year"))
        if "student_code" in extra:
            n.student_id = Student.query.filter_by(student_code=extra["student_code"]).first().id
        db.session.add(n)
        created["notifications"] += 1
    db.session.commit()
    return created


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        if "--reset" in sys.argv:
            if input("This DELETES all SAMS tables and data. Type YES to continue: ") != "YES":
                sys.exit("Cancelled.")
            db.drop_all()
        db.create_all()
        result = seed()
        print("Database ready. Newly created ->", result)
        print("\nDEVELOPMENT-ONLY demo logins:")
        print(f"  Admin   : {ADMIN['username']} / {ADMIN['password']}")
        print(f"  Student : cs2024001 / {STUDENT_PASSWORD}  (any student code, lowercase)")
