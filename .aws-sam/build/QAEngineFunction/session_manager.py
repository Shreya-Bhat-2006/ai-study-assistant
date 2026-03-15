"""Session Manager Lambda — returns a student's full session summary.

Handles GET /session. Queries all DynamoDB items under SESSION#{student_id}
and groups them by sk prefix into materials, quizzes, gaps, and qa_log.

Requirements: 7.3, 7.4, 7.5
"""
import json
import logging

from shared.db import query_by_pk
from shared.errors import CORS_HEADERS, error_response
from shared.session import get_session

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _get_student_id(event: dict) -> str | None:
    qs = event.get("queryStringParameters") or {}
    headers = event.get("headers") or {}
    return (
        qs.get("student_id")
        or headers.get("student-id")
        or headers.get("Student-Id")
        or headers.get("x-student-id")
    )


def handler(event: dict, context) -> dict:
    """Lambda entry point for GET /session."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}
    student_id = _get_student_id(event)
    if not student_id:
        return error_response(400, "MISSING_STUDENT_ID", "student_id is required")

    # Verify session exists
    session = get_session(student_id)
    if not session:
        return error_response(404, "SESSION_NOT_FOUND", f"No session found for student '{student_id}'")

    # Query all items for this student
    all_items = query_by_pk(f"SESSION#{student_id}")

    materials = []
    quizzes = []
    gaps = []
    qa_log = []

    for item in all_items:
        sk = item.get("sk", "")
        if sk == "METADATA":
            continue
        elif sk.startswith("MATERIAL#"):
            materials.append({
                "material_id": item.get("material_id"),
                "filename": item.get("filename"),
                "s3_key": item.get("s3_key"),
                "created_at": item.get("created_at"),
            })
        elif sk.startswith("QUIZ#"):
            quizzes.append({
                "quiz_id": item.get("quiz_id"),
                "material_id": item.get("material_id"),
                "question_count": len(item.get("questions", [])),
                "created_at": item.get("created_at"),
            })
        elif sk.startswith("GAP#"):
            gaps.append({
                "concept_label": item.get("concept_label"),
                "latest_score_pct": item.get("latest_score_pct"),
                "updated_at": item.get("updated_at"),
            })
        elif sk.startswith("QA#"):
            qa_log.append({
                "question": item.get("question"),
                "answer": item.get("answer"),
                "material_id": item.get("material_id"),
                "created_at": item.get("created_at"),
            })
        elif sk.startswith("EXPLANATION#"):
            # Include explanations in qa_log for completeness
            qa_log.append({
                "type": "explanation",
                "concept_label": item.get("concept_label"),
                "explanation": item.get("explanation"),
                "material_id": item.get("material_id"),
                "created_at": item.get("created_at"),
            })

    return {
        "statusCode": 200,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps({
            "session_id": session.get("pk"),
            "student_id": student_id,
            "materials": materials,
            "quizzes": quizzes,
            "gaps": gaps,
            "qa_log": qa_log,
        }),
    }
