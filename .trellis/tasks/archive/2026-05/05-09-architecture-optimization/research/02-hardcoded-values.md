# Research: Hardcoded Values Audit

- **Query**: Find ALL hardcoded timeout values, magic numbers, hardcoded URLs, configuration constants across api/ and web/
- **Scope**: internal (full codebase)
- **Date**: 2026-05-09

## Executive Summary

This audit found **~85+ hardcoded constants** across the codebase. Many are already defined as named module-level constants (a good practice), but few are externally configurable via environment variables or settings. The `api/app/convert/ocr/ai_client.py` file alone contains **~60 hardcoded constants** for tuning OCR pipeline behavior (thresholds, padding, margins, timeouts). The `api/app/worker.py` file has another **~30+ bounds constants** for image processing parameters.

---

## 1. Timeouts (Backend — api/)

### Currently Configurable (via Settings)

| File | Line | Value | Controls | Configurable? |
|------|------|-------|----------|---------------|
| `api/app/config.py` | 60 | `300` | `ocr_page_timeout_s` — per-page OCR timeout (seconds) | Yes (env) |
| `api/app/config.py` | 64 | `2` | `ocr_max_consecutive_timeouts` — page timeout circuit breaker count | Yes (env) |
| `api/app/config.py` | 67 | `3600` | `ocr_total_timeout_s` — overall OCR stage timeout (seconds) | Yes (env) |
| `api/app/config.py` | 70 | `12` | `ocr_image_region_timeout_s` — AI image-region detection timeout (seconds) | Yes (env) |

### Hardcoded (NOT configurable)

| File | Line | Value | Controls | Should be configurable? |
|------|------|-------|----------|------------------------|
| `api/app/auth.py` | 44 | `10.0` | `_OAUTH_HTTP_TIMEOUT_S` — HTTP client timeout for OAuth requests | Low — rarely needs tuning |
| `api/app/auth.py` | 31 | `60` | `ACCESS_TOKEN_EXPIRE_MINUTES` — JWT access token expiry | Medium |
| `api/app/auth.py` | 32 | `30` | `REFRESH_TOKEN_EXPIRE_DAYS` — JWT refresh token expiry | Medium |
| `api/app/auth.py` | 38 | `600` | `_STATE_EXPIRY_SECONDS` — OAuth state TTL | Low |
| `api/app/convert/ocr/ai_client.py` | 93 | `60.0` | `_RATE_LIMITER_CUTOFF_WINDOW_S` | Low — tuning knob |
| `api/app/convert/ocr/ai_client.py` | 94 | `60.0` | `_RATE_LIMITER_MAX_WAIT_S` | Low — tuning knob |
| `api/app/convert/ocr/ai_client.py` | 95 | `0.05` | `_RATE_LIMITER_SLEEP_MIN_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 96 | `5.0` | `_RATE_LIMITER_SLEEP_MAX_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 100 | `8.0` | `_RETRY_BACKOFF_BASE_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 101 | `0.75` | `_RETRY_BACKOFF_MAX_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 102 | `2` | `_RETRY_BACKOFF_MULTIPLIER` | Low |
| `api/app/convert/ocr/ai_client.py` | 103 | `2.0` | `_RATE_LIMITED_MIN_DELAY_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 104 | `0.25` | `_NON_RATE_LIMITED_MIN_DELAY_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 114 | `180.0` | `_PADDLE_VL15_PREDICT_TIMEOUT_S` | Medium — PaddleOCR-VL-1.5 predict timeout |
| `api/app/convert/ocr/ai_client.py` | 115 | `10.0` | `_PADDLE_MIN_PREDICT_TIMEOUT_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 116 | `90.0` | `_PADDLE_RETRY_TIMEOUT_CAP_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 117 | `3.0` | `_SINGLEFLIGHT_WAIT_S` — singleflight lock wait | Low |
| `api/app/convert/ocr/ai_client.py` | 120 | `0.01` | `_CONCURRENCY_WAIT_MIN_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 121 | `0.1` | `_CONCURRENCY_WAIT_MAX_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 122 | `1.0` | `_DONE_WAIT_TIMEOUT_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 125 | `5.0` | `_LAYOUT_MODEL_INIT_TIMEOUT_MIN_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 127 | `5.0` | `_LAYOUT_BLOCK_PREDICT_TIMEOUT_MIN_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 187 | `12.0` | `_REQUEST_TIMEOUT_BUFFER_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 188 | `1.5` | `_REQUEST_TIMEOUT_MULTIPLIER` | Low |
| `api/app/convert/ocr/ai_client.py` | 189 | `55.0` | `_REQUEST_TIMEOUT_CAP_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 190 | `8.0` | `_RETRY_TIMEOUT_BUFFER_S` | Low |
| `api/app/convert/ocr/ai_client.py` | 1488 | `30.0` | Paddle doc parser init timeout fallback (env overridable via `OCR_PADDLE_VL_DOCPARSER_INIT_TIMEOUT_S`) | Yes (partially — env var) |
| `api/app/convert/ocr/ai_client.py` | 2068 | `30.0` | Layout model init timeout fallback (env overridable via `OCR_AI_LAYOUT_MODEL_INIT_TIMEOUT_S`) | Yes (partially — env var) |
| `api/app/convert/ocr/ai_client.py` | 3468 | `30.0` | Image region timeout fallback (env overridable via `OCR_AI_IMAGE_REGION_TIMEOUT_S`) | Yes (partially — env var) |
| `api/app/convert/ocr/ai_client.py` | 4635 | `60.0` | Default request timeout for remote doc parser predict | Low |
| `api/app/routers/model_status.py` | 529 | `300` | Download task expiry — clean up completed tasks older than 5 minutes | Medium |

---

## 2. CPU/Concurrency Limits (Backend — api/)

### Currently Configurable (via Settings + Job Options)

| File | Line | Value | Controls | Configurable? |
|------|------|-------|----------|---------------|
| `api/app/worker.py` | 108-110 | `1 / 1 / 8` | `_OCR_AI_PAGE_CONCURRENCY_*` — OCR AI page-level concurrency bounds | Yes (via ocr_ai_page_concurrency job option) |
| `api/app/worker.py` | 112-114 | `1 / 1 / 8` | `_OCR_AI_BLOCK_CONCURRENCY_*` — block-level concurrency bounds | Yes (via ocr_ai_block_concurrency job option) |
| `api/app/worker.py` | 119-121 | `1 / 1 / 2000` | `_OCR_AI_RPM_*` — requests-per-minute bounds | Yes (via ocr_ai_requests_per_minute) |
| `api/app/worker.py` | 123-125 | `1000 / 1 / 2_000_000` | `_OCR_AI_TPM_*` — tokens-per-minute bounds | Yes (via ocr_ai_tokens_per_minute) |
| `api/app/worker.py` | 130-132 | `0 / 0 / 8` | `_OCR_AI_MAX_RETRIES_*` — max retry bounds | Yes (via ocr_ai_max_retries) |

### Hardcoded (NOT configurable)

| File | Line | Value | Controls | Should be configurable? |
|------|------|-------|----------|------------------------|
| `api/app/convert/ocr/ai_client.py` | 97 | `4.0` | `_CHARS_PER_TOKEN` — character-per-token estimate for rate limiting | Low |
| `api/app/convert/ocr/ai_client.py` | 3637 | `60` | `max_items` parameter in `_extract_deepseek_image_regions` | Low |
| `api/app/convert/ocr/ai_client.py` | 4165 | `[60, 40, 24, 16, 10]` | `attempt_limits` for layout block OCR attempt limits | Low |
| `api/app/convert/ocr/ai_client.py` | 4170 | `[180, 120, 90, 60, 40]` | `attempt_limits` for dense scanned pages | Low |

---

## 3. Render/DPI Constants (Backend)

| File | Line | Value | Controls | Configurable? |
|------|------|-------|----------|---------------|
| `api/app/config.py` | 48 | `200` | `ocr_render_dpi` — OCR rendering DPI | Yes (env) |
| `api/app/config.py` | 49 | `200` | `scanned_render_dpi` — scanned page background render DPI | Yes (env) |
| `api/app/worker.py` | 61 | `72` | `OCR_RENDER_DPI_MIN` — minimum allowed DPI | Already a constant, bounded |
| `api/app/worker.py` | 62 | `400` | `OCR_RENDER_DPI_MAX` — maximum allowed DPI | Already a constant, bounded |
| `api/app/worker.py` | 63 | `120` | `OCR_RENDER_DPI_TURBO_CAP` — turbo mode DPI cap | Already a constant |
| `api/app/worker.py` | 64 | `160` | `OCR_RENDER_DPI_FAST_CAP` — fast mode DPI cap | Already a constant |

---

## 4. Image Processing Thresholds (Backend — worker.py)

All from `api/app/worker.py`, lines 66-102. These are named module-level constants defining bounds for image background clearing and scanned region detection:

### Image Background Clear Expand (lines 69-79)
| Line | Constant | Default | Bounds |
|------|----------|---------|--------|
| 69 | `_IMG_BG_CLEAR_EXPAND_MIN_PT_DEFAULT` | `0.35` | 0.0 – 6.0 |
| 73 | `_IMG_BG_CLEAR_EXPAND_MAX_PT_DEFAULT` | `1.5` | 0.0 – 8.0 |
| 77 | `_IMG_BG_CLEAR_EXPAND_RATIO_DEFAULT` | `0.012` | 0.0 – 0.12 |

### Scanned Region Detection (lines 83-96)
| Line | Constant | Default | Bounds |
|------|----------|---------|--------|
| 84 | `_SCANNED_REGION_MIN_AREA_RATIO_DEFAULT` | `0.0025` | 0.0 – 0.35 |
| 88 | `_SCANNED_REGION_MAX_AREA_RATIO_DEFAULT` | `0.72` | 0.05 – 1.0 |
| 94 | `_SCANNED_REGION_MAX_ASPECT_RATIO_DEFAULT` | `4.8` | 1.2 – 30.0 |

### PaddleVL Docparser (lines 100-103)
| Line | Constant | Default | Bounds |
|------|----------|---------|--------|
| 101 | `_PADDLE_VL_MAX_SIDE_PX_DEFAULT` | `2200` | 0 – 6000 |

### Progress Reporting (line 137)
| Constant | Value |
|----------|-------|
| `_PROGRESS_MAX_PROCESSING` | `99` (progress clamped 0–99 during processing) |

**Status:** All have well-defined bounds but are hardcoded in worker.py. The frontend `settings.ts` already persists most of these as user settings (imageBgClearExpandMinPt, scannedImageRegionMinAreaRatio, etc.), and the backend receives them via job config. The hardcoded values serve as fallback defaults when the frontend doesn't send them.

---

## 5. OCR Pipeline Tuning Constants (Backend — ai_client.py)

`api/app/convert/ocr/ai_client.py` contains the densest concentration of magic numbers. All are named module-level constants but are not externally configurable. Categories:

### Block Crop Padding (lines 130-135)
| Line | Constant | Value |
|------|----------|-------|
| 130 | `_BLOCK_CROP_PAD_MAX_PX` | `24` |
| 131 | `_BLOCK_CROP_PAD_MIN_PX` | `2` |
| 132 | `_BLOCK_CROP_PAD_RATIO` | `0.03` |
| 133 | `_BLOCK_CROP_YPAD_MAX_PX` | `24` |
| 134 | `_BLOCK_CROP_YPAD_MIN_PX` | `2` |
| 135 | `_BLOCK_CROP_YPAD_RATIO` | `0.18` |

### Ring Margin / Visual Bounds Tightening (lines 137-143)
| Line | Constant | Value |
|------|----------|-------|
| 138 | `_RING_YMARGIN_MAX_PX` | `18` |
| 139 | `_RING_YMARGIN_MIN_PX` | `2` |
| 140 | `_RING_YMARGIN_RATIO` | `0.10` |
| 141 | `_RING_XMARGIN_MAX_PX` | `18` |
| 142 | `_RING_XMARGIN_MIN_PX` | `2` |
| 143 | `_RING_XMARGIN_RATIO` | `0.04` |

### Background / Edge Thresholds (lines 145-158)
| Line | Constant | Value |
|------|----------|-------|
| 146 | `_BG_DIFF_LIGHT_THRESHOLD` | `18.0` |
| 147 | `_BG_DIFF_DARK_THRESHOLD` | `22.0` |
| 148 | `_BG_DIFF_LIGHT_BG_LUMA` | `150.0` |
| 151 | `_EDGE_THRESH_LOW` | `22` |
| 152 | `_EDGE_THRESH_HIGH` | `26` |
| 153 | `_EDGE_HEIGHT_CUTOFF` | `96` |

### Outer Margins & Row/Col Thresholds (lines 155-164)
| Line | Constant | Value |
|------|----------|-------|
| 156 | `_OUTER_MARGIN_MAX_PX` | `12` |
| 157 | `_OUTER_MARGIN_MIN_PX` | `2` |
| 158 | `_OUTER_MARGIN_RATIO` | `0.05` |
| 161 | `_ROW_THRESHOLD_MIN_PX` | `2` |
| 162 | `_ROW_THRESHOLD_RATIO` | `0.0035` |
| 163 | `_COL_THRESHOLD_MIN_PX` | `1` |
| 164 | `_COL_THRESHOLD_RATIO` | `0.020` |

### Keep Ratios & Local Padding (lines 166-181)
| Line | Constant | Value |
|------|----------|-------|
| 167 | `_KEEP_AREA_RATIO` | `0.94` |
| 168 | `_KEEP_WIDTH_RATIO` | `0.97` |
| 169 | `_KEEP_HEIGHT_RATIO` | `0.90` |
| 172 | `_PAD_X_MAX_PX` | `18` |
| 173 | `_PAD_X_MIN_PX` | `2` |
| 174 | `_PAD_X_RATIO` | `0.08` |
| 175 | `_PAD_Y_MAX_PX` | `12` |
| 176 | `_PAD_Y_MIN_PX` | `2` |
| 177 | `_PAD_Y_RATIO` | `0.12` |
| 180 | `_TIGHTENED_WIDTH_RATIO` | `0.985` |
| 181 | `_TIGHTENED_HEIGHT_RATIO` | `0.94` |
| 184 | `_DEFAULT_TOLERANCE_PX` | `1.5` |

**Verdict:** All Low priority. These are empirically tuned visual processing parameters that rarely need per-deployment adjustment. They are already centralized as named constants.

---

## 6. OCR Bypass / Validation Thresholds (Backend — ai_client.py)

| Line | Constant | Value | Purpose |
|------|----------|-------|---------|
| 193 | `_LOW_CONFIDENCE_THRESHOLD` | `0.6` | Adaptive coverage threshold |
| 194 | `_HIGH_CONFIDENCE_THRESHOLD` | `0.85` | Adaptive coverage threshold |
| 195 | `_LOW_CONFIDENCE_COVERAGE_MULTIPLIER` | `0.6` | Coverage multiplier |
| 196 | `_HIGH_CONFIDENCE_COVERAGE_MULTIPLIER` | `1.3` | Coverage multiplier |
| 197 | `_WIDE_FLAT_MIN_ASPECT_RATIO` | `7.0` | Wide-flat block detection |
| 198 | `_WIDE_FLAT_MIN_WIDTH_RATIO` | `0.35` | Wide-flat block detection |
| 199 | `_WIDE_FLAT_MAX_HEIGHT_RATIO` | `0.18` | Wide-flat block detection |
| 200 | `_WIDE_FLAT_MAX_VERTICAL_SPAN` | `0.28` | Wide-flat block detection |
| 201 | `_WIDE_FLAT_MIN_COVERAGE_RATIO` | `0.65` | Wide-flat block detection |
| 204 | `_CONFIDENCE_BYPASS_LOW_THRESHOLD` | `0.5` | Individual confidence bypass |
| 205 | `_CONFIDENCE_BYPASS_AVG_THRESHOLD` | `0.4` | Average confidence bypass |
| 206 | `_CONFIDENCE_BYPASS_RATIO_THRESHOLD` | `0.5` | Low confidence ratio bypass |
| 209 | `_VALIDATION_DENSITY_THRESHOLD` | `0.3` | Text density validation (chars/10Kpx) |
| 210 | `_VALIDATION_COHERENCE_THRESHOLD` | `0.4` | Coherence validation |
| 211 | `_VALIDATION_MIN_CHARS_FOR_COHERENCE` | `10` | Min chars for coherence check |
| 212 | `_VALIDATION_LARGE_IMAGE_AREA` | `500000` | Large image area threshold (pixels) |
| 213 | `_VALIDATION_TOO_FEW_BLOCKS` | `2` | Too-few-blocks threshold |
| 214 | `_PIXELS_PER_10K` | `10000.0` | Density calculation factor |

**Verdict:** Low priority. These are empirically derived quality thresholds. Already centralized constants.

---

## 7. Debug/Limits (Backend)

| File | Line | Value | Controls |
|------|------|-------|----------|
| `api/app/convert/ocr/ai_client.py` | 107 | `160` | `_DEBUG_TEXT_COMPACT_LIMIT` |
| `api/app/convert/ocr/ai_client.py` | 108 | `400` | `_DEBUG_TEXT_CONTENT_LIMIT` |
| `api/app/convert/ocr/ai_client.py` | 109 | `240` | `_DEBUG_TEXTS_LIMIT` |
| `api/app/convert/ocr/ai_client.py` | 110 | `64` | `_DEBUG_LABEL_LIMIT` |
| `api/app/auth.py` | 45 | `500` | `_DEBUG_RESPONSE_TEXT_LIMIT` |

---

## 8. Limit / Capacity Sizing (Backend)

| File | Line | Value | Controls | Configurable? |
|------|------|-------|----------|---------------|
| `api/app/config.py` | 24 | `100` | `max_file_mb` — max upload file size | Yes (env) |
| `api/app/config.py` | 25 | `200` | `max_pages` — max PDF pages | Yes (env) |
| `api/app/config.py` | 28 | `1440` | `job_ttl_minutes` — job retention (24h) | Yes (env) |
| `api/app/config.py` | 30 | `15` | `job_cleanup_interval_minutes` | Yes (env) |
| `api/app/config.py` | 33 | `15` | `job_keepalive_interval_s` | Yes (env) |
| `api/app/config.py` | 35 | `200` | `job_debug_events_limit` | Yes (env) |
| `api/app/config.py` | 57 | `5` | `export_final_preview_max_pages` | Yes (env) |
| `api/app/config.py` | 90 | `60` | `rate_limit_requests` — per-window request limit | Yes (env) |
| `api/app/config.py` | 91 | `60` | `rate_limit_window_seconds` — rate limit window | Yes (env) |
| `api/app/config.py` | 93 | `500` | `min_disk_space_mb` — minimum free disk space | Yes (env) |
| `api/app/models/user.py` | 56 | `100.0` | `max_file_size_mb` — per-user max file size (DB default) | Yes (per-user column) |
| `api/app/models/user.py` | 100 | `10000` | Max file size upper bound validation | Already a constant |
| `api/app/routers/admin.py` | 302 | `10000` | `list_jobs(limit=10000)` — admin job listing limit | Medium |
| `api/app/services/redis_service.py` | 469 | `50` | `list_jobs` default limit parameter | Already a default param value |

---

## 9. Hardcoded URLs / Endpoints

### Backend
| File | Line | Value | Controls | Configurable? |
|------|------|-------|----------|---------------|
| `api/app/config.py` | 11 | `["http://localhost:3000", "http://127.0.0.1:3000"]` | `_DEFAULT_CORS_ORIGINS` — default CORS origins | Yes (via `cors_allow_origins` env) |
| `api/app/config.py` | 22 | `"127.0.0.1"` | `api_bind_host` — API server bind host | Yes (env) |
| `api/app/config.py` | 39 | `"redis://redis:6379/0"` | `redis_url` — Redis connection URL | Yes (env) |
| `api/app/config.py` | 76 | `"http://localhost:3000/auth/callback"` | `linuxdo_redirect_uri` — default OAuth redirect | Yes (env) |
| `api/app/config.py` | 82 | `"data/pdf2ppt.db"` | `sqlite_path` — SQLite database path | Yes (env) |
| `api/app/auth.py` | 23-25 | LinuxDo OAuth endpoints (`connect.linux.do`) | OAuth provider URLs | Low — external service endpoints |

### Frontend
| File | Line | Value | Controls | Configurable? |
|------|------|-------|----------|---------------|
| `web/src/lib/api.ts` | 10 | `"http://localhost:8000"` | `DEFAULT_FALLBACK_ORIGIN` — default API origin | Yes (via `NEXT_PUBLIC_API_URL` or localStorage) |
| `web/src/lib/api.ts` | 11 | `"8000"` | `DEFAULT_FALLBACK_PORT` — default port | Partially (via `NEXT_PUBLIC_API_PORT`) |
| `web/src/lib/settings.ts` | 95 | `"https://api.siliconflow.cn/v1"` | `SILICONFLOW_BASE_URL` — default SiliconFlow endpoint | Yes (user-configurable in settings) |

---

## 10. Hardcoded File Paths

### Backend — OS-level font paths (hardcoded fallbacks)
| File | Line(s) | Paths | Purpose |
|------|---------|-------|---------|
| `api/app/routers/jobs.py` | 304-312 | `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`, `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`, `/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc`, `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`, `/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf` | Chinese font availability check |
| `api/app/convert/pptx/preview.py` | 43-51 | Same font paths | Font availability for PPTX preview |
| `api/app/convert/pptx/font_utils.py` | 99-109 | Same font paths | Font discovery for PPTX generation |

### Backend — Model cache path (hardcoded default)
| File | Line | Value | Purpose |
|------|------|-------|---------|
| `api/app/convert/ocr/layout_models.py` | 184, 306, 425, 509 (4 occurrences) | `"/app/data/models"` | Default model cache directory (overridable via `MODEL_CACHE_DIR` env) |

### Backend — Job root directory
| File | Line | Value | Purpose | Configurable? |
|------|------|-------|---------|---------------|
| `api/app/config.py` | 38 | `"data/jobs"` | `job_root_dir` — per-job runtime artifacts root | Yes (env) |

---

## 11. Frontend Polling Intervals (web/)

All in `web/src/lib/constants.ts` (centralized):

| Line | Constant | Value (ms) | Used In |
|------|----------|------------|---------|
| 13 | `JOB_POLL_INTERVAL_MS` | `2000` | Tracking page |
| 16 | `JOB_LIST_POLL_INTERVAL_MS` | `4000` | Home page, Jobs page |
| 19 | `MODEL_DOWNLOAD_POLL_INTERVAL_MS` | `2000` | Model download hook |
| 22 | `MODEL_STATUS_POLL_INTERVAL_MS` | `4000` | Model status hook |
| 25 | `SETTINGS_AUTO_SAVE_DEBOUNCE_MS` | `3000` | Settings page |
| 28 | `SSE_RECONNECT_BASE_MS` | `1000` | SSE reconnection |

**Status:** Already centralized in constants.ts. NOT configurable by users (could be but rarely needed).

---

## 12. Frontend API Limits / Sizing (web/)

All in `web/src/lib/constants.ts`:

| Line | Constant | Value | Purpose |
|------|----------|-------|---------|
| 35 | `HOME_JOB_LIMIT` | `50` | Max jobs shown on home page |
| 38 | `TRACKING_JOB_LIMIT` | `60` | Max jobs tracked on tracking page |
| 41 | `JOBS_PAGE_LIMIT` | `100` | Max jobs shown on jobs page |
| 44 | `ADMIN_USERS_LIMIT` | `100` | Max admin users to fetch |
| 47 | `ADMIN_INVITES_LIMIT` | `100` | Max admin invites to fetch |

---

## 13. Frontend Timeouts (web/)

| File | Line | Value | Purpose | Configurable? |
|------|------|-------|---------|---------------|
| `web/src/lib/constants.ts` | 64 | `5 * 60 * 1000` (5 min) | `AUTH_REFRESH_CHECK_MS` — auth token refresh check | No |
| `web/src/lib/constants.ts` | 67 | `30_000` | `API_REQUEST_TIMEOUT_MS` — default API request timeout | No |
| `web/src/lib/constants.ts` | 70 | `4000` | `TOAST_DURATION_MS` — toast auto-dismiss | No |
| `web/src/lib/api.ts` | 168 | `1200` | `probeApiOrigin` timeout (ms) | No |

---

## 14. Cookie/Auth TTLs (web/)

| File | Line | Value | Purpose |
|------|------|-------|---------|
| `web/src/app/auth/callback/route.ts` | 78 | `60 * 60` (1 hour) | `maxAgeAccess` — access token cookie max age |
| `web/src/app/auth/callback/route.ts` | 79 | `30 * 24 * 60 * 60` (30 days) | `maxAgeRefresh` — refresh token cookie max age |

**Note:** The backend `auth.py` defines `ACCESS_TOKEN_EXPIRE_MINUTES = 60` and `REFRESH_TOKEN_EXPIRE_DAYS = 30` — these **should match** the frontend cookie maxAge values. They do. Both are hardcoded but consistent.

---

## 15. Default Values in Frontend Settings (web/)

`web/src/lib/settings.ts` (`defaultSettings` object, lines 129-201) contains initial values for all user-configurable settings. These are persisted to localStorage and overridden by user. Example defaults of interest:

| Setting | Default | Purpose |
|---------|---------|---------|
| `imageBgClearExpandMinPt` | `"0.35"` | Image background clear expand min (pt) |
| `imageBgClearExpandMaxPt` | `"1.5"` | Image background clear expand max (pt) |
| `imageBgClearExpandRatio` | `"0.012"` | Image background clear expand ratio |
| `scannedImageRegionMinAreaRatio` | `"0.0025"` | Scanned region min area ratio |
| `scannedImageRegionMaxAreaRatio` | `"0.72"` | Scanned region max area ratio |
| `scannedImageRegionMaxAspectRatio` | `"4.8"` | Scanned region max aspect ratio |
| `ocrRenderDpi` | `"200"` | OCR render DPI |
| `ocrPaddleVlDocparserMaxSidePx` | `"2200"` | PaddleVL docparser max side pixels |
| `ocrAiPageConcurrency` | `"1"` | OCR AI page concurrency |
| `ocrAiMaxRetries` | `"0"` | OCR AI max retries |

**Note:** Most of these defaults are also hardcoded in `api/app/worker.py` as constants — important to keep them in sync if changed.

---

## 16. PPTX Generation Constants (Backend — pptx/constants.py)

| File | Line | Value | Name | Purpose |
|------|------|-------|------|---------|
| `api/app/convert/pptx/constants.py` | 9 | `914_400` | `_EMU_PER_INCH` | PowerPoint EMU unit conversion |
| `api/app/convert/pptx/constants.py` | 10 | `72.0` | `_PTS_PER_INCH` | Points per inch |
| `api/app/convert/pptx/constants.py` | 11 | `12700.0` (computed) | `_EMU_PER_PT` | EMU per point |

**Verdict:** These are format specification constants, not configurable — PowerPoint's coordinate system is defined by the spec.

---

## 17. PPTX Generation Magic Numbers (Backend — pptx/)

From `api/app/convert/pptx/generator.py`:
| Line | Value | Context |
|------|-------|---------|
| 822 | `30.0` | `high` bound for `_normalize_float` parameter |
| 1250 | `60` | Check `len(text_erase_bboxes_pt) >= 60` |

From `api/app/convert/pptx/scanned_page.py`:
| Line | Value | Context |
|------|-------|---------|
| 427 | `0.60` | Area-to-page ratio check |
| 1586 | `9.0`, `30.0`, `0.13`, `6.0` | Delta brightness calculation |
| 2373 | `0.60` | Width target calculation |
| 2729 | `0.35`, `0.80`, `0.60` | Overlap and IOU thresholds |
| 2927 | `4.0`, `0.60` | Line height thresholds |
| 3411 | `1.2`, `30.0` | Aspect ratio bounds |
| 3608 | `0.30`, `0.020` | CJK coverage and area ratio thresholds |

**Verdict:** Low priority — empirically tuned visual layout parameters.

---

## Summary Statistics

| Category | Count | Priority |
|----------|-------|----------|
| Timeouts (all) | ~30 | Medium (auth, model status) / Low (OCR tuning) |
| Concurrency/rate limits | ~15 | Medium (bounds already configurable via job options) |
| Image processing thresholds | ~55 | Low (visual tuning knobs, centralized as constants) |
| Hardcoded URLs/endpoints | ~10 | Medium (OAuth, Redis, API origin — mostly configurable via env) |
| Hardcoded file paths | ~15 | Medium (font paths, model cache — mostly configurable via env) |
| Frontend polling/limits | ~12 | Low (centralized in constants.ts) |
| PPTX generation thresholds | ~10 | Low (format/visual tuning) |
| DPI/render constants | ~6 | Mixed (configurable via env or job options) |
| **Total** | **~150+** | |

### Key Takeaways

1. **`api/app/convert/ocr/ai_client.py` is the hotspot** — ~60 hardcoded constants for OCR pipeline behavior. All are already well-named module-level constants but none are externally configurable.
2. **Most "magic numbers" are well-organized** — the codebase primarily uses named module-level constants rather than raw inline numbers. This is good architecture.
3. **Backend already has `api/app/config.py`** for the most deployment-relevant settings (timeouts, limits, DPI, URLs). The remaining hardcoded values are algorithmic tuning parameters that change behavior, not capacity.
4. **Frontend `constants.ts` is already centralized** — all polling intervals and limits are in one file. Good practice.
5. **Several timeout values have env-var overrides** (`OCR_PADDLE_VL_DOCPARSER_INIT_TIMEOUT_S`, `OCR_AI_LAYOUT_MODEL_INIT_TIMEOUT_S`, `OCR_AI_IMAGE_REGION_TIMEOUT_S`) but default to hardcoded constants (`30.0`).
6. **Font paths are the most fragile** — hardcoded `/usr/share/fonts/` paths assume a Linux Docker environment and would fail on other platforms.

---

## Related Specs

- `.trellis/spec/backend/index.md` — backend coding guidelines
- `.trellis/spec/frontend/index.md` — frontend coding guidelines

## Caveats / Not Found

- No hardcoded API keys or secrets were found (good)
- No hardcoded database credentials found (good)
- No hardcoded SSH keys or certificates found (good)
- The `api/app/config.py` uses `_ADMIN_PLACEHOLDER_PASSWORD = "admin12345678"` which is flagged as a WARNING comment — this is acceptable for self-use mode but should be changed in production
- Contextual noise thresholds in `api/app/convert/ocr/local_providers.py` (lines 402-420) were cataloged but are well-named constants and low priority
