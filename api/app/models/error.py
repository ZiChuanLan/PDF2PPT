"""Error models and exception classes."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class ErrorCode(str, Enum):
    """Standardized error codes."""

    PDF_ENCRYPTED = "pdf_encrypted"
    FILE_TOO_LARGE = "file_too_large"
    TOO_MANY_PAGES = "too_many_pages"
    INVALID_PDF = "invalid_pdf"
    OCR_FAILED = "ocr_failed"
    CONVERSION_FAILED = "conversion_failed"
    JOB_NOT_FOUND = "job_not_found"
    INTERNAL_ERROR = "internal_error"
    VALIDATION_ERROR = "validation_error"
    AUTH_REQUIRED = "auth_required"
    AUTH_FAILED = "auth_failed"
    QUOTA_EXCEEDED = "quota_exceeded"
    FORBIDDEN = "forbidden"


class ErrorResponse(BaseModel):
    """Structured error response model."""

    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class AppException(Exception):
    """Application-specific exception with structured error info."""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        details: Optional[dict[str, Any]] = None,
        status_code: int = 400,
    ):
        self.code = code.value if isinstance(code, ErrorCode) else code
        self.message = message
        self.details = details
        self.status_code = status_code
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        """Convert to ErrorResponse model."""
        return ErrorResponse(
            code=self.code,
            message=self.message,
            details=self.details,
        )
