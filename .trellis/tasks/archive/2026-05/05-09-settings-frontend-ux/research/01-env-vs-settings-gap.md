# Research: Backend Env Vars vs Frontend Settings Gap

- **Query**: Map the gap between backend env vars and frontend settings
- **Scope**: internal
- **Date**: 2026-05-09

## Findings

---

## 1. Backend Settings (Every Field)

Source: `api/app/config.py` — `Settings(BaseSettings)` class, loaded from `.env` file.

### Infrastructure & Deployment

| # | Field | Env Var | Type | Default | Purpose |
|---|-------|---------|------|---------|---------|
| 1 | `api_bind_host` | `API_BIND_HOST` | `str` | `"127.0.0.1"` | API server bind address |
| 2 | `api_bearer_token` | `API_BEARER_TOKEN` | `str \| None` | `None` | Optional bearer token for API access |
| 3 | `redis_url` | `REDIS_URL` | `str` | `"redis://redis:6379/0"` | Redis connection URL |
| 4 | `log_level` | `LOG_LEVEL` | `str` | `"INFO"` | Logging level |
| 5 | `sqlite_path` | `SQLITE_PATH` | `str` | `"data/pdf2ppt.db"` | SQLite DB path (relative to api/) |
| 6 | `job_root_dir` | `JOB_ROOT_DIR` | `str` | `"data/jobs"` | Root dir for per-job runtime artifacts |
| 7 | `cors_allow_origins` | `CORS_ALLOW_ORIGINS` | `str` | `"http://localhost:3000,http://127.0.0.1:3000"` | Comma-separated CORS origins |
| 8 | `cors_allow_origin_regex` | `CORS_ALLOW_ORIGIN_REGEX` | `str \| None` | `None` | Optional CORS origin regex |

### Job Lifecycle

| # | Field | Env Var | Type | Default | Purpose |
|---|-------|---------|------|---------|---------|
| 9 | `job_ttl_minutes` | `JOB_TTL_MINUTES` | `int` | `1440` | Job metadata/artifact retention (24h) |
| 10 | `job_cleanup_interval_minutes` | `JOB_CLEANUP_INTERVAL_MINUTES` | `int` | `15` | Cleanup sweep cadence |
| 11 | `job_keepalive_interval_s` | `JOB_KEEPALIVE_INTERVAL_S` | `int` | `15` | Heartbeat interval for long-running stages |
| 12 | `job_debug_events_limit` | `JOB_DEBUG_EVENTS_LIMIT` | `int` | `200` | Max debug events per job |
| 13 | `job_timeout_seconds` | `JOB_TIMEOUT_SECONDS` | `int` | `3600` | RQ/inline-thread job timeout (1 hour) |

### Job Constraints

| # | Field | Env Var | Type | Default | Purpose |
|---|-------|---------|------|---------|---------|
| 14 | `max_file_mb` | `MAX_FILE_MB` | `int` | `100` | Max upload file size in MB |
| 15 | `max_pages` | `MAX_PAGES` | `int` | `200` | Max pages per document |
| 16 | `min_disk_space_mb` | `MIN_DISK_SPACE_MB` | `int` | `500` | Min free disk space (MB) for uploads |

### Rate Limiting

| # | Field | Env Var | Type | Default | Purpose |
|---|-------|---------|------|---------|---------|
| 17 | `rate_limit_requests` | `RATE_LIMIT_REQUESTS` | `int` | `60` | Requests per window per client IP |
| 18 | `rate_limit_window_seconds` | `RATE_LIMIT_WINDOW_SECONDS` | `int` | `60` | Rate limit window duration |

### Rendering / Debug Export

| # | Field | Env Var | Type | Default | Purpose |
|---|-------|---------|------|---------|---------|
| 19 | `ocr_render_dpi` | `OCR_RENDER_DPI` | `int` | `200` | OCR render DPI for scanned PDFs |
| 20 | `scanned_render_dpi` | `SCANNED_RENDER_DPI` | `int` | `200` | PPTX background render DPI |
| 21 | `export_ocr_overlay_images` | `EXPORT_OCR_OVERLAY_IMAGES` | `bool` | `False` | Export OCR overlay debug images |
| 22 | `export_layout_assist_debug_images` | `EXPORT_LAYOUT_ASSIST_DEBUG_IMAGES` | `bool` | `False` | Export layout-assist debug images |
| 23 | `export_final_preview_images` | `EXPORT_FINAL_PREVIEW_IMAGES` | `bool` | `False` | Export final preview images (opt-in) |
| 24 | `export_final_preview_max_pages` | `EXPORT_FINAL_PREVIEW_MAX_PAGES` | `int` | `5` | Max pages for final preview images |

### OCR Pipeline Tuning

| # | Field | Env Var | Type | Default | Purpose |
|---|-------|---------|------|---------|---------|
| 25 | `ocr_page_timeout_s` | `OCR_PAGE_TIMEOUT_S` | `int` | `300` | Per-page OCR timeout (seconds) |
| 26 | `ocr_max_consecutive_timeouts` | `OCR_MAX_CONSECUTIVE_TIMEOUTS` | `int` | `2` | Circuit-breaker: consecutive timeout limit |
| 27 | `ocr_total_timeout_s` | `OCR_TOTAL_TIMEOUT_S` | `int` | `3600` | Overall OCR stage timeout |
| 28 | `ocr_image_region_timeout_s` | `OCR_IMAGE_REGION_TIMEOUT_S` | `int` | `12` | AI image-region detection timeout |
| 29 | `ocr_paddle_vl_predict_timeout_s` | `OCR_PADDLE_VL_PREDICT_TIMEOUT_S` | `float` | `180.0` | PaddleOCR-VL predict timeout |
| 30 | `ocr_ai_retry_backoff_base_s` | `OCR_AI_RETRY_BACKOFF_BASE_S` | `float` | `8.0` | Base retry backoff for AI OCR calls |
| 31 | `ocr_ai_rate_limited_min_delay_s` | `OCR_AI_RATE_LIMITED_MIN_DELAY_S` | `float` | `2.0` | Min delay after rate-limited response |

### OCR AI Concurrency/Concurrency Cap Defaults & Max

| # | Field | Env Var | Type | Default | Purpose |
|---|-------|---------|------|---------|---------|
| 32 | `ocr_ai_page_concurrency_default` | `OCR_AI_PAGE_CONCURRENCY_DEFAULT` | `int` | `1` | Default page concurrency |
| 33 | `ocr_ai_page_concurrency_max` | `OCR_AI_PAGE_CONCURRENCY_MAX` | `int` | `8` | Max page concurrency cap |
| 34 | `ocr_ai_block_concurrency_default` | `OCR_AI_BLOCK_CONCURRENCY_DEFAULT` | `int` | `1` | Default block concurrency |
| 35 | `ocr_ai_block_concurrency_max` | `OCR_AI_BLOCK_CONCURRENCY_MAX` | `int` | `8` | Max block concurrency cap |
| 36 | `ocr_ai_rpm_default` | `OCR_AI_RPM_DEFAULT` | `int` | `1` | Default RPM |
| 37 | `ocr_ai_rpm_max` | `OCR_AI_RPM_MAX` | `int` | `2000` | Max RPM cap |
| 38 | `ocr_ai_tpm_default` | `OCR_AI_TPM_DEFAULT` | `int` | `1000` | Default TPM |
| 39 | `ocr_ai_tpm_max` | `OCR_AI_TPM_MAX` | `int` | `2_000_000` | Max TPM cap |
| 40 | `ocr_ai_max_retries_default` | `OCR_AI_MAX_RETRIES_DEFAULT` | `int` | `0` | Default max retries |
| 41 | `ocr_ai_max_retries_max` | `OCR_AI_MAX_RETRIES_MAX` | `int` | `8` | Max retries cap |

### Feature Toggles

| # | Field | Env Var | Type | Default | Purpose |
|---|-------|---------|------|---------|---------|
| 42 | `enable_layout_assist` | `ENABLE_LAYOUT_ASSIST` | `bool` | `False` | Enable AI layout assist stage |
| 43 | `extra_font_paths` | `EXTRA_FONT_PATHS` | `str` | `""` | Comma-separated extra font search paths |

### Auth / Deploy Mode

| # | Field | Env Var | Type | Default | Purpose |
|---|-------|---------|------|---------|---------|
| 44 | `deploy_mode` | `DEPLOY_MODE` | `str` | `"self"` | "self" (localStorage) or "public" (multi-user DB) |
| 45 | `admin_default_password` | `ADMIN_DEFAULT_PASSWORD` | `str` | `"admin12345678"` | Default admin password (self-use mode) |
| 46 | `linuxdo_client_id` | `LINUXDO_CLIENT_ID` | `str \| None` | `None` | LinuxDo OAuth client ID |
| 47 | `linuxdo_client_secret` | `LINUXDO_CLIENT_SECRET` | `str \| None` | `None` | LinuxDo OAuth client secret |
| 48 | `linuxdo_redirect_uri` | `LINUXDO_REDIRECT_URI` | `str` | `"http://localhost:3000/auth/callback"` | OAuth redirect URI |
| 49 | `jwt_secret` | `JWT_SECRET` | `str` | `""` | JWT signing secret |
| 50 | `cookie_secure` | `COOKIE_SECURE` | `bool` | `True` | Cookie secure flag |
| 51 | `admin_usernames` | `ADMIN_USERNAMES` | `str` | `""` | Comma-separated usernames auto-promoted to admin |
| 52 | `jwt_access_expire_minutes` | `JWT_ACCESS_EXPIRE_MINUTES` | `int` | `60` | JWT access token expiry |
| 53 | `jwt_refresh_expire_days` | `JWT_REFRESH_EXPIRE_DAYS` | `int` | `30` | JWT refresh token expiry |

**Total backend fields: 53**

---

## 2. Frontend Settings (Every Field)

Source: `web/src/lib/settings.ts` — `Settings` type and `defaultSettings`.

### Provider / Parse Engine

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 1 | `provider` | `Provider` | `"openai"` | Yes — Parse Engine selector |
| 2 | `preferredMainProvider` | `MainProvider` | `"openai"` | Implicit via `provider` |
| 3 | `parseEngineMode` | `ParseEngineMode` | `"local_ocr"` | Yes — Parse Engine selector |

### Main Model API

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 4 | `openaiApiKey` | `string` | `""` | Yes — SensitiveInput (hidden in public mode) |
| 5 | `openaiBaseUrl` | `string` | `""` | No explicit control in settings page (maybe elsewhere?) |
| 6 | `openaiModel` | `string` | `""` | No explicit control in settings page |
| 7 | `claudeApiKey` | `string` | `""` | No explicit control in settings page |

### MinerU

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 8 | `mineruApiToken` | `string` | `""` | Yes — SensitiveInput |
| 9 | `mineruBaseUrl` | `string` | `""` | Yes — Input |
| 10 | `mineruModelVersion` | `MineruModelVersion` | `"vlm"` | Yes — Select (pipeline/vlm/MinerU-HTML) |
| 11 | `mineruEnableFormula` | `boolean` | `true` | Yes — Checkbox |
| 12 | `mineruEnableTable` | `boolean` | `true` | Yes — Checkbox |
| 13 | `mineruLanguage` | `string` | `""` | Yes — Input |
| 14 | `mineruIsOcr` | `boolean` | `false` | Yes — Checkbox |
| 15 | `mineruHybridOcr` | `boolean` | `false` | No UI control |

### Layout Assist (force-disabled)

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 16 | `enableLayoutAssist` | `boolean` | `false` | **Forced to `false`** at `settings.ts:571` — hardcoded override in `loadStoredSettings()` |
| 17 | `layoutAssistApplyImageRegions` | `boolean` | `false` | **Forced to `false`** at `settings.ts:572` |
| 18-21 | `visualAssistMode{Local,Remote,BaiduDoc,Mineru}` | `LayoutAssistMode` | `"off"` | **Forced to `"off"`** at `settings.ts:579-582` |

### OCR

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 22 | `enableOcr` | `boolean` | `true` | No explicit control — inferred from engine mode |
| 23 | `removeFooterNotebooklm` | `boolean` | `false` | Yes — Checkbox |
| 24 | `textEraseMode` | `TextEraseMode` | `"fill"` | Yes — Select (inside AdvancedReveal) |
| 25 | `scannedPageMode` | `ScannedPageMode` | `"segmented"` | Yes — Select |
| 26 | `pptGenerationMode` | `PptGenerationMode` | `"fast"` | No explicit UI control visible (may be in homepage) |

### Image Tuning

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 27 | `imageBgClearExpandMinPt` | `string` | `"0.35"` | Yes — number input (AdvancedReveal) |
| 28 | `imageBgClearExpandMaxPt` | `string` | `"1.5"` | Yes — number input (AdvancedReveal) |
| 29 | `imageBgClearExpandRatio` | `string` | `"0.012"` | Yes — number input (AdvancedReveal) |
| 30 | `scannedImageRegionMinAreaRatio` | `string` | `"0.0025"` | Yes — number input (AdvancedReveal) |
| 31 | `scannedImageRegionMaxAreaRatio` | `string` | `"0.72"` | Yes — number input (AdvancedReveal) |
| 32 | `scannedImageRegionMaxAspectRatio` | `string` | `"4.8"` | Yes — number input (AdvancedReveal) |

### OCR DPI & Strict Mode

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 33 | `ocrRenderDpi` | `string` | `"200"` | Yes — number input (AdvancedReveal, non-mineru) |
| 34 | `ocrStrictMode` | `boolean` | `true` | Yes — Checkbox (AdvancedReveal) |

### OCR Provider

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 35 | `ocrProvider` | `OcrProvider` | `"machine"` | Yes — Radio (when available) |

### Baidu

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 36 | `baiduDocParseType` | `BaiduDocParseType` | `"paddle_vl"` | Yes — Select |
| 37 | `ocrBaiduAppId` | `string` | `""` | Yes — Input (AdvancedReveal) |
| 38 | `ocrBaiduApiKey` | `string` | `""` | Yes — SensitiveInput |
| 39 | `ocrBaiduSecretKey` | `string` | `""` | Yes — SensitiveInput |

### Tesseract

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 40 | `ocrTesseractMinConfidence` | `string` | `"35"` | Yes — number input |
| 41 | `ocrTesseractLanguage` | `string` | `"chi_sim+eng"` | Yes — text input |

### AI OCR

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 42 | `ocrAiApiKey` | `string` | `""` | Yes — SensitiveInput |
| 43 | `ocrAiProvider` | `OcrAiProvider` | `"siliconflow"` | Yes — Select |
| 44 | `ocrAiBaseUrl` | `string` | `"https://api.siliconflow.cn/v1"` | Yes — Input |
| 45 | `ocrAiModel` | `string` | `""` | Yes — Input + autocomplete dropdown |
| 46 | `ocrAiChainMode` | `OcrAiChainMode` | `"layout_block"` | Yes — Select |
| 47 | `ocrAiLayoutModel` | `OcrAiLayoutModel` | `"pp_doclayout_v3"` | Yes — Radio (with download button) |
| 48 | `ocrAiPromptPreset` | `OcrAiPromptPreset` | `"auto"` | Yes — Select (AdvancedReveal) |
| 49 | `ocrAiDirectPromptOverride` | `string` | `""` | Yes — Textarea (AdvancedReveal) |
| 50 | `ocrAiLayoutBlockPromptOverride` | `string` | `""` | Yes — Textarea (AdvancedReveal) |
| 51 | `ocrAiImageRegionPromptOverride` | `string` | `""` | Yes — Textarea (AdvancedReveal) |
| 52 | `ocrPaddleVlDocparserMaxSidePx` | `string` | `"2200"` | Yes — number input (AdvancedReveal) |

### AI OCR Concurrency / Rate Limit

| # | Field | Type | Default | UI Control? |
|---|-------|------|---------|-------------|
| 53 | `ocrAiPageConcurrencyAuto` | `boolean` | `true` | Implicit via clearing input |
| 54 | `ocrAiPageConcurrency` | `string` | `"1"` | Yes — number input (AdvancedReveal) |
| 55 | `ocrAiBlockConcurrency` | `string` | `""` | Yes — number input (AdvancedReveal) |
| 56 | `ocrAiRequestsPerMinute` | `string` | `""` | Yes — number input (AdvancedReveal) |
| 57 | `ocrAiTokensPerMinute` | `string` | `""` | Yes — number input (AdvancedReveal) |
| 58 | `ocrAiMaxRetries` | `string` | `"0"` | Yes — number input (AdvancedReveal) |

**Total frontend fields: 58**

---

## 3. Gap Analysis: Backend Env → Frontend Mapping

### 3.1 Backend env vars that ARE reflected in frontend settings (via job parameters, not env)

These are sent **per-job** as runtime parameters, not stored as env vars on the backend:

| Backend Env Var | Frontend Setting | How It Flows |
|---|---|---|
| `OCR_RENDER_DPI` (default 200) | `settings.ocrRenderDpi` ("200") | Frontend sends `ocr_render_dpi` in `JobConfig` → worker reads at runtime. The env var is a **server-side cap/default**, not directly changeable by the user. |
| `OCR_AI_PAGE_CONCURRENCY_DEFAULT/MAX` | `settings.ocrAiPageConcurrency` | Frontend sends `ocr_ai_page_concurrency` per-job. The env var caps the max at 8. |
| `OCR_AI_BLOCK_CONCURRENCY_DEFAULT/MAX` | `settings.ocrAiBlockConcurrency` | Frontend sends `ocr_ai_block_concurrency` per-job. |
| `OCR_AI_RPM_DEFAULT/MAX` | `settings.ocrAiRequestsPerMinute` | Frontend sends `ocr_ai_requests_per_minute` per-job. |
| `OCR_AI_TPM_DEFAULT/MAX` | `settings.ocrAiTokensPerMinute` | Frontend sends `ocr_ai_tokens_per_minute` per-job. |
| `OCR_AI_MAX_RETRIES_DEFAULT/MAX` | `settings.ocrAiMaxRetries` | Frontend sends `ocr_ai_max_retries` per-job. |
| `ENABLE_LAYOUT_ASSIST` | `settings.enableLayoutAssist` | **Force-disabled** in frontend! At `settings.ts:571`, `merged.enableLayoutAssist = false` always. The server env toggle cannot be overridden by the user. |
| `EXPORT_FINAL_PREVIEW_IMAGES` | N/A (indirect) | Can be triggered via `retainProcessArtifacts` job option. |
| `DEPLOY_MODE` | `deployMode` state | Fetched via `GET /api/v1/config/deploy-mode` at hook init (`use-settings.ts:55`). Controls self/public behavior. |
| `ocr_ai_*` concurrency cap env vars | Frontend `ocrAiPageConcurrency` etc. | Server caps are **hardcoded** in frontend validation at `loadStoredSettings()` (e.g., page concurrency clamped to `Math.min(8, ...)` at `settings.ts:533`). These match the server max but are **duplicated** rather than synced dynamically. |

### 3.2 Backend env vars NOT represented in ANY frontend setting

These can only be changed by an admin editing the `.env` file or via `PUT /api/v1/admin/env`:

| Group | Fields Not In Frontend | Total |
|---|---|---|
| **Infrastructure** | `api_bind_host`, `api_bearer_token`, `redis_url`, `log_level`, `sqlite_path`, `cors_allow_origins`, `cors_allow_origin_regex` | 7 |
| **Job Lifecycle** | `job_ttl_minutes`, `job_cleanup_interval_minutes`, `job_keepalive_interval_s`, `job_debug_events_limit`, `job_timeout_seconds` | 5 |
| **Job Constraints** | `max_file_mb`, `max_pages`, `min_disk_space_mb` | 3 |
| **Rate Limiting** | `rate_limit_requests`, `rate_limit_window_seconds` | 2 |
| **Debug Export** | `scanned_render_dpi`, `export_ocr_overlay_images`, `export_layout_assist_debug_images`, `export_final_preview_max_pages` | 4 |
| **OCR Pipeline** | `ocr_page_timeout_s`, `ocr_max_consecutive_timeouts`, `ocr_total_timeout_s`, `ocr_image_region_timeout_s`, `ocr_paddle_vl_predict_timeout_s`, `ocr_ai_retry_backoff_base_s`, `ocr_ai_rate_limited_min_delay_s` | 7 |
| **Frontend Auth** | `jwt_access_expire_minutes`, `jwt_refresh_expire_days` (comment says "keep in sync with frontend cookie maxAge") | 2 |
| **OAuth/Auth** | `linuxdo_client_id`, `linuxdo_client_secret`, `linuxdo_redirect_uri`, `jwt_secret`, `cookie_secure`, `admin_usernames`, `admin_default_password` | 7 |
| **Other** | `extra_font_paths`, `job_root_dir` | 2 |

**Total NOT in frontend: 39 out of 53 (73.5%)**

### 3.3 Frontend settings NOT from backend env vars

These are purely browser-side user preferences or API credential fields:

| Group | Fields |
|---|---|
| **API Credentials** | `openaiApiKey`, `openaiBaseUrl`, `openaiModel`, `claudeApiKey`, `mineruApiToken`, `mineruBaseUrl`, `ocrAiApiKey`, `ocrAiBaseUrl`, `ocrBaiduApiKey`, `ocrBaiduSecretKey`, `ocrBaiduAppId` |
| **Provider Selection** | `provider`, `preferredMainProvider`, `parseEngineMode`, `ocrProvider`, `ocrAiProvider`, `ocrAiChainMode`, `ocrAiLayoutModel`, `ocrAiModel` |
| **Process Tuning** | `pptGenerationMode`, `scannedPageMode`, `textEraseMode`, `ocrStrictMode`, `baiduDocParseType`, `ocrTesseractMinConfidence`, `ocrTesseractLanguage` |
| **Image Tuning** | All `imageBgClear*`, `scannedImageRegion*` fields, `ocrPaddleVlDocparserMaxSidePx` |
| **Prompt Overrides** | `ocrAiDirectPromptOverride`, `ocrAiLayoutBlockPromptOverride`, `ocrAiImageRegionPromptOverride`, `ocrAiPromptPreset` |
| **Other** | `removeFooterNotebooklm`, `mineruEnableFormula`, `mineruEnableTable`, `mineruLanguage`, `mineruIsOcr`, `mineruHybridOcr`, `mineruModelVersion`, `enableOcr` |

---

## 4. Settings Persistence & Sync Architecture

### 4.1 Frontend Settings Storage

Source: `web/src/hooks/use-settings.ts`

Two modes of storage based on `deploy_mode`:

| Mode | Where settings are saved | How sync works |
|---|---|---|
| **"self"** | `localStorage` (key: `"pdf-to-ppt.settings.v1"`) | Auto-save with 500ms debounce (`use-settings.ts:111-113`). Sensitive keys are **NOT** excluded — all values stored in localStorage. |
| **"public"** | `PUT /api/v1/user/preferences` (DB table `user_preferences`) | Auto-save with 500ms debounce (`use-settings.ts:117-126`). **Sensitive keys are excluded** before sending to API. Loaded on init via `GET /api/v1/user/preferences`. |

**Sensitive keys excluded in public mode** (defined at `use-settings.ts:15-22`):
- `openaiApiKey`, `claudeApiKey`, `mineruApiToken`
- `ocrBaiduApiKey`, `ocrBaiduSecretKey`, `ocrAiApiKey`

### 4.2 Deploy Mode Discovery

`use-settings.ts:55-68`: Frontend calls `GET /api/v1/config/deploy-mode` on mount. Backend (`config.py:155-172`) checks `site_settings` DB table first, then falls back to `DEPLOY_MODE` env var.

### 4.3 Backend Env Var Admin Editing

Source: `api/app/routers/admin.py:460-524` and `web/src/app/admin/env/page.tsx`

- **Endpoint**: `GET/PUT /api/v1/admin/env` — admin-only, reads/writes `.env` file directly
- **Frontend UI**: `/admin/env` page — table editor + raw text editor
- **Sensitive keys masked in GET**: `jwt_secret`, `linuxdo_client_secret`, `api_bearer_token`, `web_access_password` — shown as `••••••••`
- **Sensitive value guard on PUT**: masked values are skipped (not overwritten with the mask)
- **Effect**: Changes require container restart (`docker compose restart api worker`)

### 4.4 Site Settings (Public Mode)

Source: `api/app/routers/admin.py:527-573` and `web/src/app/admin/site-settings/page.tsx`

- **Endpoint**: `GET/PUT /api/v1/admin/site-settings` — admin-only, stores in `site_settings` DB table
- **Sensitive keys**: `openai_api_key`, `claude_api_key`, `mineru_api_token`, `ocr_baidu_api_key`, `ocr_baidu_secret_key`, `ocr_ai_api_key`
- **Purpose**: In public mode, admin configures shared API keys that all users inherit. The `model_status.py` router reads these to determine provider readiness.

### 4.5 User Preferences (Public Mode)

Source: `api/app/routers/config.py:33-72` and `api/app/models/user.py:226-247`

- **Table**: `user_preferences` (key-value store, per-user)
- **Endpoints**: `GET/PUT /api/v1/user/preferences` (authenticated user)
- **Stores**: Non-sensitive settings fields as flat key-value strings
- **No existing UI** for admin to manage per-user preferences — only used by the frontend hook auto-save

---

## 5. Settings Page UI Summary

Source: `web/src/app/settings/page.tsx` (2572 lines)

| Section | Controls |
|---|---|
| **Parse Engine** | 4 buttons: local_ocr / remote_ocr (AIOCR) / baidu_doc / mineru_cloud |
| **Advanced toggle** | Show/hide advanced params and diagnostics |
| **API Config** (shown when mineru or advanced) | API origin override (backend URL), MinerU credentials (token, base URL, model version, language, enable formula/table/OCR) |
| **Processing Strategy** | Text erase mode, scanned page mode, OCR render DPI, remove NotebookLM footer, image tuning (6 fields, all in AdvancedReveal) |
| **OCR Config** | OCR provider selector (radio), OCR strict mode, AIOCR vendor adapter, dedicated OCR API params (key, base URL, chain mode, layout model, OCR model + autocomplete), prompt experiment (preset + overrides), concurrency & rate limit (4 fields), Baidu config, Tesseract config, local OCR health check (Tesseract + PaddleOCR) |
| **Model Download** | `DownloadProgressButton` for paddleocr and layout models (integrated into the settings page) |

---

## 6. Key Architectural Observations

1. **Dual persistence**: self mode uses localStorage (client only), public mode uses server DB (survives browser). No server-side persistence for localStorage settings.

2. **Layout assist is dead code**: `enableLayoutAssist`, `layoutAssistApplyImageRegions`, and all four `visualAssistMode*` fields are force-overridden to off in `loadStoredSettings()` at lines 571-582. The backend env var `ENABLE_LAYOUT_ASSIST` cannot influence the frontend because the frontend hardcodes these off.

3. **Concurrency caps are duplicated**: `ocr_ai_page_concurrency_max = 8` on the backend, and `Math.min(8, ...)` at `settings.ts:533` on the frontend. Same for other caps. These are **not synced** — if the server-side cap changes, the frontend clamp becomes stale.

4. **Admin env editor exists but is raw**: The admin `/admin/env` page edits the `.env` file directly as raw key-value pairs. There is no form validation, field descriptions, type enforcement, or guidance about which fields affect what. Users see bare env var names like `OCR_AI_RPM_DEFAULT`.

5. **Model download is UI-only**: Model download status uses `useModelDownload` hook (starts download via API). No server-side env var controls download behavior. Download progress tracked via `useModelStatus`.

6. **Job timeout is not in frontend settings**: `JOB_TIMEOUT_SECONDS` (default 3600) is server-enforced. Frontend sends `job_timeout` in job config but there is no settings UI for it.

---

## Caveats / Not Found

- `openaiBaseUrl` and `openaiModel` are in the `Settings` type but were not found as explicit UI controls on the settings page — they may be configured elsewhere (possibly the homepage or a different page).
- `mineruHybridOcr` is in the type but has no UI control on the settings page.
- The `pptGenerationMode` field exists in `Settings` type but was not found as a visible standalone control on the settings page (it may be on the homepage).
- `enableOcr` has no direct checkbox — it is inferred from the parse engine mode.
- Some env vars like `web_access_password` appear in the `SENSITIVE_KEYS` set of admin.py but are NOT present in `config.py`'s `Settings` class — this suggests it's used elsewhere or was deprecated.
