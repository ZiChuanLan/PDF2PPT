from __future__ import annotations

import sys
from pathlib import Path


def _add_path(path: Path) -> None:
    if not path.exists():
        return
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


_REPO_ROOT = Path(__file__).resolve().parent

# Make workspace packages importable when running `pytest` from repo root.
_add_path(_REPO_ROOT / "api")
_add_path(_REPO_ROOT / "ocr_pdf2ppt_v2" / "src")
_add_path(_REPO_ROOT / "ocr_pdf2ppt_v3" / "src")

