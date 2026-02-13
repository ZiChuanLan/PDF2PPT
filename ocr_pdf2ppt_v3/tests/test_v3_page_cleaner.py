from pathlib import Path

from PIL import Image, ImageDraw

from ocr_pdf2ppt_v3.models import OcrLine
from ocr_pdf2ppt_v3.page_cleaner import erase_text_regions


def test_erase_text_regions_outputs_file(tmp_path: Path) -> None:
    image_path = tmp_path / "in.png"
    out_path = tmp_path / "out.png"

    image = Image.new("RGB", (200, 120), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((20, 40), "HELLO", fill=(0, 0, 0))
    image.save(image_path)

    lines = [OcrLine(text="HELLO", bbox=[15, 35, 110, 65], confidence=0.99)]
    result = erase_text_regions(image_path, lines, out_path)

    assert result.exists()
    assert result.stat().st_size > 0
