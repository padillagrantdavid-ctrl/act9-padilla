import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

import requests
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)
DATABASE = Path(__file__).with_name("students.db")
PARTNER_API_URL = os.environ.get(
	"PARTNER_API_URL",
	"https://prince-act8.onrender.com/api/students",
)

STUDENT_PROFILE = {
	"student_id": "24-00170",
	"name": "Grant David Padilla",
	"program": "BSIT",
	"year": 3,
	"section": "B",
}


@app.route("/")
def home():
	return render_template("index.html", partner_api_url=PARTNER_API_URL)


@app.route("/student")
def get_student():
	return jsonify(STUDENT_PROFILE)


@app.route("/hello")
def say_hello():
	name = request.args.get("name", "Student")
	return jsonify({"message": f"Hello, {name}!"})


@app.route("/academic")
def get_academic_profile():
	return jsonify(
		{
			"student_id": STUDENT_PROFILE["student_id"],
			"name": STUDENT_PROFILE["name"],
			"program": STUDENT_PROFILE["program"],
			"year": STUDENT_PROFILE["year"],
			"section": STUDENT_PROFILE["section"],
		}
	)


def get_db_connection():
	conn = sqlite3.connect(DATABASE)
	conn.row_factory = sqlite3.Row
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
	columns = {row["name"] for row in conn.execute("PRAGMA table_info(students)")}
	if "source" not in columns:
		conn.execute("ALTER TABLE students ADD COLUMN source TEXT NOT NULL DEFAULT 'Local'")
		conn.commit()
	return conn


def student_payload(default_source="External API"):
	data = request.get_json(silent=True)
	if not isinstance(data, dict):
		return None, (jsonify({"error": "A JSON object is required."}), 400)

	required_fields = ("student_id", "name", "program", "year", "section")
	if any(field not in data for field in required_fields):
		return None, (jsonify({"error": "All student fields are required."}), 400)

	values = {}
	for field in ("student_id", "name", "program", "section"):
		value = data[field]
		if not isinstance(value, str) or not value.strip():
			return None, (jsonify({"error": f"{field} must be a non-empty string."}), 400)
		values[field] = value.strip()

	year = data["year"]
	if isinstance(year, bool) or not isinstance(year, int) or year < 1:
		return None, (jsonify({"error": "year must be a positive integer."}), 400)
	values["year"] = year
	source = data.get("source", default_source)
	if source is not None:
		if not isinstance(source, str) or not source.strip():
			return None, (jsonify({"error": "source must be a non-empty string."}), 400)
		values["source"] = source.strip()
	return values, None


def valid_partner_api_url(api_url):
	try:
		parsed_url = urlsplit(api_url)
		hostname = parsed_url.hostname or ""
		return (
			parsed_url.scheme == "https"
			and hostname.endswith(".onrender.com")
			and hostname != "onrender.com"
			and parsed_url.path == "/api/students"
			and parsed_url.port in (None, 443)
			and parsed_url.username is None
			and parsed_url.password is None
			and not parsed_url.query
			and not parsed_url.fragment
		)
	except ValueError:
		return False


@app.route("/api/students", methods=["GET"])
def api_students():
	conn = get_db_connection()
	try:
		rows = conn.execute("SELECT * FROM students ORDER BY id").fetchall()
		return jsonify([dict(row) for row in rows])
	finally:
		conn.close()


@app.route("/partner-records")
def partner_records():
	if not valid_partner_api_url(PARTNER_API_URL):
		return jsonify({"error": "Configure a valid HTTPS partner /api/students Render URL."}), 500
	try:
		response = requests.get(PARTNER_API_URL, timeout=(3, 10), allow_redirects=False)
		response.raise_for_status()
		students = response.json()
	except requests.RequestException:
		return jsonify({"error": "Unable to retrieve partner data."}), 502
	except ValueError:
		return jsonify({"error": "The partner API did not return valid JSON."}), 502

	if not isinstance(students, list):
		return jsonify({"error": "The partner API must return a JSON list."}), 502
	return jsonify(students)


@app.route("/import-student", methods=["POST"])
def import_student():
	data, error = student_payload(default_source="Classmate API")
	if error:
		return error

	conn = get_db_connection()
	try:
		cursor = conn.execute(
			"""
			INSERT INTO students (student_id, name, program, year, section, source)
			VALUES (?, ?, ?, ?, ?, 'Classmate API')
			""",
			(data["student_id"], data["name"], data["program"], data["year"], data["section"]),
		)
		conn.commit()
		return jsonify({"message": "Remote record saved", "id": cursor.lastrowid}), 201
	finally:
		conn.close()


@app.route("/send-to-partner", methods=["POST"])
def send_to_partner():
	data = request.get_json(silent=True)
	if not isinstance(data, dict) or data.get("confirmed") is not True:
		return jsonify({"error": "Partner permission confirmation is required."}), 400
	if not valid_partner_api_url(PARTNER_API_URL):
		return jsonify({"error": "Configure a valid HTTPS partner /api/students Render URL."}), 500

	record = {
		"student_id": "EXT-001",
		"name": "Sample Exchange Record",
		"program": "BSIT",
		"year": 1,
		"section": "A",
		"source": "Partner API",
	}
	try:
		response = requests.post(
			PARTNER_API_URL,
			json=record,
			timeout=(3, 10),
			allow_redirects=False,
		)
		response.raise_for_status()
	except requests.RequestException:
		return jsonify({"error": "Unable to send the practice record to the partner API."}), 502

	try:
		partner_response = response.json()
	except ValueError:
		partner_response = response.text[:500]
	return jsonify(
		{
			"message": "Practice record sent to partner API.",
			"partner_status": response.status_code,
			"partner_response": partner_response,
		}
	)


@app.route("/api/students", methods=["POST"])
def add_student():
	data, error = student_payload()
	if error:
		return error

	conn = get_db_connection()
	try:
		cursor = conn.execute(
			"""
			INSERT INTO students (student_id, name, program, year, section, source)
			VALUES (?, ?, ?, ?, ?, ?)
			""",
			(
				data["student_id"],
				data["name"],
				data["program"],
				data["year"],
				data["section"],
				data["source"],
			),
		)
		conn.commit()
		return jsonify({"message": "Student added", "id": cursor.lastrowid}), 201
	finally:
		conn.close()


@app.route("/api/students/<int:student_db_id>", methods=["GET"])
def api_get_student(student_db_id):
	conn = get_db_connection()
	try:
		student = conn.execute(
			"SELECT * FROM students WHERE id = ?", (student_db_id,)
		).fetchone()
	finally:
		conn.close()

	if student is None:
		return jsonify({"error": "Student not found"}), 404
	return jsonify(dict(student))


@app.route("/api/students/<int:student_db_id>", methods=["PUT"])
def update_student(student_db_id):
	data, error = student_payload(default_source=None)
	if error:
		return error

	conn = get_db_connection()
	try:
		cursor = conn.execute(
			"""
			UPDATE students
			SET student_id = ?, name = ?, program = ?, year = ?, section = ?,
				source = COALESCE(?, source)
			WHERE id = ?
			""",
			(
				data["student_id"],
				data["name"],
				data["program"],
				data["year"],
				data["section"],
				data.get("source"),
				student_db_id,
			),
		)
		if cursor.rowcount == 0:
			return jsonify({"error": "Student not found"}), 404
		conn.commit()
		return jsonify({"message": "Student updated"})
	finally:
		conn.close()


@app.route("/api/students/<int:student_db_id>", methods=["DELETE"])
def delete_student(student_db_id):
	conn = get_db_connection()
	try:
		cursor = conn.execute(
			"DELETE FROM students WHERE id = ?", (student_db_id,)
		)
		if cursor.rowcount == 0:
			return jsonify({"error": "Student not found"}), 404
		conn.commit()
		return jsonify({"message": "Student deleted"})
	finally:
		conn.close()


if __name__ == "__main__":
	app.run(debug=True)