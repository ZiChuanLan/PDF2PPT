# Research: Backend Core Conversion Pipeline

- **Query**: Deep exploration of PDF2PPT backend architecture — full conversion flow, OCR backends, job queue, PPTX generation, caching, file management
- **Scope**: internal
- **Date**: 2026-05-09

## Architecture Diagram (Text-Based)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      FASTAPI APPLICATION (main.py)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │jobs_router│ │models_rt│ │ admin_rt │ │ auth_rt │ │config_rt │ │
│  │ /api/v1/  │ │ /api/v1/ │ │ /api/v1/ │ │/api/v1/ │ │/api/v1/  │ │
│  │  jobs/*   │ │ models/* │ │ admin/*  │ │ auth/*  │ │ config/* │ │
│  └─────┬─────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│        │                                                            │
│        │ create_job() ──► enqueues into RQ or inline thread         │
│        ▼                                                            │
│  ┌─────────────┐                                                    │
│  │ Middleware   │  bearer-auth, rate-limit, request-id              │
│  └─────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     JOB QUEUE SYSTEM (RQ + Redis)                    │
│                                                                     │
│  ┌──────────────┐     ┌────────────────────────────────────────┐   │
│  │ RedisService  │────►│ Redis (job:*, cancel flags, secrets)    │   │
│  │ (singleton)   │     │ • KEY: job:{id}  → Job(pydantic JSON)  │   │
│  │               │     │ • KEY: job:{id}:cancel → "1"           │   │
│  │  create_job() │     │ • KEY: job:{id}:secrets → API keys     │   │
│  │  update_job() │     │ • TTL: 1440 min (24h) default          │   │
│  │  get_job()    │     └────────────────────────────────────────┘   │
│  │  list_jobs()  │                                                  │
│  │  rate_limit() │                                                  │
│  └──────────────┘                                                   │
│                                                                     │
│  ┌──────────────────────┐    ┌─────────────────────────────────┐   │
│  │ RQ Worker (worker.py) │    │ In-Memory Backend (REDIS_URL=   │   │
│  │ process_pdf_job()     │    │ memory:// for local QA/dev)     │   │
│  │ ────────────────────  │    │ • Thread per job (inline)       │   │
│  │ Queue("default")      │    │ • _InMemoryRedis class          │   │
│  │ Worker.work()         │    │ • No RQ dependency needed       │   │
│  └──────────────────────┘    └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼  (process_pdf_job)
┌─────────────────────────────────────────────────────────────────────┐
│                    CONVERSION PIPELINE (worker.py)                   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ STAGE 1: PARSING (progress 5→30)                              │  │
│  │                                                                │  │
│  │  parse_provider?                                               │  │
│  │  ├── "local"  → parse_pdf_to_ir()           (PyMuPDF)         │  │
│  │  │              ──► IR {pages[], elements[{text,image,table}]} │  │
│  │  │              ──► Saves ir.parsed.json                      │  │
│  │  ├── "mineru" → parse_pdf_to_ir_with_mineru() (httpx async)  │  │
│  │  │              ──► Uploads PDF, polls MinerU API              │  │
│  │  │              ──► Downloads .zip, unpacks markdown/images   │  │
│  │  │              ──► Converts to IR via _build_ir_from_mineru  │  │
│  │  ├── "baidu_doc" → parse_pdf_to_ir_with_baidu_doc()          │  │
│  │  │              ──► Obtains OAuth token via API                │  │
│  │  │              ──► Creates doc parser task, polls for result  │  │
│  │  │              ──► Supports "general" and "paddle_vl" types   │  │
│  │  │              ──► Converts to IR (shared mineru IR builder)  │  │
│  │  └── "v2"    → legacy: routes through "local" + forces OCR    │  │
│  │                 Sets AI OCR to SiliconFlow/DeepSeek-OCR        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                               │                                     │
│                               ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ STAGE 2: OCR (progress 35→82) — only for "local" parse mode   │  │
│  │          + pages without has_text_layer + enable_ocr=True      │  │
│  │                                                                │  │
│  │  setup_ocr_runtime() → OcrSetup {ocr_manager, text_refiner,   │  │
│  │                          linebreak_refiner, ...}               │  │
│  │                                                                │  │
│  │  OCR Provider Resolution (ocr_provider param):                 │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │ "auto"     → hybrid_auto: tries local(tesseract) first, │  │  │
│  │  │              falls back to paddle, then aiocr            │  │  │
│  │  │ "tesseract"→ TesseractOcrClient (pytesseract)           │  │  │
│  │  │ "paddle"   → PaddleOcrClient (paddleocr)                │  │  │
│  │  │ "baidu"    → BaiduOcrClient (baidu-aip API)             │  │  │
│  │  │ "aiocr"    → AiOcrClient (OpenAI-compatible vision API) │  │  │
│  │  │              • Chain modes:                              │  │  │
│  │  │                - "direct" (remote_prompt_ocr)            │  │  │
│  │  │                - "doc_parser" (PaddleOCR-VL via API)     │  │  │
│  │  │                - "layout_block" (local layout + remote)  │  │  │
│  │  │              • Vendor adapters: auto, openai,            │  │  │
│  │  │                siliconflow, deepseek, ppio, novita       │  │  │
│  │  │              • Rate limits: RPM, TPM configurable        │  │  │
│  │  │              • Concurrency: page (1-8), block (1-8)      │  │  │
│  │  │              • Linebreak assist (optional AI refinement) │  │  │
│  │  │ "paddle"   → routes to paddle_vl doc_parser (remote)      │  │  │
│  │  │ "paddle_   → PaddleOcrClient (local paddle model)         │  │  │
│  │  │  local"    │                                               │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  run_ocr_stage() processes page-by-page:                       │  │
│  │  • Timeouts: page=300s, total=3600s, image_region=12s         │  │
│  │  • Circuit breaker: 2 consecutive timeouts → skip remaining    │  │
│  │  • Per-page DPI caps: turbo≤120, fast≤160, standard=200       │  │
│  │  • Outputs: ocr_debug.json, OCR text elements in IR           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                               │                                     │
│                               ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ STAGE 3: LAYOUT ASSIST (progress 82→84) — DISABLED by default│  │
│  │                                                                │  │
│  │  run_layout_assist_stage()                                     │  │
│  │  • Uses main AI key (or OCR AI key as fallback)                │  │
│  │  • Providers: OpenAI-compatible or Anthropic                   │  │
│  │  • Currently hardcoded OFF: enable_layout_assist=False         │  │
│  │  • Worker line 347: "Product-side AI layout assist has been    │  │
│  │    retired for speed-focused runs."                             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                               │                                     │
│                               ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ STAGE 4: PPTX GENERATION (progress 84→99)                     │  │
│  │                                                                │  │
│  │  run_ppt_stage() → generate_pptx_from_ir()                    │  │
│  │                                                                │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │ pdf2ppt/convert/pptx/generator.py                        │  │  │
│  │  │                                                          │  │  │
│  │  │ • Uses python-pptx library (Presentation API)            │  │  │
│  │  │ • Slide size: matches PDF page or force 16:9             │  │  │
│  │  │ • Generation modes:                                       │  │  │
│  │  │   - "standard": full-quality, smart text erase            │  │  │
│  │  │   - "fast": speed-optimized, DPI cap 120                  │  │  │
│  │  │   - "turbo": max speed, DPI cap 120, no preview exports  │  │  │
│  │  │                                                          │  │  │
│  │  │ For scanned pages (no text layer):                       │  │  │
│  │  │ 1. Render page to PNG via PyMuPDF (get_pixmap)           │  │  │
│  │  │ 2. Detect image regions (edge-detection + BFS)           │  │  │
│  │  │ 3. Erase OCR text from background (GaussianBlur fill)    │  │  │
│  │  │ 4. Overlay cropped images + editable text shapes         │  │  │
│  │  │ 5. NotebookLM footer detection/removal                   │  │  │
│  │  │                                                          │  │  │
│  │  │ For text pages (has text layer):                         │  │  │
│  │  │ 1. Place text boxes directly (font, color, size from IR) │  │  │
│  │  │ 2. Place embedded images from PDF                        │  │  │
│  │  │ 3. Build tables from PyMuPDF detected tables             │  │  │
│  │  │ 4. Handle markdown sanitization for MinerU/Baidu output  │  │  │
│  │  │                                                          │  │  │
│  │  │ Key submodules:                                          │  │  │
│  │  │ • slide_builder.py: transforms, font sizing, element iter│  │  │
│  │  │ • scanned_page.py: renders, erase, image region analysis │  │  │
│  │  │ • bbox_utils.py: bbox manipulation, padding              │  │  │
│  │  │ • color_utils.py: background/text color sampling         │  │  │
│  │  │ • font_utils.py: CJK detection, text wrapping, OCR fonts │  │  │
│  │  │ • constants.py: SlideTransform, EMU/PT conversions       │  │  │
│  │  │ • preview.py: final preview image export                 │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                               │                                     │
│                               ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ CLEANUP                                                       │  │
│  │ • Remove processing marker (.processing)                      │  │
│  │ • Delete job secrets from Redis                               │  │
│  │ • Cleanup process artifacts (unless retain_process_artifacts) │  │
│  │ • Remove ir.parsed.json intermediate file                     │  │
│  │ • Write ir.json (final IR for debugging)                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Files and Their Roles

### Entry & Configuration
| File Path | Description |
|---|---|
| `api/app/main.py` | FastAPI app entry, lifespan (DB init + cleanup daemon), CORS, 7 routers, bearer auth middleware, rate limiting (60 req/60s per IP) |
| `api/app/config.py` | Settings from env (pydantic-settings): Redis URL, DPI defaults (200), timeouts (300s page, 3600s total), rate limits, JWT, OAuth |
| `api/app/perf_policies.py` | RuntimePerformanceSettings dataclass: artifact export controls, DPI resolution, keepalive intervals |

### Router Layer (FastAPI Endpoints)
| File Path | Description |
|---|---|
| `api/app/routers/jobs.py` | Main endpoint file (~1400 lines): POST create_job (Form + V2 JSON), GET list_jobs, SSE status, cancel, file download, OCR capability checks (local + AI), artifact listing. Handles file upload streaming (1MB chunks), disk space check, user quotas |
| `api/app/routers/auth.py` | LinuxDo OAuth + admin login (JWT token, cookie-based) |
| `api/app/routers/admin.py` | Admin dashboard: user management, site settings, rate limits |
| `api/app/routers/models.py` | AI model management (CRUD for model presets) |
| `api/app/routers/model_status.py` | Model probe/status checks |
| `api/app/routers/config.py` | System configuration endpoints |
| `api/app/routers/setup.py` | Initial setup wizard (first admin creation) |

### Job Queue & State Management
| File Path | Description |
|---|---|
| `api/app/worker.py` | The core job handler: `process_pdf_job()` (1147 lines) — receives RQ job with ~60 kwargs, orchestrates the 4-stage pipeline. Also `run_worker()` for RQ Worker process. |
| `api/app/services/redis_service.py` | RedisService singleton: job CRUD (create/get/update/delete), cancel flag, secrets storage (separate key), rate limiting (sliding window), list_jobs, user quota counting. Also has `_InMemoryRedis` fallback for REDIS_URL=memory:// |
| `api/app/models/job.py` | Pydantic models: Job, JobStatus enum (pending→processing→completed/failed/cancelled), JobStage enum (upload_received→queued→parsing→ocr→layout_assist→pptx_generating→packaging→cleanup→done), plus OCR check request/response models |
| `api/app/job_paths.py` | Centralized path resolution: get_job_root_dir(), get_job_dir(), ensure_job_dir(), resolve_artifact_file(). Default: `api/data/jobs/{job_id}/` |
| `api/app/services/job_cleanup.py` | Background daemon thread: sweeps expired jobs (24h TTL), removes job directories from disk, handles `.processing` marker for active jobs |
| `api/app/job_options.py` | Validation + normalization of all ~30 job parameters (OCR providers, parse providers, generation modes, etc.) |

### Convert Pipeline — Parsing
| File Path | Description |
|---|---|
| `api/app/convert/pdf_parser.py` | `parse_pdf_to_ir()`: Extracts IR from PDF via PyMuPDF. Per page: text lines (with font/size/color/style), embedded images (extracted to artifacts/images/), tables (via pymupdf.find_tables()). Detects `has_text_layer`. Output: `{pages: [{elements: [{type, bbox_pt, text, ...}]}]}` |
| `api/app/convert/mineru_adapter.py` | MinerU API integration (~1967 lines): uploads PDF, polls task status, downloads ZIP, unpacks markdown/images, `_build_ir_from_mineru_outputs()` converts MinerU JSON layout to standard IR. Supports `vlm`, `pipeline`, `MinerU-HTML` model versions. |
| `api/app/convert/baidu_doc_adapter.py` | Baidu document parser (~1178 lines): OAuth2 token, creates parsing task, polls result. Supports `general` and `paddle_vl` (PaddleOCR-VL) parse types. Reuses MinerU's `_build_ir_from_mineru_outputs()` for IR conversion. |
| `api/app/convert/llm_adapter.py` | LLM client adapters: `OpenAiProvider` (OpenAI-compatible via `openai` package) and `AnthropicProvider` (via `anthropic` package). Used for layout assist (currently disabled). |

### Convert Pipeline — OCR
| File Path | Description |
|---|---|
| `api/app/convert/ocr/base.py` | Abstract `OcrProvider` base class (ocr_image()), constants, env helpers, PaddleOCR-VL model resolution |
| `api/app/convert/ocr/local_providers.py` | `OcrManager` (multi-provider orchestrator), `TesseractOcrClient`, `PaddleOcrClient`, `BaiduOcrClient`, `create_remote_ocr_client()`, `create_ocr_manager()`, `ocr_image_to_elements()`. Local probes: `probe_local_tesseract()`, `probe_local_paddleocr()` |
| `api/app/convert/ocr/ai_client.py` | `AiOcrClient` — OpenAI-compatible vision API OCR. Supports chain modes: `direct` (send full page image with prompt), `doc_parser` (PaddleOCR-VL structured parse via API), `layout_block` (local layout detection + per-block remote OCR). `AiOcrTextRefiner` for post-processing. |
| `api/app/convert/ocr/routing.py` | `build_ocr_route_plan()` — maps ocr_provider string to `OcrRoutePlan` (runtime_provider, route_kind: machine_ocr/remote_prompt_ocr/remote_doc_parser/local_layout_block_ocr/hybrid_auto). Controls linebreak assist, text refiner permissions. |
| `api/app/convert/ocr/vendors.py` | AI OCR vendor adapters: `AiOcrVendorAdapter`, `OpenAiAiOcrAdapter`, vendor profiles (endpoints, headers, model resolution), VENDOR_DEFAULTS for siliconflow, deepseek, ppio, novita, openai |
| `api/app/convert/ocr/prompts.py` | OCR prompt templates: per-chain-mode and per-prompt-preset prompt generation |
| `api/app/convert/ocr/json_extraction.py` | JSON extraction from AI OCR responses (robust parsing, fixing malformed JSON from LLMs) |
| `api/app/convert/ocr/result_parsing.py` | Result normalization: bbox validation, text cleanup, confidence extraction |
| `api/app/convert/ocr/utils.py` | `_coerce_bbox_xyxy()` and other shared OCR utilities |
| `api/app/convert/ocr/deepseek_parser.py` | DeepSeek-OCR specific tagged-item extraction |
| `api/app/convert/ocr/runtime_probe.py` | Runtime probing: detect available OCR capabilities, model availability |
| `api/app/convert/ocr/layout_models.py` | Local layout detection models (Paddle document layout, etc.) |

### Convert Pipeline — PPTX Generation
| File Path | Description |
|---|---|
| `api/app/convert/pptx_generator.py` | Re-export shim for backward compatibility |
| `api/app/convert/pptx/generator.py` | `generate_pptx_from_ir()` — main PPTX generation (~2200 lines): python-pptx Presentation API, slide sizing, per-page element rendering, scanned page handling with text erasure, NotebookLM footer removal, speed modes |
| `api/app/convert/pptx/slide_builder.py` | Slide helpers: `_build_transform()` (PDF→slide mapping), `_infer_font_size_pt()`, `_iter_page_elements()`, `_set_slide_size_type()` |
| `api/app/convert/pptx/scanned_page.py` | Scanned page processing (~2500 lines): `_render_pdf_page_png()` (PyMuPDF pixmap), image region detection (edge-detect + BFS connected components), text erasure (Gaussian blur fill or smart erase), background color sampling, NotebookLM footer detection via Tesseract |
| `api/app/convert/pptx/bbox_utils.py` | Bbox manipulation: coordinate coercion, EMU conversion, IOU computation, text erase padding, full-page detection |
| `api/app/convert/pptx/color_utils.py` | Color utilities: hex↔RGB, contrast picking, luma computation |
| `api/app/convert/pptx/font_utils.py` | Font/text utilities: CJK detection, OCR text normalization, wrapping preferences, font name mapping, token width estimation |
| `api/app/convert/pptx/constants.py` | Constants: `SlideTransform` dataclass, `_EMU_PER_INCH`, `_EMU_PER_PT`, `_PTS_PER_INCH` |
| `api/app/convert/pptx/preview.py` | Final preview image export for debugging |
| `api/app/convert/geometry.py` | Shared geometry helpers |

### Worker Helpers (Stage Orchestrators)
| File Path | Description |
|---|---|
| `api/app/worker_helpers/ocr_stage.py` | `run_ocr_stage()` — iterates over scanned pages, runs OCR with timeout guards, handles fallback, emits progress |
| `api/app/worker_helpers/ppt_stage.py` | `run_ppt_stage()` — wraps `generate_pptx_from_ir()` with progress reporting and cancellation checks |
| `api/app/worker_helpers/ocr_runtime.py` | `setup_ocr_runtime()` + `build_ocr_debug_payload()` — initializes OCR manager, text refiner, linebreak refiner |
| `api/app/worker_helpers/layout_assist_stage.py` | `run_layout_assist_stage()` — AI layout assistance (disabled by default) |
| `api/app/worker_helpers/layout.py` | Layout helpers: AI table application, page signature, warning extraction |
| `api/app/worker_helpers/geometry_utils.py` | Bbox geometry: center distance, overlap ratio, coordinate conversion |
| `api/app/worker_helpers/guarded.py` | `run_blocking_with_guards()` — timeout-safe blocking call wrapper |
| `api/app/worker_helpers/debug.py` | Debug artifact generation: OCR runtime debug, layout assist overlay images |

### Other
| File Path | Description |
|---|---|
| `api/app/utils/pdf.py` | PDF utility functions |
| `api/app/utils/text.py` | Text utilities: `clean_str()` |
| `api/app/utils/concurrency.py` | Concurrency utils: `run_in_daemon_thread_with_timeout()` |
| `api/app/database.py` | SQLAlchemy DB init (SQLite) |
| `api/app/dependencies.py` | FastAPI dependencies: `get_current_user_optional()` |
| `api/app/models/user.py` | User ORM models (SQLAlchemy) |
| `api/app/models/error.py` | Error models: AppException, ErrorCode, ErrorResponse |
| `api/app/schemas/job_config.py` | Structured `JobConfig` pydantic model (for V2 API) |
| `api/app/api_auth.py` | Bearer token validation |
| `api/app/auth.py` | Authentication helpers |
| `api/app/logging_config.py` | Logging setup with job/stage context |
| `api/app/services/paddle_prewarm.py` | PaddleOCR model prewarming |

## External Library Dependencies

From `api/requirements.txt`:

| Library | Version | Role |
|---|---|---|
| **fastapi** | 0.115.0 | Web framework |
| **uvicorn** | 0.30.6 | ASGI server |
| **pydantic** / pydantic-settings | 2.9.2 / 2.5.2 | Data validation, config |
| **redis** / **rq** | 5.0.8 / 1.16.2 | Job queue (Redis + RQ) |
| **pymupdf** | 1.24.10 | PDF parsing, rendering, table detection (PyMuPDF) |
| **python-pptx** | 1.0.2 | PPTX file generation |
| **Pillow** | 12.1.0 | Image processing (renders, text erasure, region detection) |
| **opencv-python-headless** | 4.10.0.84 | Image processing (optional) |
| **pytesseract** | 0.3.13 | Tesseract OCR wrapper |
| **paddleocr** / paddlepaddle / paddlex | 3.4.0 / 3.3.0 / 3.4.1 | PaddleOCR (local engine) |
| **baidu-aip** | 4.16.13 | Baidu OCR API client |
| **openai** | 2.16.0 | OpenAI-compatible API client (AI OCR + layout) |
| **anthropic** | 0.77.1 | Anthropic API client (layout assist) |
| **httpx** | 0.27.2 | HTTP client (MinerU/Baidu API calls) |
| **SQLAlchemy** | 2.0.35 | Database ORM (users, site_settings) |
| **python-jose** / **bcrypt** | 3.3.0 / 4.2.0 | JWT authentication |

## Full Conversion Flow Step-by-Step

### 1. Upload & Job Creation
1. Client uploads file (PDF/JPG/PNG/WEBP) to `POST /api/v1/jobs` (or V2 with JSON config)
2. Router `create_job()` in `routers/jobs.py`:
   - Validates file type and content type
   - Checks disk space (min 500MB free)
   - Checks user quotas (concurrent tasks, daily limit)
   - Streams file to `api/data/jobs/{uuid}/input.pdf` in 1MB chunks
   - For images: converts to single-page PDF via PyMuPDF (embeds as page image)
   - Stores API keys as secrets in Redis (not in RQ job args for security)
   - Creates job metadata in Redis: `job:{id}` with status=pending
   - Enqueues job: either RQ (`Queue.enqueue("app.worker.process_pdf_job")`) or inline thread (memory:// mode)
   - Returns `{job_id, status, created_at, expires_at}`

### 2. Job Processing (worker.py `process_pdf_job()`)

#### 2a. Initialization
- Receives job_id + ~60 parameter kwargs
- Retrieves API keys from Redis secrets store
- Creates `.processing` marker file to prevent cleanup daemon from deleting
- Normalizes all parameters (float/int clamping with defined bounds)
- Determines effective DPI (turbo capping, fast capping)

#### 2b. Stage 1 — Parsing (progress 5→30)
- **local**: Calls `parse_pdf_to_ir()` which uses PyMuPDF to:
  1. Open PDF, check encryption
  2. Per page: extract text blocks (with font/size/color/style/bbox), embedded images (extract to artifacts/images/), tables (via `find_tables()`)
  3. Detect `has_text_layer` per page
  4. Output IR: `{pages: [{page_index, page_width_pt, page_height_pt, rotation, elements: [{type, bbox_pt, text, ...}], has_text_layer, warnings}]}`
- **mineru**: Uploads PDF to MinerU API, polls task, downloads ZIP with markdown/images, converts to IR
- **baidu_doc**: Obtains Baidu OAuth token, creates doc parser task, polls for result, converts to IR
- Saves `ir.parsed.json` (debug artifact)

#### 2c. Stage 2 — OCR (progress 35→82, conditional)
Only runs when: parse_provider="local", pages exist without `has_text_layer`, and `enable_ocr=True`.
1. `setup_ocr_runtime()` initializes `OcrManager` based on `ocr_provider`:
   - **auto**: tries local (tesseract), then paddle, then AI OCR
   - **tesseract/paddle/baidu/aiocr**: specific provider
   - For AI OCR: creates `AiOcrClient` with vendor adapter, rate limits (RPM/TPM), concurrency settings
   - Optionally creates `AiOcrTextRefiner` and linebreak refiner
2. `run_ocr_stage()` iterates over scanned pages:
   - Renders page to PNG at configured DPI
   - Runs OCR (with per-page 300s timeout, 3600s total timeout)
   - Circuit breaker: 2 consecutive timeouts → skip remaining OCR pages
   - Writes OCR text elements back into IR (with bbox, confidence, color sample)
   - Optionally runs text refinement (AI-based) and linebreak splitting
   - Emits progress (36→82 range)
3. Writes `ocr_debug.json` artifact

#### 2d. Stage 3 — Layout Assist (progress 82→84, DISABLED)
- `run_layout_assist_stage()` is called but `enable_layout_assist` is hardcoded `False` at line 347
- "Product-side AI layout assist has been retired for speed-focused runs."

#### 2e. Stage 4 — PPTX Generation (progress 84→99)
1. `run_ppt_stage()` wraps `generate_pptx_from_ir()`:
   - Creates `pptx.Presentation()` (python-pptx)
   - Sets slide size based on PDF page or force 16:9
   - **Per page processing**:
     - **Text pages** (has_text_layer):
       - Place text boxes with font/size/color from IR
       - Place embedded images
       - Build PPTX tables
     - **Scanned pages** (no text layer):
       1. Render page to PNG at scanned_render_dpi via PyMuPDF
       2. Detect image regions via edge-detection + BFS connected components
       3. Build OCR text + image region info
       4. Erase OCR text from background image (GaussianBlur fill or smart erase)
       5. Clear image backgrounds for transparent crops
       6. Place background image on slide
       7. Overlay cropped image regions
       8. Overlay editable text boxes with matching colors
     - Speed modes:
       - **standard**: full quality, smart text erase
       - **fast**: DPI cap 120, force fill mode, skip previews
       - **turbo**: DPI cap 120, force fill mode, skip image region analysis on fullpage, skip previews
   - Final preview image export (if enabled and pages ≤ max)
   - Saves `output.pptx` to job directory

#### 2f. Cleanup
- Remove `.processing` marker
- Delete job secrets from Redis
- Optionally remove process artifacts (`artifacts/` subdirectories)
- Remove `ir.parsed.json`
- Update Redis: status=completed, progress=100, stage=done

### 3. Result Download
- Client polls `GET /api/v1/jobs/{job_id}` or SSE for status
- When completed, downloads via `GET /api/v1/jobs/{job_id}/file`
- PPTX served as `FileResponse` from job directory

## OCR Backend Routing Summary

| ocr_provider | runtime_provider | route_kind | Notes |
|---|---|---|---|
| `"auto"` | auto | hybrid_auto | Tries tesseract→paddle→AI OCR with fallback chain |
| `"local"` / `"tesseract"` | local/tesseract | machine_ocr | pytesseract only, allows main AI reuse for text refinement |
| `"paddle"` | paddle | remote_doc_parser | PaddleOCR-VL via API (doc_parser route), forces linebreak assist |
| `"paddle_local"` / `"machine"` / `"paddleocr"` | paddle_local | machine_ocr | Local PaddleOCR models, allows text refinement |
| `"baidu"` | baidu | machine_ocr | Baidu OCR API, no refinement allowed |
| `"aiocr"` | aiocr | depends on chain_mode | Chain modes: direct→remote_prompt_ocr, doc_parser→remote_doc_parser, layout_block→local_layout_block_ocr |

## Caching, File Storage & Temp File Management

### Job Storage
- **Root**: `api/data/jobs/` (configurable via `JOB_ROOT_DIR`)
- **Per-job dir**: `{root}/{job_uuid}/` containing:
  - `input.pdf` — uploaded file (or converted image as PDF)
  - `output.pptx` — final generated PPTX
  - `ir.json` — final intermediate representation (debug)
  - `ir.parsed.json` — parsed IR (temporary, deleted on cleanup)
  - `.processing` — marker file (exists only during active processing)
  - `artifacts/` — process artifacts subdirectories:
    - `images/` — extracted embedded PDF images
    - `page_renders/` — rendered page PNGs
    - `ocr/` — OCR debug JSON
    - `mineru/` — MinerU output (if parse_provider=mineru)
    - `baidu_doc/` — Baidu parser output
    - `layout_before/`, `layout_after/` — layout debug images
    - `final_preview/` — final preview images

### Cleanup
- **Daemon thread** (job_cleanup.py): runs every 15 minutes, deletes job directories older than TTL (24h default)
- **Processing marker**: `.processing` file prevents cleanup of active jobs
- **Artifact cleanup**: after job completes, process artifacts are removed unless `retain_process_artifacts=True`

### Memory/Performance
- **Pixmap cache**: `_PIX_RGB_ARRAY_CACHE` in scanned_page.py caches up to 24 pixmaps as numpy arrays
- **Font cache**: `_AI_OCR_PROBE_FONT_CACHE` caches font objects per size
- **Redis TTL**: job metadata auto-expires after 24h
- **Secrets cleanup**: API keys deleted from Redis immediately after job completes

## Notable Architecture Observations (Factual)

### Parameters & Complexity
- `process_pdf_job()` accepts ~60 keyword arguments — extremely wide function signature
- `create_job()` in the router mirrors most of these as Form parameters (~50 Form fields)
- V2 endpoint (`POST /api/v1/jobs/v2`) was added with structured JSON `JobConfig` to address this

### Timeouts & Hardcoding
- Multiple hardcoded timeout values throughout:
  - OCR page timeout: 300s (configurable via `OCR_PAGE_TIMEOUT_S`)
  - OCR total timeout: 3600s (configurable via `OCR_TOTAL_TIMEOUT_S`)
  - OCR image region timeout: 12s (configurable via `OCR_IMAGE_REGION_TIMEOUT_S`)
  - Job timeout in RQ: hardcoded `"1h"` string (not configurable)
  - Circuit breaker: max 2 consecutive timeouts (configurable via `OCR_MAX_CONSECUTIVE_TIMEOUTS`)
  - Keepalive: 15s default (configurable via `JOB_KEEPALIVE_INTERVAL_S`)
- Some guard timeouts (e.g., OCR stage page processing) use `run_in_daemon_thread_with_timeout()`

### Disabled Features
- `enable_layout_assist` is hardcoded `False` at worker.py line 347 with comment about retirement
- `layout_assist_apply_image_regions` also hardcoded `False`
- MinerU `hybrid_ocr` parameter is deprecated and ignored

### Monolithic Design
- `worker.py` is 1147 lines — combines parameter normalization, all 4 pipeline stages, progress reporting, cancellation handling, and cleanup in one function
- `routers/jobs.py` is 1400+ lines — combines file handling, job management, OCR probing, inline job processing, and quota checks
- `convert/pptx/generator.py` is 2200+ lines — combines text page rendering, scanned page processing, NotebookLM footer detection, image region analysis, text erasure, speed mode variations

### Dual Execution Modes
- **Production**: RQ workers process jobs via `Queue("default")`
- **Dev/QA**: `REDIS_URL=memory://` uses `_InMemoryRedis` + inline threads per job (no RQ process needed)
- RedisService auto-detects Redis availability and falls back to memory

### Cross-Module Shared IR
- MinerU and Baidu Doc parsers both feed into the same `_build_ir_from_mineru_outputs()` function (shared IR format)
- All parse providers converge to the same IR structure consumed by the PPTX generator

### Speed Optimization Patterns
- Multiple code paths guarded by `is_speed_ppt_generation` / `is_turbo_ppt_generation` flags
- DPI capping at multiple levels (turbo≤120, fast≤160)
- Skip image region analysis in speed modes with fullpage
- Force "fill" text erase mode (cheaper than "smart")
- Skip final preview export in speed modes
- OCR merging uses a union-find fast path when bbox count exceeds 240 threshold
