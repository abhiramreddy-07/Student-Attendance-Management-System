"""Reports: student-wise, class-wise, department-wise (+ CSV export). Admin only."""
import csv
import io
from collections import OrderedDict
from datetime import date

from flask import Blueprint, Response, render_template, request

from ..models import Student, User
from ..services import Summary, attendance_stats, calc_percentage
from ..utils import csv_safe, parse_date, roles_required

bp = Blueprint("reports", __name__, url_prefix="/reports")
VIEWS = ("student", "class", "department")


def _filters():
    view = request.args.get("view", "student")
    return {
        "view": view if view in VIEWS else "student",
        "department": request.args.get("department", ""),
        "year": request.args.get("year", type=int),
        "section": request.args.get("section", ""),
        "q": (request.args.get("q") or "").strip(),
        "start": parse_date(request.args.get("start")),
        "end": parse_date(request.args.get("end")),
    }


def build_report(f):
    """Return (headers, rows, totals) for the chosen view. Rows are lists of plain values."""
    query = Student.query.join(User, Student.user_id == User.id)
    if f["department"]:
        query = query.filter(Student.department == f["department"])
    if f["year"]:
        query = query.filter(Student.year == f["year"])
    if f["section"]:
        query = query.filter(Student.section == f["section"])
    if f["q"]:
        like = f"%{f['q']}%"
        query = query.filter(User.full_name.like(like) | Student.roll_number.like(like))
    students = query.order_by(Student.department, Student.year, Student.section,
                              Student.roll_number).all()
    stats = attendance_stats([s.id for s in students], f["start"], f["end"])

    if f["view"] == "student":
        headers = ["Roll No", "Student", "Department", "Year", "Section", "Present", "Absent",
                   "Working Days", "Attendance %"]
        rows = []
        for s in students:
            m = stats.get(s.id, Summary())
            rows.append([s.roll_number, s.full_name, s.department, s.year, s.section,
                         m.present, m.absent, m.total, m.percentage])
        present = sum(r[5] for r in rows)
        absent = sum(r[6] for r in rows)
    else:
        keyfn = (lambda s: (s.department, s.year, s.section)) if f["view"] == "class" \
            else (lambda s: (s.department,))
        groups = OrderedDict()
        for s in students:
            g = groups.setdefault(keyfn(s), {"students": 0, "present": 0, "absent": 0})
            m = stats.get(s.id, Summary())
            g["students"] += 1
            g["present"] += m.present
            g["absent"] += m.absent
        if f["view"] == "class":
            headers = ["Department", "Year", "Section", "Students", "Present", "Absent",
                       "Records", "Attendance %"]
            rows = [[*k, g["students"], g["present"], g["absent"], g["present"] + g["absent"],
                     calc_percentage(g["present"], g["present"] + g["absent"])]
                    for k, g in groups.items()]
            present, absent = sum(r[4] for r in rows), sum(r[5] for r in rows)
        else:
            headers = ["Department", "Students", "Present", "Absent", "Records", "Attendance %"]
            rows = [[*k, g["students"], g["present"], g["absent"], g["present"] + g["absent"],
                     calc_percentage(g["present"], g["present"] + g["absent"])]
                    for k, g in groups.items()]
            present, absent = sum(r[2] for r in rows), sum(r[3] for r in rows)
    totals = {"present": present, "absent": absent, "records": present + absent,
              "percentage": calc_percentage(present, present + absent), "rows": len(rows)}
    return headers, rows, totals


@bp.route("/")
@roles_required("admin")
def index():
    f = _filters()
    headers, rows, totals = build_report(f)
    return render_template("reports/index.html", f=f, headers=headers, rows=rows, totals=totals,
                           generated=date.today())


@bp.route("/export.csv")
@roles_required("admin")
def export_csv():
    f = _filters()
    headers, rows, totals = build_report(f)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["SAMS attendance report", f"view={f['view']}",
                f"from={f['start'] or 'start'}", f"to={f['end'] or 'today'}"])
    w.writerow(headers)
    for r in rows:
        w.writerow([csv_safe(c) for c in r])
    w.writerow([])
    w.writerow(["TOTAL", f"Present={totals['present']}", f"Absent={totals['absent']}",
                f"Records={totals['records']}", f"Attendance %={totals['percentage']}"])
    name = f"attendance_{f['view']}_{date.today():%Y%m%d}.csv"
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}"})
