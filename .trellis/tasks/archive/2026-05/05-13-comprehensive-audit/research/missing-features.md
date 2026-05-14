# Research: Missing Features & Inconsistencies

- **Query**: Find missing connections between frontend and backend: model filtering, settings fields with no UI, backend endpoints not called from frontend, OCR provider mismatches, misleading presets
- **Scope**: mixed (internal code audit)
- **Date**: 2026-05-13

## Findings

### 1. Model Filtering — `capability` Param NOT Passed by Frontend

**Backend**: `POST /api/v1/models` accepts `capability` field with values `"all"`, `"vision"`, `"ocr"` (default: `"all"`). The `_model_filtering.py` module has sophisticated vision/OCR detection logic.

**Frontend callers**:

| File | Line | capability sent? |
|------|------|:---:|
| `web/src/components/settings/ocr-strategy-section.tsx` | 95-103 | **No** |
| `web/src/components/settings/output-quality-section.tsx` | 72-79 | **No** |

Both calls send only `{ provider, api_key, base_url }`. The backend defaults to `capability: "all"`, which returns ALL models with no filtering.

**Impact**: The OCR model dropdown shows all models (including non-vision models like `gpt-3.5-turbo`, `text-embedding-ada-002`, etc.). The content AI dropdown is correct since it wants all models, but could use `capability: "all"` explicitly.

**Ref**: `api/app/routers/_model_filtering.py` lines 13, 324-331 (capability matching logic)

---

### 2. Settings Fields With NO UI Input

Settings type has **93 fields** (defined in `web/src/lib/settings.ts` lines 34-93). Comparison against all four settings UI components:

| Settings Field | Type | Has UI Input? | Where (if yes) |
|---|---|---|---|
| `ocrAiPageConcurrencyAuto` | `boolean` | **NO** | — |
| `ocrAiBlockConcurrency` | `string` | **NO** | — |
| `ocrPaddleVlDocparserMaxSidePx` | `string` | **NO** | — |

All other 90 Settings fields have at least one visible input element across the four settings components (`parsing-method-section.tsx`, `ocr-strategy-section.tsx`, `output-quality-section.tsx`, `general-advanced-section.tsx`).

**Details**:

1. **`ocrAiPageConcurrencyAuto`** — Controls whether page concurrency is auto-managed. Defaults to `true`. The `ocrAiPageConcurrency` field has a number input (ocr-strategy-section line 489-497), but there is no checkbox/toggle for `ocrAiPageConcurrencyAuto`. The user cannot switch between auto and manual concurrency mode from the UI.

2. **`ocrAiBlockConcurrency`** — Block-level concurrency for AI OCR. The settings type defines it as a `string`, validated/normalized in `loadStoredSettings()` (lines 733-742 in settings.ts). No input element exists in any component. Only page concurrency (`ocrAiPageConcurrency`) is exposed.

3. **`ocrPaddleVlDocparserMaxSidePx`** — Max side pixels for PaddleOCR-VL document parser. Defaults to `"2200"`. No UI input anywhere.

---

### 3. Backend Endpoints vs Frontend Usage

**Backend routers** (excluding `auth.py`, `setup.py`, `admin.py`):

| Router | Endpoint | Method | Called from Frontend? |
|--------|----------|:------:|:---------------------:|
| `models.py` | `/api/v1/models` | POST | ✅ ocr-strategy-section.tsx, output-quality-section.tsx |
| `models.py` | `/api/v1/models/status` | GET | ✅ use-model-status.ts |
| `models.py` (via `_download_manager.py`) | `/api/v1/models/download` | POST | ✅ use-model-download.ts |
| `models.py` (via `_download_manager.py`) | `/api/v1/models/download/status` | GET | ✅ use-model-download.ts |
| `models.py` (via `_download_manager.py`) | `/api/v1/models/download/cancel` | POST | ✅ use-model-download.ts |
| `models.py` (via `_download_manager.py`) | `/api/v1/models/delete` | POST | ✅ model-status-badge.tsx |
| `jobs.py` | `/api/v1/jobs` | GET | ✅ tracking, jobs, page.tsx |
| `jobs.py` | `/api/v1/jobs/v2` | POST | ✅ page.tsx (job creation) |
| `jobs.py` | `/api/v1/jobs/{id}` | GET | ✅ tracking, page.tsx |
| `jobs.py` | `/api/v1/jobs/{id}/artifacts` | GET | ✅ tracking/page.tsx |
| `jobs.py` | `/api/v1/jobs/{id}/download` | GET | ✅ download-utils.ts |
| `jobs.py` | `/api/v1/jobs/{id}` | DELETE | ✅ tracking, jobs/page.tsx |
| `jobs.py` | `/api/v1/jobs/{id}/cancel` | POST | ✅ jobs/page.tsx, page.tsx |
| `jobs.py` | `/api/v1/jobs/{id}/events` | SSE | ✅ api.ts `createJobEventSource()` |
| `config.py` | `/api/v1/config/deploy-mode` | GET | ✅ use-settings.ts, user-menu.tsx, login/page.tsx |
| `config.py` | `/api/v1/user/preferences` | GET | ✅ use-settings.ts |
| `config.py` | `/api/v1/user/preferences` | PUT | ✅ use-settings.ts |
| `runtime_config.py` | `/api/v1/config/runtime` | GET | ✅ admin-settings.tsx |
| `runtime_config.py` | `/api/v1/config/runtime` | PUT | ✅ admin-settings.tsx |

**No uncalled core endpoints found.** All non-auth/setup/admin endpoints are called from the frontend.

**Health probe**: `api.ts` line 176 probes `${origin}/health` directly (not through `apiFetch`), but `/health` is a FastAPI route — so it IS called, just not through the `apiFetch` wrapper.

**Job check endpoints not verified**: The `jobs.py` models include `AiOcrCheckRequest`/`LocalOcrCheckRequest` — these may be internal-only check/debug endpoints not exposed to the frontend. Not investigated further since they may be intentional.

---

### 4. OCR Provider Options — Frontend vs Backend

**Frontend `OcrProvider` type** (`web/src/lib/settings.ts` lines 5-11):
```typescript
export type OcrProvider =
  | "auto"
  | "aiocr"
  | "baidu"
  | "machine"
  | "tesseract"
  | "paddleocr"
```

**Backend `VALID_OCR_PROVIDERS`** (`api/app/job_options.py` line 10):
```python
VALID_OCR_PROVIDERS = {"auto", "aiocr", "baidu", "machine", "tesseract", "paddle", "paddle_local", "paddleocr"}
```

**Backend `OcrManager` accepted providers** (`api/app/convert/ocr/_ocr_manager.py` lines 205-215):
```python
{"auto", "aiocr", "baidu", "machine", "tesseract", "local", "paddle", "paddleocr"}
```

**Analysis**:
- Backend accepts `"paddle"` and `"paddle_local"` (legacy values) but maps them: `"paddle"` → `"aiocr"`, `"paddle_local"` → `"paddleocr"` (lines 195-204 in `_ocr_manager.py`).
- `job_options.py` also maps `"paddle"` → `"aiocr"` and `"paddle_local"` → `"paddleocr"` (lines 140-150).
- Backend also accepts `"local"` (alias for tesseract/machine).
- The frontend `OcrProvider` type uses only the **canonical** values. This is OK since legacy values are normalized server-side.
- **Local OCR radio options** in `ocr-strategy-section.tsx` (lines 32-37) only show: `"machine"`, `"tesseract"`, `"paddleocr"`, `"auto"`. The `"baidu"` and `"aiocr"` providers are NOT listed in the local OCR section (baidu has its own `baidu_doc` parse mode; aiocr is under `remote_ocr`).
- **No real inconsistency.** The frontend uses canonical provider IDs; the backend handles legacy aliases.

---

### 5. Presets — "best" Preset and `enableLayoutAssist`

**The "best" built-in preset** (`web/src/lib/settings.ts` lines 264-276):
```typescript
{
    id: "best",
    name: "最佳质量",
    description: "最高精度，启用版面辅助，适合复杂文档",
    settings: {
        parseEngineMode: "remote_ocr",
        ocrProvider: "aiocr",
        ocrAiChainMode: "layout_block",
        enableLayoutAssist: true,  // ← Sets true in user settings
        pptGenerationMode: "standard",
    },
}
```

**Server-side gate**: Layout assist is also controlled by the **`ENABLE_LAYOUT_ASSIST`** env var (`runtime_config.py` line 50, field type `bool`, default `false`). If the server-side env var is `false`, layout assist will NOT run regardless of the client-side `enableLayoutAssist` setting.

**Admin settings page** (`admin-settings.tsx` lines 198-211): Shows a checkbox for `ENABLE_LAYOUT_ASSIST` defaulting to `false` with a warning about increased processing time.

**The misleading scenario**: A user selects the "最佳质量" (best quality) preset, which sets `enableLayoutAssist: true` client-side. But if the server operator has not enabled `ENABLE_LAYOUT_ASSIST` in the runtime config (default: off), the layout assist feature silently does NOT run. The user sees the setting as "on" but gets no layout assist benefit. There is no UI indication that the feature requires server-side activation.

**Current defaults** (from `settings.ts` line 146):
```typescript
enableLayoutAssist: false,     // Default is off
```

So the default and the "fast"/"standard" presets are fine. Only the "best" preset enables it, which may not work.

**Note**: `settings.ts` lines 755-757 have a comment confirming the env var gate was removed from client-side (`"No longer force-disabled here"`), meaning the client-side toggle works — but the server-side still needs `ENABLE_LAYOUT_ASSIST=true`.

---

### 6. Parse Provider Mismatch — Frontend vs Backend (Additional Finding)

**Frontend `ParseEngineMode` type** (`settings.ts` line 3):
```typescript
export type ParseEngineMode = "local_ocr" | "remote_ocr" | "baidu_doc" | "mineru_cloud"
```

**Backend `VALID_PARSE_PROVIDERS`** (`job_options.py` line 9):
```python
VALID_PARSE_PROVIDERS = {"local", "mineru", "baidu_doc", "v2"}
```

**Key differences**:
- Frontend uses `"local_ocr"` and `"remote_ocr"` — backend accepts `"local"` and `"v2"` respectively (but NOT `"local_ocr"` or `"remote_ocr"` literally).
- Frontend uses `"mineru_cloud"` — backend accepts `"mineru"`.

**Does the app break?** This needs further investigation: the frontend likely maps `parseEngineMode` to a different parameter name or value before sending to the job creation endpoint. The `validate_and_normalize_job_options()` function in `job_options.py` calls `normalize_parse_provider()` which just does `clean_str(value).lower()`, and then checks against `VALID_PARSE_PROVIDERS`. If the frontend sends `"local_ocr"` verbatim, it would be REJECTED with "Unsupported parse provider".

**Status**: Needs verification — check the actual job creation POST body in `page.tsx` to see how `parseEngineMode` is translated.

---

## Caveats / Not Found

- **Job check endpoints**: `AiOcrCheckRequest`/`LocalOcrCheckRequest` in `jobs.py` may be debug/tool endpoints not meant for the frontend. Not investigated further.
- **Parse provider mapping**: The `parseEngineMode` → `parse_provider` translation in the job creation flow needs verification. This is flagged as finding #6.
- **`quick-presets.tsx`**: Has its own preset definitions (`"normal"`, `"scanned"`, `"high_quality"`) that are DIFFERENT from `BUILT_IN_PRESETS` in `settings.ts` (`"fast"`, `"standard"`, `"best"`). These are separate components serving different UX flows (quick-presets on the main settings page vs. the full preset system). Not an inconsistency per se, but worth noting.
