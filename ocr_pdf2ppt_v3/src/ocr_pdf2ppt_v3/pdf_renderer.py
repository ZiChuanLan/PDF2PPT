from __future__ import annotations

from pathlib import Path

import fitz

from .models import PageRender


def render_pdf_pages(
    pdf_path: Path,
    out_dir: Path,
    *,
    dpi: int = 220,
    max_pages: int | None = None,
) -> list[PageRender]:
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    pages: list[PageRender] = []
    try:
        for idx, page in enumerate(doc):
            if max_pages is not None and idx >= max_pages:
                break

            cs_rgb = getattr(fitz, "csRGB", None)
            try:
                if cs_rgb is not None:
                    pix = page.get_pixmap(dpi=int(dpi), colorspace=cs_rgb, alpha=False)
                else:
                    pix = page.get_pixmap(dpi=int(dpi), alpha=False)
            except TypeError:
                pix = page.get_pixmap(dpi=int(dpi))

            out_path = out_dir / f"page-{idx + 1:04d}.png"
            pix.save(str(out_path))

            pages.append(
                PageRender(
                    page_index=idx,
                    width_px=int(pix.width),
                    height_px=int(pix.height),
                    width_pt=float(page.rect.width),
                    height_pt=float(page.rect.height),
                    image_path=out_path,
                )
            )
    finally:
        doc.close()
    return pages
