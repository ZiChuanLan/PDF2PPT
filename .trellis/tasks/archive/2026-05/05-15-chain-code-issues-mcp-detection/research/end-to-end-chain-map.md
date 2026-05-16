# Research: End-to-End Code Chain Map

- **Query**: Map the project's end-to-end code chain with file paths, key symbols, and chain-break boundaries
- **Scope**: Internal
- **Date**: 2026-05-15

## Findings

### 1. Frontend Submit Flow

#### Entry: Home Page (`web/src/app/page.tsx`)
- **Component**: `Home` (default export, line 53)
- Triggers `submitAllJobs()` from `useJobSubmission` hook (line 189)
- Orchestrates 3 stages: `upload` → `preview` → `converting` (line 299-303)
- SSE tracking via `useSSEJobTracking` (line 252)
- Job polling via `fetchJobs` → `apiFetch('/jobs?limit=...')` (line 110-124)
- UI stage steps: `parsing` → `ocr` → `pptx_generating` → `done` (line 312-317)

#### Hook: `use-job-submission.ts` (`web/src/hooks/use-job-submission.ts`)
- **Key function**: `submitAllJobs()` (line 78)
- Flow: `validateRunConfig(settings)` → `buildJobConfig(settings, pageStart, pageEnd, options)` → `apiFetch('/jobs/v2', { method: 'POST', body: FormData })` (line 146-161)
- Builds `FormData` with `file` + `config` (JSON-stringified `JobConfig`)
- Tracks per-file state via `FileJobState[]` with `isSubmitting`, `jobId`, `status`, `error`
- Also handles: cancel (`POST /jobs/{id}/cancel`), download (`GET /jobs/{id}/download`), download-all, reset

#### Config Builder: `run-config.ts` (`web/src/lib/run-config.ts`)
- **Key function**: `buildJobConfig()` (line 614)
- Transforms user-facing `Settings` → structured `JobConfig` matching backend Pydantic schema
- Sub-config blocks: `llm`, `parse` (provider + mineru/baidu_doc), `ocr` (provider + ai + baidu + tesseract), `ppt` (generation_mode, text_erase_mode, scanned_page_mode + image_regions), `page_range`
- Also: `resolveRunConfig()` (line 268), `resolveOcrSettingsState()` (line 365), `validateRunConfig()` (line 466)

#### API Client: `api.ts` (`web/src/lib/api.ts`)
- **Key function**: `apiFetch()` (line 252) — wraps `fetch('/api/v1' + path)` with AbortController timeout and same-origin credentials
- SSE: `createJobEventSource(jobId)` → `EventSource('/api/v1/jobs/' + jobId + '/events')` (line 293)
- Download: via `downloadJobOutput` in `download-utils.ts` → `apiFetch('/jobs/' + jobId + '/download')` → blob → `<a>` click
- Model listing: `fetchModels()` → `POST /api/v1/models`
- API origin resolution: `resolveApiOrigin()` (line 198) probes `/health` on candidate origins

---

### 2. API Job Creation Flow

#### Entry: FastAPI App (`api/app/main.py`)
- Router registration (lines 90-96): `jobs_router`, `models_router`, `auth_router`, `admin_router`, `config_router`, `runtime_config_router`, `setup_router`
- Middleware chain: CORS → request_id → bearer token auth → CSRF → rate limiting
- Lifespan: `init_db()` → `start_job_cleanup_daemon()` (lines 54-58)

#### Router: `routers/jobs.py`
- **Prefix**: `/api/v1/jobs`

##### v1 Endpoint: `POST /` → `create_job()` (line 492)
- 60+ `Form()` parameters → `validate_and_normalize_job_options()` → `_create_job_core()`

##### v2 Endpoint: `POST /v2` → `create_job_v2()` (line 826)
- Receives `File` + `config` (JSON `JobConfig` string)
- Parses `JobConfig.model_validate()` → `to_worker_kwargs()` → `validate_and_normalize_job_options()` → `_create_job_core()`
- **This is the endpoint called by the frontend**

##### Core: `_create_job_core()` (line 152)
1. `_check_disk_space(settings)` — validates available disk
2. `ensure_job_dir(job_id)` — create `{JOB_ROOT}/{uuid}/`
3. Stream upload to `input.pdf` with per-chunk size check (`max_file_mb`)
4. `_write_upload_as_input_pdf()` — normalize image → single-page PDF
5. `_create_job_record_and_check_quotas()` — create Job in Redis, check user quotas
6. `_persist_job_queued()` — mark status=queued in Redis
7. `store_job_secrets()` — store API keys in Redis (separate from RQ kwargs)
8. Strip secret keys from kwargs
9. `_submit_job(job_id, kwargs)` — dispatch to worker

##### Other endpoints:
- `GET /` → `list_jobs()` (line 408) — list with RQ queue metadata
- `GET /{job_id}` → `get_job_status()` (line 918)
- `GET /{job_id}/events` → SSE stream (line 1023)
- `POST /{job_id}/cancel` → cancel (line 1067)
- `DELETE /{job_id}` → delete (line 1127)
- `GET /{job_id}/download` → output.pptx download (line 1189)
- `GET /{job_id}/artifacts` → tracking/debug images (line 1228)
- `GET /{job_id}/artifacts/file` → single artifact (line 1314)

##### Job Options Validation: `job_options.py` (`api/app/job_options.py`)
- `validate_and_normalize_job_options()` — normalizes all enum fields: parse_provider, ocr_provider, ocr_ai_provider, chain_mode, layout_model, text_erase_mode, scanned_page_mode, ppt_generation_mode, etc.

##### Schema: `schemas/job_config.py` (`api/app/schemas/job_config.py`)
- `JobConfig` — Pydantic structured config model
- `to_worker_kwargs()` — converts structured → flat kwargs dict for worker

##### Upload Utils: `routers/_upload_utils.py`
- `classify_upload_kind()`, `normalize_upload_content_type()`, `write_upload_as_input_pdf()`

##### Job Create Utils: `routers/_job_create_utils.py`
- `check_disk_space()`, `create_job_record_and_check_quotas()`, `persist_job_queued()`, `cleanup_job_on_error()`

---

### 3. Queue / Worker Dispatch

#### Dispatch: `_submit_job()` (`routers/jobs.py`, line 89)
- **Memory backend** (`REDIS_URL=memory://`): `threading.Thread(target=process_pdf_job, kwargs={"job_id": ..., "options": ...})` — daemon thread
- **Redis backend**: `Queue(connection=redis_conn).enqueue("app.worker.process_pdf_job", job_id, options=..., job_id=...)` — RQ job

#### Worker Entry: `process_pdf_job()` (`api/app/worker.py`, line 166)
- Key function receives `(job_id, *, options: JobOptions)`
- **Secrets retrieval**: `_retrieve_job_secrets(job_id)` — restore API keys from Redis
- **Processing marker**: writes `{job_dir}/.processing` to prevent cleanup daemon from deleting active jobs
- **Cancellation gate**: early `is_cancelled()` check (line 207)

---

### 4. Pipeline Stages (in `process_pdf_job`, lines 262-843)

The job transitions through these stages, each updating Redis `JobStage`:

#### Stage 1: Parsing (JobStage.parsing, progress 5→22)
- **Routes**:
  - `parse_provider == "mineru"` → `parse_pdf_to_ir_with_mineru()` (`api/app/convert/mineru_adapter.py`)
    - Polls MinerU cloud API, supports formula/table/language/is_ocr
  - `parse_provider == "baidu_doc"` → `parse_pdf_to_ir_with_baidu_doc()` (`api/app/convert/baidu_doc_adapter.py`)
    - Baidu PaddleOCR-VL or general API
  - `parse_provider == "local"` → `parse_pdf_to_ir()` (`api/app/convert/pdf_parser.py`)
    - Local PDF parsing (pymupdf-based text extraction)
  - `parse_provider == "v2"` (legacy) → mapped to local+fullpage+AI OCR
- Output: `ir.json` (document intermediate representation with pages, text blocks, layout)
- Persisted: `ir.parsed.json` (initial), `ir.json` (final after all stages)
- **Key output format**: `{ "pages": [{ "has_text_layer": bool, "ocr_used": bool, ... }], "warnings": [] }`

#### Stage 2: OCR (JobStage.ocr, progress 35→68)
- Entry condition: `parse_provider == "local"` AND `scanned_pages_exist` AND `enable_ocr == True`
- **Setup**: `setup_ocr_runtime()` (`api/app/worker_helpers/ocr_runtime.py`) — probes available OCR engines
- **Execution**: `run_ocr_stage()` (`api/app/worker_helpers/ocr_stage.py`, line 40)
  - **Parallel path** (AI OCR, `page_concurrency > 1`): `_run_parallel_ocr_executor()` → `_ocr_parallel.py`
  - **Sequential path** (default): `_run_sequential_ocr_page_loop()` → `_ocr_page_loop.py`
- OCR engines supported:
  - `tesseract` — local Tesseract via pytesseract
  - `paddleocr` — local PaddleOCR
  - `aiocr` — remote AI OCR (OpenAI-compatible) with chain modes: `direct`, `doc_parser`, `layout_block`
  - `baidu` — Baidu OCR API
- Output: enriched `ir` with OCR text blocks per page

#### Stage 3: Layout Assist (JobStage.layout_assist, progress 72→82)
- Entry condition: `enable_layout_assist == True` AND `llm_provider` available
- **Function**: `run_layout_assist_stage()` (`api/app/worker_helpers/layout_assist_stage.py`, line 33)
- **Core**: `LlmLayoutService(llm_provider).enhance_ir()` (`api/app/convert/llm_adapter.py`)
  - Uses AI (OpenAI/Anthropic) to improve text block grouping, ordering, table detection
  - Option: `layout_assist_apply_image_regions` — detect image regions
- Fallback: if provider missing → `skipped_missing_provider`
- Persisted: `ir.ai.json`, layout debug images

#### Stage 4: PPT Generation (JobStage.pptx_generating, progress 84→97)
- **Function**: `run_ppt_stage()` (`api/app/worker_helpers/ppt_stage.py`, line 60)
- **Core**: `generate_pptx_from_ir()` (`api/app/convert/pptx/generator.py` — `generate_pptx_from_ir()`)
  - Builds python-pptx slides from IR
  - Supports generation modes: `standard`, `fast`, `turbo`
  - `text_erase_mode`: `smart`, `fill`
  - `scanned_page_mode`: `segmented`, `fullpage`
  - Footer removal: `remove_footer_notebooklm`
  - Image region background clearing settings
- Progress callback: `_on_ppt_page_done()` emits granular per-page progress
- Compatibility check: inspects `generate_pptx_from_ir` signature for required features

#### Stage 5: Packaging (JobStage.packaging, progress 98)
- Final step before completion — no separate code, just progress update + final IR persistence

#### Stage 6: Cleanup (JobStage.cleanup)
- On success: `cleanup_job_process_artifacts()` — removes `artifacts/` unless `retain_process_artifacts`
- On failure: error reporting
- Always: remove `.processing` marker, delete job secrets from Redis

---

### 5. Job State Machine

#### Status enum (`api/app/models/job.py`, line 12):
```
pending → processing → completed/failed/cancelled
```

#### Stage enum (line 22):
```
upload_received → queued → parsing → ocr → layout_assist → pptx_generating → packaging → cleanup → done
```

#### Frontend status mapping (`web/src/lib/job-status.ts`):
- `JOB_STAGE_FLOW` (line 97): `[queued, parsing, ocr, layout_assist, pptx_generating, packaging, cleanup, done]`
- `STAGE_FLOW_ALIASES`: `upload_received → queued`
- `TERMINAL_JOB_STATUSES`: `{completed, failed, cancelled}`

#### Redis key structure (`api/app/services/redis_service.py`):
- `job:{job_id}` — serialized `Job` model JSON
- `job:{job_id}:cancel` — cancellation flag
- `job:{job_id}:secrets` — JSON with `api_key`, `mineru_api_token`, `ocr_baidu_api_key`, `ocr_baidu_secret_key`, `ocr_ai_api_key`
- TTL: `job_ttl_minutes` (default 1440 = 24h)

---

### 6. Model Status / Model List Flow

#### Model Status: `GET /api/v1/models/status` (`routers/models.py`, line 292)
- Returns `ModelStatusResponse { local: dict, remote: dict }`
- **Local**: `_check_local_providers()` (line 182)
  - Tesseract probe → `probe_local_tesseract()` (via `convert/ocr/runtime_probe.py`)
  - PaddleOCR probe → `probe_local_paddle_models()`
  - Layout models → `is_model_downloaded()` (via `convert/ocr/layout_models.py`)
- **Remote**: `_check_remote_providers()` (line 234)
  - Checks `site_settings` DB for: `ocr_ai_api_key`, `ocr_baidu_api_key` + `ocr_baidu_secret_key`, `mineru_api_token`

#### Model Listing: `POST /api/v1/models` (`routers/models.py`, line 57)
- **Input**: `{ provider, api_key, base_url?, capability? }`
- Calls provider's model list API (OpenAI/Anthropic)
- Filters by capability: `all`, `vision`, `ocr`
- Normalizes provider via `_model_filtering.py`

#### Frontend Model Status Hook (`web/src/hooks/use-model-status.ts`)
- `useModelStatus()` — fetches `GET /api/v1/models/status`
- `useEffectiveModelStatus()` — enriches with user settings

#### Layout Model Registry (`web/src/lib/layout-models.ts`)
- `LAYOUT_MODELS` — map of downloadable layout detection models

---

### 7. Download / Artifact Tracking Flow

#### Download: `GET /api/v1/jobs/{job_id}/download` (`routers/jobs.py`, line 1189)
- Validates `job.status == completed`
- Serves `{job_dir}/output.pptx` as `FileResponse`

#### Artifacts: `GET /api/v1/jobs/{job_id}/artifacts` (line 1228)
- Returns manifest of artifact images for each processing stage
- Subdirs: `artifacts/page_renders`, `artifacts/final_preview`, `artifacts/ocr`, `artifacts/layout_assist`
- Used by frontend tracking page (`web/src/app/tracking/page.tsx`)

#### Frontend Download: `download-utils.ts` (`web/src/lib/download-utils.ts`)
- `downloadJobOutput()` — retries with 1s delay, blob → `<a>` click

#### Frontend SSE Tracking: `use-sse-job-tracking.ts` (`web/src/hooks/use-sse-job-tracking.ts`)
- Listens to `EventSource` for real-time progress
- Falls back to polling via `fetchJobStatus()`

---

### 8. Task / Archive Governance Code

#### Job Cleanup Daemon (`api/app/services/job_cleanup.py`)
- `start_job_cleanup_daemon()` (line 128) — background thread, runs every `job_cleanup_interval_minutes` (default 15)
- `cleanup_expired_jobs()` (line 38):
  - Scans `{JOB_ROOT}/` for job directories
  - Checks Redis metadata for terminal status + expired TTL
  - Falls back to mtime + ".processing" marker for orphaned dirs
  - Deletes: `shutil.rmtree(job_dir)` + `redis_service.delete_job(job_id)`
- `cleanup_job_process_artifacts()` (line 27) — deletes `artifacts/` subfolder

#### Trellis Task Governance

**Task lifecycle** (`.trellis/scripts/task.py`):
- `create <title>` → creates `{TASK_DIR}/` with `task.json`, `implement.jsonl`, `check.jsonl`
- `start <task-dir>` → flips status to `in_progress`
- `archive <task-dir>` → moves to archive, clears active pointer

**Task state file** (`{TASK_DIR}/task.json`):
- Fields: `status` (planning/in_progress/completed), `created`, `source`, session identity
- Hooks: `after_create`, `after_start`, `after_finish`, `after_archive`

**Context JSONL** (`{TASK_DIR}/implement.jsonl`, `check.jsonl`):
- One JSON object per line: `{"file": "<path>", "reason": "<why>"}`
- Injected by sub-agent platform hooks for spec context

**Workflow state machine** (`.trellis/workflow.md`):
- `no_task` → `planning` (after create) → `in_progress` (after start) → `completed` (after archive)
- Breadcrumb prompts per state with required steps

---

### 9. Key Chain-Break Boundaries

| Boundary | Files Involved | Risk Type |
|---|---|---|
| **Frontend → API (HTTP)** | `api.ts:apiFetch` → FastAPI middleware stack → `routers/jobs.py` | Auth mismatch, CORS, CSRF token, timeout |
| **API → Redis** | `routers/_job_create_utils.py` → `redis_service.py` | Redis connection failure, TTL expiry race |
| **API → Worker (RQ/Thread)** | `_submit_job()` → `worker.py:process_pdf_job` | Thread safety (memory mode), RQ serialization skew |
| **Worker → OCR engines** | `ocr_runtime.py` → tesseract/paddle/aiocr/baidu | Missing binaries, API rate limits, model download state |
| **Worker → Cloud parsing** | `mineru_adapter.py` / `baidu_doc_adapter.py` → external API | Network failure, auth token expiry, unexpected response format |
| **Worker → LLM (layout assist)** | `llm_adapter.py:LlmLayoutService.enhance_ir()` → OpenAI/Anthropic | API key missing, rate limit, timeout |
| **Worker → PPT generation** | `ppt_stage.py` → `convert/pptx/generator.py:generate_pptx_from_ir()` | Feature version mismatch (`worker_compat_mode`), IR schema skew |
| **Worker → Redis (progress)** | `worker.py:_set_processing_progress()` → `redis_service.update_job()` | Concurrent cancellation race, terminal state guard (line 352) |
| **Cleanup daemon → Worker** | `job_cleanup.py` ↔ `worker.py:.processing` marker | Race deleting active unfinished job, orphaned directories |
| **Secrets management** | `_create_job_core` → store + `worker.py` → retrieve → delete | Leaked in RQ job description, not persisted for failed jobs |
| **JobConfig → Worker kwargs** | `schemas/job_config.py:to_worker_kwargs()` → `worker.py:process_pdf_job()` | Schema field mapping drift, missing new fields |

### 10. Data Flow Summary

```
User uploads file
  ↓
page.tsx → useJobSubmission → buildJobConfig(Settings) → apiFetch(POST /api/v1/jobs/v2)
  ↓
FastAPI: main.py middleware → routers/jobs.py:create_job_v2()
  ↓
validate_and_normalize_job_options() + JobConfig.to_worker_kwargs()
  ↓
_create_job_core():
  1. check_disk_space
  2. save input.pdf to {job_dir}/
  3. create Job record in Redis (status=pending)
  4. store secrets in Redis (separate key)
  5. strip secrets from kwargs
  6. _submit_job() → Thread / RQ
  ↓
worker.py:process_pdf_job(job_id, options):
  1. retrieve secrets from Redis
  2. write .processing marker
  3. check cancellation
  ↓
  STAGE: parsing (progress 5→22)
  ├─ local:      parse_pdf_to_ir()          → ir.json
  ├─ mineru:     parse_pdf_to_ir_with_mineru()  → ir.json
  └─ baidu_doc:  parse_pdf_to_ir_with_baidu_doc() → ir.json
  ↓
  STAGE: OCR (progress 35→68, only for local + scanned pages + OCR enabled)
  ├─ setup_ocr_runtime() → choose provider
  ├─ sequential: _run_sequential_ocr_page_loop()
  └─ parallel:   _run_parallel_ocr_executor() (AI OCR only)
  ↓
  STAGE: layout_assist (progress 72→82, if enabled + provider available)
  └─ LlmLayoutService.enhance_ir() → improved IR
  ↓
  STAGE: pptx_generating (progress 84→97)
  └─ generate_pptx_from_ir(ir, output.pptx, ...)
  ↓
  STAGE: packaging → done (progress 98→100)
  ├─ persist final ir.json
  ├─ cleanup artifacts (unless retain)
  └─ delete secrets from Redis
```

---

## Related Specs

- `.trellis/spec/backend/job-config-contracts.md` — JobConfig ↔ worker kwargs contract
- `.trellis/spec/guides/task-governance-thinking-guide.md` — task lifecycle governance patterns
- `.trellis/spec/guides/cross-layer-thinking-guide.md` — cross-layer data flow patterns

## Caveats / Not Found

- Some file paths for deeper sub-modules (e.g., specific OCR adapter files under `convert/ocr/`) were not read in detail — the map covers the top-level orchestration. Inner OCR page-loop and parallel executor implementations are referenced but their internal subcalls are not traced.
- The `convert/pptx/generator.py` and `convert/pptx/slide_builder.py` PPT generation internals are not traced beyond the entry function `generate_pptx_from_ir()`.
- The `convert/_mineru_build_ir.py` MinerU IR builder is referenced but not detailed.
- No tests were read; all analysis is from production code only.
- Task governance code (`.trellis/scripts/task.py`) is referred to by name but its full implementation was not read.
