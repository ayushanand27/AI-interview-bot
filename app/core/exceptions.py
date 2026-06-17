# app/core/exceptions.py
# ─────────────────────────────────────────────────────────────
# Custom exception classes for the entire application.
# Raised in services/, caught by exception handlers in main.py.
# Never raise raw HTTPException inside services — use these instead.
# ─────────────────────────────────────────────────────────────


class AppException(Exception):
    """
    Base exception for all application errors.
    Every custom exception inherits from this.
    Carries a message, HTTP status code, and optional detail.
    """
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        detail: str | None = None
    ):
        self.message = message          # Short human-readable message
        self.status_code = status_code  # HTTP status code to return
        self.detail = detail            # Optional extra context for debugging
        super().__init__(self.message)


# ── 400 Bad Request ───────────────────────────────────────
class BadRequestException(AppException):
    """
    Raised when the request data is invalid or malformed.
    Example: uploading a non-PDF file as a resume.
    """
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message, status_code=400, detail=detail)


# ── 401 Unauthorized ──────────────────────────────────────
class UnauthorizedException(AppException):
    """
    Raised when a request has no valid authentication token.
    Example: calling /interviews without logging in first.
    """
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, status_code=401)


# ── 403 Forbidden ─────────────────────────────────────────
class ForbiddenException(AppException):
    """
    Raised when a user is authenticated but lacks permission.
    Example: a candidate trying to access recruiter dashboard.
    """
    def __init__(self, message: str = "You do not have permission to perform this action"):
        super().__init__(message, status_code=403)


# ── 404 Not Found ─────────────────────────────────────────
class NotFoundException(AppException):
    """
    Raised when a requested resource doesn't exist in the DB.
    Example: fetching an interview that was deleted.
    """
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


# ── 409 Conflict ──────────────────────────────────────────
class ConflictException(AppException):
    """
    Raised when an action conflicts with existing data.
    Example: registering with an email that already exists.
    """
    def __init__(self, message: str):
        super().__init__(message, status_code=409)


# ── 422 Unprocessable ─────────────────────────────────────
class UnprocessableException(AppException):
    """
    Raised when data is valid format but fails business rules.
    Example: trying to start an interview that already ended.
    """
    def __init__(self, message: str):
        super().__init__(message, status_code=422)


# ── 500 Internal Server Error ─────────────────────────────
class InternalServerException(AppException):
    """
    Raised when something unexpected fails on our side.
    Example: OpenAI API is down, file system write fails.
    """
    def __init__(self, message: str = "Something went wrong. Please try again."):
        super().__init__(message, status_code=500)


# ── AI Specific ───────────────────────────────────────────
class AIException(AppException):
    """
    Raised when an OpenAI API call fails or returns bad output.
    Separate from InternalServerException so we can handle
    AI failures differently — e.g. retry, fallback, or alert.
    """
    def __init__(self, message: str = "AI service failed. Please try again."):
        super().__init__(message, status_code=503)


# ── File Specific ─────────────────────────────────────────
class FileException(AppException):
    """
    Raised when file upload, save, or read operations fail.
    Example: resume file exceeds size limit, wrong format.
    """
    def __init__(self, message: str):
        super().__init__(message, status_code=400)