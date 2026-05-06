# Research: Job Creation API — Complete Parameter Lists and Data Flow

- **Query**: Document the complete signature of `create_job()`, `process_pdf_job()`, `validate_and_normalize_job_options()`, and `createJobFormData()` with exact parameter lists.
- **Scope**: internal
- **Date**: 2026-05-03

---

## 1. API Endpoint

| Attribute | Value |
|---|---|
| URL | `POST /api/v1/jobs` |
| Router file | `api/app/routers/jobs.py` (line 676) |
| Decorator | `@router.post("", response_model=JobCreateResponse)` |
| Router prefix | `/api/v1/jobs` (line 70) |
| Auth | Optional — uses `Depends(get_current_user_optional)` |

---

## 2. `create_job()` — Full Signature (line 676–918)

```python
async def create_job(
    file: UploadFile = File(...),
    enable_ocr: bool = Form(False),
    retain_process_artifacts: bool = Form(False),
    remove_footer_notebooklm: bool = Form(False),
    text_erase_mode: str | None = Form("fill"),
    enable_layout_assist: bool = Form(False),           # DEPRECATED, forced False
    layout_assist_apply_image_regions: bool = Form(False), # DEPRECATED, forced False
    parse_provider: str = Form("local"),
    provider: str = Form("openai"),
    api_key: str | None = Form(None),
    baidu_doc_parse_type: str | None = Form("paddle_vl"),
    base_url: str | None = Form(None),
    model: str | None = Form(None),
    page_start: int | None = Form(None),
    page_end: int | None = Form(None),
    mineru_api_token: str | None = Form(None),
    mineru_base_url: str | None = Form(None),
    mineru_model_version: str | None = Form("vlm"),
    mineru_enable_formula: bool | None = Form(True),
    mineru_enable_table: bool | None = Form(True),
    mineru_language: str | None = Form(None),
    mineru_is_ocr: bool | None = Form(None),
    mineru_hybrid_ocr: bool | None = Form(False),       # DEPRECATED, ignored
    ocr_provider: str | None = Form("auto"),
    ocr_baidu_app_id: str | None = Form(None),
    ocr_baidu_api_key: str | None = Form(None),
    ocr_baidu_secret_key: str | None = Form(None),
    ocr_tesseract_min_confidence: float | None = Form(None),
    ocr_tesseract_language: str | None = Form(None),
    ocr_ai_api_key: str | None = Form(None),
    ocr_ai_provider: str | None = Form("auto"),
    ocr_ai_base_url: str | None = Form(None),
    ocr_ai_model: str | None = Form(None),
    ocr_ai_chain_mode: str | None = Form("direct"),
    ocr_ai_layout_model: str | None = Form("pp_doclayout_v3"),
    ocr_ai_prompt_preset: str | None = Form("auto"),
    ocr_ai_direct_prompt_override: str | None = Form(None),
    ocr_ai_layout_block_prompt_override: str | None = Form(None),
    ocr_ai_image_region_prompt_override: str | None = Form(None),
    ocr_paddle_vl_docparser_max_side_px: int | None = Form(None, ge=0, le=6000),
    ocr_ai_page_concurrency: int | None = Form(1, ge=1, le=8),
    ocr_ai_block_concurrency: int | None = Form(None, ge=1, le=8),
    ocr_ai_requests_per_minute: int | None = Form(None, ge=1, le=2000),
    ocr_ai_tokens_per_minute: int | None = Form(None, ge=1, le=2_000_000),
    ocr_ai_max_retries: int | None = Form(0, ge=0, le=8),
    ocr_render_dpi: int | None = Form(None, ge=72, le=400),
    ocr_geometry_mode: str | None = Form("auto"),       # DEPRECATED
    scanned_page_mode: str | None = Form("segmented"),
    ppt_generation_mode: str | None = Form("standard"),
    image_bg_clear_expand_min_pt: float | None = Form(None),
    image_bg_clear_expand_max_pt: float | None = Form(None),
    image_bg_clear_expand_ratio: float | None = Form(None),
    scanned_image_region_min_area_ratio: float | None = Form(None),
    scanned_image_region_max_area_ratio: float | None = Form(None),
    scanned_image_region_max_aspect_ratio: float | None = Form(None),
    ocr_ai_linebreak_assist: bool | None = Form(None),
    ocr_strict_mode: bool | None = Form(True),
    current_user=Depends(get_current_user_optional),
)
```

**Total: 1 file field + 53 Form fields + 1 dependency = 55 parameters**

### Parameter Grouping Summary

| Group | Count | Parameters |
|---|---|---|
| File upload | 1 | `file` |
| Core flags | 4 | `enable_ocr`, `retain_process_artifacts`, `remove_footer_notebooklm`, `text_erase_mode` |
| Deprecated (ignored) | 3 | `enable_layout_assist`, `layout_assist_apply_image_regions`, `mineru_hybrid_ocr` |
| Parse provider | 1 | `parse_provider` |
| LLM (layout assist) | 4 | `provider`, `api_key`, `base_url`, `model` |
| Page range | 2 | `page_start`, `page_end` |
| Baidu doc parser | 2 | `baidu_doc_parse_type`, `ocr_baidu_app_id` (also baidu_api_key/secret) |
| MinerU | 7 | `mineru_api_token`, `mineru_base_url`, `mineru_model_version`, `mineru_enable_formula`, `mineru_enable_table`, `mineru_language`, `mineru_is_ocr` |
| OCR provider | 1 | `ocr_provider` |
| Baidu OCR | 3 | `ocr_baidu_app_id`, `ocr_baidu_api_key`, `ocr_baidu_secret_key` |
| Tesseract | 2 | `ocr_tesseract_min_confidence`, `ocr_tesseract_language` |
| AI OCR | 14 | `ocr_ai_api_key`, `ocr_ai_provider`, `ocr_ai_base_url`, `ocr_ai_model`, `ocr_ai_chain_mode`, `ocr_ai_layout_model`, `ocr_ai_prompt_preset`, `ocr_ai_direct_prompt_override`, `ocr_ai_layout_block_prompt_override`, `ocr_ai_image_region_prompt_override`, `ocr_paddle_vl_docparser_max_side_px`, `ocr_ai_page_concurrency`, `ocr_ai_block_concurrency`, `ocr_ai_requests_per_minute`, `ocr_ai_tokens_per_minute`, `ocr_ai_max_retries` |
| OCR tuning | 3 | `ocr_render_dpi`, `ocr_geometry_mode`, `ocr_ai_linebreak_assist` |
| PPT generation | 3 | `scanned_page_mode`, `ppt_generation_mode`, `ocr_strict_mode` |
| Image region tuning | 7 | `image_bg_clear_expand_min_pt`, `image_bg_clear_expand_max_pt`, `image_bg_clear_expand_ratio`, `scanned_image_region_min_area_ratio`, `scanned_image_region_max_area_ratio`, `scanned_image_region_max_aspect_ratio` |

---

## 3. `process_pdf_job()` — Full Signature (line 119–179)

```python
def process_pdf_job(
    job_id: str,
    *,
    enable_ocr: bool = False,
    retain_process_artifacts: bool = False,
    remove_footer_notebooklm: bool = False,
    text_erase_mode: str | None = None,
    enable_layout_assist: bool = False,
    layout_assist_apply_image_regions: bool = False,
    provider: str | None = None,
    api_key: str | None = None,
    baidu_doc_parse_type: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
    parse_provider: str | None = None,
    mineru_api_token: str | None = None,
    mineru_base_url: str | None = None,
    mineru_model_version: str | None = None,
    mineru_enable_formula: bool | None = None,
    mineru_enable_table: bool | None = None,
    mineru_language: str | None = None,
    mineru_is_ocr: bool | None = None,
    mineru_hybrid_ocr: bool | None = None,
    ocr_provider: str | None = None,
    ocr_baidu_app_id: str | None = None,
    ocr_baidu_api_key: str | None = None,
    ocr_baidu_secret_key: str | None = None,
    ocr_tesseract_min_confidence: float | None = None,
    ocr_tesseract_language: str | None = None,
    ocr_ai_api_key: str | None = None,
    ocr_ai_provider: str | None = None,
    ocr_ai_base_url: str | None = None,
    ocr_ai_model: str | None = None,
    ocr_ai_chain_mode: str | None = None,
    ocr_ai_layout_model: str | None = None,
    ocr_ai_prompt_preset: str | None = None,
    ocr_ai_direct_prompt_override: str | None = None,
    ocr_ai_layout_block_prompt_override: str | None = None,
    ocr_ai_image_region_prompt_override: str | None = None,
    ocr_paddle_vl_docparser_max_side_px: int | None = None,
    ocr_ai_page_concurrency: int | None = None,
    ocr_ai_block_concurrency: int | None = None,
    ocr_ai_requests_per_minute: int | None = None,
    ocr_ai_tokens_per_minute: int | None = None,
    ocr_ai_max_retries: int | None = None,
    ocr_render_dpi: int | None = None,
    ocr_geometry_mode: str | None = None,
    scanned_page_mode: str | None = None,
    ppt_generation_mode: str | None = None,
    image_bg_clear_expand_min_pt: float | None = None,
    image_bg_clear_expand_max_pt: float | None = None,
    image_bg_clear_expand_ratio: float | None = None,
    scanned_image_region_min_area_ratio: float | None = None,
    scanned_image_region_max_area_ratio: float | None = None,
    scanned_image_region_max_aspect_ratio: float | None = None,
    ocr_ai_linebreak_assist: bool | None = None,
    ocr_strict_mode: bool | None = True,
    job_timeout: str | None = None,
) -> None:
```

**Total: 1 positional + 54 keyword args = 55 parameters**

### Key observations about `process_pdf_job`:

1. **First arg `job_id` is positional** — passed as positional in `queue.enqueue()` because RQ reserves `job_id` kwarg name (line 1098-1101).
2. **All remaining args are keyword-only** (after `*`).
3. **`job_timeout`** is only in the worker, not in the API endpoint — it's set to `"1h"` by the caller.
4. **On entry**, the function assigns all kwargs to `_` (line 182-240) as a lint suppression trick, then immediately overrides `enable_layout_assist = False` and `layout_assist_apply_image_regions = False` (lines 242-243).

---

## 4. `validate_and_normalize_job_options()` — Full Signature (line 239–261)

```python
def validate_and_normalize_job_options(
    *,
    parse_provider: str | None,
    mineru_api_token: str | None,
    provider: str | None = None,
    api_key: str | None = None,
    baidu_doc_parse_type: str | None = None,
    ocr_provider: str | None,
    ocr_ai_provider: str | None,
    ocr_ai_api_key: str | None,
    ocr_ai_model: str | None,
    ocr_ai_chain_mode: str | None,
    ocr_ai_layout_model: str | None,
    ocr_baidu_app_id: str | None = None,
    ocr_baidu_api_key: str | None = None,
    ocr_baidu_secret_key: str | None = None,
    ocr_geometry_mode: str | None,
    text_erase_mode: str | None,
    scanned_page_mode: str | None,
    ppt_generation_mode: str | None,
    page_start: int | None,
    page_end: int | None,
) -> NormalizedJobOptions:
```

**Total: 20 keyword-only parameters**

### What it returns: `NormalizedJobOptions`

```python
@dataclass(frozen=True)
class NormalizedJobOptions:
    parse_provider: str        # normalized to VALID_PARSE_PROVIDERS
    provider: str              # normalized layout provider
    baidu_doc_parse_type: str  # normalized baidu doc type
    ocr_provider: str          # normalized OCR provider
    ocr_ai_provider: str       # normalized AI OCR provider
    ocr_ai_chain_mode: str     # normalized chain mode
    ocr_ai_layout_model: str   # normalized layout model
    ocr_geometry_mode: str     # normalized geometry mode
    text_erase_mode: str       # "smart" | "fill"
    scanned_page_mode: str     # "segmented" | "fullpage"
    ppt_generation_mode: str   # "standard" | "fast" | "turbo"
```

### What it normalizes (only 11 of the 20 input params are normalized and returned):

| Input Parameter | Normalized Field | Normalizer Function |
|---|---|---|
| `parse_provider` | `parse_provider` | `normalize_parse_provider()` |
| `provider` | `provider` | `normalize_layout_provider()` |
| `baidu_doc_parse_type` | `baidu_doc_parse_type` | `normalize_baidu_doc_parse_type()` |
| `ocr_provider` | `ocr_provider` | `normalize_requested_ocr_provider()` |
| `ocr_ai_provider` | `ocr_ai_provider` | `normalize_ai_ocr_provider()` |
| `ocr_ai_chain_mode` | `ocr_ai_chain_mode` | `normalize_ai_ocr_chain_mode()` |
| `ocr_ai_layout_model` | `ocr_ai_layout_model` | `normalize_ai_ocr_layout_model()` |
| `ocr_geometry_mode` | `ocr_geometry_mode` | `normalize_ocr_geometry_mode()` |
| `text_erase_mode` | `text_erase_mode` | `normalize_text_erase_mode()` |
| `scanned_page_mode` | `scanned_page_mode` | `normalize_scanned_page_mode()` |
| `ppt_generation_mode` | `ppt_generation_mode` | `normalize_ppt_generation_mode()` |

### Parameters consumed for validation only (NOT returned):

- `mineru_api_token` — validated non-empty when `parse_provider=mineru`
- `api_key` — unused (assigned to `_`, line 265)
- `ocr_ai_api_key` — validated non-empty for explicit AI OCR providers
- `ocr_ai_model` — validated non-empty + PaddleOCR-VL constraints
- `ocr_baidu_app_id`, `ocr_baidu_api_key`, `ocr_baidu_secret_key` — validated for Baidu
- `page_start`, `page_end` — validated via `validate_page_range()`

### Validation rules (line 281–485):

1. `parse_provider` must be in `{"local", "mineru", "baidu_doc", "v2"}`
2. `provider` must be in `LAYOUT_PROVIDER_ALIASES`
3. `page_start`/`page_end` must be provided together, both >= 1
4. `mineru_api_token` required when `parse_provider=mineru`
5. `ocr_baidu_api_key`/`ocr_baidu_secret_key` required when `ocr_provider=baidu` or `parse_provider=baidu_doc`
6. `ocr_ai_api_key` + `ocr_ai_model` required when `ocr_provider=aiocr|paddle`
7. `ocr_ai_chain_mode=doc_parser` requires model name containing "paddleocr-vl"
8. `ocr_ai_chain_mode=direct` does NOT support PaddleOCR-VL models
9. `ocr_geometry_mode` only valid when `ocr_provider=aiocr`
10. `parse_provider=mineru|baidu_doc` cannot specify non-auto `ocr_provider`
11. Legacy: `parse_provider=baidu_doc` + `ocr_provider=baidu` auto-normalizes ocr to "auto"

---

## 5. `createJobFormData()` — Full Signature (line 574–726)

```typescript
export function createJobFormData(
  file: File,
  settings: Settings,
  pageStart?: number,
  pageEnd?: number,
  options?: CreateJobOptions
): FormData
```

### FormData fields it appends:

**Always appended:**
- `file` — the File object
- `parse_provider` — `"local"` | `"baidu_doc"` | `"mineru"`
- `provider` — `"openai"` | `"claude"`
- `enable_layout_assist` — always `"false"` (deprecated)
- `layout_assist_apply_image_regions` — always `"false"` (deprecated)
- `retain_process_artifacts` — boolean
- `enable_ocr` — `true` only when `parseProvider === "local"` AND `settings.enableOcr`
- `remove_footer_notebooklm` — boolean
- `text_erase_mode` — from settings
- `scanned_page_mode` — from settings
- `ppt_generation_mode` — from settings
- `ocr_strict_mode` — boolean

**Conditional — main AI credentials:**
- `api_key` — if non-empty
- `base_url` — if non-empty
- `model` — if non-empty

**Conditional — image region tuning (if non-empty):**
- `image_bg_clear_expand_min_pt`
- `image_bg_clear_expand_max_pt`
- `image_bg_clear_expand_ratio`
- `scanned_image_region_min_area_ratio`
- `scanned_image_region_max_area_ratio`
- `scanned_image_region_max_aspect_ratio`

**Conditional — OCR render:**
- `ocr_render_dpi` — if valid positive integer

**Conditional — MinerU (`parseProvider === "mineru"`):**
- `mineru_api_token` — always (trimmed)
- `mineru_model_version`
- `mineru_enable_formula` — boolean
- `mineru_enable_table` — boolean
- `mineru_is_ocr` — boolean
- `mineru_base_url` — if non-empty
- `mineru_language` — if non-empty

**Conditional — Baidu doc (`parseProvider === "baidu_doc"`):**
- `ocr_baidu_app_id`
- `ocr_baidu_api_key`
- `ocr_baidu_secret_key`
- `baidu_doc_parse_type`

**Conditional — Local OCR AI params (`parseProvider === "local"` AND `shouldAttachOcrAiParams`):**
- `ocr_provider` — effective OCR provider
- `ocr_ai_api_key` — if non-empty
- `ocr_ai_base_url` — if non-empty
- `ocr_ai_model` — if non-empty
- `ocr_ai_provider` — effective AI OCR provider
- `ocr_ai_chain_mode` — e.g. `"direct"` | `"doc_parser"` | `"layout_block"`
- `ocr_ai_layout_model` — e.g. `"pp_doclayout_v3"`
- `ocr_ai_prompt_preset` — from settings
- `ocr_ai_direct_prompt_override` — if non-empty
- `ocr_ai_layout_block_prompt_override` — if non-empty
- `ocr_ai_image_region_prompt_override` — if non-empty
- `ocr_paddle_vl_docparser_max_side_px` — if valid
- `ocr_ai_page_concurrency` — always (1–8)
- `ocr_ai_block_concurrency` — if non-null
- `ocr_ai_requests_per_minute` — if valid
- `ocr_ai_tokens_per_minute` — if valid
- `ocr_ai_max_retries` — if valid

**Conditional — Baidu OCR fields (when `effectiveOcrProvider === "baidu"`):**
- `ocr_baidu_app_id`
- `ocr_baidu_api_key`
- `ocr_baidu_secret_key`

**Conditional — Tesseract fields (when `effectiveOcrProvider === "tesseract"` or `"auto"`):**
- `ocr_tesseract_language` — if non-empty
- `ocr_tesseract_min_confidence` — if valid number

**Conditional — page range:**
- `page_start` — if both pageStart and pageEnd provided
- `page_end` — if both pageStart and pageEnd provided

---

## 6. Data Flow: Frontend → API → Worker

```
Frontend                    API                         Worker
──────────                  ───                         ──────
createJobFormData()   →     POST /api/v1/jobs
  builds FormData           create_job()
  from Settings               ↓
                              validate_and_normalize_job_options()
                                returns NormalizedJobOptions (11 fields)
                              ↓
                              writes input.pdf to job dir
                              creates Redis job record
                              ↓
                              if memory:// backend:
                                Thread(process_pdf_job, kwargs={...54 kwargs})
                              else:
                                queue.enqueue("app.worker.process_pdf_job",
                                  job_id,           ← positional
                                  ...all kwargs,    ← same 54 kwargs
                                  job_timeout="1h"
                                )
                              ↓
                            process_pdf_job(job_id, **kwargs)
                              normalize_ocr_runtime_params()
                              parse PDF (local/mineru/baidu_doc)
                              OCR stage (if needed)
                              PPT generation stage
                              → output.pptx
```

### Critical note on RQ `job_id` naming conflict:

The API endpoint uses `job_id` (UUID) as the conversion identifier, but RQ's `Queue.enqueue()` reserves `job_id` as its own kwarg for the RQ job identifier. To work around this:
- The conversion `job_id` is passed as a **positional arg** (line 1101: `queue.enqueue("app.worker.process_pdf_job", job_id, ...)`)
- The RQ job id is also set to match: `job_id=job_id` (line 1158) — this is the RQ-level identifier
- In the worker signature, `job_id` is the first positional arg, NOT a kwarg

---

## 7. What `create_job` does NOT pass to `process_pdf_job`

The API endpoint does NOT pass these `NormalizedJobOptions` fields directly. Instead:
- `normalized_options.parse_provider` → `parse_provider` kwarg
- `normalized_options.provider` → `provider` kwarg
- `normalized_options.baidu_doc_parse_type` → `baidu_doc_parse_type` kwarg
- `normalized_options.ocr_provider` → `ocr_provider` kwarg
- `normalized_options.ocr_ai_provider` → `ocr_ai_provider` kwarg
- `normalized_options.ocr_ai_chain_mode` → `ocr_ai_chain_mode` kwarg
- `normalized_options.ocr_ai_layout_model` → `ocr_ai_layout_model` kwarg
- `normalized_options.ocr_geometry_mode` → `ocr_geometry_mode` kwarg
- `normalized_options.text_erase_mode` → `text_erase_mode` kwarg
- `normalized_options.scanned_page_mode` → `scanned_page_mode` kwarg
- `normalized_options.ppt_generation_mode` → `ppt_generation_mode` kwarg

The other Form params (raw, not normalized) are passed as-is.

---

## Caveats / Not Found

- The `enable_layout_assist` and `layout_assist_apply_image_regions` params are deprecated and forced to `False` both in `create_job()` (line 951-952) and `process_pdf_job()` (line 242-243). They still exist in signatures for backward compatibility.
- `mineru_hybrid_ocr` is deprecated and ignored (line 755 comment).
- `ocr_geometry_mode` is deprecated (line 859-865 comment).
- The worker does internal parameter normalization (e.g., `normalize_text_erase_mode`, `normalize_scanned_page_mode`) in addition to the API-level normalization, suggesting some redundancy.
