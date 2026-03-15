"""QA Engine Lambda — answers student questions grounded in study materials.

Receives { student_id, material_id, question }, loads the parsed material
from DynamoDB, builds a context-grounded prompt, invokes Bedrock, logs the
Q&A pair to the session, and returns the answer.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 7.3
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from shared.bedrock import invoke_model
from shared.db import get_item, put_item
from shared.errors import error_response
from shared.parser import deserialize, DeserializationError
from shared.session import upsert_session

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _get_body(event: dict) -> dict:
    """Parse JSON body from API Gateway event."""
    body = event.get("body") or "{}"
    if isinstance(body, str):
        return json.loads(body)
    return body


def _build_prompt(raw_text: str, question: str) -> str:
    """Build a context-grounded prompt for Bedrock."""
    return (
        "You are a helpful study assistant. Use only the study material below to answer "
        "the student's question. If the answer is not in the material, say so.\n\n"
        f"--- STUDY MATERIAL ---\n{raw_text}\n--- END MATERIAL ---\n\n"
        f"Student question: {question}\n\nAnswer:"
    )


def handler(event: dict, context) -> dict:
    """Lambda entry point for POST /qa."""
    # --- Parse and validate request body ---
    try:
        body = _get_body(event)
    except (json.JSONDecodeError, Exception) as exc:
        return error_response(400, "INVALID_JSON", f"Request body must be valid JSON: {exc}")

    student_id = body.get("student_id")
    material_id = body.get("material_id")
    question = body.get("question")

    missing = [f for f, v in [("student_id", student_id), ("material_id", material_id), ("question", question)] if not v]
    if missing:
        return error_response(400, "MISSING_FIELDS", f"Missing required fields: {', '.join(missing)}")

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

    # --- Invoke Bedrock ---
    prompt = _build_prompt(raw_text, question)
    try:
        answer = invoke_model(prompt)
    except Exception as exc:
        logger.error("Bedrock invocation failed: %s", exc)
        return error_response(502, "BEDROCK_ERROR", f"AI service error: {exc}")

    # --- Log Q&A pair to session ---
    now = datetime.now(timezone.utc).isoformat()
    log_item = {
        "pk": f"SESSION#{student_id}",
        "sk": f"QA#{now}#{uuid.uuid4()}",
        "question": question,
        "answer": answer,
        "material_id": material_id,
        "created_at": now,
    }
    put_item(log_item)

    # Ensure session exists
    upsert_session(student_id)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"answer": answer}),
    }
