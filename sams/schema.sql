-- SAMS MySQL schema (generated from app/models.py by make_schema.py)
-- Usage:  mysql -u root -p < schema.sql
CREATE DATABASE IF NOT EXISTS sams_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE sams_db;

CREATE TABLE IF NOT EXISTS users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(80) NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	`role` VARCHAR(20) NOT NULL, 
	full_name VARCHAR(120) NOT NULL, 
	mobile VARCHAR(20), 
	photo VARCHAR(255), 
	active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	last_login DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_users_role CHECK (role IN ('admin','student'))
);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE INDEX ix_users_role ON users (`role`);
CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE IF NOT EXISTS holidays (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	holiday_date DATE NOT NULL, 
	reason VARCHAR(120) NOT NULL, 
	created_by INTEGER, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE UNIQUE INDEX ix_holidays_holiday_date ON holidays (holiday_date);

CREATE TABLE IF NOT EXISTS qr_sessions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	token VARCHAR(64) NOT NULL, 
	department VARCHAR(60) NOT NULL, 
	year INTEGER NOT NULL, 
	section VARCHAR(10) NOT NULL, 
	session_date DATE NOT NULL, 
	session_name VARCHAR(60) NOT NULL, 
	created_by INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	expires_at DATETIME NOT NULL, 
	is_active BOOL NOT NULL, 
	closed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE UNIQUE INDEX ix_qr_sessions_token ON qr_sessions (token);

CREATE TABLE IF NOT EXISTS students (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	student_code VARCHAR(20) NOT NULL, 
	roll_number VARCHAR(30) NOT NULL, 
	department VARCHAR(60) NOT NULL, 
	year INTEGER NOT NULL, 
	section VARCHAR(10) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE INDEX ix_students_class ON students (department, year, section);
CREATE UNIQUE INDEX ix_students_roll_number ON students (roll_number);
CREATE UNIQUE INDEX ix_students_student_code ON students (student_code);

CREATE TABLE IF NOT EXISTS attendance (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	student_id INTEGER NOT NULL, 
	attendance_date DATE NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	marked_by INTEGER, 
	source VARCHAR(10) NOT NULL, 
	qr_session_id INTEGER, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_attendance_student_date UNIQUE (student_id, attendance_date), 
	CONSTRAINT ck_attendance_status CHECK (status IN ('Present','Absent')), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(marked_by) REFERENCES users (id), 
	FOREIGN KEY(qr_session_id) REFERENCES qr_sessions (id)
);
CREATE INDEX ix_attendance_attendance_date ON attendance (attendance_date);
CREATE INDEX ix_attendance_student_id ON attendance (student_id);

CREATE TABLE IF NOT EXISTS attendance_audit_logs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	student_id INTEGER NOT NULL, 
	attendance_date DATE NOT NULL, 
	old_status VARCHAR(10), 
	new_status VARCHAR(10) NOT NULL, 
	changed_by INTEGER, 
	changed_at DATETIME NOT NULL, 
	note VARCHAR(200), 
	PRIMARY KEY (id), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(changed_by) REFERENCES users (id)
);
CREATE INDEX ix_attendance_audit_logs_changed_at ON attendance_audit_logs (changed_at);
CREATE INDEX ix_attendance_audit_logs_student_id ON attendance_audit_logs (student_id);

CREATE TABLE IF NOT EXISTS notifications (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	title VARCHAR(150) NOT NULL, 
	message TEXT NOT NULL, 
	target_type VARCHAR(10) NOT NULL, 
	department VARCHAR(60), 
	year INTEGER, 
	section VARCHAR(10), 
	student_id INTEGER, 
	created_by INTEGER, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_notification_target CHECK (target_type IN ('all','class','student')), 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE INDEX ix_notifications_created_at ON notifications (created_at);

CREATE TABLE IF NOT EXISTS notification_reads (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	notification_id INTEGER NOT NULL, 
	student_id INTEGER NOT NULL, 
	read_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_read_once UNIQUE (notification_id, student_id), 
	FOREIGN KEY(notification_id) REFERENCES notifications (id) ON DELETE CASCADE, 
	FOREIGN KEY(student_id) REFERENCES students (id) ON DELETE CASCADE
);
CREATE INDEX ix_notification_reads_student_id ON notification_reads (student_id);
