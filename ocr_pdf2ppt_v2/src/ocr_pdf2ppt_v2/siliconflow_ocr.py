from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path
from typing import Any

from PIL import Image

from .models import OcrLine, PageRender

_SYSTEM_PROMPT = (
    "You are a high-precision OCR extractor. "
    "Return ONLY JSON array. "
    "Each item: {\"text\": string, \"bbox\": [x0,y0,x1,y1], \"confidence\": number}. "
    "bbox must be in pixel coordinates of the provided image. "
    "No markdown, no explanations."
)

_USER_PROMPT = (
    "Extract visible text lines from this page image. "
    "Keep original reading order. "
    "If no text, return [] exactly."
)


class SiliconFlowOcrClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_image_side_px: int = 2200,
    ):
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:
            raise RuntimeError("Missing dependency: install package 'openai'") from exc

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_image_side_px = max(512, int(max_image_side_px))

    def _extract_json_array(self, content: str) -> list[dict[str, Any]]:
        content = (content or "").strip()
        if not content:
            return []
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            if isinstance(parsed, dict):
                for key in ("items", "lines", "results", "data"):
                    value = parsed.get(key)
                    if isinstance(value, list):
                        return [item for item in value if isinstance(item, dict)]
        except Exception:
            pass

        match = re.search(r"\[[\s\S]*\]", content)
        if not match:
            return []
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]

    def _prepare_data_url(self, image_path: Path) -> tuple[str, float, float]:
        image = Image.open(image_path).convert("RGB")
        orig_w, orig_h = image.size

        max_side = max(orig_w, orig_h)
        req_w = orig_w
        req_h = orig_h
        if max_side > self._max_image_side_px:
            ratio = float(self._max_image_side_px) / float(max_side)
            req_w = max(32, int(round(orig_w * ratio)))
            req_h = max(32, int(round(orig_h * ratio)))
            image = image.resize((req_w, req_h), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        payload = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_url = f"data:image/png;base64,{payload}"

        scale_x = float(orig_w) / float(req_w)
        scale_y = float(orig_h) / float(req_h)
        return data_url, scale_x, scale_y

    def ocr_page(self, page: PageRender) -> list[OcrLine]:
        image_path = Path(page.image_path)
        data_url, scale_x, scale_y = self._prepare_data_url(image_path)

        content = [
            {"type": "text", "text": _USER_PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]

        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        )

        raw = ""
        if response.choices:
            raw = response.choices[0].message.content or ""

        items = self._extract_json_array(raw)
        lines: list[OcrLine] = []
        for item in items:
            text = str(item.get("text") or "").strip()
            bbox = item.get("bbox")
            if not text or not isinstance(bbox, list) or len(bbox) != 4:
                continue
            try:
                x0, y0, x1, y1 = [float(v) for v in bbox]
            except Exception:
                continue
            mapped_bbox = [x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y]

            conf_raw = item.get("confidence")
            confidence: float | None = None
            if conf_raw is not None:
                try:
                    confidence = float(conf_raw)
                    if confidence > 1.0 and confidence <= 100.0:
                        confidence = confidence / 100.0
                    confidence = max(0.0, min(1.0, confidence))
                except Exception:
                    confidence = None

            lines.append(OcrLine(text=text, bbox=mapped_bbox, confidence=confidence))
        return lines
