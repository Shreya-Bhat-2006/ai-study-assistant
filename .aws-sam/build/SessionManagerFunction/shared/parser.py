"""Text extraction and JSON serialization for study materials."""
import json
import io
from typing import Optional


class ExtractionError(Exception):
    """Raised when text extraction from a study material fails."""


class DeserializationError(Exception):
    """Raised when JSON deserialization of a parsed material fails."""


def extract_pdf(file_bytes: bytes, material_id: str, filename: str) -> dict:
    """Extract text from a PDF file using PyMuPDF.

    Returns the canonical parsed schema with sections list.
    Each section has a heading (from block metadata) and text.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ExtractionError(f"PyMuPDF (fitz) is not installed: {e}") from e

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise ExtractionError(f"Failed to open PDF: {e}") from e

    sections = []
    raw_parts = []

    try:
        for page in doc:
            blocks = page.get_text("dict").get("blocks", [])
            for block in blocks:
                if block.get("type") != 0:  # 0 = text block
                    continue
                lines = block.get("lines", [])
                block_text = ""
                for line in lines:
                    for span in line.get("spans", []):
                        block_text += span.get("text", "")
                    block_text += "\n"
                block_text = block_text.strip()
                if not block_text:
                    continue

                # Heuristic: treat short lines (≤80 chars, no period at end) as headings
                first_line = block_text.split("\n")[0].strip()
                is_heading = len(first_line) <= 80 and not first_line.endswith(".")
                heading: Optional[str] = first_line if is_heading and len(block_text.split("\n")) > 1 else None

                sections.append({"heading": heading, "text": block_text})
                raw_parts.append(block_text)
    except Exception as e:
        raise ExtractionError(f"Failed to extract text from PDF: {e}") from e
    finally:
        doc.close()

    if not sections:
        raise ExtractionError("PDF contained no extractable text")

    raw_text = "\n\n".join(raw_parts)
    return {
        "material_id": material_id,
        "filename": filename,
        "sections": sections,
        "raw_text": raw_text,
    }


def extract_text(file_bytes: bytes, material_id: str, filename: str) -> dict:
    """Extract text from a plain-text file (utf-8 decode).

    Returns the canonical parsed schema with a single section (heading=None).
    """
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ExtractionError(f"Failed to decode text file as UTF-8: {e}") from e

    if not text.strip():
        raise ExtractionError("Text file is empty")

    return {
        "material_id": material_id,
        "filename": filename,
        "sections": [{"heading": None, "text": text}],
        "raw_text": text,
    }


def serialize(parsed: dict) -> str:
    """JSON-serialize the parsed material representation."""
    return json.dumps(parsed)


def deserialize(json_str: str) -> dict:
    """Deserialize a JSON string back to the parsed material dict.

    Raises DeserializationError on any failure.
    """
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise DeserializationError(f"Failed to deserialize parsed material: {e}") from e
