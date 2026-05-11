# Research: OCR Provider Status Detection and Selection Logic

- **Query**: OCR provider status detection and selection logic in the pdf2ppt codebase
- **Scope**: internal
- **Date**: 2025-05-05

## Findings

### 1. Frontend OCR Model Selector (Stage 2 — `web/src/app/page.tsx`)

**File**: `web/src/app/page.tsx`

The OCR model selector in Stage 2 (preview/config panel) is **NOT hardcoded** — it reads from settings and model status. Here's how it works:

#### Parse Engine Mode Selector (line 1052-1072)
```tsx
<Select
  value={settingsSnapshot.parseEngineMode}
  onChange={(e) => {
    const mode = e.target.value as ParseEngineMode
    updateSettingsSnapshot((prev) => ({
      ...prev,
      parseEngineMode: mode,
      ...(mode === "remote_ocr" ? { ocrProvider: "aiocr" as const }
        : mode === "baidu_doc" ? { ocrProvider: "baidu" as const }
        : mode === "mineru_cloud" ? { ocrProvider: "auto" as const }
        : {}),
    }))
  }}
>
  <option value="local_ocr">{PARSE_ENGINE_MODE_LABELS.local_ocr}</option>
  <option value="remote_ocr">{PARSE_ENGINE_MODE_LABELS.remote_ocr}</option>
  <option value="baidu_doc">{PARSE_ENGINE_MODE_LABELS.baidu_doc}</option>
  <option value="mineru_cloud">{PARSE_ENGINE_MODE_LABELS.mineru_cloud}</option>
</Select>
```

**Key behavior**: When switching modes, `ocrProvider` is auto-set to match the mode:
- `remote_ocr` → `ocrProvider = "aiocr"`
- `baidu_doc` → `ocrProvider = "baidu"`
- `mineru_cloud` → `ocrProvider = "auto"`
- `local_ocr` → keeps user's existing choice

#### Local OCR Provider Selector (line 1081-1111)
When `parseEngineMode === "local_ocr"`, a second dropdown shows:
```tsx
<Select value={settingsSnapshot.ocrProvider} ...>
  <option value="paddleocr" disabled={!!modelStatus && !modelStatus.local.paddleocr?.ready}>
    PaddleOCR{modelStatus && !modelStatus.local.paddleocr?.ready ? " (未就绪)" : ""}
  </option>
  <option value="tesseract" disabled={!!modelStatus && !modelStatus.local.tesseract?.ready}>
    Tesseract{modelStatus && !modelStatus.local.tesseract?.ready ? " (未就绪)" : ""}
  </option>
</Select>
```

**Key behavior**: Options are **disabled** when the backend reports the provider is not ready. The "(未就绪)" suffix is appended to the label text.

#### AIOCR Model Selector (line 1163-1200)
When `parseEngineMode === "remote_ocr"`, an OCR model dropdown appears:
```tsx
{settingsSnapshot.ocrAiApiKey.trim() && settingsSnapshot.ocrAiBaseUrl.trim() ? (
  <Select value={...} onChange={...}>
    <option value="Qwen/Qwen2.5-VL-7B-Instruct">Qwen2.5-VL-7B</option>
    <option value="Qwen/Qwen2.5-VL-32B-Instruct">Qwen2.5-VL-32B</option>
    <option value="paddleocr/PaddleOCR-VL-1.5">PaddleOCR-VL</option>
    <option value="deepseek-ai/DeepSeek-OCR">DeepSeek-OCR</option>
    <option value="openai/gpt-4o-mini">GPT-4o-mini</option>
    {/* Custom model option if current model isn't in the preset list */}
  </Select>
) : (
  <div className="flex items-center gap-2 text-xs text-amber-600">
    <AlertCircleIcon className="size-3.5" />
    <span>请先配置 API Key 和 Base URL</span>
    <Link href="/settings" className="underline hover:text-amber-800">去设置</Link>
  </div>
)}
```

**Key behavior**: The model dropdown is **hardcoded** with 5 preset models. If the user has a custom model not in the list, it shows as a `__custom__` option. If `ocrAiApiKey` or `ocrAiBaseUrl` are empty, the dropdown is replaced with a "请先配置 API Key 和 Base URL" warning.

---

### 2. Frontend OCR Status Detection

#### `useModelStatus` Hook (`web/src/hooks/use-model-status.ts`)

**File**: `web/src/hooks/use-model-status.ts` (67 lines)

A simple hook that fetches `GET /api/v1/models/status` on mount and provides a `refetch()` function. Returns `{ data, isLoading, error, refetch }`.

**No automatic polling** — it fetches once on mount and on manual `refetch()` calls.

Used in `page.tsx` line 234:
```tsx
const { data: modelStatus, isLoading: isModelStatusLoading, refetch: refetchModelStatus } = useModelStatus()
```

#### `ModelStatusBadge` Component (`web/src/components/model-status-badge.tsx`)

**File**: `web/src/components/model-status-badge.tsx` (479 lines)

This is the expandable status indicator shown next to the parse engine selector (line 1073-1078):
```tsx
<ModelStatusBadge
  status={modelStatus}
  isLoading={isModelStatusLoading}
  parseEngineMode={settingsSnapshot.parseEngineMode}
  onStatusChange={() => void refetchModelStatus()}
/>
```

**How it determines readiness**:

1. **Provider filtering** (line 44-58): Based on `parseEngineMode`, it filters which providers to display:
   - `local_ocr` → `["tesseract", "paddleocr"]`
   - `remote_ocr` → `[...Object.keys(LAYOUT_MODELS), "aiocr"]` (all layout models + AIOCR)
   - `baidu_doc` → `["baidu_doc"]`
   - `mineru_cloud` → `["mineru"]`

2. **Overall status calculation** (line 80-93):
   ```tsx
   function getOverallStatus(status, providers): "ready" | "partial" | "unknown" {
     const all = providers.map(p => getProviderStatus(status, p.key, p.kind)).filter(Boolean)
     if (all.length === 0) return "unknown"
     const readyCount = all.filter(s => s.ready).length
     if (readyCount === all.length) return "ready"
     if (readyCount === 0) return "partial"
     return "partial"
   }
   ```

3. **Dot color** (line 95-112):
   - Green (`bg-emerald-500`): all providers ready
   - Yellow (`bg-amber-500`): some providers not ready (partial)
   - Gray (`bg-muted-foreground/40`): status unknown or loading

4. **Badge label** (line 460-462):
   - `"模型就绪"` when all ready
   - `"部分就绪"` when partial
   - `"检查中"` when loading

5. **Expanded details panel**: Shows per-provider rows with status dots, issue tags, and download/config buttons.

#### Preflight Warning Dialog (line 263-287 in `page.tsx`)

When the user clicks "开始转换", a preflight check runs:
```tsx
if (modelStatus && !preflightAcknowledged) {
  const mode = settingsSnapshot.parseEngineMode
  const requiredProviders = []
  if (mode === "local_ocr") {
    if (settingsSnapshot.ocrProvider === "paddleocr")
      requiredProviders.push({ key: "paddleocr", kind: "local", label: "PaddleOCR" })
  } else if (mode === "remote_ocr") {
    requiredProviders.push({ key: "aiocr", kind: "remote", label: "AIOCR" })
  } else if (mode === "baidu_doc") {
    requiredProviders.push({ key: "baidu_doc", kind: "remote", label: "百度文档解析" })
  } else if (mode === "mineru_cloud") {
    requiredProviders.push({ key: "mineru", kind: "remote", label: "MinerU" })
  }
  const notReady = requiredProviders.filter(p => {
    const bucket = p.kind === "local" ? modelStatus.local : modelStatus.remote
    return bucket[p.key] && !bucket[p.key].ready
  })
  if (notReady.length > 0) {
    const names = notReady.map(p => p.label).join("、")
    setPreflightWarning(`${names} 未就绪，任务可能在运行时失败。是否继续？`)
    return
  }
}
```

This generates the dynamic warning text like `"AIOCR 未就绪，任务可能在运行时失败。是否继续？"` — **the exact text is NOT hardcoded**; it's constructed from the provider labels.

---

### 3. Backend Model Status API (`api/app/routers/model_status.py`)

**File**: `api/app/routers/model_status.py` (590 lines)

**Endpoint**: `GET /api/v1/models/status` (line 246-275)

Returns `ModelStatusResponse` with two dicts: `local` and `remote`, each mapping provider keys to `ModelProviderStatus { ready, issues, provider, configured }`.

#### Local Provider Check (`_check_local_providers`, line 136-185)

Checks three categories:

1. **Tesseract** (line 141-152): Calls `probe_local_tesseract(language="chi_sim+eng")` from `runtime_probe.py`. Returns `ready=bool(probe.get("ready"))`.

2. **PaddleOCR** (line 155-166): Calls `probe_local_paddle_models(language="ch")`. Returns `ready=bool(probe.get("ready"))`.

3. **Layout models** (line 169-184): Iterates over `LAYOUT_MODELS` dict, checks `is_model_downloaded(model_id)` for each.

#### Remote Provider Check (`_check_remote_providers`, line 188-238)

Checks credential presence in the `site_settings` DB table:

1. **AIOCR** (line 199-209):
   ```python
   ocr_ai_api_key = _get_setting(db, "ocr_ai_api_key")
   ocr_ai_configured = bool(ocr_ai_api_key)
   providers["aiocr"] = ModelProviderStatus(
       ready=ocr_ai_configured,
       issues=["api_key_missing"] if not ocr_ai_configured else [],
       configured=ocr_ai_configured,
   )
   ```
   **Condition**: `ocr_ai_api_key` must exist and be non-empty in `site_settings`.

2. **Baidu Doc** (line 212-224): Needs both `ocr_baidu_api_key` AND `ocr_baidu_secret_key`.

3. **MinerU** (line 227-236): Needs `mineru_api_token`.

**Important**: The `_get_setting` helper (line 127-133) reads from the `site_settings` DB table via `SiteSettingsORM`. There is **no env-var fallback** — by design (comment at line 191-196).

---

### 4. Settings/Config Flow

#### Frontend Settings Storage

**File**: `web/src/lib/settings.ts` (587 lines)

Settings are stored in `localStorage` under key `"pdf-to-ppt.settings.v1"`. The `Settings` type has ~60 fields including all OCR-related config.

Key OCR fields:
- `parseEngineMode`: `"local_ocr" | "remote_ocr" | "baidu_doc" | "mineru_cloud"`
- `ocrProvider`: `"auto" | "aiocr" | "baidu" | "machine" | "tesseract" | "paddleocr"`
- `ocrAiApiKey`, `ocrAiBaseUrl`, `ocrAiModel`: AIOCR credentials (frontend-local)
- `ocrAiChainMode`: `"direct" | "doc_parser" | "layout_block"`
- `ocrAiLayoutModel`: layout model ID for layout_block chain

**Critical distinction**: The frontend `Settings` object stores OCR API keys locally in the browser. The backend `site_settings` table stores them separately. The `ModelStatusBadge` reads from the backend status API, NOT from frontend settings.

#### Backend Settings Storage

**File**: `api/app/routers/model_status.py` line 127-133

```python
def _get_setting(db: Session, key: str) -> str | None:
    row = db.query(SiteSettingsORM).filter(SiteSettingsORM.key == key).first()
    if row and row.value is not None:
        val = str(row.value).strip()
        return val if val else None
    return None
```

Settings are stored in the `site_settings` table (key-value pairs). The admin settings page writes to this table.

#### Config Endpoints (`api/app/routers/config.py`)

**File**: `api/app/routers/config.py` (72 lines)

Only exposes:
- `GET /api/v1/config/deploy-mode` — returns deploy mode from site_settings or env var
- `GET /api/v1/user/preferences` — user-specific preferences
- `PUT /api/v1/user/preferences` — update user preferences

**No OCR config endpoint** — OCR credentials are managed through the admin settings page which writes directly to `site_settings`.

#### How Job Submission Uses Settings

When a job is submitted via `POST /api/v1/jobs/v2`, the frontend sends a structured `JobConfig` JSON (built by `buildJobConfig()` in `run-config.ts`). The backend worker resolves OCR credentials through a priority chain:
1. Per-job `ocr_ai_api_key` from the request
2. Site-wide `ocr_ai_api_key` from `site_settings` DB
3. Main API key as fallback (for backward compat)

---

### 5. The "⚠️ AIOCR 未就绪" Warning

**There is NO exact string "⚠️ AIOCR 未就绪"** in the codebase. The grep for `AIOCR.*未就绪` returned no matches.

The actual warning mechanisms are:

1. **Preflight warning** (dynamic, `page.tsx` line 284):
   ```tsx
   setPreflightWarning(`${names} 未就绪，任务可能在运行时失败。是否继续？`)
   ```
   Where `names` is constructed from provider labels (e.g., "AIOCR", "百度文档解析", "MinerU"). This renders as `⚠️ AIOCR 未就绪，任务可能在运行时失败。是否继续？` at line 1227.

2. **Local OCR not ready hint** (`page.tsx` line 1104-1109):
   ```tsx
   {modelStatus && !modelStatus.local.paddleocr?.ready && !modelStatus.local.tesseract?.ready && (
     <div className="flex items-center gap-1.5 text-xs text-amber-600 mt-1">
       <AlertCircleIcon className="size-3.5" />
       <span>本地 OCR 未就绪，请前往设置配置</span>
     </div>
   )}
   ```

3. **Option disabled labels** (`page.tsx` line 1097, 1100):
   ```tsx
   PaddleOCR{modelStatus && !modelStatus.local.paddleocr?.ready ? " (未就绪)" : ""}
   Tesseract{modelStatus && !modelStatus.local.tesseract?.ready ? " (未就绪)" : ""}
   ```

4. **Settings page** (`settings/page.tsx` line 2425, 2470):
   ```tsx
   : "未就绪"
   ```
   Used in Tesseract and PaddleOCR runtime status display.

---

## File Index

| File Path | Lines | Description |
|---|---|---|
| `web/src/app/page.tsx` | 1572 | Main page with OCR selector, preflight check, status badge |
| `web/src/components/model-status-badge.tsx` | 479 | Expandable status badge with per-provider readiness |
| `web/src/hooks/use-model-status.ts` | 67 | Hook fetching `GET /api/v1/models/status` |
| `web/src/hooks/use-model-download.ts` | 193 | Hook for model download progress tracking |
| `web/src/lib/settings.ts` | 587 | Settings type, defaults, localStorage persistence |
| `web/src/lib/run-config.ts` | 1030 | Run config resolution, job config building |
| `web/src/lib/layout-models.ts` | 100 | Layout model registry (5 models) |
| `api/app/routers/model_status.py` | 590 | Backend status endpoint, download endpoints |
| `api/app/routers/config.py` | 72 | Deploy mode and user preferences endpoints |
| `api/app/convert/ocr/runtime_probe.py` | 447 | Local OCR runtime probing (tesseract, paddleocr) |
| `web/src/app/settings/page.tsx` | ~2506 | Settings page with "未就绪" labels |

## Key Code Locations

| What | File | Line(s) |
|---|---|---|
| Parse engine mode selector | `page.tsx` | 1052-1072 |
| Local OCR provider selector | `page.tsx` | 1081-1111 |
| AIOCR model dropdown (hardcoded 5 models) | `page.tsx` | 1163-1200 |
| Preflight "未就绪" warning generation | `page.tsx` | 263-287 |
| Preflight warning display | `page.tsx` | 1225-1254 |
| Local OCR "未就绪" hint | `page.tsx` | 1104-1109 |
| `ModelStatusBadge` overall status logic | `model-status-badge.tsx` | 80-93 |
| `ModelStatusBadge` dot color logic | `model-status-badge.tsx` | 95-112 |
| Backend AIOCR ready check | `model_status.py` | 199-209 |
| Backend Baidu ready check | `model_status.py` | 212-224 |
| Backend MinerU ready check | `model_status.py` | 227-236 |
| Backend local provider probes | `model_status.py` | 136-185 |
| Tesseract probe | `runtime_probe.py` | 17-106 |
| PaddleOCR probe | `runtime_probe.py` | 311-439 |
| `_get_setting` DB helper | `model_status.py` | 127-133 |
| `validateRunConfig` (config validation) | `run-config.ts` | 511-571 |
| `buildJobConfig` (job submission) | `run-config.ts` | 657-806 |

## Caveats / Not Found

1. **No "⚠️ AIOCR 未就绪" exact string exists** — the warning is dynamically constructed from provider labels + "未就绪" suffix.

2. **AIOCR model list is hardcoded** in `page.tsx` (5 models). There's no API endpoint to fetch available models. The backend doesn't validate model names at the status check level.

3. **Frontend settings and backend settings are separate stores** — the frontend localStorage settings are NOT what the backend status API reads from. The backend reads from `site_settings` DB table.

4. **The `configured` field** in `ModelProviderStatus` is only set for remote providers. For local providers, it defaults to `True`.

5. **No automatic status polling** — `useModelStatus` fetches once on mount. Status is refreshed on `refetchModelStatus()` call (triggered by download completion or manual refresh).
