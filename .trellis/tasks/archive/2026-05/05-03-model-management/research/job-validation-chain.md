# Research: Job Submission Validation Chain

- **Query**: Trace the complete validation flow from frontend "开始转换" click through API submission to worker runtime
- **Scope**: internal
- **Date**: 2026-05-03

## Findings

### Complete Validation Flow Diagram

```
User clicks "开始转换" (handleConvertAll)
│
├─► [Frontend] Pre-checks (synchronous, immediate)
│   ├─ Auth check: user must be logged in
│   ├─ validateRunConfig(settings) → checks:
│   │   ├─ MinerU: mineruApiToken required
│   │   ├─ Baidu: ocrBaiduApiKey + ocrBaiduSecretKey required
│   │   ├─ AIOCR: ocrAiApiKey required
│   │   ├─ AIOCR: ocrAiModel required
│   │   ├─ AIOCR+doc_parser: model must include "paddleocr-vl"
│   │   └─ AIOCR+direct: model must NOT be PaddleOCR-VL
│   ├─ Page range validation (start/end both present, start ≤ end)
│   └─ buildJobConfig() → creates JSON config payload
│
├─► [API] POST /api/v1/jobs/v2 (synchronous, submission time)
│   ├─ JSON parse + Pydantic model_validate (JobConfig schema)
│   │   └─ Field-level constraints: ge/le bounds on ints, Literal types
│   ├─ job_config.to_worker_kwargs() → flat kwargs
│   ├─ validate_and_normalize_job_options() → checks:
│   │   ├─ parse_provider ∈ {local, mineru, baidu_doc, v2}
│   │   ├─ provider alias normalization + validation
│   │   ├─ page_start/page_end must be provided together, ≥ 1, start ≤ end
│   │   ├─ MinerU: mineru_api_token required
│   │   ├─ Baidu doc: baidu_doc_parse_type alias validation
│   │   ├─ ocr_provider ∈ {auto, aiocr, baidu, machine, tesseract, paddle, paddle_local}
│   │   ├─ ocr_ai_provider ∈ {auto, openai, siliconflow, deepseek, ppio, novita}
│   │   ├─ ocr_ai_chain_mode alias validation → {direct, doc_parser, layout_block}
│   │   ├─ ocr_ai_layout_model alias validation → {pp_doclayout_v3}
│   │   ├─ ocr_geometry_mode alias validation → {auto, local_tesseract, direct_ai}
│   │   ├─ text_erase_mode ∈ {smart, fill}
│   │   ├─ scanned_page_mode alias validation → {segmented, fullpage}
│   │   ├─ ppt_generation_mode alias validation → {standard, fast, turbo}
│   │   ├─ Cross-field: ocr_geometry_mode only with aiocr
│   │   ├─ Cross-field: mineru + non-auto ocr_provider = error
│   │   ├─ Cross-field: baidu_doc + non-auto ocr_provider = error
│   │   ├─ AI OCR: ocr_ai_api_key required for aiocr/paddle providers
│   │   ├─ AI OCR: doc_parser chain requires PaddleOCR-VL model
│   │   ├─ AI OCR: direct chain rejects PaddleOCR-VL model
│   │   ├─ AI OCR: ocr_ai_model required for explicit AI OCR
│   │   ├─ Baidu OCR: api_key + secret_key required
│   │   └─ Baidu doc parser: api_key + secret_key required
│   ├─ File type validation (PDF/PNG/JPG/JPEG/WebP)
│   ├─ File size ≤ max_file_mb
│   ├─ Image→PDF conversion (if image upload)
│   └─ Job queued → returns job_id
│
└─► [Worker] process_pdf_job (asynchronous, runtime)
    ├─ Input PDF existence check
    ├─ Parse provider validation (duplicate of API check)
    ├─ parse_pdf_to_ir() / parse_pdf_to_ir_with_mineru() / parse_pdf_to_ir_with_baidu_doc()
    │   ├─ PDF encrypted detection → AppException
    │   ├─ Too many pages detection → AppException
    │   └─ Invalid PDF detection → AppException
    ├─ OCR stage (if scanned pages + OCR enabled):
    │   ├─ setup_ocr_runtime() → creates OCR provider instances
    │   │   ├─ Local tesseract: probes binary availability
    │   │   ├─ Local paddle: probes binary availability
    │   │   ├─ Baidu OCR: validates credentials (runtime call)
    │   │   └─ AI OCR: creates remote client (connects to API)
    │   └─ ocr_image() per page → runtime API calls to AI OCR models
    ├─ PPT generation (LLM calls for layout)
    └─ Error handling:
        ├─ AppException → status=failed, error={code, message, details}
        ├─ JobCancelledError → status=cancelled
        └─ Generic Exception → status=failed, error={code: internal_error, message}
```

### What's Validated Early vs Late

#### ✅ Validated at Submission Time (before job starts)

| Check | Location | Layer |
|---|---|---|
| User authentication | `page.tsx:231` | Frontend |
| MinerU API token present | `run-config.ts:510` + `job_options.py:307` | FE + API |
| Baidu credentials present | `run-config.ts:517` + `job_options.py:494` | FE + API |
| AIOCR API key present | `run-config.ts:542` + `job_options.py:447` | FE + API |
| AIOCR model name present | `run-config.ts:548` + `job_options.py:485` | FE + API |
| AIOCR chain mode + model compatibility | `run-config.ts:551-562` + `job_options.py:456-484` | FE + API |
| Parse provider valid | `job_options.py:288` | API |
| OCR provider valid | `job_options.py:329` | API |
| Page range consistency | `page.tsx:246-253` + `job_options.py:216-242` | FE + API |
| File type (PDF/image) | `page.tsx:77-82` + `jobs.py:83-94` | FE + API |
| File size limit | `jobs.py:993-998` | API |
| PPT generation mode valid | `job_options.py:403` | API |
| Cross-field parse/OCR provider conflicts | `job_options.py:413-444` | API |

#### ❌ Only Validated at Runtime (worker)

| Check | Location | Failure Mode |
|---|---|---|
| PDF encrypted | Worker → `parse_pdf_to_ir` | Job fails with error code `pdf_encrypted` |
| PDF invalid/corrupt | Worker → `parse_pdf_to_ir` | Job fails with error code `invalid_pdf` |
| Too many pages | Worker → `parse_pdf_to_ir` | Job fails with error code `too_many_pages` |
| Local OCR binary missing (tesseract) | Worker → `setup_ocr_runtime` | Job fails at OCR stage |
| Local OCR binary missing (paddle) | Worker → `setup_ocr_runtime` | Job fails at OCR stage |
| AI OCR API unreachable | Worker → `create_remote_ocr_client` / `ocr_image` | Job fails during OCR |
| AI OCR API key invalid | Worker → API call returns 401 | Job fails during OCR |
| AI OCR model not found | Worker → API call returns 404 | Job fails during OCR |
| AI OCR rate limited | Worker → API call returns 429 | Job fails (or retries if configured) |
| MinerU API unreachable | Worker → `parse_pdf_to_ir_with_mineru` | Job fails at parsing stage |
| MinerU API token invalid | Worker → API call returns 401 | Job fails at parsing stage |
| Baidu API unreachable | Worker → `parse_pdf_to_ir_with_baidu_doc` | Job fails at parsing stage |
| Baidu credentials invalid | Worker → API call returns auth error | Job fails at parsing stage |
| LLM API unreachable (PPT gen) | Worker → LLM call | Job fails at generation stage |
| LLM API key invalid | Worker → LLM call returns 401 | Job fails at generation stage |
| Local layout model missing | Worker → `setup_ocr_runtime` | Job fails if layout_block chain selected |

### Current Error Handling

#### Frontend Error Display

1. **Submission errors** (API returns 4xx): Displayed as `actionError` in a red box below the config panel (`page.tsx:1072-1076`)
   - Uses `readResponseErrorMessage()` which parses JSON `{code, message}` from API response
   - Falls back to HTTP status text if no JSON body

2. **Job creation errors** (per-file): Stored in `FileJobState.error`, shown inline next to each file in the converting stage (`page.tsx:1170-1215`)

3. **Runtime errors** (job status polling): 
   - Frontend polls `GET /api/v1/jobs/{job_id}` every 2 seconds
   - When `status === "failed"`, the error is shown from `job.error` or `job.message`
   - The error display in the file job list shows the stage label + error message

4. **Network errors**: `normalizeFetchError()` handles:
   - `AbortError` → "请求已取消"
   - `TypeError` with network/fetch → "网络连接失败，请检查 API 地址与后端 CORS 设置"
   - Other errors → original message

#### API Error Response Format

```json
{
  "code": "validation_error",
  "message": "Human-readable error message",
  "details": { "field": "additional_context" }
}
```

Error codes defined in `ErrorCode` enum: `pdf_encrypted`, `file_too_large`, `too_many_pages`, `invalid_pdf`, `ocr_failed`, `conversion_failed`, `job_not_found`, `internal_error`, `validation_error`, `auth_required`, `auth_failed`, `quota_exceeded`, `forbidden`.

#### Worker Error Propagation

Worker catches errors and updates Redis job metadata:
- `AppException` → `{code, message, details}` stored in `job.error`
- Generic `Exception` → `{code: "internal_error", message: str(e)}` stored in `job.error`
- Frontend reads this via polling and displays to user

### Gaps Where Errors Could Be Caught Earlier

| Gap | Current Behavior | Could Be |
|---|---|---|
| **AI OCR API key validity** | Only validated when worker calls the API | Could pre-flight check with `/ocr/ai/check` endpoint |
| **AI OCR model availability** | Only validated at runtime | Could pre-flight check |
| **Local OCR binary installed** | Only checked at worker startup | Frontend has `/ocr/local/check` endpoint but not called before submission |
| **MinerU API token validity** | Only validated when worker calls MinerU | Could pre-flight check |
| **Baidu credentials validity** | Only validated when worker calls Baidu | Could pre-flight check |
| **LLM API key validity** | Never validated before worker | Could pre-flight check with a lightweight call |
| **LLM model availability** | Never validated before worker | Could pre-flight check |
| **Remote API reachability** | Never validated before worker | Could pre-flight check |

### Existing Pre-flight Check Endpoints

The API already has two check endpoints that could be used for pre-validation:

1. **`POST /api/v1/jobs/ocr/local/check`** (`jobs.py:249-285`)
   - Checks if local OCR runtime (tesseract/paddle) is available
   - Returns `{ok: bool, check: {ready, ...}}`
   - **Not called by frontend before submission**

2. **`POST /api/v1/jobs/ocr/ai/check`** (`jobs.py:502-548`)
   - Runs actual AI OCR probe with a synthetic image
   - Validates API key, model, and bbox output
   - Returns `{ok: bool, check: {ready, valid_bbox_items, ...}}`
   - **Not called by frontend before submission**

### Key File Locations

| File | Description |
|---|---|
| `web/src/app/page.tsx` | Homepage with `handleConvertAll` (line 228) |
| `web/src/lib/run-config.ts` | `validateRunConfig()` (line 506), `buildJobConfig()` (line 652) |
| `web/src/lib/settings.ts` | Settings type definitions and defaults |
| `web/src/lib/api.ts` | `apiFetch()`, error normalization |
| `api/app/routers/jobs.py` | `/v2` endpoint (line 1198), check endpoints (lines 249, 502) |
| `api/app/job_options.py` | `validate_and_normalize_job_options()` (line 245) |
| `api/app/schemas/job_config.py` | `JobConfig` Pydantic model (line 327) |
| `api/app/worker.py` | `process_pdf_job()` (line 119), error handling (lines 962-984) |
| `api/app/models/error.py` | `ErrorCode` enum, `AppException` class |
| `api/app/convert/ocr/local_providers.py` | `create_remote_ocr_client()` (line 101) |
| `api/app/convert/ocr/runtime_probe.py` | `probe_local_tesseract()`, `probe_local_paddleocr()` |

### Validation Duplication Analysis

There is significant duplication between frontend and backend validation:

| Validation | Frontend (`validateRunConfig`) | Backend (`validate_and_normalize_job_options`) |
|---|---|---|
| MinerU token required | ✅ | ✅ |
| Baidu credentials required | ✅ | ✅ |
| AIOCR API key required | ✅ | ✅ |
| AIOCR model required | ✅ | ✅ |
| PaddleOCR-VL chain compat | ✅ | ✅ |
| Parse provider valid | ❌ (hardcoded options) | ✅ |
| OCR provider valid | ❌ (hardcoded options) | ✅ |
| Page range logic | ✅ | ✅ |

The frontend validation is a subset of the backend validation. The backend adds:
- Alias normalization (accepts many variant strings)
- Cross-field constraint validation (parse provider vs OCR provider conflicts)
- Numeric bounds on concurrent settings

### Opportunities for Improvement

1. **Pre-flight validation endpoint**: A single `/api/v1/jobs/validate` endpoint could run all checks that currently only happen at runtime, returning structured results for each check (API key validity, model availability, local binary presence).

2. **Progressive validation**: Instead of all-or-nothing at submission, validate in stages:
   - Stage 1 (immediate): Config syntax + required fields (already done)
   - Stage 2 (pre-submit): API key reachability + model availability
   - Stage 3 (runtime): Actual processing

3. **Better error surfacing**: Currently runtime errors show as generic "Conversion failed" or raw exception messages. Could provide more actionable messages (e.g., "API key expired" instead of "401 Unauthorized").

4. **Local OCR pre-check integration**: The `/ocr/local/check` endpoint exists but isn't called before submission when `parseEngineMode=local_ocr` + `ocrProvider=machine`.

---

## Caveats / Not Found

- The `setup_ocr_runtime()` function in worker was not fully traced (it's in `convert/ocr/local_providers.py`); the exact error messages for missing local binaries are not captured here.
- LLM validation (for PPT generation) was not deeply traced — it's unclear exactly what errors surface when the LLM API key is missing vs invalid vs rate-limited.
- The MinerU and Baidu doc parsing error paths were not fully traced to their API call implementations.
