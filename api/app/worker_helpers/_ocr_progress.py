"""Progress tracking helpers for OCR stage (split from ocr_stage.py)."""

from __future__ import annotations

from typing import Any


def _progress_in_span(
    done: int,
    total: int,
    *,
    start: int,
    end: int,
) -> int:
    if total <= 0:
        return int(end)
    ratio = max(0.0, min(1.0, float(done) / float(total)))
    return int(round(float(start) + (float(end - start) * ratio)))


def _summarize_ocr_page_runtime(
    *, page_entries: list[dict[str, Any]], ocr_manager: Any
) -> dict[str, Any]:
    provider_counts: dict[str, int] = {}
    fallback_reason_counts: dict[str, int] = {}
    pages_with_elements = 0
    pages_with_errors = 0
    pages_with_fallback = 0

    for entry in page_entries:
        if not isinstance(entry, dict):
            continue
        if "error" in entry or "warning" in entry:
            pages_with_errors += 1
        if int(entry.get("elements") or 0) > 0:
            pages_with_elements += 1

        used_provider = str(entry.get("used_provider") or "").strip()
        if used_provider:
            provider_counts[used_provider] = provider_counts.get(used_provider, 0) + 1

        fallback_reason = str(entry.get("fallback_reason") or "").strip()
        if fallback_reason:
            pages_with_fallback += 1
            fallback_reason_counts[fallback_reason] = (
                fallback_reason_counts.get(fallback_reason, 0) + 1
            )

    ai_provider_disabled = bool(getattr(ocr_manager, "ai_provider_disabled", False))
    ai_provider_disabled_reason = getattr(
        ocr_manager, "ai_provider_disabled_reason", None
    )

    return {
        "provider_counts": provider_counts,
        "distinct_provider_count": len(provider_counts),
        "pages_with_elements": pages_with_elements,
        "pages_with_errors": pages_with_errors,
        "fallback_pages": pages_with_fallback,
        "fallback_reason_counts": fallback_reason_counts,
        "ai_provider_disabled": ai_provider_disabled,
        "ai_provider_disabled_reason": ai_provider_disabled_reason,
    }


def _format_ocr_progress_message(
    *,
    ocr_page_processed: int,
    ocr_page_targets: int,
    pdf_page_index: int,
    source_page_count: int,
    overall_progress: int,
) -> str:
    ocr_total = max(1, int(ocr_page_targets))
    ocr_stage_percent = int(
        round((max(0, int(ocr_page_processed) - 1) / float(ocr_total)) * 100.0)
    )
    pdf_page_number = max(1, int(pdf_page_index) + 1)
    pdf_total = max(pdf_page_number, int(source_page_count or 0))
    return (
        "OCR 识别中（"
        f"OCR页 {int(ocr_page_processed)}/{ocr_total}，"
        f"PDF页 {pdf_page_number}/{pdf_total}，"
        f"OCR阶段 {ocr_stage_percent}%，"
        f"总进度 {int(overall_progress)}%"
        "）"
    )


def _format_parallel_ocr_progress_message(
    *,
    completed_pages: int,
    total_pages: int,
    running_pages: int,
    page_concurrency: int,
    latest_pdf_page_index: int | None,
    source_page_count: int,
    overall_progress: int,
) -> str:
    pdf_page_number = (
        max(1, int(latest_pdf_page_index) + 1)
        if latest_pdf_page_index is not None
        else None
    )
    pdf_total = max(
        int(source_page_count or 0),
        pdf_page_number or 1,
    )
    latest_page_text = (
        f"，最近 PDF页 {pdf_page_number}/{pdf_total}"
        if pdf_page_number is not None
        else ""
    )
    return (
        "OCR 识别中（"
        f"已完成 {int(completed_pages)}/{max(1, int(total_pages))} 页，"
        f"运行中 {max(0, int(running_pages))} 页，"
        f"页并发 {max(1, int(page_concurrency))}"
        f"{latest_page_text}，"
        f"总进度 {int(overall_progress)}%"
        "）"
    )
