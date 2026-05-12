"""Shared utilities for mineru/baidu adapter modules.

Contains helper functions that were duplicated between mineru_adapter.py and
baidu_doc_adapter.py, extracted for DRY maintenance.
"""

from __future__ import annotations

from typing import Any


_IMAGE_KIND_TOKENS = (
    "image",
    "img",
    "figure",
    "picture",
    "photo",
    "chart",
    "graphic",
    "illustration",
    "screenshot",
    "logo",
    "seal",
)


def _is_image_like_kind(kind: str, *, tokens: tuple[str, ...] | None = None) -> bool:
    """Return True if *kind* looks like an image type.

    Matches any token in ``_IMAGE_KIND_TOKENS`` (or *tokens* if supplied)
    as a case-insensitive substring of *kind*.
    """
    if not kind:
        return False
    lowered = kind.lower()
    match_tokens: tuple[str, ...] = tokens if tokens is not None else _IMAGE_KIND_TOKENS
    return any(token in lowered for token in match_tokens)
