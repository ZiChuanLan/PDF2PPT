from __future__ import annotations

import sys
from pathlib import Path


_API_DIR = Path(__file__).resolve().parents[1]
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))


from app.convert.ocr import _coerce_bbox_xyxy  # noqa: E402


class _ArrayLike:
    def __init__(self, value):
        self._value = value

    def tolist(self):
        return self._value


def test_coerce_bbox_accepts_tolist_objects() -> None:
    raw = _ArrayLike([[10, 20], [30, 40], [25, 18], [12, 38]])
    bbox = _coerce_bbox_xyxy(raw)
    assert bbox == [10.0, 18.0, 30.0, 40.0]

