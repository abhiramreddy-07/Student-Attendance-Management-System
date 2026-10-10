import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Student, User  # noqa: E402
from config import TestConfig  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    class Cfg(TestConfig):
        UPLOAD_FOLDER = str(tmp_path)
    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_student(code, dept="Computer Science", year=2, section="A", roll=None, password="Student@123"):
    u = User(username=code.lower(), email=f"{code.lower()}@t.example.edu", role="student",
             full_name=f"Student {code}")
    u.set_password(password)
    s = Student(user=u, student_code=code, roll_number=roll or f"R-{code}", department=dept,
                year=year, section=section)
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture()
def admin(app):
    u = User(username="admin", email="admin@t.example.edu", role="admin", full_name="Admin T")
    u.set_password("Admin@123")
    db.session.add(u)
    db.session.commit()
    return u


def login(client, ident, password, role):
    return client.post("/login", data={"identifier": ident, "password": password, "role": role},
                       follow_redirects=True)


@pytest.fixture()
def admin_client(client, admin):
    login(client, "admin", "Admin@123", "admin")
    return client


@pytest.fixture()
def weekday():
    d = date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
