from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.worker_helpers import ocr_stage


class _GuardedOcrManager:
    def __init__(self) -> None:
        self.detect_calls = 0

    def detect_image_regions(self, _image_path: str) -> list[list[float]]:
        self.detect_calls += 1
        return [[10.0, 20.0, 30.0, 40.0]]

    def convert_bbox_to_pdf_coords(
        self,
        *,
        bbox,
        image_width: int,
        image_height: int,
        page_width_pt: float,
        page_height_pt: float,
    ) -> list[float]:
        assert bbox == [10.0, 20.0, 30.0, 40.0]
        assert image_width == 100
        assert image_height == 200
        assert page_width_pt == 720.0
        assert page_height_pt == 1440.0
        return [72.0, 144.0, 216.0, 288.0]


class _PolygonGuardedOcrManager(_GuardedOcrManager):
    def detect_image_regions(self, _image_path: str) -> list[dict[str, object]]:
        self.detect_calls += 1
        return [
            {
                "bbox": [10.0, 20.0, 30.0, 40.0],
                "geometry_kind": "polygon",
                "geometry_source": "polygon_points",
                "geometry_points": [
                    [10.0, 20.0],
                    [30.0, 20.0],
                    [30.0, 40.0],
                    [10.0, 40.0],
                ],
            }
        ]


def test_detect_page_image_regions_skips_when_disabled() -> None:
    manager = _GuardedOcrManager()

    regions, error, skip_reason = ocr_stage._detect_page_image_regions(
        enabled=False,
        image_path=Path("unused.png"),
        ocr_manager=manager,
        page_index=0,
        ocr_image_region_timeout=12,
        page_w_pt=720.0,
        page_h_pt=1440.0,
        skip_reason="fast_ppt_generation_mode",
    )

    assert regions == []
    assert error is None
    assert skip_reason == "fast_ppt_generation_mode"
    assert manager.detect_calls == 0


def test_detect_page_image_regions_converts_regions_when_enabled(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "page-0000.png"
    Image.new("RGB", (100, 200), color=(255, 255, 255)).save(image_path)
    manager = _GuardedOcrManager()

    regions, error, skip_reason = ocr_stage._detect_page_image_regions(
        enabled=True,
        image_path=image_path,
        ocr_manager=manager,
        page_index=0,
        ocr_image_region_timeout=12,
        page_w_pt=720.0,
        page_h_pt=1440.0,
    )

    assert regions == [[72.0, 144.0, 216.0, 288.0]]
    assert error is None
    assert skip_reason is None
    assert manager.detect_calls == 1


def test_detect_page_image_regions_converts_polygon_regions_when_enabled(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "page-0001.png"
    Image.new("RGB", (100, 200), color=(255, 255, 255)).save(image_path)
    manager = _PolygonGuardedOcrManager()

    regions, error, skip_reason = ocr_stage._detect_page_image_regions(
        enabled=True,
        image_path=image_path,
        ocr_manager=manager,
        page_index=1,
        ocr_image_region_timeout=12,
        page_w_pt=720.0,
        page_h_pt=1440.0,
    )

    assert regions == [
        {
            "bbox_pt": [72.0, 144.0, 216.0, 288.0],
            "geometry_kind": "polygon",
            "geometry_source": "polygon_points",
            "geometry_points_pt": [
                [72.0, 144.0],
                [216.0, 144.0],
                [216.0, 288.0],
                [72.0, 288.0],
            ],
        }
    ]
    assert error is None
    assert skip_reason is None
    assert manager.detect_calls == 1
