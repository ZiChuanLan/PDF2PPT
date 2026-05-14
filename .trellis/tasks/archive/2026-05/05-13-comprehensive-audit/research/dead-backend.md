# Research: Backend Dead Code Audit

- **Query**: Find dead/never-referenced Python modules, functions, and features in `api/app/`
- **Scope**: internal
- **Date**: 2026-05-13

## Findings

### 1. Certainly Dead: Config Field `admin_default_password`

**File**: `api/app/config.py:90`

```python
admin_default_password: str = _ADMIN_PLACEHOLDER_PASSWORD
```

**Evidence**: Zero references in any app code outside `config.py` itself. The comment on line 15 says "used as a fallback when the env var is unset", but `grep -r admin_default_password api/app/` returns only the two lines in `config.py` (definition + comment). No router, auth module, or service ever reads `settings.admin_default_password`.

**Classification**: Dead config — field exists but no code reads it. Safe to delete.

---

### 2. Dead `__init__.py` Files (Never Imported by App Code)

| File | Exported Symbols | Import Pattern |
|---|---|---|
| `api/app/models/__init__.py` | Re-exports from `error`, `job`, `user` sub-modules | **Zero imports** — all app code imports directly from sub-modules (e.g., `from app.models.error import AppException`) |
| `api/app/schemas/__init__.py` | Re-exports from `job_config.py` | **Zero imports** — `routers/jobs.py` imports directly via `from ..schemas.job_config import JobConfig` |

**Evidence**:
```bash
grep -r "from app.models import" api/app/      # 0 results
grep -r "from app.schemas import" api/app/     # 0 results
```

**Classification**: Dead facade files — no code reaches them. They re-export but nobody asks. Safe to delete, but low priority (no runtime impact).

---

### 3. No Dead Python Modules Found

Every `api/app/**/*.py` file was traced through the import graph:

#### Entry Points
- **`main.py`** (FastAPI app) → imports from `api_auth`, `config`, `database`, `logging_config`, `models.error`, `routers/*`, `services/job_cleanup`, `services/redis_service`, `security` (lazy)
- **`worker.py`** (RQ worker) → imports from `config`, `job_options`, `job_paths`, `convert/*`, `logging_config`, `models/*`, `perf_policies`, `services/*`, `utils/text`, `worker_helpers/*`
- **Shell scripts** → `python -m app.services.paddle_prewarm`

#### Transitive Import Chains (All Alive)

```
convert/ocr/__init__.py
├── ai_client.py → _ai_helpers, _ai_rate_limiter, _ai_paddle_doc, _ai_layout_block, _ai_chat, _ai_text_refiner
│                  deepseek_parser, prompts, json_extraction, result_parsing, routing, utils, vendors
├── base.py → utils/concurrency.py
├── local_providers.py → _ocr_remote, _baidu_ocr, _tesseract_ocr, _paddle_ocr, _ocr_manager, _ocr_postprocess, runtime_probe
│   _ocr_postprocess.py → _ocr_constants.py
│   _ocr_manager.py → _ocr_constants.py
├── routing.py → base.py
├── vendors.py → base.py
└── layout_models.py → base.py

convert/ (top-level)
├── baidu_doc_adapter.py → _baidu_extract, _mineru_build_ir, _mineru_extract, _adapter_utils
├── mineru_adapter.py → _mineru_build_ir, _mineru_extract
├── _mineru_build_ir.py → _mineru_extract, _adapter_utils
├── _mineru_extract.py → _adapter_utils
├── llm_adapter.py → (standalone, imported by worker.py)
├── pdf_parser.py → (standalone, imported by worker.py)
└── geometry.py → worker_helpers/geometry_utils.py

convert/pptx/
├── font_utils.py → _font_measure, _font_wrap, _font_fit_ocr, _font_fit_mineru
├── scanned_page.py → _scanned_render, _scanned_region_detect, _scanned_color, _scanned_erase, _scanned_ink, _scanned_region_build
│   _scanned_erase.py → _scanned_render, _scanned_region_detect, _scanned_color, bbox_utils
│   _scanned_region_build.py → font_utils, _scanned_erase, _scanned_region_detect, _scanned_render, bbox_utils, slide_builder
│   _scanned_ink.py → _scanned_region_detect, _scanned_color
│   _scanned_color.py → _scanned_region_detect, _scanned_render
│   _scanned_region_detect.py → _scanned_render, bbox_utils
├── preview.py → font_utils, scanned_page, slide_builder, bbox_utils, utils/fonts.py
├── slide_builder.py → (standalone, imported by scanned_page, _scanned_region_build, generator/*)
├── bbox_utils.py → font_utils
└── generator/
    ├── __init__.py → main, probing, text_erase, markdown_utils, footer
    ├── main.py → font_utils, scanned_page, slide_builder, bbox_utils, _parameter_parser, footer
    ├── _text_page.py → font_utils, scanned_page, slide_builder, bbox_utils, markdown_utils
    ├── _scanned_page.py → font_utils, scanned_page, slide_builder, bbox_utils, _parameter_parser, markdown_utils, text_erase
    ├── probing.py → font_utils, bbox_utils, preview, markdown_utils
    ├── _parameter_parser.py → (standalone)
    ├── text_erase.py → (standalone, imported via __init__)
    ├── markdown_utils.py → (standalone, imported via __init__)
    └── footer.py → bbox_utils, scanned_page, markdown_utils

routers/
├── __init__.py → admin, auth, config, jobs, models, runtime_config, setup
├── jobs.py → _job_create_utils, _ocr_check, _upload_utils, schemas/job_config
├── models.py → _model_filtering, _download_manager, convert/ocr/*
├── admin.py → auth.py (not routers/auth.py — the standalone auth module!)
├── config.py → (standalone)
└── (all routers included in main.py via routers/__init__.py exports)
```

**Conclusion**: Zero orphan modules. Every `api/app/**/*.py` is reachable through the import graph or shell script invocation.

---

### 4. No Functions with Dead Naming Patterns

Searched for `_unused`, `deprecated_`, `DEPRECATED`, `UNUSED` across all Python files — **zero results**.

---

### 5. All Routers Included in `main.py`

| Router | Exported in `routers/__init__.py` | Included in `main.py` |
|---|---|---|
| `admin` | ✅ | ✅ `app.include_router(admin_router)` |
| `auth` | ✅ | ✅ `app.include_router(auth_router)` |
| `config` | ✅ | ✅ `app.include_router(config_router)` |
| `jobs` | ✅ | ✅ `app.include_router(jobs_router)` |
| `models` | ✅ | ✅ `app.include_router(models_router)` |
| `runtime_config` | ✅ | ✅ `app.include_router(runtime_config_router)` |
| `setup` | ✅ | ✅ `app.include_router(setup_router)` |

No orphan routers.

---

### 6. Env Vars: Cross-Reference

**Env vars in `docker-compose.yml` / shell scripts but NOT in `config.py`:**

These are used by shell scripts or prewarm logic, not pydantic Settings:
- `APP_SERVICE_ROLE` — read by `services/paddle_prewarm.py`
- `OCR_PADDLE_LAYOUT_PREWARM`, `OCR_PADDLE_LAYOUT_PREWARM_TARGET` — prewarm
- `OCR_PADDLE_VL_PREWARM`, `OCR_PADDLE_VL_PREWARM_TARGET` — prewarm
- `OCR_PADDLE_VL_DOCPARSER_USE_QUEUES` — read by `_ai_paddle_doc.py` via `os.getenv`
- `OCR_AI_REQUEST_TIMEOUT_S` — read by `_ai_chat.py` via `os.getenv`
- `EMBEDDED_WORKER_CONCURRENCY`, `WORKER_CONCURRENCY` — used in shell scripts
- `SILICONFLOW_*` — not read by backend at all (referenced in `.env.example` but consumed by frontend or not used)

**`config.py` fields with undocumented env var equivalents (not in `.env.example`):**

Many advanced OCR AI tuning fields have config.py definitions with sensible defaults but no `.env.example` documentation. This is likely intentional (they're advanced tunables), but notable:

| Config Field | Default | Documented? |
|---|---|---|
| `ocr_paddle_vl_predict_timeout_s` | 180.0 | ❌ |
| `ocr_ai_retry_backoff_base_s` | 8.0 | ❌ |
| `ocr_ai_page_concurrency_default/max` | 1/8 | ❌ |
| `ocr_ai_block_concurrency_default/max` | 1/8 | ❌ |
| `ocr_ai_rpm_default/max` | 1/2000 | ❌ |
| `ocr_ai_tpm_default/max` | 1000/2M | ❌ |
| `enable_layout_assist` | False | ❌ |
| `enable_csrf` | False | ❌ |
| `job_timeout_seconds` | 3600 | ❌ |
| `rate_limit_requests` / `rate_limit_window_seconds` | 60/60 | ❌ |
| `min_disk_space_mb` | 500 | ❌ |
| `admin_default_password` | "" | ❌ (and **dead** — see #1) |

---

### 7. Potential Dead Code (Low Confidence — Needs Manual Review)

| Item | Location | Why Suspicious |
|---|---|---|
| `models/__init__.py` | `api/app/models/__init__.py` | Never imported; all code imports from sub-modules directly |
| `schemas/__init__.py` | `api/app/schemas/__init__.py` | Never imported; only `schemas/job_config.py` is directly imported |
| `admin_default_password` | `api/app/config.py:90` | Zero references in app code; no auth or setup code reads it |

---

## Caveats / Not Found

- **No truly orphan `.py` files**: Every module in `api/app/` is reachable. The codebase is clean in this regard.
- **No `_unused`/`deprecated_` patterns** found.
- **`paddle_prewarm.py`** appears dead if checked only by Python imports, but it's invoked via `python -m app.services.paddle_prewarm` in `run_api.sh` / `run_worker.sh` — it IS alive.
- **Static code analysis coverage is incomplete** — runtime-only imports (e.g., `import paddleocr` inside try/except blocks) and shell-script invocations may mask actual usage.
- **Not checked**: `__init__.py` files that are purely empty (like `api/app/__init__.py`) — these are benign even if functionally useless.
