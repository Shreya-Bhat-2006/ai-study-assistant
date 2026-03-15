"""Material Processor Lambda — handles study material uploads.

Receives a multipart/form-data request from API Gateway, validates the file,
extracts text, stores the raw file in S3, and persists the parsed content to
DynamoDB. Upserts the student session record.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 7.1, 7.2, 8.1, 8.2, 8.4
"""
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from email import message_from_bytes
from email.policy import HTTP

import boto3

from shared.db import get_item, put_item
from shared.errors import CORS_HEADERS, error_response
from shared.parser import (
    DeserializationError,
    ExtractionError,
    deserialize,
    extract_pdf,
    extract_text,
    serialize,
)
from shared.session import upsert_session

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {"application/pdf", "text/plain"}
ALLOWED_EXTENSIONS = {".pdf", ".txt"}


def _get_s3_client():
    return boto3.client("s3")


def _parse_multipart(event: dict) -> tuple[str, bytes, str]:
    """Parse a multipart/form-data API Gateway event.

    Returns (filename, file_bytes, content_type).
    Raises ValueError with a descriptive message on parse failure.
    """
    content_type_header = (
        event.get("headers", {}).get("content-type")
        or event.get("headers", {}).get("Content-Type")
        or ""
    )

    body = event.get("body", "") or ""
    if event.get("isBase64Encoded", False):
        body_bytes = base64.b64decode(body)
    else:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body

    # Build a MIME message so the stdlib can parse the multipart boundary
    raw_message = f"Content-Type: {content_type_header}\r\n\r\n".encode() + body_bytes
    msg = message_from_bytes(raw_message, policy=HTTP)

    for part in msg.walk():
        disposition = part.get_content_disposition()
        if disposition != "attachment" and "filename" not in (part.get_param("name", header="content-disposition") or ""):
            # Try to find the file part by checking for a filename param
            filename = part.get_filename()
            if not filename:
                continue
        else:
            filename = part.get_filename()
            if not filename:
                continue

        file_bytes = part.get_payload(decode=True)
        part_content_type = part.get_content_type()
        return filename, file_bytes, part_content_type

    raise ValueError("No file part found in multipart request")


def _get_student_id(event: dict) -> str | None:
    """Extract student_id from headers or query string parameters."""
    headers = event.get("headers") or {}
    qs = event.get("queryStringParameters") or {}
    return (
        headers.get("student-id")
        or headers.get("Student-Id")
        or headers.get("x-student-id")
        or qs.get("student_id")
    )


def handler(event: dict, context) -> dict:
    """Lambda entry point for POST /materials."""
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    # --- Validate student_id ---
    student_id = _get_student_id(event)
    if not student_id:
        return error_response(400, "MISSING_STUDENT_ID", "student_id is required")

    # --- Parse multipart body ---
    try:
        filename, file_bytes, content_type = _parse_multipart(event)
    except (ValueError, Exception) as exc:
        logger.warning("Failed to parse multipart body: %s", exc)
        return error_response(400, "INVALID_REQUEST", f"Could not parse multipart body: {exc}")

    # --- Validate file size ---
    if len(file_bytes) > MAX_FILE_SIZE:
        return error_response(
            400,
            "FILE_TOO_LARGE",
            f"File exceeds the 10 MB limit (received {len(file_bytes)} bytes)",
        )

    # --- Validate file type ---
    ext = os.path.splitext(filename)[1].lower()
    normalised_ct = content_type.split(";")[0].strip().lower()
    if normalised_ct not in ALLOWED_CONTENT_TYPES and ext not in ALLOWED_EXTENSIONS:
        return error_response(
            400,
            "UNSUPPORTED_FILE_TYPE",
            f"Unsupported file type '{content_type}'. Only PDF and plain text are accepted.",
        )

    material_id = str(uuid.uuid4())

    # --- Extract text (must succeed before any writes) ---
    try:
        if normalised_ct == "application/pdf" or ext == ".pdf":
            parsed = extract_pdf(file_bytes, material_id, filename)
        else:
            parsed = extract_text(file_bytes, material_id, filename)
    except ExtractionError as exc:
        logger.warning("Text extraction failed for %s: %s", filename, exc)
        return error_response(422, "EXTRACTION_FAILED", str(exc))

    # --- Serialize parsed content ---
    try:
        serialized = serialize(parsed)
        # Verify round-trip before writing (Requirement 8.4)
        deserialize(serialized)
    except DeserializationError as exc:
        logger.error("Deserialization round-trip failed for %s: %s", filename, exc)
        return error_response(500, "SERIALIZATION_ERROR", "Internal error processing material content")

    # --- Store raw file in S3 ---
    bucket_name = os.environ.get("BUCKET_NAME", "study-assistant-materials")
    s3_key = f"{student_id}/{material_id}/{filename}"
    try:
        s3 = _get_s3_client()
        s3.put_object(Bucket=bucket_name, Key=s3_key, Body=file_bytes, ContentType=content_type)
    except Exception as exc:
        logger.error("S3 upload failed: %s", exc)
        return error_response(500, "S3_UPLOAD_FAILED", "Failed to store file")

    # --- Persist parsed content to DynamoDB ---
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "pk": f"SESSION#{student_id}",
        "sk": f"MATERIAL#{material_id}",
        "material_id": material_id,
        "s3_key": s3_key,
        "filename": filename,
        "parsed_content": serialized,
        "created_at": now,
    }
    put_item(item)

    # --- Upsert session ---
    upsert_session(student_id)

    return {
        "statusCode": 200,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps({"material_id": material_id, "status": "ok"}),
    }
