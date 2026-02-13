"""Dev helper: inspect PPTX text and bounding boxes.

Usage:
  python api/scripts/inspect_pptx.py output.pptx

Prints slide size and each shape's bbox. For text shapes, prints paragraph runs.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path


def _ensure_api_on_path() -> None:
    api_dir = Path(__file__).resolve().parents[1]
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))


def _safe_str(value: object) -> str:
    try:
        return str(value)
    except Exception:
        return "<unprintable>"


def main() -> int:
    _ensure_api_on_path()

    parser = argparse.ArgumentParser(description="Inspect PPTX shapes/text")
    parser.add_argument("pptx_path", help="Path to .pptx file")
    args = parser.parse_args()

    pptx_path = Path(args.pptx_path)
    if not pptx_path.exists():
        print(f"ERROR: file not found: {pptx_path}", file=sys.stderr)
        return 2

    try:
        pptx = importlib.import_module("pptx")
        Presentation = getattr(pptx, "Presentation")
    except Exception as e:
        print(f"ERROR: python-pptx import failed: {e}", file=sys.stderr)
        return 2

    prs = Presentation(str(pptx_path))
    slide_w = int(prs.slide_width)
    slide_h = int(prs.slide_height)
    print(
        f"pptx={pptx_path} slides={len(prs.slides)} slide_width_emu={slide_w} slide_height_emu={slide_h}"
    )

    for si, slide in enumerate(prs.slides):
        print(f"slide={si}")
        for shi, shape in enumerate(slide.shapes):
            left = int(getattr(shape, "left", 0) or 0)
            top = int(getattr(shape, "top", 0) or 0)
            width = int(getattr(shape, "width", 0) or 0)
            height = int(getattr(shape, "height", 0) or 0)

            kind = "shape"
            if getattr(shape, "has_text_frame", False):
                kind = "text"
            elif getattr(shape, "has_table", False):
                kind = "table"
            elif getattr(shape, "shape_type", None) is not None:
                kind = _safe_str(getattr(shape, "shape_type"))

            print(
                f"  shape={shi} kind={kind} left_emu={left} top_emu={top} width_emu={width} height_emu={height}"
            )

            if getattr(shape, "has_text_frame", False):
                tf = shape.text_frame
                for pi, p in enumerate(tf.paragraphs):
                    run_texts: list[str] = []
                    for ri, run in enumerate(p.runs):
                        text = _safe_str(getattr(run, "text", ""))
                        size = getattr(getattr(run, "font", None), "size", None)
                        size_pt = (
                            getattr(size, "pt", None) if size is not None else None
                        )
                        if size_pt is None:
                            run_texts.append(f"run={ri} text={text!r}")
                        else:
                            run_texts.append(
                                f"run={ri} text={text!r} size_pt={float(size_pt):.2f}"
                            )
                    joined = " | ".join(run_texts)
                    if joined:
                        print(f"    p={pi} {joined}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
