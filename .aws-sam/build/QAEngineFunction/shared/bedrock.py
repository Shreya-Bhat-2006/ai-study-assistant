"""Bedrock Runtime client wrapper — uses Converse API for Nova models."""
import json
import os
import boto3


def get_client():
    return boto3.client("bedrock-runtime")


def invoke_model(prompt: str) -> str:
    """Invoke the configured Bedrock model with a text prompt.

    Uses the Converse API which works with all Nova models.
    Raises any boto3/Bedrock errors to the caller.
    """
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
    client = get_client()

    response = client.converse(
        modelId=model_id,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 4096, "temperature": 0.7},
    )

    return response["output"]["message"]["content"][0]["text"]
