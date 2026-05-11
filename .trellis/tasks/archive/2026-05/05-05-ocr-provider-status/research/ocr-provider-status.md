# Research: OCR Provider Status Detection

- **Query**: How does the backend `/api/v1/models/status` endpoint report OCR provider readiness, and how does the frontend display it?
- **Scope**: internal
- **Date**: 2025-05-05

## Findings

### Backend Status Detection

#### 1. `/api/v1/models/status` Endpoint

**File**: `api/app/routers/model_status.py`

The endpoint returns a `ModelStatusResponse` with two dictionaries:
- `local`: dict[str, ModelProviderStatus]
- `remote`: dict[str, ModelProviderStatus]

**Local providers** (lines 136-185):
- **Tesseract**: Calls `probe_local_tesseract(language="chi_sim+eng")` → checks `ready` flag
- **PaddleOCR**: Calls `probe_local_paddle_models(language="ch")` → checks `ready` flag
- **Layout models**: Iterates `LAYOUT_MODELS` dict, calls `is_model_downloaded(model_id)` for each

**Remote providers** (lines 188-238):
- **AIOCR**: Checks `ocr_ai_api_key` in site_settings DB
- **Baidu Doc**: Checks `ocr_baidu_api_key` + `ocr_baidu_secret_key`
- **MinerU**: Checks `mineru_api_token`

**Response model** (lines 60-75):
```python
class ModelProviderStatus(BaseModel):
    ready: bool
    issues: list[str] = []
    provider: Optional[str] = None
    configured: bool = True  # Only meaningful for remote providers
```

#### 2. Runtime Probe Functions

**File**: `api/app/convert/ocr/runtime_probe.py`

**`probe_local_tesseract()`** (lines 17-106):
- Checks if `pytesseract` package is importable
- Checks if tesseract binary is available via `pytesseract.get_tesseract_version()`
- Checks if required language packs are installed via `pytesseract.get_languages()`
- Returns `ready: bool` based on all checks passing

**`probe_local_paddleocr()`** (lines 109-192):
- Checks if `paddleocr` package is importable
- Checks if `paddle` and `PaddleOCR` can be imported (lightweight, no engine construction)
- Returns `ready: bool` based on package + runtime availability

**`probe_local_paddle_models()`** (lines 311-439):
- Calls `probe_local_paddleocr()` first for runtime check
- Scans PaddleOCR model cache directories for det/rec/cls model files
- Returns `ready: bool` only if runtime available AND required model files (det, rec) found

#### 3. Layout Model Status Pattern

**File**: `api/app/convert/ocr/layout_models.py`

**`is_model_downloaded()`** (lines 251-265):
- For PaddleX models: Checks `~/.paddlex/official_models/` directory
- For DocLayout-YOLO: Checks `MODEL_CACHE_DIR/doclayout_yolo/` for ONNX file

**Download endpoints** (lines 425-590):
- `POST /api/v1/models/download`: Triggers background download
- `GET /api/v1/models/download/status`: Polls download progress
- `POST /api/v1/models/download/cancel`: Requests cancellation

**Download tracking** uses in-memory `DownloadTask` dataclass with:
- `model_id`, `status` (downloading/completed/failed/cancelled), `progress` (0.0-1.0), `message`

---

### Frontend UI

#### 1. Settings Page (`web/src/app/settings/page.tsx`)

**OCR Provider Status Display** (lines 331-334):
- Uses `useModelStatus()` hook to fetch `/api/v1/models/status`
- Uses `useModelDownload()` hook for download management
- Shows `ModelStatusBadge` component

**Local OCR Check** (lines 787-869):
- Separate "本地 OCR 综合检测" button
- Calls `POST /jobs/ocr/local/check` for each provider
- Shows runtime + models status in separate cards
- NOT integrated with the main model status system

**Layout Model Download** (lines 229-236):
- `ocrAiLayoutModelOptions` built from `LAYOUT_MODELS` registry
- Download buttons shown inline with model selector

#### 2. Main Page (`web/src/app/page.tsx`)

**Model Status Badge** (lines 234, 1073-1078):
- Uses `useModelStatus()` hook
- Shows `ModelStatusBadge` next to parse engine selector
- Badge expands to show per-provider status

**OCR Provider Selector** (lines 1081-1101):
- For `local_ocr` mode: Shows PaddleOCR/Tesseract dropdown
- PaddleOCR option disabled if `!modelStatus.local.paddleocr?.ready`
- Shows "(未就绪)" text when not ready

#### 3. Model Status Badge Component

**File**: `web/src/components/model-status-badge.tsx`

**Display logic** (lines 30-51):
- `PROVIDER_DISPLAY` array defines all providers with labels
- `ENGINE_PROVIDER_MAP` filters providers by parse engine mode
- For `local_ocr`: Shows tesseract, paddleocr
- For `remote_ocr`: Shows all layout models + aiocr

**Status dot colors** (lines 95-102):
- Green (`bg-emerald-500`): `ready === true`
- Amber (`bg-amber-500`): `configured === false` (remote only)
- Red (`bg-red-500`): `ready === false` and configured
- Gray (`bg-muted-foreground/40`): Unknown/loading

**Download buttons** (lines 197-218):
- Shown for downloadable models when `!ready` and not downloading
- Uses `DownloadProgressButton` component

---

### Layout Model Status Pattern (What We Want to Replicate)

The layout model pattern is the gold standard:

1. **Backend**:
   - `LAYOUT_MODELS` registry with metadata
   - `is_model_downloaded()` checks local cache
   - Status reported in `/api/v1/models/status` as individual entries
   - Download endpoints with progress tracking

2. **Frontend**:
   - `LAYOUT_MODELS` registry mirrored in `web/src/lib/layout-models.ts`
   - `useModelStatus()` hook fetches status
   - `useModelDownload()` hook manages downloads
   - `ModelStatusBadge` shows per-model status with download buttons
   - `DownloadProgressButton` shows progress bar during download

3. **Integration**:
   - Status badge appears next to model selector
   - Download buttons inline with model options
   - Real-time progress polling during download

---

### What's Missing for OCR Providers

#### Current State

**Tesseract**:
- ✅ Backend: `probe_local_tesseract()` detects readiness
- ✅ Backend: Status reported in `/api/v1/models/status`
- ❌ Frontend: No download button (requires system package install)
- ❌ Frontend: Status only shown in "本地 OCR 综合检测" modal

**PaddleOCR**:
- ✅ Backend: `probe_local_paddleocr()` detects runtime
- ✅ Backend: `probe_local_paddle_models()` detects model files
- ✅ Backend: Status reported in `/api/v1/models/status`
- ✅ Backend: Download endpoints exist (`POST /models/download` with `model=paddleocr`)
- ❌ Frontend: No download button in main page or settings
- ❌ Frontend: Status only shown in "本地 OCR 综合检测" modal
- ❌ Frontend: PaddleOCR option disabled on main page but no download prompt

**Remote Providers (AIOCR, Baidu, MinerU)**:
- ✅ Backend: Credential presence checked
- ✅ Frontend: Status shown in ModelStatusBadge
- ✅ Frontend: "配置" button links to settings when not configured

#### What Needs to Change

1. **Frontend Main Page**:
   - Show download button for PaddleOCR when not ready (like layout models)
   - Show status badge for Tesseract/PaddleOCR in OCR provider selector
   - Maybe: Show download progress for PaddleOCR

2. **Frontend Settings Page**:
   - Integrate PaddleOCR download into main model status system
   - Remove separate "本地 OCR 综合检测" or integrate with main status
   - Show PaddleOCR download button alongside layout model downloads

3. **Backend** (optional):
   - Consider adding Tesseract download endpoint (if feasible)
   - Or: Document that Tesseract requires system package install

---

### Key Files

| File | Lines | Description |
|------|-------|-------------|
| `api/app/routers/model_status.py` | 1-590 | Main status endpoint + download endpoints |
| `api/app/convert/ocr/runtime_probe.py` | 1-447 | Tesseract/PaddleOCR probe functions |
| `api/app/convert/ocr/layout_models.py` | 1-565 | Layout model registry + download logic |
| `web/src/app/settings/page.tsx` | 1-2000+ | Settings page with OCR config |
| `web/src/app/page.tsx` | 1-1200+ | Main page with OCR selector |
| `web/src/components/model-status-badge.tsx` | 1-479 | Status badge component |
| `web/src/hooks/use-model-status.ts` | 1-67 | Status fetching hook |
| `web/src/hooks/use-model-download.ts` | 1-193 | Download management hook |
| `web/src/components/download-progress-button.tsx` | 1-92 | Download progress UI |
| `web/src/lib/layout-models.ts` | 1-100 | Frontend layout model registry |

---

## Caveats / Not Found

- Tesseract has no download endpoint (requires system package)
- PaddleOCR download exists but not exposed in frontend UI
- "本地 OCR 综合检测" is separate from main model status system
- No progress tracking for PaddleOCR download (indeterminate only)
