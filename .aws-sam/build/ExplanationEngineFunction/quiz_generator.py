"""Quiz Generator Lambda — generates multiple-choice quizzes from study materials.

Receives { student_id, material_id, num_questions }, loads parsed material,
invokes Bedrock to generate structured quiz questions, validates and persists
the quiz, and returns it to the student.

Retries Bedrock once on parse failure before returning 502.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 7.3
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from shared.bedrock import invoke_model
from shared.db import get_item, put_item
from shared.errors import CORS_HEADERS, error_response
from shared.parser import deserialize, DeserializationError
from shared.session import upsert_session

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MIN_QUESTIONS = 5
MAX_QUESTIONS = 20


def _get_body(event: dict) -> dict:
    body = event.get("body") or "{}"
    if isinstance(body, str):
        return json.loads(body)
    return body


def _build_prompt(raw_text: str, num_questions: int) -> str:
    return (
        f"You are a quiz generator. Based on the study material below, generate exactly "
        f"{num_questions} multiple-choice questions. Each question must test a distinct concept.\n\n"
        "Return ONLY a JSON array with no extra text. Each element must have:\n"
        '  "question_id": unique string,\n'
        '  "text": question text,\n'
        '  "options": array of exactly 4 strings (e.g. ["A. ...", "B. ...", "C. ...", "D. ..."]),\n'
        '  "correct_answer": one of the option strings,\n'
        '  "concept_label": short concept name being tested\n\n'
        f"--- STUDY MATERIAL ---\n{raw_text}\n--- END MATERIAL ---\n\n"
        "JSON array:"
    )


def _parse_questions(raw_response: str, num_questions: int) -> list[dict]:
    """Parse and validate Bedrock quiz response into a list of question dicts.

    Raises ValueError with a descriptive message if the response is malformed.
    """
    # Strip markdown code fences if present
    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    questions = json.loads(text)  # raises JSONDecodeError on bad JSON

    if not isinstance(questions, list):
        raise ValueError("Expected a JSON array of questions")

    if len(questions) != num_questions:
        raise ValueError(f"Expected {num_questions} questions, got {len(questions)}")

    for i, q in enumerate(questions):
        if not q.get("text", "").strip():
            raise ValueError(f"Question {i} has empty text")
        options = q.get("options", [])
        if len(options) != 4:
            raise ValueError(f"Question {i} must have exactly 4 options, got {len(options)}")
        if q.get("correct_answer") not in options:
            raise ValueError(f"Question {i} correct_answer is not one of the options")
        if not q.get("concept_label", "").strip():
            raise ValueError(f"Question {i} has empty concept_label")
        # Ensure question_id is set
        if not q.get("question_id"):
            q["question_id"] = str(uuid.uuid4())

    return questions


def handler(event: dict, context) -> dict:
    """Lambda entry point for POST /quizzes."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}
    # --- Parse and validate request body ---
    try:
        body = _get_body(event)
    except (json.JSONDecodeError, Exception) as exc:
        return error_response(400, "INVALID_JSON", f"Request body must be valid JSON: {exc}")

    student_id = body.get("student_id")
    material_id = body.get("material_id")
    num_questions_raw = body.get("num_questions")

    missing = [f for f, v in [("student_id", student_id), ("material_id", material_id)] if not v]
    if missing:
        return error_response(400, "MISSING_FIELDS", f"Missing required fields: {', '.join(missing)}")

    # Validate num_questions
    try:
        num_questions = int(num_questions_raw) if num_questions_raw is not None else 10
    except (TypeError, ValueError):
        return error_response(400, "INVALID_NUM_QUESTIONS", "num_questions must be an integer")

    if not (MIN_QUESTIONS <= num_questions <= MAX_QUESTIONS):
        return error_response(
            400,
            "INVALID_NUM_QUESTIONS",
            f"num_questions must be between {MIN_QUESTIONS} and {MAX_QUESTIONS}",
        )

    # --- Load parsed material from DynamoDB ---
    item = get_item(f"SESSION#{student_id}", f"MATERIAL#{material_id}")
    if not item:
        return error_response(404, "MATERIAL_NOT_FOUND", f"Material '{material_id}' not found for student '{student_id}'")

    try:
        parsed = deserialize(item["parsed_content"])
    except (DeserializationError, KeyError) as exc:
        logger.error("Failed to deserialize material %s: %s", material_id, exc)
        return error_response(500, "MATERIAL_CORRUPT", "Stored material content could not be read")

    raw_text = parsed.get("raw_text", "")

    # --- Invoke Bedrock with retry-once on parse failure ---
    prompt = _build_prompt(raw_text, num_questions)
    questions = None
    last_error = None

    for attempt in range(2):
        try:
            raw_response = invoke_model(prompt)
            questions = _parse_questions(raw_response, num_questions)
            break  # success
        except Exception as exc:
            last_error = exc
            logger.warning("Quiz generation attempt %d failed: %s", attempt + 1, exc)

    if questions is None:
        logger.error("Quiz generation failed after 2 attempts: %s", last_error)
        return error_response(502, "QUIZ_GENERATION_FAILED", f"Failed to generate quiz: {last_error}")

    # --- Persist quiz to DynamoDB ---
    quiz_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    quiz_item = {
        "pk": f"SESSION#{student_id}",
        "sk": f"QUIZ#{quiz_id}",
        "quiz_id": quiz_id,
        "material_id": material_id,
        "questions": questions,
        "created_at": now,
    }
    put_item(quiz_item)

    # Ensure session exists
    upsert_session(student_id)

    return {
        "statusCode": 200,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps({"quiz_id": quiz_id, "questions": questions}),
    }
