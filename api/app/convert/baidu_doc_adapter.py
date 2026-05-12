"""Baidu document parser integration helpers."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Callable

import httpx
import pymupdf

from app.models.error import AppException, ErrorCode
from app.utils.text import clean_str as _clean_str

from ._adapter_utils import _IMAGE_KIND_TOKENS, _is_image_like_kind  # noqa: F401  # re-export
from ._baidu_extract import (
    _collect_content_items,
    _collect_page_payload,
    _extract_image_path,
    _extract_kind,
    _extract_page_idx,
    _extract_result_container,
    _extract_status,
    _extract_task_id,
    _extract_text,
    _find_result_url,
    _looks_like_parse_result_payload,
    _maybe_parse_json,
    _normalize_bbox_to_pdf_pt,
    _raise_if_baidu_error,
    _resolve_result_payload,
)
from ._mineru_build_ir import _build_ir_from_mineru_outputs
from ._mineru_extract import _extract_pdf_page_sizes


_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
_BAIDU_DOC_ENDPOINTS = {
    "general": {
        "task_url": "https://aip.baidubce.com/rest/2.0/brain/online/v2/parser/task",
        "result_url": "https://aip.baidubce.com/rest/2.0/brain/online/v2/parser/task/query",
    },
    "paddle_vl": {
        "task_url": "https://aip.baidubce.com/rest/2.0/brain/online/v2/paddle-vl-parser/task",
        "result_url": "https://aip.baidubce.com/rest/2.0/brain/online/v2/paddle-vl-parser/task/query",
    },
}
_SUCCESS_STATUSES = {"success", "succeeded", "done", "finished", "completed"}
_FAILED_STATUSES = {"failed", "error", "cancelled", "canceled", "timeout"}
_ACTIVE_STATUSES = {"created", "queued", "pending", "processing", "running"}


class BaiduDocParserClient:
    def __init__(
        self,
        *,
        api_key: str,
        secret_key: str,
        parse_type: str = "paddle_vl",
        timeout_s: float = 60.0,
    ) -> None:
        self.api_key = _clean_str(api_key)
        self.secret_key = _clean_str(secret_key)
        self.parse_type = _clean_str(parse_type) or "paddle_vl"
        if not self.api_key or not self.secret_key:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="Baidu document parser requires api_key / secret_key",
                status_code=400,
            )
        endpoints = _BAIDU_DOC_ENDPOINTS.get(self.parse_type)
        if endpoints is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                message="Unsupported Baidu document parser type",
                details={"parse_type": parse_type},
                status_code=400,
            )
        self.task_url = endpoints["task_url"]
        self.result_url = endpoints["result_url"]
        self.client = httpx.Client(
            timeout=httpx.Timeout(timeout_s),
            follow_redirects=True,
        )
        self._access_token: str | None = None

    def close(self) -> None:
        self.client.close()

    def get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        response = self.client.post(
            _TOKEN_URL,
            params={
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.secret_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
        _raise_if_baidu_error(payload, context="token request")
        token = _clean_str(payload.get("access_token") if isinstance(payload, dict) else None)
        if not token:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="Failed to obtain Baidu access token",
                details={"payload": payload},
                status_code=502,
            )
        self._access_token = token
        return token

    def submit_task(self, pdf_path: Path) -> dict[str, Any]:
        payload = {
            "file_data": base64.b64encode(pdf_path.read_bytes()).decode("ascii"),
            "file_name": pdf_path.name or "input.pdf",
        }
        response = self.client.post(
            self.task_url,
            params={"access_token": self.get_access_token()},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=payload,
        )
        response.raise_for_status()
        data = response.json()
        _raise_if_baidu_error(data, context="task submission")
        if _extract_task_id(data) is None:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="Baidu document parser did not return task_id",
                details={"payload": data},
                status_code=502,
            )
        return data

    def get_result(self, task_id: str) -> dict[str, Any]:
        response = self.client.post(
            self.result_url,
            params={"access_token": self.get_access_token()},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"task_id": task_id},
        )
        response.raise_for_status()
        payload = response.json()
        _raise_if_baidu_error(payload, context="result polling")
        return payload


def _create_selected_pdf(
    source_pdf: Path,
    out_pdf: Path,
    *,
    page_start: int | None,
    page_end: int | None,
) -> Path:
    if page_start is None or page_end is None:
        return source_pdf

    src = pymupdf.open(str(source_pdf))
    out = pymupdf.open()
    try:
        out.insert_pdf(src, from_page=int(page_start) - 1, to_page=int(page_end) - 1)
        out.save(str(out_pdf))
    except Exception as e:
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="Failed to build selected-page PDF for Baidu parser",
            details={"error": str(e), "page_start": page_start, "page_end": page_end},
            status_code=500,
        )
    finally:
        out.close()
        src.close()
    return out_pdf


def parse_pdf_to_ir_with_baidu_doc(
    pdf_path: str | Path,
    artifacts_dir: str | Path,
    *,
    api_key: str | None,
    secret_key: str | None,
    parse_type: str = "paddle_vl",
    page_start: int | None = None,
    page_end: int | None = None,
    poll_interval_s: float = 2.0,
    poll_timeout_s: float = 900.0,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    path = Path(pdf_path)
    if not path.exists():
        raise AppException(
            code=ErrorCode.INVALID_PDF,
            message="PDF file not found",
            details={"path": str(path)},
        )

    out_dir = Path(artifacts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    upload_pdf = _create_selected_pdf(
        path,
        out_dir / "selected-pages.pdf",
        page_start=page_start,
        page_end=page_end,
    )
    upload_page_sizes = _extract_pdf_page_sizes(upload_pdf)
    original_page_sizes = _extract_pdf_page_sizes(path)

    def _step_check() -> None:
        if cancel_check is not None:
            cancel_check()

    client: BaiduDocParserClient | None = None

    try:
        client = BaiduDocParserClient(
            api_key=_clean_str(api_key) or "",
            secret_key=_clean_str(secret_key) or "",
            parse_type=parse_type,
        )
        _step_check()
        submit_payload = client.submit_task(upload_pdf)
        (out_dir / "submit_task.json").write_text(
            json.dumps(submit_payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )

        task_id = _extract_task_id(submit_payload)
        if not task_id:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="Baidu document parser missing task_id",
                details={"payload": submit_payload},
                status_code=502,
            )

        started_at = time.monotonic()
        latest_payload: dict[str, Any] = submit_payload
        latest_status = _extract_status(submit_payload)
        while True:
            _step_check()
            latest_status = _extract_status(latest_payload)
            if latest_status in _SUCCESS_STATUSES | _FAILED_STATUSES:
                break
            if time.monotonic() - started_at >= float(poll_timeout_s):
                raise AppException(
                    code=ErrorCode.CONVERSION_FAILED,
                    message="Baidu document parser timed out",
                    details={"task_id": task_id, "status": latest_status},
                    status_code=504,
                )
            time.sleep(max(0.2, float(poll_interval_s)))
            latest_payload = client.get_result(task_id)

        (out_dir / "task_result.json").write_text(
            json.dumps(latest_payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )

        if latest_status in _FAILED_STATUSES:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="Baidu document parser failed",
                details={"task_id": task_id, "status": latest_status, "payload": latest_payload},
                status_code=502,
            )

        result_payload, result_source = _resolve_result_payload(latest_payload, client=client.client)
        (out_dir / "result_payload.json").write_text(
            json.dumps(result_payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )

        payload_page_sizes: dict[int, tuple[float, float]] = {}
        _collect_page_payload(result_payload, out_pages=payload_page_sizes)
        content_items: list[dict[str, Any]] = []
        seen_items: set[tuple[int, str, str, str]] = set()
        _collect_content_items(
            result_payload,
            page_idx=None,
            payload_page_sizes=payload_page_sizes,
            pdf_page_sizes=upload_page_sizes,
            out_items=content_items,
            seen=seen_items,
        )
        if not content_items:
            raise AppException(
                code=ErrorCode.CONVERSION_FAILED,
                message="Baidu document parser returned no parseable layout items",
                details={"task_id": task_id, "status": latest_status},
                status_code=502,
            )

        ir = _build_ir_from_mineru_outputs(
            source_pdf=path,
            content_items=content_items,
            page_sizes=original_page_sizes or upload_page_sizes,
            page_start=page_start,
            page_end=page_end,
            image_output_dir=out_dir / "images",
            image_path_prefix=f"{out_dir.name}/images",
            layout_source="baidu_doc",
            warning_prefix="baidu_doc",
        )
        ir["warnings"] = list(ir.get("warnings") or [])
        ir["warnings"].append(f"baidu_doc_task_id={task_id}")
        ir["warnings"].append(f"baidu_doc_parse_type={parse_type}")
        ir["warnings"].append(f"baidu_doc_status={latest_status or 'success'}")
        ir["warnings"].append(f"baidu_doc_result_source={result_source}")
        return ir
    except httpx.HTTPError as e:
        response = getattr(e, "response", None)
        detail = {
            "error": str(e),
            "status_code": getattr(response, "status_code", None),
        }
        if response is not None:
            try:
                detail["response"] = response.json()
            except Exception:
                detail["response_text"] = response.text
        raise AppException(
            code=ErrorCode.CONVERSION_FAILED,
            message="Baidu document parser request failed",
            details=detail,
            status_code=502,
        ) from e
    finally:
        if client is not None:
            client.close()
