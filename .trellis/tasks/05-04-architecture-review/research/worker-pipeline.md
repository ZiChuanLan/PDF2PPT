# Research: Worker Processing Pipeline

- **Query**: Research the Worker processing pipeline in the pdf2ppt project
- **Scope**: internal
- **Date**: 2026-05-04

## Findings

### Files Found

| File Path | Description |
|---|---|
| `api/app/worker.py` | Main RQ worker entry point and `process_pdf_job` handler (1018 lines) |
| `api/app/worker_helpers/__init__.py` | Exports all worker helper functions |
| `api/app/worker_helpers/ocr_stage.py` | OCR processing stage with parallel/sequential modes (1249 lines) |
| `api/app/worker_helpers/ppt_stage.py` | PPTX generation stage (174 lines) |
| `api/app/worker_helpers/ocr_runtime.py` | OCR runtime setup and configuration (646 lines) |
| `api/app/worker_helpers/layout_assist_stage.py` | AI layout assist stage (192 lines) |
| `api/app/worker_helpers/guarded.py` | Thread-safe blocking operation runner with cancel/heartbeat (63 lines) |
| `api/app/worker_helpers/debug.py` | Debug image export and OCR runtime diagnostics (299 lines) |
| `api/app/worker_helpers/layout.py` | Layout utility functions |
| `api/app/worker_helpers/geometry_utils.py` | Geometry conversion utilities |
| `api/app/convert/pdf_parser.py` | PDF parsing with PyMuPDF → IR generation (340 lines) |
| `api/app/convert/mineru_adapter.py` | MinerU API integration (1967 lines) |
| `api/app/convert/baidu_doc_adapter.py` | Baidu document parser integration (1178 lines) |
| `api/app/convert/pptx/generator.py` | PPTX generation from IR (2221 lines) |
| `api/app/convert/ocr/__init__.py` | OCR package facade |
| `api/app/convert/ocr/local_providers.py` | Local OCR providers (Tesseract, Paddle, Baidu) and OcrManager (3838 lines) |
| `api/app/convert/ocr/ai_client.py` | AI OCR client for remote providers |
| `api/app/convert/ocr/routing.py` | OCR route planning and provider selection |
| `api/app/services/redis_service.py` | Redis job metadata storage (413 lines) |
| `api/app/services/job_cleanup.py` | Job artifact cleanup daemon (162 lines) |
| `api/app/models/job.py` | Job, JobStage, JobStatus models (326 lines) |
| `api/app/models/error.py` | AppException and ErrorCode definitions (57 lines) |
| `api/app/perf_policies.py` | Performance settings and artifact export policies (105 lines) |
| `api/app/utils/concurrency.py` | Daemon thread with timeout helper (46 lines) |
| `api/app/job_paths.py` | Job directory path resolution (87 lines) |

### Architecture Overview

The pipeline uses **RQ (Redis Queue)** for background job processing. The main entry point is `process_pdf_job()` in `worker.py`.

#### Pipeline Stages (sequential)

```
1. Upload & Queue → 2. Parsing → 3. OCR → 4. Layout Assist → 5. PPTX Generation → 6. Packaging → 7. Cleanup
```

**Job Stages** (from `models/job.py`):
- `upload_received` → `queued` → `parsing` → `ocr` → `layout_assist` → `pptx_generating` → `packaging` → `cleanup` → `done`

### Stage Details

#### 1. Job Initialization (worker.py:119-271)

- Sets up Redis service, performance settings, job paths
- Creates job directory structure: `{job_id}/input.pdf`, `{job_id}/output.pptx`, `{job_id}/ir.json`, `{job_id}/artifacts/`
- Checks cancellation flag before starting
- Normalizes ~50+ configuration parameters (OCR provider, DPI, concurrency, etc.)

#### 2. PDF Parsing Stage (worker.py:442-639)

**Three parse providers:**
- `local` — PyMuPDF-based parsing (`pdf_parser.py`)
- `mineru` — MinerU cloud API (`mineru_adapter.py`)
- `baidu_doc` — Baidu document parser API (`baidu_doc_adapter.py`)
- `v2` — Legacy mode, routes through local with forced OCR

**Local parsing** (`pdf_parser.py:200-340`):
- Opens PDF with PyMuPDF
- Extracts text elements (font, size, color, bold/italic)
- Extracts images (saved to `artifacts/images/`)
- Extracts tables via `page.find_tables()`
- Detects `has_text_layer` per page
- Returns IR: `{source_pdf, page_count, pages: [{page_index, page_width_pt, page_height_pt, elements, has_text_layer}]}`

**MinerU/Baidu parsing:**
- Cloud-based async polling with cancel checks
- Poll callbacks refresh job TTL and check cancellation
- Returns same IR structure

**Progress**: 5% → 22% during parsing

#### 3. OCR Stage (worker_helpers/ocr_stage.py)

**Condition**: Only runs when `parse_provider=local` AND scanned pages exist (no text layer) AND `enable_ocr=True`

**OCR Runtime Setup** (`ocr_runtime.py:91-527`):
- Creates `OcrManager` with provider chain (Tesseract, PaddleOCR, Baidu, AI OCR)
- Configures text refiner and linebreak refiner (AI post-processing)
- Route planning via `build_ocr_route_plan()`
- Supports strict mode (fail fast) vs best-effort mode (degrade gracefully)

**Two execution modes:**

1. **Sequential mode** (default, `page_concurrency=1`):
   - Iterates pages one by one
   - Renders PDF page to image at `ocr_render_dpi`
   - Calls `ocr_image_to_elements()` with timeout
   - Detects image regions per page
   - Exports overlay images for debugging

2. **Parallel mode** (`page_concurrency > 1` AND AI OCR):
   - Uses `ThreadPoolExecutor` with `page_concurrency` workers
   - Each page gets its own OCR runtime instance (`ocr_runtime_factory`)
   - Sliding window: submits new page as each completes
   - Total timeout: `ocr_total_timeout_s` (default 3600s)

**Timeout handling:**
- Per-page timeout: `ocr_page_timeout_s` (default 300s)
- Consecutive timeout circuit breaker: `ocr_max_consecutive_timeouts` (default 2)
- Image region detection timeout: `ocr_image_region_timeout_s` (default 12s)

**Progress**: 35% → 68% during OCR

#### 4. Layout Assist Stage (worker_helpers/layout_assist_stage.py)

**Currently disabled** in production (`enable_layout_assist = False` forced at line 242)

When enabled:
- Uses LLM provider (OpenAI/Anthropic) to enhance IR layout
- Runs `LlmLayoutService.enhance_ir()` with cancel/heartbeat guards
- Applies AI-detected tables
- Exports debug images comparing before/after

**Progress**: 72% → 82%

#### 5. PPTX Generation Stage (worker_helpers/ppt_stage.py)

- Calls `generate_pptx_from_ir()` from `convert/pptx/generator.py`
- Runs in guarded thread (`run_blocking_with_guards`) with cancel/heartbeat
- Supports worker compat mode (detects missing generator features)
- Three generation modes: normal, fast, turbo (affects DPI and image region detection)

**Progress**: 84% → 98%

#### 6. Cleanup (worker.py:986-999)

- `cleanup_job_process_artifacts()` removes `artifacts/` directory
- Skipped if `retain_process_artifacts=True`
- Always runs in `finally` block

### Error Handling

**Exception hierarchy:**
- `JobCancelledError` — internal control flow for cancellation
- `AppException` — structured errors with `ErrorCode` enum
- Generic `Exception` — caught as fallback

**Error codes** (`models/error.py`):
- `PDF_ENCRYPTED`, `FILE_TOO_LARGE`, `TOO_MANY_PAGES`, `INVALID_PDF`
- `OCR_FAILED`, `CONVERSION_FAILED`
- `JOB_NOT_FOUND`, `INTERNAL_ERROR`, `VALIDATION_ERROR`
- `AUTH_REQUIRED`, `AUTH_FAILED`, `QUOTA_EXCEEDED`, `FORBIDDEN`

**Error handling pattern:**
- `JobCancelledError` → log and return (status already set to cancelled)
- `AppException` → set status=failed with structured error
- Generic `Exception` → set status=failed with INTERNAL_ERROR

### Resource Management

**Memory:**
- PDF pages rendered to images at configurable DPI (72-400)
- Fast/turbo modes cap DPI at 120/160
- Each OCR page creates a PNG image in `artifacts/ocr/`
- Parallel OCR creates multiple images simultaneously

**Disk:**
- Job artifacts stored in `{job_root_dir}/{job_id}/`
- Includes: `input.pdf`, `output.pptx`, `ir.json`, `ir.parsed.json`, `ir.ocr.json`, `ir.ai.json`, `artifacts/`
- Cleanup daemon runs periodically (default every 15 minutes)
- Job TTL: default 1440 minutes (24 hours)

**GPU:**
- No explicit GPU management in worker code
- OCR providers (PaddleOCR, Tesseract) may use GPU if available
- AI OCR is remote API-based, no local GPU usage

**Concurrency:**
- `run_blocking_with_guards()` — thread with cancel polling and heartbeat
- `run_in_daemon_thread_with_timeout()` — daemon thread with timeout
- OCR parallel mode uses `ThreadPoolExecutor`
- Redis operations are thread-safe

### Progress Reporting

**Redis-based updates:**
- `_set_processing_progress(stage, progress, message)` updates job in Redis
- Progress is clamped 0-99 during processing, 100 on completion
- Progress never goes backwards (monotonically non-decreasing)
- Each update checks cancellation flag

**Debug events:**
- `RedisService.append_debug_event()` stores recent events (default limit 200)
- Events include: seq, timestamp, level, message, source, stage, progress
- Deduplication: skips identical consecutive events

### Cancellation

**Mechanism:**
- Redis key `job:{job_id}:cancel` acts as cancellation flag
- `_abort_if_cancelled()` checks flag at multiple points
- Raises `JobCancelledError` to unwind stack
- Checked: before parsing, before OCR, during OCR page iteration, before PPTX generation

**Cancellation points:**
- Before each stage starts
- Before/after each OCR page
- During polling (MinerU/Baidu)
- In heartbeat callbacks

### Heartbeat/TTL

- `refresh_job_ttl()` extends Redis TTL during long operations
- Default keepalive interval: 15 seconds
- Used in `run_blocking_with_guards()` for PPTX generation and layout assist
- MinerU/Baidu polling also refreshes TTL

### Temporary File Management

**Created during processing:**
- `artifacts/images/` — extracted PDF images
- `artifacts/ocr/` — OCR rendered pages, overlay images, debug JSON
- `artifacts/mineru/` or `artifacts/baidu_doc/` — cloud parser outputs
- `artifacts/layout_assist/` — layout assist debug images
- `ir.parsed.json`, `ir.ocr.json`, `ir.ai.json` — intermediate IR snapshots

**Cleanup:**
- `cleanup_job_process_artifacts()` deletes entire `artifacts/` directory
- Runs in `finally` block unless `retain_process_artifacts=True`
- Cleanup daemon handles expired jobs

### Potential Issues

1. **Memory pressure from parallel OCR**: Multiple pages rendered simultaneously at high DPI could consume significant memory. No explicit memory limits.

2. **Thread safety in OCR manager**: `_process_parallel_ai_ocr_page` creates separate OCR runtime per page via `ocr_runtime_factory`, but the factory calls `setup_ocr_runtime()` which may have shared state.

3. **No retry mechanism in worker**: RQ handles job-level retries, but individual OCR page failures are handled with best-effort degradation, not page-level retries.

4. **Timeout cascading**: Per-page timeout + total timeout + consecutive timeout circuit breaker create complex timeout interactions.

5. **Disk space**: Large PDFs with many images can consume significant disk space before cleanup.

6. **Cleanup daemon race condition**: If a job is still processing when cleanup runs, it could delete artifacts. Mitigated by checking terminal status.

7. **Redis connection handling**: Falls back to in-memory store if Redis unavailable, but in-memory store doesn't persist across restarts.

8. **OCR provider chain complexity**: Multiple providers with fallback, strict/best-effort modes, and AI provider disable logic create complex state management.

### Code Patterns

**Guarded execution pattern** (used throughout):
```python
run_blocking_with_guards(
    lambda: some_blocking_operation(),
    cancel_check=lambda: abort_if_cancelled(...),
    operation_name="operation",
    heartbeat=heartbeat,
    heartbeat_interval_s=keepalive_interval_s,
)
```

**Progress reporting pattern:**
```python
_set_processing_progress(
    JobStage.ocr,
    progress_value,
    f"OCR 识别中（{completed}/{total} 页）",
)
```

**Cancellation check pattern:**
```python
abort_if_cancelled(stage=JobStage.ocr, message="Job cancelled")
```

### Related Specs

- `.trellis/spec/backend/index.md` — Backend spec index
- `.trellis/spec/frontend/index.md` — Frontend spec index

## Caveats / Not Found

- No explicit memory limits or resource quotas in worker code
- No metrics/observability integration (Prometheus, etc.)
- No distributed tracing
- No explicit GPU memory management
- Worker compat mode detection suggests generator API may change independently
