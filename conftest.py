"""Root pytest configuration: Hypothesis profile and moto fixtures."""
import os
import pytest
import boto3
from moto import mock_aws
from hypothesis import settings, HealthCheck

# ---------------------------------------------------------------------------
# Hypothesis profile
# ---------------------------------------------------------------------------
settings.register_profile(
    "ci",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci")

# ---------------------------------------------------------------------------
# Environment defaults (must be set before any shared module is imported
# inside a test so that boto3 clients pick up the right table/bucket names)
# ---------------------------------------------------------------------------
os.environ.setdefault("TABLE_NAME", "study-assistant")
os.environ.setdefault("BUCKET_NAME", "study-assistant-materials")
os.environ.setdefault("BEDROCK_MODEL_ID", "amazon.titan-text-express-v1")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")


# ---------------------------------------------------------------------------
# moto DynamoDB fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def dynamodb_table():
    """Spin up a moto-mocked DynamoDB table named 'study-assistant'."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
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
        yield boto3.resource("dynamodb", region_name="us-east-1").Table("study-assistant")


# ---------------------------------------------------------------------------
# moto S3 fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def s3_bucket():
    """Spin up a moto-mocked S3 bucket named 'study-assistant-materials'."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="study-assistant-materials")
        yield boto3.resource("s3", region_name="us-east-1").Bucket("study-assistant-materials")


# ---------------------------------------------------------------------------
# Combined fixture (DynamoDB + S3 in the same moto context)
# ---------------------------------------------------------------------------
@pytest.fixture
def aws_services():
    """Provide both DynamoDB table and S3 bucket inside a single moto context."""
    with mock_aws():
        # DynamoDB
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
        table = ddb.Table("study-assistant")

        # S3
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="study-assistant-materials")
        bucket = boto3.resource("s3", region_name="us-east-1").Bucket("study-assistant-materials")

        yield {"table": table, "bucket": bucket}
