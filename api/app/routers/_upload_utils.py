# pyright: reportMissingImports=false

"""Upload file processing utilities for job creation."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from ..models.error import AppException, ErrorCode

_SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
_SUPPORTED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
_DEFAULT_UPLOAD_IMAGE_DPI = 144.0


def normalize_upload_content_type(value: str | None) -> str:
    return str(value or "").split(";", 1)[0].strip().lower()


def classify_upload_kind(*, filename: str, content_type: str | None) -> str | None:
    suffix = Path(filename or "").suffix.lower()
    normalized_content_type = normalize_upload_content_type(content_type)
    if normalized_content_type in _SUPPORTED_IMAGE_MIME_TYPES:
        return "image"
    if normalized_content_type == "application/pdf":
        return "pdf"
    if suffix in _SUPPORTED_IMAGE_EXTENSIONS:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    return None


def resolve_upload_image_dpi(image: Image.Image) -> tuple[float, float]:
    raw_dpi = image.info.get("dpi")

    def _normalize_axis(value: Any) -> float | None:
        try:
            numeric = float(value)
        except Exception:
            return None
        if not (36.0 <= numeric <= 1200.0):
            return None
        return numeric

    if isinstance(raw_dpi, (tuple, list)):
        x = _normalize_axis(raw_dpi[0] if len(raw_dpi) >= 1 else None)
        y = _normalize_axis(raw_dpi[1] if len(raw_dpi) >= 2 else None)
    else:
        x = _normalize_axis(raw_dpi)
        y = x

    resolved_x = x or _DEFAULT_UPLOAD_IMAGE_DPI
    resolved_y = y or resolved_x or _DEFAULT_UPLOAD_IMAGE_DPI
    return resolved_x, resolved_y


def flatten_upload_image(image: Image.Image) -> Image.Image:
    normalized = ImageOps.exif_transpose(image)
    has_alpha = "A" in normalized.getbands()
    has_palette_transparency = normalized.info.get("transparency") is not None
    if has_alpha or has_palette_transparency:
        rgba = normalized.convert("RGBA")
        flattened = Image.new("RGB", rgba.size, (255, 255, 255))
        flattened.paste(rgba, mask=rgba.getchannel("A"))
        rgba.close()
        if normalized is not image:
            normalized.close()
        return flattened

    converted = normalized.convert("RGB")
    if normalized is not image:
        normalized.close()
    return converted


def write_upload_as_input_pdf(
    *,
    filename: str,
    content_type: str | None,
    content: bytes | None,
    output_path: Path,
) -> str:
    upload_kind = classify_upload_kind(
        filename=filename,
        content_type=content_type,
    )
    if upload_kind == "pdf":
        if content is not None:
            output_path.write_bytes(content)
        # If content is None, file was already written via streaming
        return upload_kind
    if upload_kind != "image":
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Only PDF, PNG, JPG, JPEG, and WEBP files are supported",
            details={
                "filename": filename,
                "content_type": normalize_upload_content_type(content_type),
            },
        )

    # For images, we need to read the content if not provided
    if content is None:
        content = output_path.read_bytes()

    try:
        source_image = Image.open(io.BytesIO(content))
        source_image.load()
    except UnidentifiedImageError as e:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Uploaded image could not be decoded",
            details={"filename": filename, "error": str(e)},
        ) from e
    except Exception as e:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="Failed to read uploaded image",
            details={"filename": filename, "error": str(e)},
        ) from e

    prepared_image: Image.Image | None = None
    pdf_doc: pymupdf.Document | None = None
    try:
        prepared_image = flatten_upload_image(source_image)
        dpi_x, dpi_y = resolve_upload_image_dpi(source_image)
        page_width_pt = max(1.0, float(prepared_image.width) * 72.0 / float(dpi_x))
        page_height_pt = max(1.0, float(prepared_image.height) * 72.0 / float(dpi_y))

        encoded = io.BytesIO()
        suffix = Path(filename or "").suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            prepared_image.save(encoded, format="JPEG", quality=95, subsampling=0)
        else:
            prepared_image.save(encoded, format="PNG")

        pdf_doc = pymupdf.open()
        page = pdf_doc.new_page(width=page_width_pt, height=page_height_pt)
        page.insert_image(page.rect, stream=encoded.getvalue())
        pdf_doc.save(str(output_path))
        return upload_kind
    finally:
        if pdf_doc is not None:
            pdf_doc.close()
        if prepared_image is not None:
            prepared_image.close()
        source_image.close()
