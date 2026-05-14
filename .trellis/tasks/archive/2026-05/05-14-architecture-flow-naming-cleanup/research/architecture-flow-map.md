# Research: Architecture & End-to-End Flow Map

- **Query**: Full frontend → API → queue → worker → OCR/layout → PPT output architecture map
- **Scope**: Internal (repo inspection only)
- **Date**: 2026-05-14

## Findings

### 1. End-to-End Chain Overview

```
Frontend (web/)                      Backend (api/)
═══════════════════                  ════════════════════════════════════════
page.tsx                              main.py (FastAPI app)
  │                                     ├── routers/jobs.py     (job CRUD)
  ├── useJobSubmission()                ├── routers/models.py   (model listing/status)
  │   └── apiFetch("/jobs/v2") ──POST──→├── routers/admin.py    (admin panel)
  ├── useSSEJobTracking()               ├── routers/auth.py     (auth)
  │   └── EventSource("/jobs/{id}/events") ←── SSE streaming
  ├── fetchJobs() /api/jobs?limit=50 ←── GET /api/v1/jobs
  └── download /api/jobs/{id}/download ←── GET /api/v1/jobs/{id}/download

                                Job Queue (Redis RQ)
                                ══════════════════
                                Thread (memory://) or RQ (Redis)
                                    │
                          worker.py::process_pdf_job()
                            │
                    ┌───────┼───────────┐
                    ▼       ▼           ▼
              parse     OCR      layout_assist  ppt_stage
              stage     stage    stage          (generate_pptx_from_ir)
                    │       │           │           │
                    ▼       ▼           ▼           ▼
              ir.json ← OCR → ir.ai.json → output.pptx
```

### 2. Layer-by-Layer Breakdown

#### 2.1 Frontend → API Submission

| Layer | File | Key Symbol | Role |
|---|---|---|---|
| Home page | `web/src/app/page.tsx` | `Home()` | Entry: upload → preview → converting 3-stage UI |
| Job submission | `web/src/hooks/use-job-submission.ts` | `submitAllJobs()` | Builds FormData, calls `POST /api/v1/jobs/v2` |
| Run config | `web/src/lib/run-config.ts` | `buildJobConfig()` | Converts Settings → structured `JobConfig` JSON |
| API client | `web/src/lib/api.ts` | `apiFetch()` | Same-origin proxy via Next.js rewrites `/api/v1/*` |
| SSE tracking | `web/src/hooks/use-sse-job-tracking.ts` | `useSSEJobTracking()` | Opens EventSource per active job, exponential backoff reconnection |
| Settings | `web/src/lib/settings.ts` | `Settings` type | LocalStorage-persisted; 4 `parseEngineMode` values determine pipeline |

**Submission flow**: `page.tsx` → `useJobSubmission.submitAllJobs()` → `buildJobConfig(settings)` produces structured `JobConfig` → `apiFetch("/jobs/v2", { method: "POST", body: FormData with config JSON })` → backend receives.

#### 2.2 API Router (job creation)

| File | Key Symbol | Role |
|---|---|---|
| `api/app/routers/jobs.py` | `create_job()` (v1, Form params, L491) | 60+ Form params → normalized → `_create_job_core` |
| `api/app/routers/jobs.py` | `create_job_v2()` (v2, JSON config, L825) | Parses `JobConfig` JSON → `to_worker_kwargs()` → normalized → `_create_job_core` |
| `api/app/routers/jobs.py` | `_create_job_core()` (L152) | Shared: stream upload to disk → create Redis record → store secrets → `_submit_job` |
| `api/app/routers/jobs.py` | `_submit_job()` (L89) | Thread (memory://) or RQ `Queue.enqueue()` |
| `api/app/job_options.py` | `validate_and_normalize_job_options()` | Validates + normalizes every option string enum |
| `api/app/schemas/job_config.py` | `JobConfig.to_worker_kwargs()` | Structured → flat kwargs for worker |

**v2 config path**: `JobConfig` schema (`schemas/job_config.py`) → `to_worker_kwargs()` → validates with `validate_and_normalize_job_options()` → calls `_create_job_core()`.

#### 2.3 Queue & Worker

| File | Key Symbol | Role |
|---|---|---|
| `api/app/worker.py` | `process_pdf_job()` (L166) | Main job handler: parse → OCR → layout_assist → PPT |
| `api/app/worker.py` | `run_worker()` (L846) | RQ worker entry point |
| `api/app/worker.py` | `_retrieve_job_secrets()` (L70) | Pulls API keys from Redis (not in RQ kwargs) |
| `api/app/worker_helpers/__init__.py` | `run_ocr_stage`, `run_layout_assist_stage`, `run_ppt_stage` | Module re-exports |
| `api/app/services/redis_service.py` | `RedisService` | Job metadata CRUD, secrets, cancel flags, rate limiting |

**Dispatch modes**:
- **Memory mode** (`REDIS_URL=memory://`): `_submit_job` spawns a `threading.Thread(target=process_pdf_job, ...)` — worker runs inline in the API process.
- **Production mode** (Redis): `_submit_job` calls `Queue.enqueue("app.worker.process_pdf_job", ...)` — worker runs in a separate process.

#### 2.4 Parse Stage (PDF → IR)

| Provider | File | Key Function | Notes |
|---|---|---|---|
| **local** (default) | `api/app/convert/pdf_parser.py` | `parse_pdf_to_ir()` | PyMuPDF-based: extracts text lines, images, tables into IR JSON |
| **mineru** | `api/app/convert/mineru_adapter.py` | `parse_pdf_to_ir_with_mineru()` | Cloud MinerU API → IR |
| **baidu_doc** | `api/app/convert/baidu_doc_adapter.py` | `parse_pdf_to_ir_with_baidu_doc()` | Baidu Doc Parser API → IR |
| **v2** (legacy) | `worker.py` inline (L352-394) | Maps to local + fullpage + AI OCR | Forces `enable_ocr=True`, `scanned_page_mode=fullpage`, routes to SiliconFlow/DeepSeek OCR |

**IR structure** (`ir.json`):
```python
{
  "source_pdf": "path",
  "page_count": N,
  "source_page_count": N,
  "pages": [
    {
      "page_index": int,
      "page_width_pt": float,
      "page_height_pt": float,
      "has_text_layer": bool,
      "elements": [{"type": "text"|"image"|"table", "bbox_pt": [...], ...}],
      "warnings": [...]
    }
  ],
  "warnings": [...]
}
```

**IR persistence**: Three snapshots saved:
1. `ir.parsed.json` — after parse stage
2. `ir.ocr.json` — after OCR stage (in `ocr_stage.py` L224)
3. `ir.ai.json` — after layout assist stage (in `layout_assist_stage.py` L135)
4. `ir.json` — final IR before PPT generation (worker.py L735)

#### 2.5 OCR Stage

| File | Key Symbol | Role |
|---|---|---|
| `api/app/worker_helpers/ocr_stage.py` | `run_ocr_stage()` | Entry: decides sequential vs parallel mode |
| `api/app/worker_helpers/_ocr_page_loop.py` | `_run_sequential_ocr_page_loop()` | Sequential per-page OCR |
| `api/app/worker_helpers/_ocr_parallel.py` | `_run_parallel_ocr_executor()` | Concurrent page OCR (when `page_concurrency > 1` & AI OCR) |
| `api/app/worker_helpers/ocr_runtime.py` | `setup_ocr_runtime()` | Probes local engines, configures OCR manager |
| `api/app/convert/ocr/_ocr_manager.py` | `_OcrManager` | Orchestrates OCR providers: Tesseract, PaddleOCR, Baidu, AI OCR |
| `api/app/convert/ocr/vendors.py` | various | AI OCR vendor adapters (SiliconFlow, DeepSeek, Novita, PPIO) |
| `api/app/convert/ocr/ai_client.py` | `AiOcrClient` | OpenAI-compatible chat completion for AI OCR |

**OCR provider resolution** (complex chain):
1. `setup_ocr_runtime()` in `ocr_runtime.py` — probes local engines, resolves auto-detection
2. `_OcrManager` manages routing: tries primary provider, falls back on failure
3. Supports: `tesseract`, `paddleocr`, `baidu_ocr`, `aiocr` (remote AI)
4. AI OCR chain modes: `direct` (single prompt), `doc_parser` (PaddleOCR-VL), `layout_block` (local layout detection + per-block OCR)

#### 2.6 Layout Assist Stage

| File | Key Symbol | Role |
|---|---|---|
| `api/app/worker_helpers/layout_assist_stage.py` | `run_layout_assist_stage()` | Calls LlmLayoutService.enhance_ir() with OCR+LLM |
| `api/app/convert/llm_adapter.py` | `LlmLayoutService` | OpenAI/Anthropic client for layout enhancement |

Only runs when `enable_layout_assist=True` AND valid provider credentials exist.

#### 2.7 PPT Generation Stage

| File | Key Symbol | Role |
|---|---|---|
| `api/app/worker_helpers/ppt_stage.py` | `run_ppt_stage()` | Entry: configures generator, calls `generate_pptx_from_ir` |
| `api/app/convert/pptx/generator/main.py` | `generate_pptx_from_ir()` | Main PPTX generation, dispatches to scanned/text page builders |
| `api/app/convert/pptx/generator/_text_page.py` | `_build_text_page_slide()` | Text-layer page → editable PPTX elements |
| `api/app/convert/pptx/generator/_scanned_page.py` | `_build_scanned_page_slide()` | Scanned page → background image + overlay blocks |

#### 2.8 Output / Download

| Endpoint | File | Role |
|---|---|---|
| `GET /api/v1/jobs/{id}/download` | `routers/jobs.py:1189` | Returns `output.pptx` as FileResponse |
| `GET /api/v1/jobs/{id}/artifacts` | `routers/jobs.py:1228` | Returns artifact manifest for tracking UI |
| `GET /api/v1/jobs/{id}/events` | `routers/jobs.py:1023` | SSE stream for real-time progress |
| `GET /api/v1/jobs/{id}/artifacts/file` | `routers/jobs.py:1314` | Individual artifact file |
| Download client | `web/src/lib/download-utils.ts` | `downloadJobOutput()` — triggers browser download |

### 3. Job State Machine

```
Status: pending → processing → completed
                   ↓              failed
                   ↓           cancelled
              (via cancel)
```

**JobStage progression**: `upload_received → queued → parsing → ocr → layout_assist → pptx_generating → packaging → done`

**Progress mapping** (worker.py `_set_processing_progress`):
| JobStage | Progress |
|---|---|
| parsing | 5 → 22 |
| ocr | 35 → 68 |
| layout_assist | 72 → 82 |
| pptx_generating | 84 → 97 |
| packaging | 98 |
| done | 100 |

### 4. Key Data Flow: Settings → JobConfig → Worker Kwargs

```
Settings (localStorage)                  JobConfig (JSON POST body)     Worker kwargs (flat dict)
══════════════════════                   ════════════════════════       ════════════════════════
parseEngineMode                                                           parse_provider
├─ "local_ocr"    → parse.provider="local"     ocr.provider="machine"
├─ "remote_ocr"   → parse.provider="local"     ocr.provider="aiocr"
├─ "baidu_doc"    → parse.provider="baidu_doc"  ocr.provider= (omitted)
└─ "mineru_cloud" → parse.provider="mineru"     ocr.provider= (omitted)

ocrProvider        → ocr.provider
ocrAiApiKey        → ocr.ai.api_key
ocrAiModel         → ocr.ai.model
ocrAiChainMode     → ocr.ai.chain_mode
enableLayoutAssist → enable_layout_assist (→ layout_assist in worker)
pptGenerationMode  → ppt.generation_mode

Flow: buildJobConfig(settings) → JobConfig JSON → POST /jobs/v2
      → create_job_v2() parses JobConfig → to_worker_kwargs() → _create_job_core()
```

### 5. Secret Handling Architecture

```
Frontend never sees raw secrets (they stay in localStorage/settings).

POST /jobs/v2:
  - secrets arrive in to_worker_kwargs() output (ocr_ai_api_key, ocr_baidu_api_key, etc.)
  - _create_job_core() extracts secrets → store_job_secrets() into Redis (hashed key)
  - kwargs cleaned before RQ enqueue (secrets replaced with None)

Worker process_pdf_job():
  - _retrieve_job_secrets() pulls from Redis
  - Merges into JobOptions
  - finally: delete_job_secrets() cleans up
```

### 6. Naming Drifts & Responsibility Boundary Issues

#### Hotspot 1: `enable_layout_assist` hardcoded to `False` in v2 `to_worker_kwargs()`

**File**: `api/app/schemas/job_config.py` lines 390-391
```python
"enable_layout_assist": False,         # ← HARDCODED
"layout_assist_apply_image_regions": False,  # ← HARDCODED
```

**Impact**: The `JobConfig` model has `enable_layout_assist` and `layout_assist_apply_image_regions` as top-level fields, and `buildJobConfig()` in `run-config.ts` sets them from user settings. But `to_worker_kwargs()` ignores these fields and always produces `False`. This means layout assist is **silently disabled for all v2 API submissions** even when the user enables it in settings.

**Root cause**: When `JobConfig` was introduced, `to_worker_kwargs()` was written with hardcoded stubs instead of reading the actual fields.

#### Hotspot 2: Frontend stage step code `"generating"` ≠ backend `"pptx_generating"`

**File**: `web/src/app/page.tsx` lines 307-311
```typescript
const STEPS = [
  { code: "parsing", label: "解析" },
  { code: "ocr", label: "OCR" },
  { code: "generating", label: "生成" },     // ← "generating" not "pptx_generating"
  { code: "done", label: "完成" },
]
```

**Impact**: The stage-step UI uses its own simplified codes that don't match backend `JobStage` values. The mapping in `flowToStep[8] = [0, 0, 1, 2, 2, 3, 3, 3]` is fragile — it works only because 8 backend stages map down to 4 frontend steps by index, but a reader can't easily verify correctness.

#### Hotspot 3: Home UI stage labels vs backend `JOB_STAGE_LABELS` duplication

**File**: `web/src/app/page.tsx` L307-311 vs `web/src/lib/job-status.ts` L67-76

The home page has its own hardcoded stage step definitions that partially overlap with `JOB_STAGE_LABELS` in `job-status.ts`. The `job-detail-card.tsx` component uses `JOB_STAGE_LABELS` directly, but the home page uses custom `STEPS` — two different label sources for the same backend data.

#### Hotspot 4: `ParseEngineMode` vs `parse_provider` cross-layer name mismatch

| Frontend (settings.ts) | Backend `parse_provider` | Notes |
|---|---|---|
| `local_ocr` | `local` | Frontend implies OCR, backend just means "local PyMuPDF parse" |
| `remote_ocr` | `local` | Confusing: "remote" in frontend but "local" parse_provider |
| `baidu_doc` | `baidu_doc` | Consistent |
| `mineru_cloud` | `mineru` | Frontend adds "_cloud" suffix, backend doesn't |

The frontend `parseEngineMode` mixes parse provider AND OCR strategy into a single enum; the backend separates them. This creates complex mapping logic in `resolveParseEngineMode()` (run-config.ts:183-203) and cross-validation in `job_options.py`.

#### Hotspot 5: `parser` vs `parse` naming (inconsistent abbreviation)

The `_create_job_core()` function in `routers/jobs.py` receives `parse_provider` after normalization. But this value is stored in the `api/app/convert/pdf_parser.py` module and accessed through `normalize_parse_provider()` in `job_options.py`. The `schemas/job_config.py` calls it `ParseConfig.provider`. The inconsistency is minor but noticeable: `parser` vs `parse`.

#### Hotspot 6: `mineru_hybrid_ocr` deprecated but still in kwargs path

**File**: `api/app/worker.py` line 399: `if options.mineru_hybrid_ocr is not None:` — logs warning but still accepts.  
**File**: `api/app/schemas/job_config.py` line 408: `"mineru_hybrid_ocr": False,` — emits it unconditionally.

The `to_worker_kwargs()` still includes `"mineru_hybrid_ocr": False` even though the worker ignores it. Should be removed.

#### Hotspot 7: OCR geometry mode `"auto"` vs explicit aliases

The `normalize_ocr_geometry_mode()` in `job_options.py` handles ~8 aliases but the field is only meaningful when `ocr_provider=aiocr`. The frontend doesn't expose this setting in the UI, but it's always sent as `"auto"` in kwargs. The cross-validation (`job_options.py` L440-449) rejects non-auto modes for non-AIOCR providers — reasonable but adds complexity.

#### Hotspot 8: Progress bar frontend uses different schemes

The home page multi-file stepper (`page.tsx` L306-328) uses a simplified 4-step mapping (`parsing/ocr/generating/done`), while the job detail card in `tracking/` page uses the full 8-stage `JOB_STAGE_FLOW`. There is no shared mapping utility between the two.

#### Hotspot 9: Redis `get_job()` deserialization vs `Job` model

The `RedisService` stores job metadata as JSON strings. The `get_job()` method must reconstruct `Job` model instances. This creates a tight coupling between the serialization format and the Pydantic model. Any field rename in `Job` requires migrating existing Redis data.

## Top 5 Cleanup Hotspots

1. **`schemas/job_config.py` L390-391**: `enable_layout_assist` and `layout_assist_apply_image_regions` hardcoded to `False` in `to_worker_kwargs()`. Should use `self.enable_layout_assist` and `self.layout_assist_apply_image_regions` instead.

2. **`web/src/app/page.tsx` L307-311 vs `web/src/lib/job-status.ts`**: Home page's `STEPS` array uses `"generating"` as a stage code, but the backend uses `"pptx_generating"`. The `flowToStep` mapping array is opaque and fragile.

3. **`schemas/job_config.py` L408**: `mineru_hybrid_ocr: False` → deprecated flag that's always emitted but always ignored by the worker. Remove from `to_worker_kwargs()`.

4. **Frontend `parseEngineMode` vs backend `parse_provider`+`ocr_provider`**: The frontend encodes both parse and OCR strategy into one enum. This requires non-obvious mapping in both `run-config.ts` (frontend) and `job_options.py` (backend). A future refactor could flatten this into two independent controls.

5. **`api/app/services/redis_service.py`**: Job metadata is stored/loaded as JSON, with `Job` Pydantic model coupling. There are no migration helpers if the model changes. Consider adding a schema version field to the stored JSON.

### Related Specs

- `.trellis/spec/backend/index.md` — backend coding guidelines
- `.trellis/spec/frontend/index.md` — frontend coding guidelines
- `.trellis/spec/guides/cross-layer-thinking-guide.md` — data flow across layers
- `.trellis/spec/guides/code-reuse-thinking-guide.md` — pattern duplication awareness

## Caveats / Not Found

- The `/api/v1/jobs/v2` endpoint still uses Form-encoded `file` + `config` string (not pure JSON POST) — this is because the file upload and structured config are combined in a single multipart request. This is a pragmatic design choice, not a bug.
- The `_create_job_core()` function is not easily mockable for tests — it directly calls `settings`, `get_redis_service()`, file system operations, and `_submit_job()`. Tests work around this via the memory backend.
- Some CSS/UI component files (settings sections, tracking components) were not inspected in detail. The naming analysis focused on data flow files.
