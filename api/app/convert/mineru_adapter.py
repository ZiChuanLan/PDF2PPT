"""MinerU API integration helpers."""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, cast

import httpx

from app.models.error import AppException, ErrorCode
from app.utils.text import clean_str as _clean_str

from ._mineru_build_ir import (
    _build_ir_from_mineru_outputs,
    _recover_missing_notebooklm_footer_elements,
)
from ._mineru_extract import (
    _estimate_content_items_quality,
    _extract_content_items,
    _extract_content_items_from_layout,
    _extract_page_sizes,
    _extract_pdf_page_sizes,
    _find_json_file,
    _load_json,
    _normalize_mineru_token,
    _parse_page_ranges,
    _should_prefer_layout_candidate,
)


_DEFAULT_BASE_URL = "https://mineru.net"
_TERMINAL_STATES = {"done", "failed"}
_ACTIVE_STATES = {"waiting-file", "pending", "running", "converting"}


class MineruClient:
    """Minimal MinerU client for file-upload batch parsing."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        token_cleaned = _normalize_mineru_token(token)
        if not token_cleaned:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="MinerU token is required",
            )
        self.base_url = _clean_str(base_url) or _DEFAULT_BASE_URL
        self._headers = {
            "Authorization": f"Bearer {token_cleaned}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        self._timeout = float(timeout_seconds)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers,
                json=json_body,
                timeout=self._timeout,
            )
        except Exception as e:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="MinerU request failed",
                details={"path": path, "error": str(e)},
                status_code=502,
            )

        try:
            payload = response.json()
        except Exception as e:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="MinerU returned invalid JSON",
                details={
                    "path": path,
                    "status_code": response.status_code,
                    "error": str(e),
                },
                status_code=502,
            )

        if response.status_code >= 400:
            msg_code = (
                str(payload.get("msgCode") or payload.get("code") or "").strip().upper()
            )
            if msg_code in {"A0202", "A0211"} or response.status_code == 401:
                raise AppException(
                    code=ErrorCode.CONVERSION_FAILED,
                    message="MinerU token invalid or expired",
                    details={
                        "path": path,
                        "status_code": response.status_code,
                        "response": payload,
                    },
                    status_code=502,
                )
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="MinerU request rejected",
                details={
                    "path": path,
                    "status_code": response.status_code,
                    "response": payload,
                },
                status_code=502,
            )

        code = payload.get("code")
        if code not in (0, "0"):
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="MinerU API returned an error",
                details={"path": path, "response": payload},
                status_code=502,
            )
        return payload

    def create_upload_batch(
        self,
        *,
        file_name: str,
        data_id: str | None = None,
        model_version: str | None = None,
        enable_formula: bool | None = None,
        enable_table: bool | None = None,
        language: str | None = None,
        is_ocr: bool | None = None,
        page_ranges: str | None = None,
    ) -> tuple[str, str]:
        file_item: dict[str, Any] = {"name": file_name}
        if _clean_str(data_id):
            file_item["data_id"] = _clean_str(data_id)
        if is_ocr is not None:
            file_item["is_ocr"] = bool(is_ocr)
        if _clean_str(page_ranges):
            file_item["page_ranges"] = _clean_str(page_ranges)

        body: dict[str, Any] = {
            "files": [file_item],
            "model_version": _clean_str(model_version) or "vlm",
        }
        if enable_formula is not None:
            body["enable_formula"] = bool(enable_formula)
        if enable_table is not None:
            body["enable_table"] = bool(enable_table)
        if _clean_str(language):
            body["language"] = _clean_str(language)

        payload = self._request_json("POST", "/api/v4/file-urls/batch", json_body=body)
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="MinerU returned invalid upload batch payload",
                details={"response": payload},
                status_code=502,
            )

        batch_id = _clean_str(str(data.get("batch_id") or ""))
        file_urls = data.get("file_urls") or data.get("files") or []
        upload_url = ""
        if isinstance(file_urls, list) and file_urls:
            upload_url = str(file_urls[0] or "").strip()

        if not batch_id or not upload_url:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="MinerU did not return upload URL",
                details={"response": payload},
                status_code=502,
            )

        return (batch_id, upload_url)

    def upload_file(
        self,
        *,
        upload_url: str,
        file_path: Path,
        cancel_check: Callable[[], None] | None = None,
    ) -> None:
        if cancel_check is not None:
            cancel_check()
        try:
            with file_path.open("rb") as f:
                response = httpx.put(
                    upload_url,
                    data=cast(Any, f),
                    timeout=max(self._timeout, 120.0),
                )
        except Exception as e:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="Failed to upload file to MinerU",
                details={"error": str(e)},
                status_code=502,
            )

        if response.status_code >= 400:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="MinerU upload URL rejected file",
                details={"status_code": response.status_code},
                status_code=502,
            )

        if cancel_check is not None:
            cancel_check()

    def poll_batch_result(
        self,
        *,
        batch_id: str,
        poll_interval_s: float = 2.0,
        timeout_s: float = 1200.0,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + float(timeout_s)

        while True:
            if cancel_check is not None:
                cancel_check()

            payload = self._request_json(
                "GET", f"/api/v4/extract-results/batch/{batch_id}"
            )
            data = payload.get("data") or {}
            extract_result = (
                data.get("extract_result") if isinstance(data, dict) else None
            )

            first_item: dict[str, Any] | None = None
            if isinstance(extract_result, list) and extract_result:
                if isinstance(extract_result[0], dict):
                    first_item = extract_result[0]

            if first_item is None:
                if time.monotonic() >= deadline:
                    raise AppException(
                        code=ErrorCode.CONVERSION_FAILED,
                        message="Timed out waiting for MinerU batch result",
                        details={"batch_id": batch_id},
                        status_code=504,
                    )
                time.sleep(max(0.2, float(poll_interval_s)))
                continue

            state = str(first_item.get("state") or "").strip().lower()
            if state in _TERMINAL_STATES:
                return first_item

            if state not in _ACTIVE_STATES and state:
                pass

            if time.monotonic() >= deadline:
                raise AppException(
                    code=ErrorCode.CONVERSION_FAILED,
                    message="Timed out waiting for MinerU parsing to finish",
                    details={"batch_id": batch_id, "last_state": state},
                    status_code=504,
                )

            time.sleep(max(0.2, float(poll_interval_s)))

    def download_result_zip(
        self,
        *,
        zip_url: str,
        output_zip: Path,
        cancel_check: Callable[[], None] | None = None,
    ) -> None:
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        if cancel_check is not None:
            cancel_check()
        try:
            with httpx.stream(
                "GET", zip_url, timeout=max(self._timeout, 120.0)
            ) as response:
                response.raise_for_status()
                with output_zip.open("wb") as f:
                    for chunk in response.iter_bytes():
                        if cancel_check is not None:
                            cancel_check()
                        if chunk:
                            f.write(chunk)
        except Exception as e:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="Failed to download MinerU result archive",
                details={"error": str(e)},
                status_code=502,
            )


def parse_pdf_to_ir_with_mineru(
    pdf_path: str | Path,
    artifacts_dir: str | Path,
    *,
    token: str | None,
    base_url: str | None = None,
    model_version: str | None = None,
    enable_formula: bool | None = None,
    enable_table: bool | None = None,
    language: str | None = None,
    is_ocr: bool | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    data_id: str | None = None,
    poll_interval_s: float = 2.0,
    poll_timeout_s: float = 3600.0,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    path = Path(pdf_path)
    if not path.exists():
        raise AppException(
            code=ErrorCode.INVALID_PDF,
            message="PDF file not found",
            details={"path": str(path)},
        )

    token_cleaned = _normalize_mineru_token(token)
    if not token_cleaned:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            message="MinerU token is required when parse_provider=mineru",
        )

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    page_ranges = _parse_page_ranges(page_start=page_start, page_end=page_end)

    def _step_check() -> None:
        if cancel_check is not None:
            cancel_check()

    client = MineruClient(token=token_cleaned, base_url=base_url)
    _step_check()
    batch_id, upload_url = client.create_upload_batch(
        file_name=path.name,
        data_id=data_id,
        model_version=model_version,
        enable_formula=enable_formula,
        enable_table=enable_table,
        language=language,
        is_ocr=is_ocr,
        page_ranges=page_ranges,
    )

    (out_dir / "create_batch.json").write_text(
        json.dumps(
            {"batch_id": batch_id, "upload_url": upload_url},
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _step_check()

    client.upload_file(
        upload_url=upload_url,
        file_path=path,
        cancel_check=cancel_check,
    )
    _step_check()
    result = client.poll_batch_result(
        batch_id=batch_id,
        poll_interval_s=poll_interval_s,
        timeout_s=poll_timeout_s,
        cancel_check=cancel_check,
    )
    _step_check()
    (out_dir / "batch_result.json").write_text(
        json.dumps(result, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    state = str(result.get("state") or "").strip().lower()
    if state != "done":
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="MinerU parsing failed",
            details={
                "state": result.get("state"),
                "err_msg": result.get("err_msg"),
                "batch_id": batch_id,
            },
            status_code=502,
        )

    zip_url = _clean_str(result.get("full_zip_url"))
    if not zip_url:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="MinerU did not return result archive URL",
            details={"batch_id": batch_id, "result": result},
            status_code=502,
        )

    archive_path = out_dir / "result.zip"
    extracted_dir = out_dir / "result"
    client.download_result_zip(
        zip_url=zip_url,
        output_zip=archive_path,
        cancel_check=cancel_check,
    )
    _step_check()

    extracted_dir.mkdir(parents=True, exist_ok=True)
    try:
        _step_check()
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extracted_dir)
        _step_check()
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="Failed to extract MinerU result archive",
            details={"path": str(archive_path), "error": str(e)},
            status_code=500,
        )

    content_candidates = [
        path
        for path in extracted_dir.rglob("*.json")
        if "content_list" in path.name.lower()
    ]
    if not content_candidates:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="MinerU output missing content_list JSON",
            details={"path": str(extracted_dir)},
            status_code=500,
        )

    def _content_candidate_sort_key(path: Path) -> tuple[int, int, str]:
        name = path.name.lower()
        if name == "content_list.json":
            rank = 0
        elif name.endswith("_content_list.json"):
            rank = 1
        elif "content_list_v2" in name:
            rank = 2
        else:
            rank = 3
        return (rank, len(str(path)), str(path))

    content_candidates.sort(key=_content_candidate_sort_key)

    content_json: Path | None = None
    content_items: list[dict[str, Any]] = []
    content_score: tuple[int, int] = (-1, -1)
    for candidate in content_candidates:
        _step_check()
        items = _extract_content_items(_load_json(candidate))
        candidate_score = _estimate_content_items_quality(items)
        if candidate_score > content_score:
            content_score = candidate_score
            content_json = candidate
            content_items = items

    if content_json is None:
        content_json = content_candidates[0]
        content_items = _extract_content_items(_load_json(content_json))
        content_score = _estimate_content_items_quality(content_items)
    selected_items = content_items
    selected_score = content_score
    selected_source = (
        f"content:{content_json.name}"
        if content_json is not None
        else "content:unknown"
    )

    layout_json = _find_json_file(
        extracted_dir,
        exact_name="layout.json",
        suffix_name="_layout.json",
        contain_name="layout",
    )
    layout_score: tuple[int, int] = (-1, -1)
    used_layout_items = False
    if layout_json is not None:
        layout_items = _extract_content_items_from_layout(_load_json(layout_json))
        layout_score = _estimate_content_items_quality(layout_items)
        if _should_prefer_layout_candidate(
            content_items=content_items,
            content_score=content_score,
            layout_items=layout_items,
            layout_score=layout_score,
        ):
            selected_items = layout_items
            selected_score = layout_score
            selected_source = f"layout:{layout_json.name}"
            used_layout_items = True

    if not selected_items:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="MinerU result JSON has no parseable items",
            details={
                "content_json": str(content_json) if content_json is not None else None,
                "layout_json": str(layout_json) if layout_json is not None else None,
            },
            status_code=500,
        )

    page_sizes: dict[int, tuple[float, float]] = {}
    middle_json = _find_json_file(
        extracted_dir,
        exact_name="middle.json",
        suffix_name="_middle.json",
        contain_name="middle",
    )
    if middle_json is not None:
        _step_check()
        middle_payload = _load_json(middle_json)
        page_sizes = _extract_page_sizes(middle_payload)
    pdf_page_sizes = _extract_pdf_page_sizes(path)
    if pdf_page_sizes:
        merged_page_sizes = dict(page_sizes)
        merged_page_sizes.update(pdf_page_sizes)
        page_sizes = merged_page_sizes

    _step_check()
    ir = _build_ir_from_mineru_outputs(
        source_pdf=path,
        content_items=selected_items,
        page_sizes=page_sizes,
        page_start=page_start,
        page_end=page_end,
        image_output_dir=out_dir / "images",
        image_path_prefix=f"{out_dir.name}/images",
        mineru_result_dir=extracted_dir,
        mineru_result_path_prefix=f"{out_dir.name}/result",
    )
    _step_check()
    ir["warnings"] = list(ir.get("warnings") or [])
    if used_layout_items:
        recovered_footer_count = _recover_missing_notebooklm_footer_elements(
            ir=ir,
            content_items=content_items,
            source_pdf=path,
            page_sizes=page_sizes,
            page_start=page_start,
            page_end=page_end,
        )
        if recovered_footer_count > 0:
            ir["warnings"].append(
                f"mineru_recovered_footer_items={recovered_footer_count}"
            )
    ir["warnings"].append(f"mineru_batch_id={batch_id}")
    ir["warnings"].append(f"mineru_content_json={content_json.name}")
    if layout_json is not None:
        ir["warnings"].append(
            f"mineru_layout_quality=usable:{layout_score[0]},score:{layout_score[1]}"
        )
    ir["warnings"].append(f"mineru_selected_source={selected_source}")
    ir["warnings"].append(
        f"mineru_content_quality=usable:{content_score[0]},score:{content_score[1]}"
    )
    if used_layout_items:
        ir["warnings"].append(
            f"mineru_selected_quality=usable:{selected_score[0]},score:{selected_score[1]}"
        )
    return ir
