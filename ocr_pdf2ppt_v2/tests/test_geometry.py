from ocr_pdf2ppt_v2.geometry import clamp_bbox_px, px_bbox_to_pt_bbox


def test_clamp_bbox_px_basic() -> None:
    bbox = clamp_bbox_px([-5, 3, 120, 101], width=100, height=90)
    assert bbox == [0.0, 3.0, 100.0, 90.0]


def test_clamp_bbox_px_invalid() -> None:
    assert clamp_bbox_px([10, 10, 9, 20], width=100, height=100) is None


def test_px_bbox_to_pt_bbox() -> None:
    out = px_bbox_to_pt_bbox(
        [100, 200, 300, 400],
        image_width_px=1000,
        image_height_px=2000,
        page_width_pt=500,
        page_height_pt=1000,
    )
    assert out == [50.0, 100.0, 150.0, 200.0]
