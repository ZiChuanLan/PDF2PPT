"""PDF utility functions."""

from pathlib import Path

import pymupdf

from app.config import get_settings
from app.models.error import AppException, ErrorCode


def is_pdf_encrypted(file_path: str | Path) -> bool:
    """Check if a PDF file is encrypted/password-protected.

    Args:
        file_path: Path to the PDF file.

    Returns:
        True if the PDF is encrypted, False otherwise.
    """
    try:
        doc = pymupdf.open(str(file_path))
        encrypted = doc.is_encrypted
        doc.close()
        return encrypted
    except Exception:
        # If we can't open it, treat as invalid PDF
        return False


def validate_pdf(file_path: str | Path) -> int:
    """Validate a PDF file and return page count.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Number of pages in the PDF.

    Raises:
        AppException: If the PDF is invalid, encrypted, or exceeds limits.
    """
    settings = get_settings()
    path = Path(file_path)

    # Check file exists
    if not path.exists():
        raise AppException(
            code=ErrorCode.INVALID_PDF,
            message="PDF file not found",
            details={"path": str(path)},
        )

    # Check file size
    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb > settings.max_file_mb:
        raise AppException(
            code=ErrorCode.FILE_TOO_LARGE,
            message=f"File size {file_size_mb:.1f}MB exceeds limit of {settings.max_file_mb}MB",
            details={"size_mb": file_size_mb, "limit_mb": settings.max_file_mb},
        )

    # Try to open the PDF
    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        raise AppException(
            code=ErrorCode.INVALID_PDF,
            message="Unable to open PDF file",
            details={"error": str(e)},
        )

    # Check encryption
    if doc.is_encrypted:
        doc.close()
        raise AppException(
            code=ErrorCode.PDF_ENCRYPTED,
            message="PDF is password-protected",
            details={"encrypted": True},
        )

    # Check page count
    page_count = doc.page_count
    doc.close()

    if page_count > settings.max_pages:
        raise AppException(
            code=ErrorCode.TOO_MANY_PAGES,
            message=f"PDF has {page_count} pages, exceeds limit of {settings.max_pages}",
            details={"pages": page_count, "limit": settings.max_pages},
        )

    return page_count
