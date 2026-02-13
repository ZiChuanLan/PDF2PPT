from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from .config import get_settings
from .pipeline import convert_pdf_to_ppt

app = FastAPI(title="OCR PDF2PPT V2", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/convert")
async def convert(
    file: UploadFile = File(...),
    api_key: str | None = Form(None),
    base_url: str | None = Form(None),
    model: str | None = Form(None),
    render_dpi: int = Form(220),
    max_pages: int | None = Form(None),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf file is supported")

    settings = get_settings()
    resolved_key = api_key or settings.siliconflow_api_key
    if not resolved_key:
        raise HTTPException(status_code=400, detail="Missing api_key")

    with tempfile.TemporaryDirectory(prefix="ocr-pdf2ppt-v2-") as tmp:
        tmp_dir = Path(tmp)
        input_pdf = tmp_dir / "input.pdf"
        with input_pdf.open("wb") as fp:
            shutil.copyfileobj(file.file, fp)

        output_pptx = tmp_dir / "output.pptx"

        try:
            convert_pdf_to_ppt(
                input_pdf=input_pdf,
                output_pptx=output_pptx,
                api_key=resolved_key,
                base_url=base_url or settings.siliconflow_base_url,
                model=model or settings.siliconflow_model,
                render_dpi=render_dpi,
                max_pages=max_pages,
                work_dir=tmp_dir / "work",
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"convert failed: {exc}") from exc

        body = output_pptx.read_bytes()
        return Response(
            content=body,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": "attachment; filename=output.pptx"},
        )
