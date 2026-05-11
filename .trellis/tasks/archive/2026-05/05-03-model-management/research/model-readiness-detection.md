# Research: Model Readiness Detection & Prewarm Mechanisms

- **Query**: How does the project detect model readiness, prewarm models, and handle fallbacks?
- **Scope**: internal
- **Date**: 2026-05-03

## Findings

### 1. Runtime Probe System (`api/app/convert/ocr/runtime_probe.py`)

Four probe functions exist, all returning `dict[str, Any]` with a `ready: bool` field:

| Probe Function | What It Checks | Key Fields Returned |
|---|---|---|
| `probe_local_tesseract(language)` | pytesseract package → binary → language packs | `python_package_available`, `binary_available`, `version`, `available_languages`, `missing_languages` |
| `probe_local_paddleocr(language)` | paddleocr package → paddle + PaddleOCR imports | `python_package_available`, `binary_available` (runtime), `version` |
| `probe_local_tesseract_models(language)` | Delegates to `probe_local_tesseract` + checks `TESSDATA_PREFIX` for `.traineddata` files | `model_root_dir`, `found_models`, `missing_models`, `model_files` |
| `probe_local_paddle_models(language)` | Delegates to `probe_local_paddleocr` + scans cache dirs for `det`/`rec`/`cls` model files | `model_root_dir`, `found_models`, `missing_models`, `model_files` |

**How they're called:**
- **API endpoint**: `POST /api/v1/ocr/local/check` in `api/app/routers/jobs.py:249-285` — accepts `provider` (tesseract/paddle/tesseract_models/paddle_models) and `language`, returns `LocalOcrCheckResponse` with `ok: bool` and `check: LocalOcrCheckResult`
- **At provider init**: `TesseractOcrClient.__init__()` calls `probe_local_tesseract()` to validate binary + language availability before accepting the provider
- **NOT called at startup** — probes are on-demand only

**PaddleOCR model file discovery** (`_resolve_paddle_model_roots`):
- Checks `PADDLE_OCR_MODEL_DIR` env (override)
- Checks `PADDLEOCR_HOME` env → `{home}/whl`, `{home}`
- Checks `XDG_CACHE_HOME` env → `{cache}/paddleocr/whl`, `{cache}/paddleocr`
- Falls back to `~/.paddleocr/whl`, `~/.paddleocr`
- Scans for files matching `.pdmodel`, `.pdiparams`, `.onnx`, `inference.yml`, `inference.json`
- Looks for tokens `det`, `rec` (required), `cls` (optional) in file paths

### 2. Prewarm System (`api/app/services/paddle_prewarm.py`)

Two prewarm functions, both gated by env flags:

#### PP-DocLayout Local Prewarm
- **Function**: `run_local_paddle_layout_prewarm()`
- **Env flags**: `OCR_PADDLE_LAYOUT_PREWARM=true` (gate), `OCR_PADDLE_LAYOUT_PREWARM_TARGET` (service role, default "worker"), `OCR_PADDLE_LAYOUT_PREWARM_MODEL` (default "PP-DocLayoutV3")
- **What it does**: Calls `paddlex.create_model(model_name)` which downloads model weights if not cached
- **Failure mode**: Logs exception, continues (non-fatal)

#### PaddleOCR-VL Remote Prewarm
- **Function**: `run_paddle_doc_prewarm()`
- **Env flags**: `OCR_PADDLE_VL_PREWARM=true` (gate), `OCR_PADDLE_VL_PREWARM_TARGET`, `OCR_PADDLE_VL_PREWARM_MODEL` (must be PaddleOCR-VL model), `OCR_PADDLE_VL_PREWARM_API_KEY` (required), `OCR_PADDLE_VL_PREWARM_PROVIDER` (default "siliconflow"), `OCR_PADDLE_VL_PREWARM_BASE_URL`, `OCR_PADDLE_VL_PREWARM_MAX_SIDE_PX`, `OCR_PADDLE_VL_PREWARM_REQUIRED`
- **What it does**: Creates a remote OCR client and calls `client._get_paddle_doc_parser()` to validate API connectivity
- **Failure mode**: If `required=true`, raises (fatal); otherwise logs and continues

#### CLI Entrypoint
- `main()` function runs both prewarms sequentially
- Called at container startup via `python -m app.services.paddle_prewarm` or similar

#### Service Role Gating
- `_should_prewarm_for_role()` checks `APP_SERVICE_ROLE` env against `OCR_PADDLE_*_PREWARM_TARGET` (default "worker")
- Supports "all", "both", "*" to target all roles, or comma-separated role list

### 3. Model Download Triggers

| Model | Download Trigger | Automatic? |
|---|---|---|
| **Local PaddleOCR models** (det/rec/cls) | First `PaddleOCR()` constructor call in `PaddleOcrClient._ensure_engine()` | ✅ Auto on first use |
| **PP-DocLayout** | Explicit `paddlex.create_model("PP-DocLayoutV3")` call in prewarm | ❌ Requires prewarm env flag |
| **Tesseract** | System package install (`apt install tesseract-ocr`) | ❌ Manual install |
| **Tesseract language packs** | System package install (`apt install tesseract-ocr-chi-sim`) | ❌ Manual install |

**Lazy loading**: `LazyPaddleOcrClient` wraps `PaddleOcrClient` — defers import + model download until first `ocr_image()` call. Used as fallback provider to avoid startup cost.

### 4. Existing API Endpoints for Model Status

| Endpoint | Method | File | Purpose |
|---|---|---|---|
| `/api/v1/ocr/local/check` | POST | `api/app/routers/jobs.py:249` | Check local OCR provider readiness (tesseract/paddle + model variants) |
| `/api/v1/models` | POST | `api/app/routers/models.py:367` | List available AI models from remote providers (OpenAI/SiliconFlow/Claude etc.) — filters by capability (all/vision/ocr) |

**No existing endpoints for:**
- Unified model status dashboard (`GET /api/v1/models/status`)
- Model download trigger (`POST /api/v1/models/download`)
- Prewarm trigger via API

**Admin env editor**: `GET/PUT /api/v1/admin/env` in `api/app/routers/admin.py` — can read/write `.env` file, but changes require container restart.

### 5. OCR Provider Fallback Chain

The `OcrManager` class in `local_providers.py` implements the fallback chain:

#### Provider Modes
| Mode | Primary | Fallback Chain |
|---|---|---|
| `auto` (non-strict) | Baidu → Tesseract → PaddleOCR local → AI OCR | All available providers combined |
| `auto` (strict) | AI OCR only | No local fallback |
| `aiocr` | AI OCR | + Tesseract fallback + PaddleOCR lazy fallback (if not strict) |
| `baidu` | Baidu | + Tesseract fallback + PaddleOCR lazy fallback (if not strict) |
| `machine` | PaddleOCR local → Tesseract | PaddleOCR first, Tesseract as fallback |
| `tesseract`/`local` | Tesseract only | No fallback |

#### Fallback Behavior
- `ocr_image()`: Iterates `self.providers` list, tries each until one succeeds
- If AI OCR fails with specific errors (empty result, timeout, gibberish), sets `ai_provider_disabled=True` for remaining pages
- `ocr_image_lines()` (auto mode): Combines results from ALL available providers — Baidu/Tesseract/Paddle for geometry, AI as supplement
- Merges line items using `_merge_line_items_prefer_primary()` to avoid duplicates

#### Key Error Handling
- Each provider failure logs warning and continues to next
- `RuntimeError("All OCR providers failed")` raised only if all providers fail
- AI OCR can be disabled mid-batch if it returns consistently bad results

### 6. Gaps and Optimization Opportunities

1. **No unified model status API** — probes exist but no single endpoint returns all model statuses at once
2. **No API-triggered prewarm** — prewarm only runs at container startup via env flags
3. **No API-triggered download** — PP-DocLayout download requires manual env config + restart
4. **No UI for model status** — frontend has no model readiness indicators
5. **Env-based configuration** — all prewarm settings in env vars, no DB/UI management
6. **No download progress** — model downloads are blocking with no progress reporting
7. **LazyPaddleOcrClient not probed** — the lazy wrapper doesn't expose model status until first use

### 7. Key File Locations

| File | Purpose |
|---|---|
| `api/app/convert/ocr/runtime_probe.py` | Runtime availability probes (4 functions) |
| `api/app/services/paddle_prewarm.py` | Prewarm helpers + CLI entrypoint |
| `api/app/convert/ocr/local_providers.py` | OcrManager + fallback chain + provider implementations |
| `api/app/convert/ocr/routing.py` | Route plan builder (OcrRoutePlan) |
| `api/app/convert/ocr/base.py` | Constants, language normalization, model names |
| `api/app/convert/ocr/ai_client.py` | AiOcrClient (remote OCR) + doc_parser integration |
| `api/app/routers/jobs.py` | `/api/v1/ocr/local/check` endpoint |
| `api/app/routers/models.py` | `/api/v1/models` endpoint (remote model listing) |
| `api/app/routers/admin.py` | Admin env editor + site settings |

## Caveats / Not Found

- No existing `GET /api/v1/models/status` endpoint — needs to be created
- No existing `POST /api/v1/models/download` endpoint — needs to be created
- No existing UI component for model status display
- The `probe_local_paddle_models` scan can be slow on large cache directories (rglob with no depth limit)
- PP-DocLayout model name defaults to "PP-DocLayoutV3" but no version validation exists
