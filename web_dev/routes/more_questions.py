from flask import Blueprint, request, jsonify
from more_questions_db import get_db_connection

questions_bp = Blueprint("questions", __name__)


@questions_bp.route("/questions", methods=["GET"])
def get_questions():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM questions ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])


@questions_bp.route("/questions", methods=["POST"])
def add_question():
    data = request.get_json()

    if not data or "text" not in data:
        return (
            jsonify({"error": {"code": 400, "message": "Question text required"}}),
            400,
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO questions (text, status) VALUES (?, ?)",
        (data["text"], "unanswered"),
    )

    conn.commit()
    conn.close()

    return jsonify({"success": True}), 201
