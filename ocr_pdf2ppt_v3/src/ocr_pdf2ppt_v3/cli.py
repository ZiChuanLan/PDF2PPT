from __future__ import annotations

import argparse
from pathlib import Path

from .config import get_settings
from .pipeline import convert_pdf_to_ppt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OCR PDF to editable PPT (V3)")
    parser.add_argument("--input", required=True, help="Input PDF path")
    parser.add_argument("--output", required=True, help="Output PPTX path")
    parser.add_argument("--api-key", default=None, help="SiliconFlow API key")
    parser.add_argument("--base-url", default=None, help="SiliconFlow base URL")
    parser.add_argument("--model", default=None, help="SiliconFlow model")
    parser.add_argument(
        "--ocr-backend",
        default="auto",
        choices=["auto", "openai_chat", "paddle_doc_parser"],
        help="OCR backend: auto-detect by model, or force a backend",
    )
    parser.add_argument("--render-dpi", type=int, default=220)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--work-dir", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()

    api_key = args.api_key or settings.siliconflow_api_key
    if not api_key:
        raise SystemExit("Missing API key: use --api-key or set SILICONFLOW_API_KEY")

    result = convert_pdf_to_ppt(
        input_pdf=Path(args.input),
        output_pptx=Path(args.output),
        api_key=api_key,
        base_url=args.base_url or settings.siliconflow_base_url,
        model=args.model or settings.siliconflow_model,
        ocr_backend=args.ocr_backend or settings.siliconflow_ocr_backend,
        render_dpi=args.render_dpi,
        max_pages=args.max_pages,
        work_dir=Path(args.work_dir) if args.work_dir else None,
    )
    print(
        "done:",
        result.output_pptx,
        f"pages={result.pages}",
        f"fallback_pages={result.fallback_pages}",
        f"empty_pages={result.empty_pages}",
        f"debug={result.debug_json}",
    )


if __name__ == "__main__":
    main()
