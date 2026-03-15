"""Property-based tests for session management (Properties 14 and 15).

# Feature: study-assistant, Property 14: Idempotent Session Creation
# Feature: study-assistant, Property 15: Entity Scoping to Session
"""
import os
import sys

import boto3
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

# Ensure shared/ is importable when running from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from shared.session import upsert_session, get_session
from shared.db import put_item, query_by_pk

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_STUDENT_ID_STRATEGY = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=64,
)


def _setup_table():
    """Create the study-assistant DynamoDB table inside an active moto context."""
    ddb = boto3.resource("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="study-assistant",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


# ---------------------------------------------------------------------------
# Property 14: Idempotent Session Creation
# Validates: Requirements 7.1, 7.2
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(
    student_id=VALID_STUDENT_ID_STRATEGY,
    call_count=st.integers(min_value=1, max_value=10),
)
def test_property_14_idempotent_session_creation(student_id, call_count):
    """Calling upsert_session N times must result in exactly one METADATA record.

    **Validates: Requirements 7.1, 7.2**
    """
    with mock_aws():
        os.environ["TABLE_NAME"] = "study-assistant"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"

        _setup_table()

        for _ in range(call_count):
            upsert_session(student_id)

        pk = f"SESSION#{student_id}"
        items = query_by_pk(pk)
        metadata_items = [i for i in items if i["sk"] == "METADATA"]

        assert len(metadata_items) == 1, (
            f"Expected exactly 1 METADATA record after {call_count} upsert calls "
            f"for student '{student_id}', found {len(metadata_items)}"
        )


# ---------------------------------------------------------------------------
# Property 15: Entity Scoping to Session
# Validates: Requirements 7.3
# ---------------------------------------------------------------------------

_SK_PREFIXES = ["METADATA", "MATERIAL#mat1", "QUIZ#q1", "RESULT#q1",
                "GAP#concept1", "QA#2024-01-01T00:00:00#uuid1",
                "EXPLANATION#2024-01-01T00:00:00#uuid1"]


@settings(max_examples=100)
@given(
    student_id=VALID_STUDENT_ID_STRATEGY,
    sk_prefix=st.sampled_from(_SK_PREFIXES),
)
def test_property_15_entity_scoping_to_session(student_id, sk_prefix):
    """Every entity written via put_item must have pk == SESSION#{student_id}.

    **Validates: Requirements 7.3**
    """
    with mock_aws():
        os.environ["TABLE_NAME"] = "study-assistant"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"

        _setup_table()

        expected_pk = f"SESSION#{student_id}"
        item = {
            "pk": expected_pk,
            "sk": sk_prefix,
            "student_id": student_id,
            "data": "test-value",
        }
        put_item(item)

        items = query_by_pk(expected_pk)
        matching = [i for i in items if i["sk"] == sk_prefix]

        assert len(matching) == 1, (
            f"Expected 1 item with sk='{sk_prefix}' under pk='{expected_pk}', "
            f"found {len(matching)}"
        )
        assert matching[0]["pk"] == expected_pk, (
            f"Item pk '{matching[0]['pk']}' does not equal expected '{expected_pk}'"
        )
