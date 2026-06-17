"""File upload validation helpers."""

from pathlib import Path

from app.core.config import settings
from app.core.exceptions import BadRequestException

PDF_MAGIC = b"%PDF-"

ALLOWED_DOCUMENT_EXTENSIONS = frozenset({".pdf", ".doc", ".docx", ".txt"})

ALLOWED_DOCUMENT_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "application/octet-stream",
        "application/x-pdf",
    }
)

ACCEPTED_FORMATS_MESSAGE = (
    "Upload must be PDF, Word (.doc/.docx), or plain text (.txt)."
)


def document_extension(filename: str) -> str:
    """Return lowercase file extension including the dot."""
    return Path(filename or "").suffix.lower()


def validate_document_upload(
    data: bytes,
    content_type: str | None,
    filename: str,
) -> str:
    """
    Validate resume/JD uploads. Returns the normalized lowercase extension.

    Raises BadRequestException when the file is empty, too large, or unsupported.
    """
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if not data:
        raise BadRequestException("Uploaded file is empty.")
    if len(data) > max_bytes:
        raise BadRequestException(
            f"File exceeds the {settings.MAX_FILE_SIZE_MB} MB limit."
        )

    ext = document_extension(filename)
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise BadRequestException(ACCEPTED_FORMATS_MESSAGE)

    if ext == ".pdf" and not data.startswith(PDF_MAGIC):
        raise BadRequestException(
            "File is not a valid PDF. Please upload a real PDF document."
        )

    if content_type and content_type not in ALLOWED_DOCUMENT_MIME_TYPES:
        raise BadRequestException(
            f"Invalid content type for {ext}. {ACCEPTED_FORMATS_MESSAGE}"
        )

    return ext


def validate_pdf_upload(
    data: bytes,
    content_type: str | None,
    filename: str,
) -> None:
    """Backward-compatible PDF-only validator."""
    ext = validate_document_upload(data, content_type, filename)
    if ext != ".pdf":
        raise BadRequestException(ACCEPTED_FORMATS_MESSAGE)
