"""Standard HTTP error response builder."""
import json


def error_response(status_code: int, error_code: str, message: str) -> dict:
    """Build a standard Lambda proxy error response.

    Returns a dict compatible with API Gateway Lambda proxy integration.
    Body format: { "error": "SHORT_CODE", "message": "..." }
    """
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": error_code, "message": message}),
    }
