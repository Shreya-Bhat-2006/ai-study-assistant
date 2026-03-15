"""Gap Detector Lambda — scores quiz submissions and tracks concept gaps.

Handles two routes:
  POST /quizzes/{quiz_id}/submit  — score answers, detect gaps, persist result
  GET  /gaps                      — return current concept gaps for a student

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 7.3
"""
import json
import logging
from datetime import datetime, timezone
from collections import defaultdict
from decimal import Decimal

from shared.db import get_item, put_item, query_by_pk
from shared.errors import CORS_HEADERS, error_response
from shared.session import get_session, upsert_session

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GAP_THRESHOLD = 0.60  # concepts scoring below 60% are flagged as gaps


def _get_body(event: dict) -> dict:
    body = event.get("body") or "{}"
    if isinstance(body, str):
        return json.loads(body)
    return body


def _score_answers(questions: list[dict], answers: list[dict]) -> tuple[float, dict[str, float]]:
    """Compute overall score and per-concept scores.

    Returns (overall_pct, { concept_label: score_pct }).
    """
    # Build lookup: question_id -> question
    q_map = {q["question_id"]: q for q in questions}

    concept_correct: dict[str, int] = defaultdict(int)
    concept_total: dict[str, int] = defaultdict(int)
    total_correct = 0

    for ans in answers:
        qid = ans.get("question_id")
        submitted = ans.get("answer")
        q = q_map.get(qid)
        if not q:
            continue
        label = q["concept_label"]
        concept_total[label] += 1
        if submitted == q["correct_answer"]:
            concept_correct[label] += 1
            total_correct += 1

    total_questions = len(questions)
    overall_pct = round(total_correct / total_questions * 100, 2) if total_questions else 0.0

    per_concept = {
        label: round(concept_correct[label] / concept_total[label] * 100, 2)
        for label in concept_total
    }
    return overall_pct, per_concept


def _handle_submit(event: dict) -> dict:
    """Handle POST /quizzes/{quiz_id}/submit."""
    try:
        body = _get_body(event)
    except (json.JSONDecodeError, Exception) as exc:
        return error_response(400, "INVALID_JSON", f"Request body must be valid JSON: {exc}")

    student_id = body.get("student_id")
    quiz_id = (
        body.get("quiz_id")
        or (event.get("pathParameters") or {}).get("quiz_id")
    )
    answers = body.get("answers")

    missing = [f for f, v in [("student_id", student_id), ("quiz_id", quiz_id), ("answers", answers)] if not v]
    if missing:
        return error_response(400, "MISSING_FIELDS", f"Missing required fields: {', '.join(missing)}")

    if not isinstance(answers, list):
        return error_response(400, "INVALID_ANSWERS", "'answers' must be a list")

    # Validate each answer has required fields
    bad = [i for i, a in enumerate(answers) if not a.get("question_id") or "answer" not in a]
    if bad:
        return error_response(400, "MISSING_FIELDS", f"Answers at indices {bad} are missing 'question_id' or 'answer'")

    # Load quiz from DynamoDB
    quiz_item = get_item(f"SESSION#{student_id}", f"QUIZ#{quiz_id}")
    if not quiz_item:
        return error_response(404, "QUIZ_NOT_FOUND", f"Quiz '{quiz_id}' not found for student '{student_id}'")

    questions = quiz_item.get("questions", [])

    # Score answers
    overall_pct, per_concept = _score_answers(questions, answers)

    # Identify concept gaps (score < 60%)
    now = datetime.now(timezone.utc).isoformat()
    gaps = []
    for label, score in per_concept.items():
        if score < GAP_THRESHOLD * 100:
            gaps.append(label)
            put_item({
                "pk": f"SESSION#{student_id}",
                "sk": f"GAP#{label}",
                "concept_label": label,
                "latest_score_pct": Decimal(str(score)),
                "updated_at": now,
            })

    # Persist quiz result
    put_item({
        "pk": f"SESSION#{student_id}",
        "sk": f"RESULT#{quiz_id}",
        "quiz_id": quiz_id,
        "overall_score_pct": Decimal(str(overall_pct)),
        "per_concept": {k: Decimal(str(v)) for k, v in per_concept.items()},
        "submitted_at": now,
    })

    upsert_session(student_id)

    response_body: dict = {
        "score_pct": float(overall_pct),
        "per_concept": {k: float(v) for k, v in per_concept.items()},
    }
    # Always include gaps field when student has any recorded gaps (Requirement 5.3)
    all_gaps = _get_all_gaps(student_id)
    if all_gaps:
        response_body["gaps"] = all_gaps

    return {
        "statusCode": 200,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(response_body),
    }


def _get_all_gaps(student_id: str) -> list[str]:
    """Return all concept gap labels for a student from DynamoDB."""
    items = query_by_pk(f"SESSION#{student_id}")
    return [
        item["concept_label"]
        for item in items
        if item.get("sk", "").startswith("GAP#")
    ]


def _handle_get_gaps(event: dict) -> dict:
    """Handle GET /gaps."""
    qs = event.get("queryStringParameters") or {}
    headers = event.get("headers") or {}
    student_id = qs.get("student_id") or headers.get("student-id") or headers.get("Student-Id")

    if not student_id:
        return error_response(400, "MISSING_STUDENT_ID", "student_id is required")

    session = get_session(student_id)
    if not session:
        return error_response(404, "SESSION_NOT_FOUND", f"No session found for student '{student_id}'")

    gaps = _get_all_gaps(student_id)
    return {
        "statusCode": 200,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps({"gaps": gaps}),
    }


def handler(event: dict, context) -> dict:
    """Lambda entry point — routes to submit or get-gaps handler."""
    http_method = event.get("httpMethod", "").upper()
    path = event.get("path", "")
    if http_method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}
    if http_method == "GET" or path.endswith("/gaps"):
        return _handle_get_gaps(event)
    return _handle_submit(event)
