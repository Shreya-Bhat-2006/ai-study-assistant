"""Explanation Engine Lambda — generates targeted explanations for concept gaps.

Receives { student_id, concept_label, material_id }, verifies the concept is
in the student's recorded gaps, loads the parsed material, invokes Bedrock
with a targeted prompt, logs the explanation to the session, and returns it.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 7.3
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


def _get_body(event: dict) -> dict:
    body = event.get("body") or "{}"
    if isinstance(body, str):
        return json.loads(body)
    return body


def _build_prompt(raw_text: str, concept_label: str) -> str:
    """Build a targeted explanation prompt grounded in the study material."""
    return (
        f"You are a patient study tutor. A student is struggling with the concept: '{concept_label}'.\n"
        "Using ONLY the study material below, provide a clear, focused explanation of this concept. "
        "Use simple language, examples from the material where possible, and keep the explanation concise.\n\n"
        f"--- STUDY MATERIAL ---\n{raw_text}\n--- END MATERIAL ---\n\n"
        f"Explain '{concept_label}' to the student:"
    )


def handler(event: dict, context) -> dict:
    """Lambda entry point for POST /explanations."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}
    # --- Parse and validate request body ---
    try:
        body = _get_body(event)
    except (json.JSONDecodeError, Exception) as exc:
        return error_response(400, "INVALID_JSON", f"Request body must be valid JSON: {exc}")

    student_id = body.get("student_id")
    concept_label = body.get("concept_label")
    material_id = body.get("material_id")

    missing = [
        f for f, v in [
            ("student_id", student_id),
            ("concept_label", concept_label),
            ("material_id", material_id),
        ]
        if not v
    ]
    if missing:
        return error_response(400, "MISSING_FIELDS", f"Missing required fields: {', '.join(missing)}")

    # --- Verify concept is in student's recorded gaps (Requirement 6.3) ---
    gap_item = get_item(f"SESSION#{student_id}", f"GAP#{concept_label}")
    if not gap_item:
        return error_response(
            404,
            "CONCEPT_NOT_IN_GAPS",
            f"Concept '{concept_label}' is not in the recorded gaps for student '{student_id}'",
        )

    # --- Load parsed material from DynamoDB ---
    material_item = get_item(f"SESSION#{student_id}", f"MATERIAL#{material_id}")
    if not material_item:
        return error_response(404, "MATERIAL_NOT_FOUND", f"Material '{material_id}' not found for student '{student_id}'")

    try:
        parsed = deserialize(material_item["parsed_content"])
    except (DeserializationError, KeyError) as exc:
        logger.error("Failed to deserialize material %s: %s", material_id, exc)
        return error_response(500, "MATERIAL_CORRUPT", "Stored material content could not be read")

    raw_text = parsed.get("raw_text", "")

    # --- Invoke Bedrock ---
    prompt = _build_prompt(raw_text, concept_label)
    try:
        explanation = invoke_model(prompt)
    except Exception as exc:
        logger.error("Bedrock invocation failed: %s", exc)
        return error_response(502, "BEDROCK_ERROR", f"AI service error: {exc}")

    # --- Log explanation to session (Requirement 6.5) ---
    now = datetime.now(timezone.utc).isoformat()
    log_item = {
        "pk": f"SESSION#{student_id}",
        "sk": f"EXPLANATION#{now}#{uuid.uuid4()}",
        "concept_label": concept_label,
        "explanation": explanation,
        "material_id": material_id,
        "created_at": now,
    }
    put_item(log_item)

    upsert_session(student_id)

    return {
        "statusCode": 200,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps({"explanation": explanation}),
    }
