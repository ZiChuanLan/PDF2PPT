from ocr_pdf2ppt_v3.models import OcrLine
from ocr_pdf2ppt_v3.quality_gate import assess_quality, sanitize_lines


def test_sanitize_removes_suspicious_wide_line() -> None:
    lines = [
        OcrLine(text="正常标题", bbox=[100, 100, 400, 160], confidence=0.95, source="ai_primary"),
        OcrLine(
            text="大脑(TheBrain):aonwe=<(",
            bbox=[50, 300, 1900, 420],
            confidence=0.6,
            source="ai_primary",
        ),
    ]

    cleaned = sanitize_lines(lines=lines, width=2000, height=1200, source="ai_primary")
    texts = [line.text for line in cleaned]
    assert "正常标题" in texts
    assert "大脑(TheBrain):aonwe=<(" not in texts


def test_assess_quality_detects_empty() -> None:
    fallback, reason, stats = assess_quality(lines=[], width=1000, height=1000)
    assert fallback is True
    assert reason == "empty"
    assert stats.total == 0
