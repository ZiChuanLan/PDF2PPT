from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from .geometry import normalize_bbox_to_px, parse_bbox_candidate
from .models import OcrLine, PageRender, VisualRegion

_PRIMARY_SYSTEM_PROMPT = (
    "You are a strict OCR extraction engine for document-to-slide reconstruction. "
    "Output only JSON (no markdown). Return an object: "
    "{\"lines\": [{\"text\": string, \"bbox\": [x0,y0,x1,y1], \"confidence\": number}]}. "
    "Do not merge distant regions. Keep each text line local and compact. "
    "bbox must tightly wrap text and stay in image pixel coordinates."
)

_PRIMARY_USER_PROMPT = (
    "Extract visible textual lines from this slide page image. "
    "Rules: 1) Keep reading order top-to-bottom then left-to-right; "
    "2) Use one bbox per local text line (never span multiple blocks/cards); "
    "3) Ignore decorative icons/background graphics; "
    "4) If uncertain, output fewer but precise lines; "
    "5) If no text, return {\"lines\": []}."
)

_RETRY_SYSTEM_PROMPT = (
    "You are an OCR rescue pass. Output only JSON object {\"lines\": [...]} with local tight bboxes. "
    "Prefer precision over recall. Never output a bbox that spans multiple visual blocks."
)

_RETRY_USER_PROMPT = (
    "Second-pass OCR for editable PPT reconstruction. "
    "Return only reliable text lines with compact local boxes. "
    "Discard noisy mixed gibberish and decorative text-like patterns. "
    "If unsure, skip it. If no reliable text, return {\"lines\": []}."
)

_LAYOUT_SYSTEM_PROMPT = (
    "You are a slide layout detector. Output only JSON object: "
    "{\"image_regions\": [{\"bbox\": [x0,y0,x1,y1], \"label\": string, \"confidence\": number}]}. "
    "Detect non-text visual regions such as photos, charts, logos, screenshots, and icon groups. "
    "Do not output plain background panels. Keep bboxes compact and non-overlapping when possible."
)

_LAYOUT_USER_PROMPT = (
    "Detect image-like visual regions for this slide page. "
    "Return only regions that should become editable image objects in PPT."
)


class SiliconFlowOcrClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        max_image_side_px: int = 2200,
        request_timeout_seconds: float = 60.0,
    ):
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:
            raise RuntimeError("Missing dependency: install package 'openai'") from exc

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_image_side_px = max(512, int(max_image_side_px))
        self._request_timeout_seconds = max(5.0, float(request_timeout_seconds))

    @staticmethod
    def _extract_text_candidate(item: dict[str, Any]) -> str:
        for key in ("text", "content", "transcription", "value", "label"):
            value = item.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text
        return ""

    @staticmethod
    def _parse_json_payload(content: str) -> list[dict[str, Any]]:
        text = (content or "").strip()
        if not text:
            return []

        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None

        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]

        if isinstance(parsed, dict):
            for key in (
                "lines",
                "items",
                "results",
                "data",
                "blocks",
                "ocr_results",
                "detections",
                "words",
                "tokens",
            ):
                value = parsed.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                obj = json.loads(match.group(0))
                if isinstance(obj, dict):
                    for key in (
                        "lines",
                        "items",
                        "results",
                        "data",
                        "blocks",
                        "ocr_results",
                        "detections",
                        "words",
                        "tokens",
                    ):
                        value = obj.get(key)
                        if isinstance(value, list):
                            return [item for item in value if isinstance(item, dict)]
            except Exception:
                pass

        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                arr = json.loads(match.group(0))
                if isinstance(arr, list):
                    return [item for item in arr if isinstance(item, dict)]
            except Exception:
                pass

        return []

    @staticmethod
    def _parse_json_object(content: str) -> dict[str, Any]:
        text = (content or "").strip()
        if not text:
            return {}

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1).strip())
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return {}

    def _prepare_data_url(self, image_path: Path) -> tuple[str, float, float, int, int]:
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
        return data_url, scale_x, scale_y, req_w, req_h

    def _normalize_bbox(
        self,
        *,
        raw_bbox: Any,
        page: PageRender,
        scale_x: float,
        scale_y: float,
        req_w: int,
        req_h: int,
    ) -> list[float] | None:
        parsed_bbox = parse_bbox_candidate(raw_bbox)
        if parsed_bbox is None:
            return None

        x0, y0, x1, y1 = parsed_bbox
        raw_coord_max = max(abs(x0), abs(y0), abs(x1), abs(y1))
        request_side = float(max(req_w, req_h))
        prefer_raw = raw_coord_max > (request_side * 1.2)

        scaled_bbox = normalize_bbox_to_px(
            x0=x0 * scale_x,
            y0=y0 * scale_y,
            x1=x1 * scale_x,
            y1=y1 * scale_y,
            width=page.width_px,
            height=page.height_px,
        )
        raw_bbox_px = normalize_bbox_to_px(
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            width=page.width_px,
            height=page.height_px,
        )

        bbox = raw_bbox_px if prefer_raw else scaled_bbox
        if bbox is None:
            bbox = scaled_bbox or raw_bbox_px
        return bbox

    def _normalize_ai_line(
        self,
        *,
        item: dict[str, Any],
        page: PageRender,
        scale_x: float,
        scale_y: float,
        req_w: int,
        req_h: int,
        source: Literal["ai_primary", "ai_retry"],
    ) -> OcrLine | None:
        text = self._extract_text_candidate(item)
        if not text:
            return None

        bbox = self._normalize_bbox(
            raw_bbox=item.get("bbox")
            or item.get("box")
            or item.get("rect")
            or item.get("position")
            or item.get("points"),
            page=page,
            scale_x=scale_x,
            scale_y=scale_y,
            req_w=req_w,
            req_h=req_h,
        )
        if bbox is None:
            return None

        confidence_raw = item.get("confidence")
        if confidence_raw is None:
            for key in ("score", "prob", "probability", "conf"):
                if item.get(key) is not None:
                    confidence_raw = item.get(key)
                    break

        confidence: float | None = None
        if confidence_raw is not None:
            try:
                confidence = float(confidence_raw)
                if confidence > 1.0 and confidence <= 100.0:
                    confidence = confidence / 100.0
                confidence = max(0.0, min(1.0, confidence))
            except Exception:
                confidence = None

        return OcrLine(text=text, bbox=bbox, confidence=confidence, source=source)

    def _normalize_visual_region(
        self,
        *,
        item: dict[str, Any],
        page: PageRender,
        scale_x: float,
        scale_y: float,
        req_w: int,
        req_h: int,
    ) -> VisualRegion | None:
        bbox = self._normalize_bbox(
            raw_bbox=item.get("bbox")
            or item.get("box")
            or item.get("rect")
            or item.get("position")
            or item.get("points"),
            page=page,
            scale_x=scale_x,
            scale_y=scale_y,
            req_w=req_w,
            req_h=req_h,
        )
        if bbox is None:
            return None

        confidence_raw = item.get("confidence")
        if confidence_raw is None:
            for key in ("score", "prob", "probability", "conf"):
                if item.get(key) is not None:
                    confidence_raw = item.get(key)
                    break

        confidence: float | None = None
        if confidence_raw is not None:
            try:
                confidence = float(confidence_raw)
                if confidence > 1.0 and confidence <= 100.0:
                    confidence = confidence / 100.0
                confidence = max(0.0, min(1.0, confidence))
            except Exception:
                confidence = None

        label_raw = item.get("label") or item.get("type") or item.get("class") or item.get("name")
        label = str(label_raw).strip() if label_raw is not None else None
        if label == "":
            label = None

        return VisualRegion(bbox=bbox, label=label, confidence=confidence, source="ai_layout")

    def ocr_page(
        self,
        page: PageRender,
        *,
        pass_mode: Literal["primary", "retry"] = "primary",
    ) -> list[OcrLine]:
        image_path = Path(page.image_path)
        data_url, scale_x, scale_y, req_w, req_h = self._prepare_data_url(image_path)

        if pass_mode == "retry":
            system_prompt = _RETRY_SYSTEM_PROMPT
            user_prompt = _RETRY_USER_PROMPT
            source = "ai_retry"
        else:
            system_prompt = _PRIMARY_SYSTEM_PROMPT
            user_prompt = _PRIMARY_USER_PROMPT
            source = "ai_primary"

        content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]

        response = self._client.with_options(
            timeout=self._request_timeout_seconds
        ).chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
        )

        raw = ""
        if response.choices:
            raw = response.choices[0].message.content or ""

        items = self._parse_json_payload(raw)
        lines: list[OcrLine] = []
        for item in items:
            normalized = self._normalize_ai_line(
                item=item,
                page=page,
                scale_x=scale_x,
                scale_y=scale_y,
                req_w=req_w,
                req_h=req_h,
                source=source,
            )
            if normalized is None:
                continue
            lines.append(normalized)

        lines.sort(key=lambda item: (float(item.bbox[1]), float(item.bbox[0])))
        return lines

    def detect_layout_regions(self, page: PageRender) -> list[VisualRegion]:
        image_path = Path(page.image_path)
        data_url, scale_x, scale_y, req_w, req_h = self._prepare_data_url(image_path)

        response = self._client.with_options(
            timeout=self._request_timeout_seconds
        ).chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": _LAYOUT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _LAYOUT_USER_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )

        raw = ""
        if response.choices:
            raw = response.choices[0].message.content or ""

        obj = self._parse_json_object(raw)
        region_items: list[dict[str, Any]] = []
        for key in ("image_regions", "images", "figures", "visual_regions", "regions"):
            value = obj.get(key)
            if isinstance(value, list):
                region_items = [item for item in value if isinstance(item, dict)]
                if region_items:
                    break

        regions: list[VisualRegion] = []
        for item in region_items:
            normalized = self._normalize_visual_region(
                item=item,
                page=page,
                scale_x=scale_x,
                scale_y=scale_y,
                req_w=req_w,
                req_h=req_h,
            )
            if normalized is None:
                continue
            regions.append(normalized)

        regions.sort(key=lambda item: (float(item.bbox[1]), float(item.bbox[0])))
        return regions
