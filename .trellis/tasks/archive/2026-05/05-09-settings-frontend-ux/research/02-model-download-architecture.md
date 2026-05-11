# Research: Model Download & Local Model Management Architecture

- **Query**: Map the model download and local model management architecture
- **Scope**: internal
- **Date**: 2026-05-09

## Findings

### 1. Model Registry (`api/app/convert/ocr/layout_models.py`)

#### Model Definitions

Five layout models are registered in the `LAYOUT_MODELS` dict (line 42–98):

| model_id | display_name | provider | size_mb | recommended |
|---|---|---|---|---|
| `pp_doclayout_s` | PP-DocLayout-S | paddlex | 1.2 | false |
| `pp_doclayout_m` | PP-DocLayout-M | paddlex | 23.0 | false |
| `pp_doclayout_l` | PP-DocLayout-L | paddlex | 124.0 | false |
| `pp_doclayout_v3` | PP-DocLayoutV3 | paddlex | 126.0 | **true** |
| `doclayout_yolo` | DocLayout-YOLO | doclayout_yolo | 10.0 | false |

Each model is represented by a frozen `LayoutModelInfo` dataclass (line 27–39) with fields: `model_id`, `display_name`, `provider`, `size_mb`, `speed_label`, `accuracy`, `description`, `paddlex_model_name`, `recommended`.

Default model: `pp_doclayout_v3` (line 100: `DEFAULT_LAYOUT_MODEL_ID = "pp_doclayout_v3"`).

#### Cache Locations

- **DocLayout-YOLO**: `$MODEL_CACHE_DIR/doclayout_yolo/doclayout_yolo_docstructbench_imgsz1024.onnx` where `MODEL_CACHE_DIR` defaults to `/app/data/models` (line 184, 306).
- **PaddleX models**: Cached in `~/.paddlex/official_models/` directory. The check function (`_is_paddlex_model_cached`, line 268–301) inspects this directory and matches subdirectory names against the model name (case-insensitive, with `-`/`_`/whitespace normalization).

#### Download Mechanisms

**PaddleX models** (line 360–417):
- Download via `paddlex.create_model(model_name)`, which triggers auto-download of weights.
- PaddleX provides **no progress hooks** — the progress callback signals `null` progress (indeterminate).
- Cancellable variant (`_download_paddlex_model_cancellable`, line 379) checks cancellation before and after, but cannot interrupt mid-download.

**DocLayout-YOLO** (line 420–541):
- Download from HuggingFace Hub: `wybxc/DocLayout-YOLO-DocStructBench-onnx` repo.
- Uses `hf_hub_download` with a custom `_CancellableTqdm` wrapper (lines 442–494) for progress tracking and cancellation.
- Progress is determinate (0.0–1.0) with 1% reporting interval.

#### Provider Architecture

- `LayoutModelProvider` Protocol (line 108–120): defines `predict(image_path) -> list[dict]` interface.
- `PaddleXLayoutProvider` (line 128–162): wraps `paddlex.create_model()` and `model.predict()`.
- `DocLayoutYoloProvider` (line 165–218): wraps `doclayout_yolo.DocLayoutYOLO`, auto-downloads weights on first init.
- `get_layout_model(model_id)` (line 229–248): thread-safe singleton factory with `_provider_cache` + `_provider_lock`.

#### Status Checks

- `is_model_downloaded(model_id)` (line 251–265): dispatches to provider-specific cache checks.
- `normalize_layout_model_id(raw)` (line 544–571): canonicalizes aliases (e.g., `"pp-doclayout"` → `"pp_doclayout_v3"`).

---

### 2. Model Status/Download API (`api/app/routers/model_status.py`)

#### Endpoints

All under prefix `/api/v1/models`:

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/status` | Public | Unified model readiness (local + remote) |
| POST | `/download` | Admin | Start background model download |
| GET | `/download/status` | Public | Poll download progress |
| POST | `/download/cancel` | Admin | Cancel active download |

#### GET `/status` (line 246–275)

Returns `ModelStatusResponse` with two buckets:
- **`local`**: tesseract, paddleocr, pp_doclayout_s, pp_doclayout_m, pp_doclayout_l, pp_doclayout_v3, doclayout_yolo — each as `ModelProviderStatus(ready, issues, provider)`.
- **`remote`**: aiocr, baidu_doc, mineru — each as `ModelProviderStatus(ready, issues, configured)`.

Local providers checked via probe functions (`probe_local_tesseract`, `probe_local_paddle_models`, `is_model_downloaded`), remote providers checked against DB `site_settings` table (lines 188–238).

#### POST `/download` (line 425–512)

Admin-only. Accepts `{"model": "..."}` — supports layout model IDs/aliases + `paddleocr`.

Download flow:
1. Resolve model alias to canonical ID (`_resolve_layout_model_alias`, line 399–422).
2. Check for existing active download — return "already downloading" if so.
3. Create `DownloadTask` in `_download_tasks` dict (thread-safe via `_download_tasks_lock`).
4. Spawn daemon `threading.Thread` running `_background_download_layout_model` or `_background_download_paddleocr`.
5. Return immediately with status `"downloading"`.

PaddleOCR download (line 278–301): constructs `PaddleOcrClient(language="ch")` and calls `_ensure_engine()` — this triggers PaddleOCR to download its det/rec/cls models to its own cache.

#### Download State Tracking (lines 39–52)

`DownloadTask` dataclass (in-memory, not persisted):
```
model_id: str
status: str       # "downloading" | "completed" | "failed" | "cancelled"
progress: float   # 0.0-1.0 (huggingface) or None (paddlex)
message: str
started_at: float
cancel_requested: bool
```

Stored in `_download_tasks: dict[str, DownloadTask]` with threading lock.

#### GET `/download/status` (line 515–543)

Returns all download tasks. Cleans up completed/failed/cancelled entries older than **5 minutes** (300s).

#### POST `/download/cancel` (line 546–590)

Sets `task.cancel_requested = True`. The download thread's cancel checker (line 304–314) polls this flag periodically; the actual cancellation happens at the next check point.

---

### 3. LLM Model Listing API (`api/app/routers/models.py`)

This is a **different endpoint** from the model status/download endpoints. It provides LLM model listing for AI provider configuration.

- Prefix: `/api/v1/models`
- Endpoint: `POST /api/v1/models` (note: POST, not GET — line 367)
- Accepts `ModelListRequest(provider, api_key, base_url, capability)`.
- `capability` filter: `"all"`, `"vision"`, `"ocr"` (line 346–361).
- Calls provider APIs (OpenAI-compatible or Anthropic) to list available models.
- Applies vision model heuristics (`_is_vision_model`, `_is_ocr_model`) to filter results.
- This is **unrelated** to local model management — it's for configuring which remote LLM/vision/OCR models are available.

**Key observation**: This uses `POST` with an API key in the request body (not stored server-side), so it proxies the model list request through the server to avoid exposing API keys to the browser.

---

### 4. Frontend Download Hook (`web/src/hooks/use-model-download.ts`)

`useModelDownload()` hook (line 29–183):

**State Management**:
- `downloads: Record<string, DownloadStatusItem>` — current download states.
- Uses `mountedRef` for safe unmount handling.

**Polling** (lines 80–104):
- Polls `GET /api/v1/models/download/status` with interval = `MODEL_DOWNLOAD_POLL_INTERVAL_MS` = **2000ms** (2 seconds, from `web/src/lib/constants.ts` line 19).
- Polling starts when any download has `status === "downloading"`, stops when none are downloading.
- Immediate fetch on start (line 91).
- Fetches on mount to pick up active downloads from other pages (line 107–109).

**Actions**:
- `startDownload(modelId)` → POST `/models/download` with `{model: modelId}` → immediately fetches status.
- `cancelDownload(modelId)` → POST `/models/download/cancel` with `{model: modelId}`.

**Callbacks**:
- `onDownloadComplete(modelId)` — triggered with toast on transition from "downloading" → "completed".
- `onDownloadFailed(modelId, message)` — triggered with toast on transition from "downloading" → "failed".
- `onDownloadCancelled(modelId)` — triggered with toast on transition from "downloading" → "cancelled".

**Model Label Mapping** (line 189–198): static `getModelLabel()` maps model IDs to human-readable Chinese/English names.

Returns: `{ downloads, startDownload, cancelDownload, getDownloadState, isDownloading }`.

---

### 5. Frontend Status Hook (`web/src/hooks/use-model-status.ts`)

`useModelStatus()` (line 28–67):

- Fetches `GET /api/v1/models/status` on mount (`refetch()` on mount, line 58–64).
- Returns `{ data, isLoading, error, refetch }`.
- No auto-polling — consumers call `refetch()` on demand.

`useEffectiveModelStatus(backend, settings)` (line 76–133):

- Merges backend status with frontend localStorage-based credential checks.
- Overrides `ready`/`configured` for remote providers (aiocr, baidu_doc, mineru) when the user has entered credentials in the Settings page (which are stored in localStorage, not in the DB).
- The backend checks DB `site_settings`, but in self-hosted mode, credentials are only in localStorage — this hook bridges that gap.
- Specifically checks:
  - aiocr: `ocrAiApiKey` + `ocrAiBaseUrl` must both be non-empty.
  - baidu_doc: `ocrBaiduApiKey` + `ocrBaiduSecretKey` must both be non-empty.
  - mineru: `mineruApiToken` must be non-empty.

---

### 6. Model Status UI Component (`web/src/components/model-status-badge.tsx`)

`ModelStatusBadge` (line 399–480):

**Props**: `status`, `isLoading`, `parseEngineMode`, `onStatusChange`, `className`.

**Visual Design**:
- Shows a colored dot (green/amber/red/gray) + status text ("模型就绪" / "部分就绪" / "未就绪" / "检查中").
- Clicking the dot opens a portal-based `DetailsPanel` popover.

**Details Panel** (line 229–371):
- Rendered via `createPortal` to `document.body` (bypasses overflow:hidden ancestors).
- Positioned below the trigger button, clamped to viewport.
- Closes on click outside or Escape key.
- Sections: "本地模型" (tesseract, paddleocr), "版面分析模型" (all LAYOUT_MODELS), "远程 API" (aiocr, baidu_doc, mineru).
- Each row shows: status dot, model name, size (for layout models), kind badge ("本地"/"远程"), issues tags, action buttons.
- "打开设置页" link at bottom navigates to `/settings`.

**Provider Display Map** (line 30–58):
- `PROVIDER_DISPLAY`: ordered list of all providers with keys/labels/kinds.
- `ENGINE_PROVIDER_MAP`: maps `ParseEngineMode` → relevant provider keys.
  - `local_ocr`: tesseract, paddleocr
  - `remote_ocr`: all LAYOUT_MODELS + aiocr
  - `baidu_doc`: baidu_doc only
  - `mineru_cloud`: mineru only
- `DOWNLOADABLE_MODELS` (line 61–64): marks which local models are downloadable (all LAYOUT_MODELS + paddleocr).

**Download Button in Badge** (via `DownloadProgressButton`, `web/src/components/download-progress-button.tsx`):

`DownloadProgressButton` (line 13–91):
- When downloading: shows progress bar (determinate for huggingface with % display, indeterminate/pulsing bar for paddlex) + "取消" cancel button + status message.
- When idle: shows "下载" button with `DownloadIcon`.
- Props: `modelId`, `label`, `downloadState`, `onDownload`, `onCancel` callback functions.

**Download Confirmation** (line 428–442 in model-status-badge.tsx):
- Before starting download, shows `window.confirm()` with model name + size in MB.

---

### 7. Model Prewarming (`api/app/services/paddle_prewarm.py`)

Container startup prewarming for Paddle models.

**Two independent prewarm paths**:

1. **`run_local_paddle_layout_prewarm()`** (line 135–165):
   - Triggered by env var `OCR_PADDLE_LAYOUT_PREWARM=true`.
   - Target role filter via `OCR_PADDLE_LAYOUT_PREWARM_TARGET` (default: "worker", supports "all"/"both"/"*").
   - Model name via `OCR_PADDLE_LAYOUT_PREWARM_MODEL` (default: "PP-DocLayoutV3").
   - Calls `paddlex.create_model(config.model_name)` to download weights at startup.
   - Non-blocking — failures are logged, not raised.

2. **`run_paddle_doc_prewarm()`** (line 168–212):
   - Triggered by `OCR_PADDLE_VL_PREWARM=true`.
   - Requires `OCR_PADDLE_VL_PREWARM_MODEL` (must be a PaddleOCR-VL model), `OCR_PADDLE_VL_PREWARM_API_KEY`.
   - Optional `OCR_PADDLE_VL_PREWARM_PROVIDER` (default: "siliconflow").
   - Creates a remote OCR client and pre-warms the PaddleOCR-VL doc parser.
   - If `OCR_PADDLE_VL_PREWARM_REQUIRED=true`, failure raises an exception (blocks startup).

**CLI entry** (line 215–225): `main()` function runs both prewarm paths — used by container startup scripts.

**Role filtering** (line 57–66): env var `<PREWARM>_TARGET` controls which service roles get prewarmed (comma-separated, with "all"/"both"/"*" support).

---

### 8. Local OCR Provider Initialization (`api/app/convert/ocr/local_providers.py`)

This 2500+ line file contains the local OCR infrastructure. Key classes:

**OCR Clients**:
- `BaiduOcrClient` (line 671–858): wraps `baidu-aip` SDK, reads credentials from env vars or constructor params.
- `TesseractOcrClient` (line 864–1186): wraps `pytesseract`, multi-PSM/language fallback strategy.
- `PaddleOcrClient` (line 1189–1542): wraps `paddleocr.PaddleOCR`, supports PaddleOCR 2.x and 3.x (PaddleX pipeline) output formats. Uses `_ensure_engine()` (line 1209–1245) for lazy init with fallback constructor attempts.
- `LazyPaddleOcrClient` (line 1546–1563): wrapper that delays PaddleOCR loading until first use.

**OcrManager** (line 1566–2527):
- Orchestrates multiple OCR providers in a priority chain.
- Supports provider modes: `auto`, `aiocr`, `baidu`, `machine`, `tesseract`, `local`, `paddle`, `paddleocr`.
- In `auto` mode: Baidu → Tesseract → PaddleOCR → AI OCR as supplement.
- Implements fallback with `strict_no_fallback` flag.
- Can disable AI OCR provider after runtime failures (line 2374–2394: checks error messages for markers like "timed out", "returned no items", "empty").
- `ocr_image_lines()` (line 1972–2324): combines providers for line-level OCR, with word-merge detection heuristics.
- Factory function `create_ocr_manager()` (line 2478–2529): constructs OcrManager with all config params.

**Model Loading Behavior**:
- PaddleOCR: `_ensure_engine()` triggers `PaddleOCR()` construction which auto-downloads det/rec/cls models on first use (if not cached in PaddleOCR's default location).
- Tesseract: checks binary availability and language packs via `probe_local_tesseract()` on init.
- Baidu: only validates credentials, no local model loading.

---

### Data Flow Summary

```
[User clicks download in ModelStatusBadge]
    → useModelDownload.startDownload(modelId)
        → POST /api/v1/models/download {model: modelId}
            → model_status.py:download_model()
                → Creates DownloadTask in memory
                → Spawns daemon thread:
                    → layouts_models.cancellable_download_layout_model()
                        → PaddleX: paddlex.create_model() [auto-download]
                        → DocLayout-YOLO: hf_hub_download() [with tqdm progress]
                    → Updates _download_tasks[modelId] on completion
    → useModelDownload polls GET /api/v1/models/download/status every 2s
        → Updates downloads state
        → Fires callbacks on status transitions

[Model readiness displayed in UI]
    → useModelStatus.refetch() → GET /api/v1/models/status
        → model_status.py:get_model_status()
            → _check_local_providers(): probes tesseract/paddleocr/layout_models
            → _check_remote_providers(): checks DB site_settings for API keys
    → useEffectiveModelStatus() merges with localStorage credentials
    → ModelStatusBadge renders colored dot + details panel

[Container startup]
    → paddle_prewarm.main()
        → run_local_paddle_layout_prewarm()
            → paddlex.create_model() [download if not cached]
        → run_paddle_doc_prewarm()
            → Creates AiOcrClient + _get_paddle_doc_parser() [warm remote parser]
```

---

### Files Referenced

| File Path | Description |
|---|---|
| `api/app/convert/ocr/layout_models.py` | Layout model registry, provider classes, download/cache logic |
| `api/app/routers/model_status.py` | REST endpoints for model status, download, progress, cancel |
| `api/app/routers/models.py` | LLM model listing endpoint (unrelated to local model management) |
| `api/app/services/paddle_prewarm.py` | Container startup Paddle model prewarming |
| `api/app/convert/ocr/local_providers.py` | Local OCR clients, OcrManager orchestration |
| `web/src/hooks/use-model-download.ts` | Frontend download state management + polling hook |
| `web/src/hooks/use-model-status.ts` | Frontend model readiness query hook + localStorage merge |
| `web/src/components/model-status-badge.tsx` | Model status indicator UI with portal popover + download buttons |
| `web/src/components/download-progress-button.tsx` | Download button with progress bar + cancel |
| `web/src/lib/layout-models.ts` | Frontend layout model registry (mirrors backend) |
| `web/src/lib/constants.ts` | Contains `MODEL_DOWNLOAD_POLL_INTERVAL_MS = 2000` |

### Caveats / Not Found

- Download state is purely **in-memory** (not persisted to DB/file) — server restart loses active download tracking.
- PaddleX downloads provide **no progress feedback** — the UI shows an indeterminate pulsing bar.
- PaddleX downloads are **not truly cancellable** mid-flight — cancel is checked only before/after `create_model()`.
- The 5-minute cleanup window for completed/failed/cancelled download tasks means stale entries are auto-removed.
- No frontend model **deletion** or **cache management** function exists — models once downloaded cannot be removed from the UI.
- The `MODEL_CACHE_DIR` env var only affects DocLayout-YOLO; PaddleX uses its own `~/.paddlex/` cache path.
- The `models.py` router registers at the same prefix (`/api/v1/models`) as `model_status.py` — they coexist in the same FastAPI app, differentiated by path (`/status` vs `""` POST).
