# pyright: reportMissingImports=false

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.convert.pptx import scanned_page


class _PixStub:
    def __init__(self, image: Image.Image) -> None:
        rgb = image.convert("RGB")
        self.width, self.height = rgb.size
        self.n = 3
        self.samples = rgb.tobytes()


def test_erase_regions_fill_uses_polygon_mask_when_available(tmp_path) -> None:
    render_path = tmp_path / "render.png"
    out_path = tmp_path / "render.clean.png"

    image = Image.new("RGB", (120, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, 100, 100], fill=(180, 180, 180))
    draw.polygon([(60, 20), (100, 60), (60, 100), (20, 60)], fill=(0, 0, 0))
    image.save(render_path)

    result_path = scanned_page._erase_regions_in_render_image(
        render_path,
        out_path=out_path,
        erase_bboxes_pt=[[20.0, 20.0, 100.0, 100.0]],
        erase_polygons_pt=[
            [[60.0, 20.0], [100.0, 60.0], [60.0, 100.0], [20.0, 60.0]]
        ],
        page_height_pt=120.0,
        dpi=72,
        text_erase_mode="fill",
    )

    assert result_path == out_path
    cleaned = Image.open(result_path).convert("RGB")
    center = cleaned.getpixel((60, 60))
    corner = cleaned.getpixel((24, 24))

    assert min(center) >= 230
    assert 150 <= corner[0] <= 210
    assert abs(int(corner[0]) - int(corner[1])) <= 5
    assert abs(int(corner[1]) - int(corner[2])) <= 5


def test_erase_regions_fill_keeps_protected_pixels(tmp_path) -> None:
    render_path = tmp_path / "render.protect.png"
    out_path = tmp_path / "render.protect.clean.png"

    image = Image.new("RGB", (120, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, 100, 100], fill=(180, 180, 180))
    draw.rectangle([20, 48, 100, 72], fill=(0, 0, 0))
    image.save(render_path)

    result_path = scanned_page._erase_regions_in_render_image(
        render_path,
        out_path=out_path,
        erase_bboxes_pt=[[20.0, 48.0, 100.0, 72.0]],
        protect_bboxes_pt=[[60.0, 20.0, 100.0, 100.0]],
        page_height_pt=120.0,
        dpi=72,
        text_erase_mode="fill",
    )

    assert result_path == out_path
    cleaned = Image.open(result_path).convert("RGB")
    erased_left = cleaned.getpixel((36, 60))
    protected_right = cleaned.getpixel((84, 60))

    assert min(erased_left) >= 150
    assert max(protected_right) <= 40


def test_clear_regions_for_transparent_crops_uses_polygon_mask_when_available(
    tmp_path,
) -> None:
    render_path = tmp_path / "render.png"
    out_path = tmp_path / "render.clear.png"

    image = Image.new("RGB", (120, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, 100, 100], fill=(180, 180, 180))
    draw.polygon([(60, 20), (100, 60), (60, 100), (20, 60)], fill=(0, 0, 0))
    image.save(render_path)

    result_path = scanned_page._clear_regions_for_transparent_crops(
        cleaned_render_path=render_path,
        out_path=out_path,
        regions_pt=[[20.0, 20.0, 100.0, 100.0]],
        regions_polygons_pt=[
            [[60.0, 20.0], [100.0, 60.0], [60.0, 100.0], [20.0, 60.0]]
        ],
        pix=_PixStub(image),
        page_height_pt=120.0,
        dpi=72,
    )

    assert result_path == out_path
    cleared = Image.open(result_path).convert("RGB")
    center = cleared.getpixel((60, 60))
    corner = cleared.getpixel((24, 24))

    assert min(center) >= 230
    assert 150 <= corner[0] <= 210
    assert abs(int(corner[0]) - int(corner[1])) <= 5
    assert abs(int(corner[1]) - int(corner[2])) <= 5


def test_build_scanned_image_region_infos_preserves_polygon_masked_crop(
    tmp_path,
) -> None:
    render_path = tmp_path / "render.png"
    image = Image.new("RGB", (120, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([20, 20, 100, 100], fill=(180, 180, 180))
    draw.polygon([(60, 20), (100, 60), (60, 100), (20, 60)], fill=(0, 0, 0))
    image.save(render_path)

    infos = scanned_page._build_scanned_image_region_infos(
        page={
            "image_regions": [
                {
                    "bbox_pt": [20.0, 20.0, 100.0, 100.0],
                    "geometry_kind": "polygon",
                    "geometry_points_pt": [
                        [60.0, 20.0],
                        [100.0, 60.0],
                        [60.0, 100.0],
                        [20.0, 60.0],
                    ],
                }
            ]
        },
        render_path=render_path,
        artifacts_dir=tmp_path / "artifacts",
        page_index=0,
        page_w_pt=120.0,
        page_h_pt=120.0,
        scanned_render_dpi=72,
        baseline_ocr_h_pt=12.0,
        ocr_text_elements=[],
        has_full_page_bg_image=False,
        text_coverage_ratio_fn=lambda _bbox: (0.0, 0),
        text_inside_counts_fn=lambda _bbox: (0, 0),
    )

    assert len(infos) == 1
    assert infos[0].geometry_kind == "polygon"
    assert infos[0].geometry_points_pt == [
        [60.0, 20.0],
        [100.0, 60.0],
        [60.0, 100.0],
        [20.0, 60.0],
    ]

    crop = Image.open(infos[0].crop_path).convert("RGBA")
    assert crop.getpixel((4, 4))[3] == 0
    assert crop.getpixel((40, 40))[3] == 255


def test_small_text_fragment_region_rejects_small_same_line_crop() -> None:
    assert scanned_page._is_small_text_fragment_region(
        [66.24, 296.64, 190.08, 397.44],
        page_w_pt=1366.08,
        page_h_pt=768.0,
        baseline_ocr_h_pt=34.55,
        ocr_text_elements=[
            {
                "text": "模型(思想引擎)",
                "bbox_pt": [168.81, 368.52, 319.97, 401.63],
            }
        ],
    )


def test_small_text_fragment_region_keeps_large_diagram_region() -> None:
    assert not scanned_page._is_small_text_fragment_region(
        [581.76, 129.6, 1330.56, 705.6],
        page_w_pt=1366.08,
        page_h_pt=768.0,
        baseline_ocr_h_pt=34.55,
        ocr_text_elements=[
            {
                "text": "短期记忆(上下文)",
                "bbox_pt": [788.96, 151.15, 919.97, 166.99],
            },
            {
                "text": "Planning",
                "bbox_pt": [1030.0, 330.0, 1120.0, 390.0],
            },
        ],
    )


def test_apply_max_filter_l_matches_pil_max_filter() -> None:
    image = Image.new("L", (9, 9), 0)
    for x, y, value in (
        (0, 0, 12),
        (2, 2, 160),
        (4, 1, 200),
        (6, 6, 80),
        (8, 8, 255),
    ):
        image.putpixel((x, y), value)

    expected = image.filter(ImageFilter.MaxFilter(5))
    actual = scanned_page._apply_max_filter_l(image, size=5)

    assert list(actual.getdata()) == list(expected.getdata())


def test_save_scanned_regions_debug_overlay_writes_regions_json_only(tmp_path) -> None:
    render_path = tmp_path / "render.png"
    Image.new("RGB", (120, 120), "white").save(render_path)

    scanned_page._save_scanned_regions_debug_overlay(
        render_path=render_path,
        regions_pt=[[20.0, 20.0, 100.0, 100.0]],
        artifacts_dir=tmp_path / "artifacts",
        page_index=0,
        page_h_pt=120.0,
        scanned_render_dpi=72,
    )

    json_path = tmp_path / "artifacts" / "image_regions" / "page-0000.regions.json"
    png_path = tmp_path / "artifacts" / "image_regions" / "page-0000.regions.png"

    assert json_path.exists()
    assert not png_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["page_index"] == 0
    assert payload["regions_pt"] == [[20.0, 20.0, 100.0, 100.0]]
