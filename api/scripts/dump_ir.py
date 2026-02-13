"""Dev helper: dump PDF IR JSON.

Usage:
  python api/scripts/dump_ir.py fixtures/pdfs/text.pdf -o /tmp/ir.json
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path


def _ensure_api_on_path() -> None:
    api_dir = Path(__file__).resolve().parents[1]
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))


def main() -> int:
    _ensure_api_on_path()

    from app.convert.pdf_parser import parse_pdf_to_ir
    from app.models.error import AppException

    parser = argparse.ArgumentParser(description="Dump PDF IR JSON")
    parser.add_argument("pdf_path", help="Path to input PDF")
    parser.add_argument(
        "--output",
        "-o",
        help="Write IR JSON to this path (default: stdout)",
        default=None,
    )
    parser.add_argument(
        "--artifacts-dir",
        help="Directory to write extracted artifacts (images)",
        default=None,
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    output_path = Path(args.output) if args.output else None

    artifacts_dir = (
        Path(args.artifacts_dir)
        if args.artifacts_dir
        else (
            (output_path.parent / "artifacts")
            if output_path
            else Path(".sisyphus/tmp/dump_ir")
        )
    )
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Some PyMuPDF features (e.g. table detection) can emit advisory messages
        # to stdout. Keep stdout clean so piping to `jq` works.
        with redirect_stdout(sys.stderr):
            ir = parse_pdf_to_ir(pdf_path, artifacts_dir)
    except AppException as e:
        print(f"ERROR: {e.code}: {e.message}", file=sys.stderr)
        if getattr(e, "details", None):
            print(json.dumps(e.details, ensure_ascii=True), file=sys.stderr)
        return 2

    payload = json.dumps(ir, ensure_ascii=True, indent=2)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
