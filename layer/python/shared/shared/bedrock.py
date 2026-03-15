"""Bedrock Runtime client wrapper."""
import json
import os
import boto3


def get_client():
    """Return a Bedrock Runtime boto3 client."""
    return boto3.client("bedrock-runtime")


def invoke_model(prompt: str) -> str:
    """Invoke the configured Bedrock model with a text prompt.

    Uses the BEDROCK_MODEL_ID environment variable to select the model.
    Returns the raw text response from the model.

    Raises:
        Exception: propagates any boto3 / Bedrock errors to the caller.
    """
    model_id = os.environ.get("BEDROCK_MODEL_ID", "amazon.titan-text-express-v1")
    client = get_client()

    body = json.dumps(
        {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 4096,
                "temperature": 0.7,
            },
        }
    )

    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    response_body = json.loads(response["body"].read())
    return _parse_response(response_body)


def _parse_response(response_body: dict) -> str:
    """Extract the text output from a Bedrock response body.

    Supports Amazon Titan and Anthropic Claude response shapes.
    """
    # Amazon Titan
    if "results" in response_body:
        return response_body["results"][0]["outputText"]
    # Anthropic Claude (messages API)
    if "content" in response_body:
        return response_body["content"][0]["text"]
    # Anthropic Claude (legacy completion API)
    if "completion" in response_body:
        return response_body["completion"]
    raise ValueError(f"Unrecognised Bedrock response shape: {list(response_body.keys())}")
