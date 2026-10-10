"""Regenerates schema.sql (MySQL DDL) from the SQLAlchemy models, so the two never drift."""
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import create_app
from app.extensions import db

app = create_app()
parts = ["-- SAMS MySQL schema (generated from app/models.py by make_schema.py)",
         "-- Usage:  mysql -u root -p < schema.sql",
         "CREATE DATABASE IF NOT EXISTS sams_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
         "USE sams_db;", ""]
with app.app_context():
    for table in db.metadata.sorted_tables:
        parts.append(str(CreateTable(table, if_not_exists=True).compile(dialect=mysql.dialect())).strip() + ";")
        for idx in sorted(table.indexes, key=lambda i: i.name):
            parts.append(str(CreateIndex(idx).compile(dialect=mysql.dialect())).strip() + ";")
        parts.append("")
open("schema.sql", "w", encoding="utf-8").write("\n".join(parts))
print("schema.sql written")
