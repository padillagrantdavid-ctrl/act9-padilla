import sqlite3
from pathlib import Path


DATABASE = Path(__file__).with_name("students.db")

SAMPLE_STUDENTS = [
	("24-00170", "Grant David Padilla", "BSIT", 3, "B"),
	("24-00171", "Alex Morgan", "BSIT", 1, "A"),
	("24-00172", "Sam Rivera", "BSCS", 2, "B"),
	("24-00173", "Jordan Lee", "BSIT", 2, "C"),
	("24-00174", "Taylor Cruz", "BSCS", 4, "A"),
]


with sqlite3.connect(DATABASE) as conn:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS students (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			student_id TEXT NOT NULL,
			name TEXT NOT NULL,
			program TEXT NOT NULL,
			year INTEGER NOT NULL,
			section TEXT NOT NULL,
			source TEXT NOT NULL DEFAULT 'Local'
		)
		"""
	)
	columns = {row[1] for row in conn.execute("PRAGMA table_info(students)")}
	if "source" not in columns:
		conn.execute("ALTER TABLE students ADD COLUMN source TEXT NOT NULL DEFAULT 'Local'")
	count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
	if count == 0:
		conn.executemany(
			"""
			INSERT INTO students (student_id, name, program, year, section, source)
			VALUES (?, ?, ?, ?, ?, 'Local')
			""",
			SAMPLE_STUDENTS,
		)

print("Database created successfully.")
