"""One-step database setup: creates the MySQL database (if missing), the tables and the demo data.

Usage:  python setup_db.py
Reads DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME from .env (see .env.example).
Safe to run repeatedly - it never duplicates data.
"""
import os
import sys

import pymysql
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

host = os.environ.get("DB_HOST", "localhost")
port = int(os.environ.get("DB_PORT", "3306"))
user = os.environ.get("DB_USER", "root")
password = os.environ.get("DB_PASSWORD", "")
name = os.environ.get("DB_NAME", "sams_db")

if not name.replace("_", "").isalnum():
    sys.exit(f"DB_NAME '{name}' may only contain letters, digits and underscores.")

try:
    conn = pymysql.connect(host=host, port=port, user=user, password=password)
except pymysql.err.OperationalError as e:
    code = e.args[0]
    if code == 1045:
        sys.exit("Access denied: DB_USER / DB_PASSWORD in your .env file are wrong.")
    sys.exit(f"Cannot connect to MySQL at {host}:{port} - is the MySQL service running?\n{e}")

with conn.cursor() as cur:
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
conn.close()
print(f"Connected to MySQL at {host}:{port} - database '{name}' is ready.")

from app import create_app  # noqa: E402  (imported after the database exists)
from app.extensions import db  # noqa: E402
import seed  # noqa: E402

app = create_app()
with app.app_context():
    db.create_all()
    result = seed.seed()
print("Tables created and demo data loaded. Newly created ->", result)
print("Demo logins:  admin / Admin@123   |   cs2024001 / Student@123")
print("\nAll done. Start the site with:  python run.py   ->  http://127.0.0.1:5000")
