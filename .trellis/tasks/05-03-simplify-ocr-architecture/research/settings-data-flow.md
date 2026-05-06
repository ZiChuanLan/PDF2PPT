# Research: Settings Data Flow (Frontend → Worker)

- **Query**: How do settings flow from the frontend settings page to the backend worker?
- **Scope**: internal
- **Date**: 2026-05-03

## Findings

### Architecture Overview

There are **three distinct storage layers** for settings, and the path differs based on **deploy mode** (`self` vs `public`):

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                               │
│                                                                          │
│  Settings Page ──useSettings()──┬── self mode ──→ localStorage           │
│   (web/src/app/settings/        │   key: pdf-to-ppt.settings.v1          │
│    page.tsx)                    │                                        │
│                                 └── public mode ─→ PUT /user/preferences │
│                                      (DB: UserPreferencesORM)            │
│                                                                          │
│  Homepage ──createJobFormData()──→ POST /api/v1/jobs  (FormData)         │
│   (web/src/app/page.tsx)                                                  │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI)                                 │
│                                                                          │
│  POST /api/v1/jobs (jobs.py:create_job)                                  │
│    ├── validate_and_normalize_job_options() → NormalizedJobOptions        │
│    ├── Creates job in Redis                                              │
│    └── Queues process_pdf_job() with ALL settings as kwargs              │
│                                                                          │
│  Worker (worker.py:process_pdf_job)                                      │
│    ├── Normalizes each param individually (inline _normalize_*)          │
│    ├── setup_ocr_runtime() → creates OCR manager with OCR params         │
│    ├── run_ocr_stage()                                                   │
│    ├── run_ppt_stage() → uses text_erase_mode, scanned_page_mode, etc.  │
│    └── get_settings() → reads env/config for global settings only        │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1. Frontend Settings Storage

**File**: `web/src/hooks/use-settings.ts`

The `useSettings()` hook manages two storage backends based on deploy mode:

#### Self Mode (`deployMode === "self"`)
- **Storage**: `localStorage` under key `pdf-to-ppt.settings.v1`
- **Load**: `localStorage.getItem(SETTINGS_STORAGE_KEY)` → parsed as JSON → merged with `defaultSettings`
- **Save**: `localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))`
- **Auto-save**: 500ms debounce after any settings change
- **All keys are stored** (including API keys)

#### Public Mode (`deployMode === "public"`)
- **Storage**: `UserPreferencesORM` table in SQLite (key-value pairs per user)
- **Load**: `GET /api/v1/user/preferences` → `{ preferences: { key: value } }` → merged with `defaultSettings`
- **Save**: `PUT /api/v1/user/preferences` → `{ preferences: { key: value } }`
- **Auto-save**: 500ms debounce, only **non-sensitive** keys are saved
- **Sensitive keys excluded from API save** (defined in `SENSITIVE_KEYS`):
  - `openaiApiKey`, `siliconflowApiKey`, `claudeApiKey`
  - `mineruApiToken`, `ocrBaiduApiKey`, `ocrBaiduSecretKey`, `ocrAiApiKey`

#### Deploy Mode Detection
- `GET /api/v1/config/deploy-mode` → `{ mode: "self" | "public" }`
- Reads from `SiteSettingsORM` table first, falls back to `DEPLOY_MODE` env var

### 2. Settings Type Definition

**File**: `web/src/lib/settings.ts`

The `Settings` type has ~60 fields covering:

| Category | Key Fields |
|---|---|
| **LLM Provider** | `provider`, `openaiApiKey`, `siliconflowApiKey`, `claudeApiKey`, `openaiBaseUrl`, etc. |
| **Parse Engine** | `parseEngineMode` (local_ocr/remote_ocr/baidu_doc/mineru_cloud) |
| **MinerU** | `mineruApiToken`, `mineruBaseUrl`, `mineruModelVersion`, etc. |
| **OCR Provider** | `ocrProvider` (auto/aiocr/baidu/tesseract/paddle_local) |
| **AI OCR** | `ocrAiApiKey`, `ocrAiProvider`, `ocrAiBaseUrl`, `ocrAiModel`, `ocrAiChainMode`, etc. |
| **OCR Tuning** | `ocrRenderDpi`, `ocrStrictMode`, `ocrTesseractLanguage`, etc. |
| **PPT Generation** | `pptGenerationMode` (standard/fast/turbo), `scannedPageMode`, `textEraseMode` |
| **Image Tuning** | `imageBgClearExpand*`, `scannedImageRegion*` |

### 3. Run Config Resolution

**File**: `web/src/lib/run-config.ts`

Before settings are sent to the API, `resolveRunConfig()` transforms the raw `Settings` into a `RunConfig`:

```
Settings ──resolveRunConfig()──→ RunConfig
  - parseEngineMode → parseProvider (local/baidu_doc/mineru)
  - ocrAiApiKey, ocrAiBaseUrl, ocrAiModel → effectiveOcrAiKey, effectiveOcrAiBaseUrl, effectiveOcrAiModel
  - ocrAiPageConcurrency → resolved (auto or manual)
  - ocrAiBlockConcurrency → resolved (auto or manual)
```

Key resolution logic:
- **OCR AI config source**: If `parseEngineMode === "remote_ocr"` and `ocrAiApiKey` is set → "dedicated"; otherwise "none"
- **Page concurrency auto**: Based on `pptGenerationMode` and `ocrAiChainMode` (e.g., turbo+direct → 4, turbo+layout_block → 2)
- **Block concurrency auto**: Derived from page concurrency for layout_block mode

### 4. Job Creation (Frontend → API)

**File**: `web/src/lib/run-config.ts` → `createJobFormData()`

When a user uploads a file on the homepage, `createJobFormData()` builds a `FormData` with **every relevant setting as a separate form field**:

```
FormData {
  file: <binary>
  parse_provider: "local" | "baidu_doc" | "mineru"
  provider: "openai" | "claude"
  api_key: "..."
  base_url: "..."
  model: "..."
  enable_ocr: "true" | "false"
  text_erase_mode: "fill" | "smart"
  scanned_page_mode: "segmented" | "fullpage"
  ppt_generation_mode: "standard" | "fast" | "turbo"
  ocr_provider: "auto" | "aiocr" | "baidu" | "tesseract" | "paddle_local"
  ocr_ai_api_key: "..."
  ocr_ai_base_url: "..."
  ocr_ai_model: "..."
  ocr_ai_provider: "auto" | "openai" | "siliconflow" | ...
  ocr_ai_chain_mode: "direct" | "doc_parser" | "layout_block"
  ocr_ai_layout_model: "pp_doclayout_v3"
  ocr_ai_prompt_preset: "auto" | ...
  ocr_ai_direct_prompt_override: "..."
  ocr_ai_layout_block_prompt_override: "..."
  ocr_ai_image_region_prompt_override: "..."
  ocr_paddle_vl_docparser_max_side_px: "2200"
  ocr_ai_page_concurrency: "1"
  ocr_ai_block_concurrency: "1"
  ocr_ai_requests_per_minute: "..."
  ocr_ai_tokens_per_minute: "..."
  ocr_ai_max_retries: "0"
  ocr_render_dpi: "200"
  ocr_strict_mode: "true"
  image_bg_clear_expand_min_pt: "0.35"
  image_bg_clear_expand_max_pt: "1.5"
  image_bg_clear_expand_ratio: "0.012"
  scanned_image_region_min_area_ratio: "0.0025"
  scanned_image_region_max_area_ratio: "0.72"
  scanned_image_region_max_aspect_ratio: "4.8"
  mineru_api_token: "..."  (if parse_provider=mineru)
  mineru_model_version: "vlm"
  mineru_enable_formula: "true"
  mineru_enable_table: "true"
  mineru_is_ocr: "false"
  mineru_base_url: "..."
  mineru_language: "..."
  ocr_baidu_app_id: "..."  (if baidu_doc)
  ocr_baidu_api_key: "..."
  ocr_baidu_secret_key: "..."
  ocr_tesseract_language: "..."  (if tesseract)
  ocr_tesseract_min_confidence: "35"
}
```

**Total: ~40+ form fields** are sent per job creation request.

### 5. API Receives and Validates

**File**: `api/app/routers/jobs.py` → `create_job()`

The FastAPI endpoint receives every setting as a **separate `Form()` parameter** (60+ parameters on the function signature).

Key steps:
1. **`validate_and_normalize_job_options()`** (`job_options.py`) — validates and normalizes a subset of settings:
   - `parse_provider`, `provider`, `baidu_doc_parse_type`, `ocr_provider`, `ocr_ai_provider`, `ocr_ai_chain_mode`, `ocr_ai_layout_model`, `ocr_geometry_mode`, `text_erase_mode`, `scanned_page_mode`, `ppt_generation_mode`
   - Returns `NormalizedJobOptions` dataclass
2. **Creates job in Redis** via `redis_service.create_job()`
3. **Queues `process_pdf_job()`** with **ALL settings as keyword arguments** (both normalized and raw)

### 6. Worker Receives Settings as kwargs

**File**: `api/app/worker.py` → `process_pdf_job()`

The worker function signature accepts **50+ keyword parameters**, one per setting. Inside:

1. **Assigns all params to `_`** (line 182-240) — they are used locally
2. **Normalizes numeric params inline** using `_normalize_int()` / `_normalize_float()`:
   - `ocr_render_dpi` → clamped 72-400
   - `image_bg_clear_expand_*` → clamped ranges
   - `scanned_image_region_*` → clamped ranges
   - `ocr_ai_page_concurrency` → 1-8
   - `ocr_ai_block_concurrency` → 1-8 (optional)
   - etc.
3. **`setup_ocr_runtime()`** (`worker_helpers/ocr_runtime.py`) — receives all OCR-related params and creates:
   - `OcrRuntimeSetup` dataclass
   - `ocr_manager` — the actual OCR provider instance
   - `text_refiner`, `linebreak_refiner`
   - Effective OCR config (resolved from request params + env fallbacks)
4. **`run_ocr_stage()`** — uses `ocr_manager` to OCR scanned pages
5. **`run_ppt_stage()`** — uses normalized settings for PPT generation

### 7. Worker Also Reads Global Config

**File**: `api/app/config.py`

The worker also calls `get_settings()` for **global server config** (not per-job settings):
- `redis_url`, `max_file_mb`, `max_pages`
- `ocr_render_dpi`, `scanned_render_dpi` (used as defaults)
- `siliconflow_api_key`, `siliconflow_base_url`, `siliconflow_model` (env fallback for legacy v2 mode)
- `export_ocr_overlay_images`, `export_layout_assist_debug_images`, etc.
- `ocr_page_timeout_s`, `ocr_total_timeout_s`

These are **environment variables**, not per-job settings. They serve as fallback defaults.

### 8. Site Settings (Admin) vs User Settings

#### Site Settings (`admin.py` → `/admin/site-settings`)
- **DB Table**: `SiteSettingsORM` (key-value, no user_id)
- **Purpose**: Admin-level config for public mode (e.g., deploy mode, global API keys)
- **Sensitive keys**: `openai_api_key`, `siliconflow_api_key`, `claude_api_key`, `mineru_api_token`, `ocr_baidu_api_key`, `ocr_baidu_secret_key`, `ocr_ai_api_key`
- **Read by**: `get_deploy_mode()` reads from site_settings to determine deploy mode

#### User Preferences (`config.py` → `/user/preferences`)
- **DB Table**: `UserPreferencesORM` (key-value, per user_id)
- **Purpose**: Per-user settings in public mode (non-sensitive settings only)
- **Written by**: Frontend `useSettings()` hook in public mode
- **Read by**: Frontend `useSettings()` hook on page load

#### Environment Variables (`config.py` → `Settings` class)
- **Purpose**: Server-wide defaults and secrets
- **Not per-user, not per-job**
- **Examples**: `REDIS_URL`, `MAX_FILE_MB`, `SILICONFLOW_API_KEY`, `OCR_RENDER_DPI`

### Data Flow Diagram

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  localStorage│     │ UserPreferences │     │  SiteSettings    │
│  (self mode) │     │  (public mode)  │     │  (admin config)  │
└──────┬──────┘     └────────┬────────┘     └────────┬─────────┘
       │                     │                        │
       └──────────┬──────────┘                        │
                  ▼                                   │
         ┌────────────────┐                           │
         │  useSettings() │ ◄─── deploy mode ────────┘
         │  (React hook)  │     (GET /config/deploy-mode)
         └───────┬────────┘
                 │
                 ▼
    ┌─────────────────────────┐
    │  resolveRunConfig()     │
    │  (run-config.ts)        │
    │  - resolve parse mode   │
    │  - resolve OCR config   │
    │  - resolve concurrency  │
    └────────────┬────────────┘
                 │
                 ▼
    ┌─────────────────────────┐
    │  createJobFormData()    │
    │  → ~40 Form fields      │
    └────────────┬────────────┘
                 │ POST /api/v1/jobs
                 ▼
    ┌─────────────────────────┐
    │  jobs.py:create_job()   │
    │  - validate_and_norm()  │
    │  - create Redis job     │
    │  - queue worker         │
    └────────────┬────────────┘
                 │
                 ▼
    ┌─────────────────────────┐
    │  worker.py:             │
    │  process_pdf_job()      │
    │  - 50+ kwargs           │
    │  - inline normalization │
    │  - setup_ocr_runtime()  │
    │  - run_ocr_stage()      │
    │  - run_ppt_stage()      │
    └─────────────────────────┘
```

### Key Files

| File Path | Description |
|---|---|
| `web/src/lib/settings.ts` | Settings type definition (60 fields), defaults, validation |
| `web/src/hooks/use-settings.ts` | React hook: load/save from localStorage or API |
| `web/src/lib/run-config.ts` | RunConfig resolution, `createJobFormData()`, `validateRunConfig()` |
| `web/src/app/settings/page.tsx` | Settings UI page |
| `web/src/app/page.tsx` | Homepage that calls `createJobFormData()` |
| `api/app/routers/jobs.py` | Job creation endpoint (60+ Form params) |
| `api/app/routers/config.py` | User preferences API, deploy mode API |
| `api/app/routers/admin.py` | Site settings API (admin) |
| `api/app/job_options.py` | Validation/normalization for job option subset |
| `api/app/worker.py` | Worker: receives 50+ kwargs, normalizes, processes |
| `api/app/worker_helpers/ocr_runtime.py` | OCR runtime setup from worker params |
| `api/app/config.py` | Global server settings (env vars) |

### Observations

1. **Massive parameter threading**: Every setting is passed as a separate form field from frontend → API → worker. The `create_job()` function has 60+ parameters, and `process_pdf_job()` has 50+.

2. **No settings abstraction layer**: There's no "job config" object that bundles settings. Each setting is individually threaded through the entire stack.

3. **Normalization is duplicated**: Frontend (`loadStoredSettings`, `resolveRunConfig`) and backend (`job_options.py`, worker `_normalize_*` functions) both normalize the same values independently.

4. **Two-tier settings**: Global server config (env vars via `get_settings()`) provides defaults, but per-job settings from the frontend override them at the API/worker level.

5. **Public mode sensitive key handling**: In public mode, API keys are stored in `SiteSettingsORM` (admin-set), and the frontend excludes sensitive keys from `UserPreferencesORM`. The worker falls back to env vars for credentials.

### Caveats / Not Found

- How `SiteSettingsORM` values are actually consumed by the worker (for public mode API key resolution) was not traced. The worker appears to primarily use request-time kwargs, with env vars as fallback.
- The `process_pdf_job` function signature is extremely long (50+ params) and the actual usage pattern (assigning all to `_` then using them locally) suggests significant refactoring opportunity.
