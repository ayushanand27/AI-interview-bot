"""Custom HTTP exceptions for consistent API error responses."""

from fastapi import HTTPException, status


class SessionNotFoundError(HTTPException):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Interview session '{session_id}' not found.",
        )


class InvalidSessionStateError(HTTPException):
    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )


class QuestionsNotGeneratedError(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Questions have not been generated for this session yet.",
        )
