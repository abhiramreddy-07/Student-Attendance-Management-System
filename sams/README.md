# SAMS – Student Attendance Management System

Flask + MySQL web app that replaces paper attendance registers: student management, daily attendance,
automatic percentages, QR-code attendance, reports (print + CSV), notifications and role-based dashboards.

**Stack:** Python 3.10+ · Flask (Blueprints) · Flask-SQLAlchemy · Flask-Login · Flask-WTF (CSRF) · MySQL ·
Bootstrap 5 · Bootstrap Icons · Chart.js · html5-qrcode (scanner) · `qrcode` (QR generation).

---------------------------------------------------------------------------------------------------

## 0. FASTEST WAY (database already wired up)

1. Open `.env` and set `DB_PASSWORD` to your MySQL password (leave empty if MySQL has none, e.g. XAMPP). Make sure MySQL is running.
2. Windows: double-click **`setup.bat`** (creates venv, installs packages, creates database `sams_db`, tables and demo data). Then double-click **`start.bat`** and open http://127.0.0.1:5000.
   Any OS: `pip install -r requirements.txt`, `python setup_db.py`, `python run.py`.

`setup_db.py` connects using `.env`, creates the database itself (no `mysql` command needed), creates the tables and loads demo data. It was tested against a live MySQL-compatible server (MariaDB 10.11): tables, seed, re-run safety, all admin pages and student login, plus the 41 automated tests. The detailed manual steps below still work.

---------------------------------------------------------------------------------------------------

## 1. Quick start (Windows, step by step)

You need: **Python 3.10+** (tick "Add Python to PATH" in the installer) and **MySQL 8** (MySQL Installer or XAMPP/MariaDB).
Open **PowerShell** inside the project folder (`sams`).

```powershell
# 1) virtual environment + dependencies
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2) configuration
copy .env.example .env
notepad .env          # put YOUR MySQL password in DB_PASSWORD, and any long random text in SECRET_KEY

# 3) create the empty database (enter your MySQL root password when asked)
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS sams_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 4) create tables + demo data (safe to run again, it never duplicates anything)
python seed.py

# 5) start the website
python run.py
```
Open **http://127.0.0.1:5000** in your browser.

> `mysql` not recognised? Use *MySQL Command Line Client* from the Start menu and paste only the
> `CREATE DATABASE ...;` statement, or create `sams_db` in MySQL Workbench / phpMyAdmin.
> Prefer raw SQL over `seed.py`'s table creation? Run `mysql -u root -p < schema.sql` first (it creates the database
> and all tables), then `python seed.py` to add the demo data.

macOS / Linux: same steps, but `source venv/bin/activate` and `cp .env.example .env`.

Internet access is needed in the browser: Bootstrap, icons, Chart.js and the QR scanner library load from CDNs.

## 2. Demo accounts (DEVELOPMENT ONLY – delete/change before any real use)

| Role | Username | Password |
|---|---|---|
| Admin / Faculty | `admin` | `Admin@123` |
| Student (any of 12) | `cs2024001`, `cs2024002` … `it2024001` … `ec2024003` | `Student@123` |

On the login page choose **Student** or **Admin / Faculty** first. All demo people and `@sams.example.edu` emails are fictional.
`IT2024004` (Arjun Kulkarni) deliberately has low attendance so you can show the warning banner.
Seed data covers the last 15 working days (Mon–Fri) and includes one demo holiday. If you open the app on a weekend,
"Today" cards show 0 because nothing is recorded for that day – mark attendance or use a QR session to fill it.

## 3. How to demonstrate / test each module

| Module | Steps |
|---|---|
| **Login / roles** | Log in as admin → dashboard. Log out (top-right menu). Log in as `cs2024001` → student dashboard. While logged in as a student open `http://127.0.0.1:5000/students/` → **Unauthorized Access** page. |
| **Admin dashboard** | Cards, 14-day trend line, department doughnut, recent activity, recent notifications – all computed from MySQL. |
| **Students** | *Students → Add Student*: fill the form (a password is auto-generated and shown **once**). Search by name/roll, filter by dept/year/section, pagination after 10 rows. Eye = details, pencil = edit, person-slash = deactivate (blocks login), trash = permanent delete (confirmation dialog). Try a duplicate roll number/email → clear error. |
| **Mark attendance** | *Mark Attendance* → pick `Computer Science / Year 2 / Section A` and a weekday → *Load class* → use **All Present / All Absent** or tick individually → *Save*. Load the same date again: saved statuses are shown and **locked** until you tick *"I want to edit saved attendance"*. Edits are written to the audit log. |
| **History & edit** | *Attendance History* → filter → pencil icon → change status (a reason is mandatory). See the change under *Audit Log*. |
| **Holidays** | *Holidays* → add a date. It is excluded from working days and attendance can't be marked on it. |
| **Percentage** | Student detail page / student dashboard: `Present ÷ (Present+Absent) × 100`. Use the date-range filter. A student with no records shows 0 % (no crash). |
| **QR attendance** | Admin: *QR Sessions → New* → choose class + validity → QR appears with a live countdown and scan counter. Student (other browser/phone): *Scan QR Attendance* → *Start camera* (or paste the manual code printed under the QR). Success refreshes the student dashboard. Admin can **Close session** (optionally marking non-scanners Absent). |
| **Reports** | *Reports* → choose student-/class-/department-wise, filters and date range → **Print** (browser print dialog, sidebar hidden) or **Export CSV**. |
| **Notifications** | Admin: *Notifications → New* → Everyone / a class (dept, optional year & section) / one student. Student: bell icon shows unread count; opening one marks it read; *Mark all read*. |
| **Profile** | *My Profile*: students can change mobile + photo; admin also name + email. Role, student ID and class can never be edited by the user. *Change Password* enforces ≥8 chars with letters and digits. |

### QR scanning: camera, HTTPS and testing on a phone
* Browsers only allow camera access on **HTTPS or `http://localhost`**. On the same PC `http://127.0.0.1:5000` / `localhost` is fine (use `localhost` if the browser refuses `127.0.0.1`); the first time the browser asks for **camera permission** – click *Allow*.
* To scan with a **phone**, the page must be HTTPS. Easiest ways:
  1. `flask --app run run --cert=adhoc --host=0.0.0.0` and open `https://<your-PC-IP>:5000` on the phone (accept the self-signed-certificate warning), phone and PC on the same Wi-Fi; or
  2. a tunnel such as `ngrok http 5000` / `cloudflared tunnel --url http://localhost:5000`.
* Show the QR on the admin screen, open *Scan QR Attendance* on the phone logged in as a student of that class.
* If the camera cannot be used, the student pastes the **manual code** shown under the QR, or the faculty marks them from *Mark Attendance* (the manual alternative).
* When serving over HTTPS set `SESSION_COOKIE_SECURE=1` in `.env`.

## 4. Automated tests

```powershell
python -m pytest -q
```
41 tests cover: login/logout, roles & URL tampering, student CRUD + validation + duplicates + pagination, attendance marking,
edit-confirmation + audit log, DB-level duplicate prevention, the 45/50 = 90 % example, zero-record case, date ranges, holidays,
QR creation/scan/expiry/closed/wrong class/duplicate/no-overwrite, reports + CSV (+ formula-injection protection),
notification targeting/read status, password rules, protected profile fields, photo-upload validation,
empty-database pages and rendering of every page for both roles.
**The tests run on an in-memory SQLite database** so they need no MySQL; the application itself is configured for MySQL.

## 5. Project structure

```
sams/
  config.py  run.py  seed.py  schema.sql  make_schema.py  requirements.txt  .env.example  README.md
  app/
    __init__.py        application factory, error handlers, template globals
    extensions.py      db, login_manager, csrf
    models.py          SQLAlchemy models
    services.py        attendance % rules, dashboard statistics (single source of truth)
    utils.py           role decorator, validators, safe upload handling, CSV safety
    auth/              login, logout, profile, change password
    admin/             admin dashboard
    portal/            student dashboard + own attendance history
    students/          student CRUD, deactivate, reset password
    attendance/        mark, history, edit, audit log, holidays
    qr_attendance/     sessions, QR image, scanner page, token validation
    reports/           reports + CSV export
    notifications/     send / list / read
    templates/  static/ (css, js, uploads)
  tests/
```

## 6. Database design (MySQL via SQLAlchemy)

```
users 1───1 students 1───* attendance            holidays
  │             │  └──* attendance_audit_logs
  │             └─────* notification_reads *───1 notifications (target: all | class | one student)
  └─* qr_sessions ─* attendance.qr_session_id          users ─* attendance.marked_by
```
| Table | Purpose / key constraints |
|---|---|
| `users` | Login accounts for admins **and** students. Unique `username`, unique `email`, `role` (CHECK admin/student), hashed password, `active` flag. |
| `students` | One row per student, 1-to-1 with `users`. Unique `student_code` and `roll_number`; composite index on (department, year, section). |
| `attendance` | `student_id`, `attendance_date`, `status` (CHECK Present/Absent), `marked_by`, `source` (manual/qr), `created_at`, `updated_at`. **UNIQUE (student_id, attendance_date)** stops duplicates at database level. |
| `attendance_audit_logs` | Every create/edit: old → new status, who, when, note. |
| `holidays` | Non-working days; excluded from every percentage; attendance blocked on them. |
| `notifications` | title, message, `target_type` (all/class/student) + target columns, author, created time. |
| `notification_reads` | One row per (notification, student) – gives per-student read status. UNIQUE pair. |
| `qr_sessions` | Random 43-char `token` (unique), class, date, `expires_at`, `is_active`. |

`schema.sql` is generated from the models (`python make_schema.py`), so it always matches the code.

**Attendance % = Present ÷ (Present + Absent) × 100**, using only recorded, non-holiday days
(45 present of 50 working days → 90 %). Zero records → 0 %. The same function (`app/services.py`) feeds the dashboards, student pages and reports.

## 7. Security summary

* Passwords hashed with Werkzeug (scrypt); no plain-text passwords; no public registration; admin comes from `seed.py`.
* Session auth (Flask-Login), `HttpOnly` + `SameSite=Lax` cookies, secure remember-me cookie (14 days, opt-in checkbox).
* Role checks on **every** route (`roles_required`). Student pages never take a student ID from the URL/form – they always use the logged-in user, so changing a URL or form value cannot reveal another student's data (tested).
* CSRF tokens on all forms and on the QR `fetch` call; ORM queries only (no string-built SQL); Jinja auto-escaping.
* QR: unguessable `secrets.token_urlsafe(32)` tokens, validated server-side (login, class membership, open/expired/closed, holiday, duplicates). The QR never identifies the student; a QR scan can't overwrite an Absent mark made by faculty.
* Uploads: extension allow-list, 2 MB limit, verified & re-encoded with Pillow, random file names.
* CSV export neutralises spreadsheet-formula injection; open-redirect protection on `?next=`; generic login error messages.
* Secrets only in `.env` (git-ignored). If `SECRET_KEY` is missing a random one is generated per run.

## 8. Known limitations / honest notes
* Email/SMS notifications are **not** implemented (in-app only), as agreed in the requirements.
* Attendance is daily (not subject-wise). Non-working days are managed through the *Holidays* page.
* The automated tests use SQLite; the application and `setup_db.py` were additionally verified against a live MariaDB/MySQL server (see section 0).
* The camera scanner must be tried on a real device/browser (see section 3).
* `run.py` uses Flask's development server (fine for a demo). For production use a WSGI server and HTTPS.

## 9. Troubleshooting
| Problem | Fix |
|---|---|
| `Access denied for user 'root'` | Wrong `DB_PASSWORD` in `.env`. |
| `Unknown database 'sams_db'` | Run the `CREATE DATABASE` command from step 3. |
| `Can't connect to MySQL server` | Start the MySQL service (Windows → Services → MySQL80). |
| `ModuleNotFoundError` | Activate the venv (`venv\Scripts\activate`) and run `pip install -r requirements.txt`. |
| Page looks unstyled / charts missing | Browser has no internet (CDN files). |
| Camera won't start | Use `localhost` or HTTPS, allow permission, or use the manual code box. |
| Start over | `python seed.py --reset` (type YES) – drops and recreates all tables. |
