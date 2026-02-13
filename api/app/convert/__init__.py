"""Conversion pipeline modules."""

from __future__ import annotations

# Keep package imports lightweight. Some submodules (e.g. PDF parsing) require
# optional native dependencies that may not be present in minimal environments.
try:
    from .pdf_parser import parse_pdf_to_ir
except Exception:  # pragma: no cover
    parse_pdf_to_ir = None  # type: ignore[assignment]

__all__ = ["parse_pdf_to_ir"]
