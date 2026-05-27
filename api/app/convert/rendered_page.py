"""Zero-copy wrapper around PyMuPDF pixmap for OCR pipeline.

Avoids redundant image I/O by lazily converting between formats:
- PIL Image (for dimension queries and in-memory processing)
- PNG bytes (for API uploads)
- Tempfile path (for OCR providers that require a file path)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class RenderedPage:
    """Lazy wrapper around a PyMuPDF pixmap.

    The pixmap is kept in memory. Format conversions (PIL Image, PNG bytes,
    disk file) are deferred until first access and then cached.
    """

    def __init__(self, pixmap: Any, page_index: int) -> None:
        self._pixmap = pixmap
        self.page_index = page_index
        self.width: int = pixmap.width
        self.height: int = pixmap.height
        self._pil_image: Any | None = None
        self._png_bytes: bytes | None = None
        self._temp_path: Path | None = None

    def as_pil_image(self) -> Any:
        """Return a cached PIL Image (RGB)."""
        if self._pil_image is None:
            from PIL import Image
            # PyMuPDF pixmap → raw RGB bytes → PIL Image (zero extra copy)
            self._pil_image = Image.frombytes(
                "RGB", (self.width, self.height), self._pixmap.samples
            )
        return self._pil_image

    def as_png_bytes(self) -> bytes:
        """Return cached PNG bytes (lazy)."""
        if self._png_bytes is None:
            self._png_bytes = self._pixmap.tobytes("png")
        return self._png_bytes

    def as_tempfile_path(self, directory: Path) -> Path:
        """Write PNG to *directory* once, return the cached path."""
        if self._temp_path is None:
            self._temp_path = directory / f"page-{self.page_index:04d}.png"
            self._temp_path.write_bytes(self.as_png_bytes())
        return self._temp_path

    def save_to(self, path: Path) -> Path:
        """Explicitly save PNG to *path* (not cached)."""
        path.write_bytes(self.as_png_bytes())
        return path
