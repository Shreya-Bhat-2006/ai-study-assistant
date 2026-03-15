"""Standard HTTP error response builder."""
import json

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,student-id,Student-Id,x-student-id,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def error_response(status_code: int, error_code: str, message: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": error_code, "message": message}),
    }
