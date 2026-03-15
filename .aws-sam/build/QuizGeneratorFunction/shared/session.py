"""Session upsert and retrieval logic (create-or-reuse pattern)."""
from datetime import datetime, timezone

from shared.db import get_item, put_item, query_by_pk


def _session_pk(student_id: str) -> str:
    return f"SESSION#{student_id}"


def upsert_session(student_id: str) -> dict:
    """Create a session METADATA record if one does not already exist.

    Implements the idempotent create-or-reuse pattern (Requirements 7.1, 7.2):
    - If a METADATA record already exists it is returned unchanged.
    - If no record exists a new one is created and returned.
    """
    pk = _session_pk(student_id)
    sk = "METADATA"

    existing = get_item(pk, sk)
    if existing:
        return existing

    now = datetime.now(timezone.utc).isoformat()
    item = {
        "pk": pk,
        "sk": sk,
        "student_id": student_id,
        "created_at": now,
        "updated_at": now,
    }
    put_item(item)
    return item


def get_session(student_id: str) -> dict | None:
    """Return the session METADATA record, or None if it does not exist."""
    return get_item(_session_pk(student_id), "METADATA")


def get_all_session_items(student_id: str) -> list[dict]:
    """Return every DynamoDB item scoped to this student's session."""
    return query_by_pk(_session_pk(student_id))
