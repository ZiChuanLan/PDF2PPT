"""Dev helper: compare IR vs PPTX layout fidelity.

Usage:
  python api/scripts/compare_layout.py --ir /path/to/ir.json --pptx output.pptx

Outputs a JSON report and a top-level `pass` field.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _ensure_api_on_path() -> None:
    api_dir = Path(__file__).resolve().parents[1]
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))


_WS_RE = re.compile(r"\s+")


def _norm_text(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip())


def _coerce_bbox_pt(bbox: Any) -> tuple[float, float, float, float]:
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        x0, y0, x1, y1 = bbox
        x0f, y0f, x1f, y1f = float(x0), float(y0), float(x1), float(y1)
        return (min(x0f, x1f), min(y0f, y1f), max(x0f, x1f), max(y0f, y1f))
    raise ValueError(f"Invalid bbox_pt: {bbox!r}")


def _ir_bbox_norm(
    bbox_pt: Any, *, page_width_pt: float, page_height_pt: float
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = _coerce_bbox_pt(bbox_pt)
    if page_width_pt <= 0 or page_height_pt <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    left = x0 / page_width_pt
    top = (page_height_pt - y1) / page_height_pt
    width = (x1 - x0) / page_width_pt
    height = (y1 - y0) / page_height_pt
    return (left, top, width, height)


def _ppt_bbox_norm(
    *,
    left_emu: int,
    top_emu: int,
    width_emu: int,
    height_emu: int,
    slide_w_emu: int,
    slide_h_emu: int,
) -> tuple[float, float, float, float]:
    if slide_w_emu <= 0 or slide_h_emu <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        left_emu / slide_w_emu,
        top_emu / slide_h_emu,
        width_emu / slide_w_emu,
        height_emu / slide_h_emu,
    )


def _center(b: tuple[float, float, float, float]) -> tuple[float, float]:
    l, t, w, h = b
    return (l + w / 2.0, t + h / 2.0)


@dataclass(frozen=True)
class MatchResult:
    ir_index: int
    ppt_index: int
    text: str
    ir_bbox_norm: tuple[float, float, float, float]
    ppt_bbox_norm: tuple[float, float, float, float]
    center_distance: float
    size_delta_w: float
    size_delta_h: float
    bbox_ok: bool


def main() -> int:
    _ensure_api_on_path()

    parser = argparse.ArgumentParser(description="Compare IR vs PPTX layout")
    parser.add_argument("--ir", required=True, help="Path to IR JSON")
    parser.add_argument("--pptx", required=True, help="Path to PPTX")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    ir_path = Path(args.ir)
    pptx_path = Path(args.pptx)
    if not ir_path.exists():
        print(f"ERROR: IR not found: {ir_path}", file=sys.stderr)
        return 2
    if not pptx_path.exists():
        print(f"ERROR: PPTX not found: {pptx_path}", file=sys.stderr)
        return 2

    try:
        ir = json.loads(ir_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: failed to parse IR JSON: {e}", file=sys.stderr)
        return 2

    try:
        pptx = importlib.import_module("pptx")
        Presentation = getattr(pptx, "Presentation")
    except Exception as e:
        print(f"ERROR: python-pptx import failed: {e}", file=sys.stderr)
        return 2

    prs = Presentation(str(pptx_path))
    slide_w_emu = int(prs.slide_width)
    slide_h_emu = int(prs.slide_height)

    pages = ir.get("pages")
    if not isinstance(pages, list):
        print("ERROR: IR missing pages[]", file=sys.stderr)
        return 2

    # Thresholds from plan.
    match_rate_min = 0.80
    center_dist_max = 0.03
    size_delta_max = 0.20

    total_ir = 0
    total_matched = 0
    all_bbox_ok = True
    page_reports: list[dict[str, Any]] = []

    for page in pages:
        if not isinstance(page, dict):
            continue
        page_index = int(page.get("page_index") or 0)
        page_w_pt = float(page.get("page_width_pt") or 0.0)
        page_h_pt = float(page.get("page_height_pt") or 0.0)

        ir_text_blocks: list[dict[str, Any]] = []
        for el in page.get("elements") or []:
            if not isinstance(el, dict) or el.get("type") != "text":
                continue
            text = _norm_text(str(el.get("text") or ""))
            if not text:
                continue
            ir_text_blocks.append(
                {
                    "text": text,
                    "bbox_norm": _ir_bbox_norm(
                        el.get("bbox_pt"),
                        page_width_pt=page_w_pt,
                        page_height_pt=page_h_pt,
                    ),
                }
            )

        if page_index >= len(prs.slides):
            slide = None
            ppt_text_shapes: list[dict[str, Any]] = []
        else:
            slide = prs.slides[page_index]
            ppt_text_shapes = []
            for shi, shape in enumerate(slide.shapes):
                if not getattr(shape, "has_text_frame", False):
                    continue
                text = _norm_text(getattr(shape, "text", "") or "")
                if not text:
                    continue
                left = int(getattr(shape, "left", 0) or 0)
                top = int(getattr(shape, "top", 0) or 0)
                width = int(getattr(shape, "width", 0) or 0)
                height = int(getattr(shape, "height", 0) or 0)
                ppt_text_shapes.append(
                    {
                        "shape_index": shi,
                        "text": text,
                        "bbox_norm": _ppt_bbox_norm(
                            left_emu=left,
                            top_emu=top,
                            width_emu=width,
                            height_emu=height,
                            slide_w_emu=slide_w_emu,
                            slide_h_emu=slide_h_emu,
                        ),
                    }
                )

        used_ppt: set[int] = set()
        matches: list[MatchResult] = []
        unmatched_ir: list[dict[str, Any]] = []

        for ii, ir_block in enumerate(ir_text_blocks):
            ir_text = ir_block["text"]
            ir_bbox = ir_block["bbox_norm"]
            candidates = [
                s
                for s in ppt_text_shapes
                if s["text"] == ir_text and int(s["shape_index"]) not in used_ppt
            ]
            if not candidates:
                unmatched_ir.append(
                    {"ir_index": ii, "text": ir_text, "bbox_norm": ir_bbox}
                )
                continue

            ir_cx, ir_cy = _center(ir_bbox)
            best = None
            best_dist = 1e9
            for cand in candidates:
                ppt_bbox = cand["bbox_norm"]
                ppt_cx, ppt_cy = _center(ppt_bbox)
                dx = ppt_cx - ir_cx
                dy = ppt_cy - ir_cy
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best = cand

            assert best is not None
            used_ppt.add(int(best["shape_index"]))

            ppt_bbox = best["bbox_norm"]
            _, _, ir_w, ir_h = ir_bbox
            _, _, ppt_w, ppt_h = ppt_bbox
            size_dw = abs(ppt_w - ir_w)
            size_dh = abs(ppt_h - ir_h)
            bbox_ok = (
                best_dist <= center_dist_max
                and size_dw <= size_delta_max
                and size_dh <= size_delta_max
            )

            matches.append(
                MatchResult(
                    ir_index=ii,
                    ppt_index=int(best["shape_index"]),
                    text=ir_text,
                    ir_bbox_norm=ir_bbox,
                    ppt_bbox_norm=ppt_bbox,
                    center_distance=float(best_dist),
                    size_delta_w=float(size_dw),
                    size_delta_h=float(size_dh),
                    bbox_ok=bool(bbox_ok),
                )
            )

        page_total_ir = len(ir_text_blocks)
        page_matched = len(matches)
        total_ir += page_total_ir
        total_matched += page_matched
        if any(not m.bbox_ok for m in matches):
            all_bbox_ok = False

        page_reports.append(
            {
                "page_index": page_index,
                "ir_text_blocks": page_total_ir,
                "ppt_text_shapes": len(ppt_text_shapes),
                "matched": page_matched,
                "match_rate": (page_matched / page_total_ir) if page_total_ir else 1.0,
                "matches": [
                    {
                        "ir_index": m.ir_index,
                        "ppt_shape_index": m.ppt_index,
                        "text": m.text,
                        "ir_bbox_norm": list(m.ir_bbox_norm),
                        "ppt_bbox_norm": list(m.ppt_bbox_norm),
                        "center_distance": m.center_distance,
                        "size_delta": {"w": m.size_delta_w, "h": m.size_delta_h},
                        "bbox_ok": m.bbox_ok,
                    }
                    for m in matches
                ],
                "unmatched_ir": unmatched_ir,
            }
        )

    match_rate = (total_matched / total_ir) if total_ir else 1.0
    passed = bool(match_rate >= match_rate_min and all_bbox_ok)

    report: dict[str, Any] = {
        "pass": passed,
        "match_rate": match_rate,
        "totals": {"ir_text_blocks": total_ir, "matched": total_matched},
        "thresholds": {
            "match_rate_min": match_rate_min,
            "center_distance_max": center_dist_max,
            "size_delta_max": size_delta_max,
        },
        "slide": {"width_emu": slide_w_emu, "height_emu": slide_h_emu},
        "pages": page_reports,
    }

    payload = json.dumps(
        report,
        ensure_ascii=True,
        indent=2 if args.pretty else None,
        sort_keys=False,
    )
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
