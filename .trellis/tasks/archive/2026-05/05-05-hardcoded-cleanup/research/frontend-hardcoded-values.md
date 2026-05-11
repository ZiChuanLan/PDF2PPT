# Research: Frontend Hardcoded Values and Magic Numbers

- **Query**: Find all hardcoded magic values, magic numbers, and hardcoded strings in the frontend TypeScript/React code
- **Scope**: internal
- **Date**: 2026-05-05

## Findings

### 1. Magic Numbers — Polling Intervals & Timeouts

| File | Line | Value | Description | Has Config? |
|------|------|-------|-------------|-------------|
| `web/src/app/page.tsx` | 578 | `4000` | Job list polling interval (ms) | No |
| `web/src/app/jobs/page.tsx` | 95 | `4000` | Job list polling interval (ms) | No |
| `web/src/app/tracking/page.tsx` | 342 | `3000` | Job list polling interval (ms) | No |
| `web/src/app/tracking/page.tsx` | 388 | `2000` | Tracked job status polling interval (ms) | No |
| `web/src/hooks/use-model-download.ts` | 88 | `1000` | Model download status polling interval (ms) | No |
| `web/src/hooks/use-settings.ts` | 134 | `500` | Settings save debounce timeout (ms) | No |
| `web/src/components/auth-provider.tsx` | 31 | `500` | Auth retry delay (ms) | No |
| `web/src/app/settings/page.tsx` | 704 | `400` | Search debounce timeout (ms) | No |
| `web/src/lib/api.ts` | 168 | `1200` | API origin probe timeout (ms) | No |

### 2. Magic Numbers — Limits & Sizes

| File | Line | Value | Description | Has Config? |
|------|------|-------|-------------|-------------|
| `web/src/app/page.tsx` | 229 | `100` | MAX_FILE_SIZE_MB (100MB) | No |
| `web/src/lib/auth.ts` | 75 | `10` | Default daily_task_limit | No (fallback) |
| `web/src/lib/auth.ts` | 76 | `100` | Default max_file_size_mb | No (fallback) |
| `web/src/lib/auth.ts` | 77 | `2` | Default concurrent_task_limit | No (fallback) |
| `web/src/app/settings/page.tsx` | 500, 506 | `16` | Search results slice limit | No |
| `web/src/app/settings/page.tsx` | 1391 | `72` | OCR DPI min value | No |
| `web/src/app/settings/page.tsx` | 1392 | `400` | OCR DPI max value | No |
| `web/src/app/settings/page.tsx` | 2360 | `100` | Tesseract confidence max | No |
| `web/src/lib/settings.ts` | 506 | `6000` | Prompt override max length | No |
| `web/src/lib/settings.ts` | 533 | `8` | Max page concurrency | No |
| `web/src/lib/settings.ts` | 569 | `8` | Max retries cap | No |
| `web/src/lib/api.ts` | 274 | `220` | Response text truncation length | No |
| `web/src/app/page.tsx` | 94-95 | `1024` | Bytes to KB/MB/GB conversion | No |
| `web/src/app/auth/callback/route.ts` | 78 | `3600` | Access token max age (1 hour) | No |
| `web/src/app/auth/callback/route.ts` | 79 | `2592000` | Refresh token max age (30 days) | No |
| `web/src/app/auth/callback/route.ts` | 69 | `300` | Error data slice limit | No |

### 3. Magic Numbers — API Query Limits

| File | Line | Value | Description | Has Config? |
|------|------|-------|-------------|-------------|
| `web/src/app/page.tsx` | 190 | `50` | `/jobs?limit=50` | No |
| `web/src/app/jobs/page.tsx` | 75 | `50` | `/jobs?limit=50` | No |
| `web/src/app/tracking/page.tsx` | 199 | `60` | `/jobs?limit=60` | No |
| `web/src/app/admin/page.tsx` | 60 | `100` | `/admin/users?limit=100` | No |
| `web/src/app/admin/invites/page.tsx` | 53 | `100` | `/admin/invites?limit=100` | No |

### 4. Magic Numbers — UI Layout & Positioning

| File | Line | Value | Description | Has Config? |
|------|------|-------|-------------|-------------|
| `web/src/components/model-status-badge.tsx` | 278 | `272` | Tooltip width for positioning | No |
| `web/src/components/model-status-badge.tsx` | 278 | `8` | Minimum left position | No |
| `web/src/components/model-status-badge.tsx` | 279 | `9999` | Z-index for tooltip | No |
| `web/src/app/settings/page.tsx` | 549 | `12` | Safe margin for dropdown | No |
| `web/src/app/settings/page.tsx` | 551 | `280` | Minimum dropdown width | No |
| `web/src/app/settings/page.tsx` | 562 | `180` | Minimum above-available space | No |
| `web/src/app/settings/page.tsx` | 999 | `1440` | Max container width (px) | No |

### 5. Hardcoded URLs & Ports

| File | Line | Value | Description | Has Config? |
|------|------|-------|-------------|-------------|
| `web/src/lib/api.ts` | 10 | `"http://localhost:8000"` | DEFAULT_FALLBACK_ORIGIN | Yes (env) |
| `web/src/lib/api.ts` | 11 | `"8000"` | DEFAULT_FALLBACK_PORT | Yes (env) |
| `web/src/lib/api.ts` | 125 | `["8000", "8001"]` | Candidate ports for auto-detect | No |
| `web/src/app/auth/callback/route.ts` | 42 | `"http://api:8000"` | Docker internal API origin | Yes (env) |
| `web/src/lib/settings.ts` | 95 | `"https://api.siliconflow.cn/v1"` | SILICONFLOW_BASE_URL | No |

### 6. Hardcoded localStorage Keys

| File | Line | Value | Description | Has Config? |
|------|------|-------|-------------|-------------|
| `web/src/lib/api.ts` | 9 | `"ppt_opencode_api_origin"` | API origin storage key | No |
| `web/src/lib/settings.ts` | 100 | `"pdf-to-ppt.settings.v1"` | Settings storage key | No |
| `web/src/components/auth-provider.tsx` | 60 | `"userLoggedOut"` | Logout flag key | No |
| `web/src/app/page.tsx` | 82 | `"ppt-opencode:home:active-job-id"` | Active job ID key | No |

### 7. Hardcoded CSS Colors (Brand/Theme)

| Color | Usage Count | Files | Description |
|-------|-------------|-------|-------------|
| `#cc0000` | 20+ | page.tsx, settings/page.tsx, login/page.tsx, jobs/page.tsx, admin/env/page.tsx, badge.tsx, button.tsx | Primary brand color (red) |
| `#111111` | 10+ | settings/page.tsx, page.tsx, jobs/page.tsx, admin/users/[id]/page.tsx, tracking/page.tsx | Dark accent (checkbox, shadow) |
| `#f0f0f0` | 3 | settings/page.tsx, input.tsx, select.tsx | Focus background color |
| `#ecebe7` | 1 | pdf-canvas-preview.tsx:268 | PDF canvas background |
| `#c8c8c8` | 2 | pdf-canvas-preview.tsx:274, 283 | Canvas border color |
| `#a80000` | 1 | badge.tsx:14 | Destructive hover color |

### 8. Hardcoded Status Colors

| File | Lines | Colors | Description |
|------|-------|--------|-------------|
| `web/src/components/model-status-badge.tsx` | 98-112 | `bg-emerald-500`, `bg-amber-500`, `bg-red-500`, `bg-muted-foreground/40` | Provider status indicators |
| `web/src/app/settings/page.tsx` | 1944-1945, 2423-2424, 2468-2469 | `emerald-500/40`, `amber-500/40` | Status border colors |
| `web/src/app/setup/page.tsx` | 441, 490, 558 | `bg-emerald-500`, `bg-amber-500`, `bg-red-500` | Model status indicators |

### 9. Hardcoded Z-Index Values

| File | Line | Value | Description |
|------|------|-------|-------------|
| `web/src/components/model-status-badge.tsx` | 279 | `9999` | Tooltip z-index |
| `web/src/app/settings/page.tsx` | 603 | `120` | Dropdown z-index |
| `web/src/components/workbench-nav.tsx` | 75 | `40` | Sticky nav z-index |
| `web/src/components/user-menu.tsx` | 119 | `50` | User menu dropdown z-index |
| `web/src/app/admin/page.tsx` | 558 | `50` | Modal overlay z-index |
| `web/src/app/tracking/page.tsx` | 975, 978, 981 | `20` | Compare divider z-index |

### 10. Hardcoded API Paths (Prefix Pattern)

All API calls use the pattern `/api/v1${path}` defined in `api.ts:254`. The following paths are used directly as string literals:

**Auth paths:**
- `/auth/me`, `/auth/logout`, `/auth/login-password`, `/auth/auto-login`, `/auth/register`, `/auth/callback`, `/auth/change-password`

**Job paths:**
- `/jobs`, `/jobs/${id}`, `/jobs/${id}/cancel`, `/jobs/${id}/download`, `/jobs/${id}/events`, `/jobs/${id}/artifacts`, `/jobs/v2`

**Model paths:**
- `/models/status`, `/models/download`, `/models/download/status`, `/models/download/cancel`

**Admin paths:**
- `/admin/users`, `/admin/users/${id}`, `/admin/users/${id}/reset-password`, `/admin/users/batch-delete`, `/admin/stats`, `/admin/env`, `/admin/invites`, `/admin/site-settings`

**Config paths:**
- `/config/deploy-mode`, `/user/preferences`, `/setup/status`, `/setup/complete`

**Hardcoded query parameters:**
- `?limit=50` (jobs), `?limit=60` (tracking), `?limit=100` (admin users, invites)

### 11. Hardcoded Default Settings Values

File: `web/src/lib/settings.ts` lines 129-201

Key hardcoded defaults:
- `ocrRenderDpi: "200"` — Default OCR render DPI
- `ocrTesseractMinConfidence: "35"` — Default Tesseract confidence threshold
- `ocrTesseractLanguage: "chi_sim+eng"` — Default OCR language
- `ocrAiPageConcurrency: "1"` — Default AI OCR page concurrency
- `ocrAiMaxRetries: "0"` — Default max retries
- `ocrPaddleVlDocparserMaxSidePx: "2200"` — Default PaddleVL max side pixels
- `imageBgClearExpandMinPt: "0.35"` — Image background clear expand min
- `imageBgClearExpandMaxPt: "1.5"` — Image background clear expand max
- `imageBgClearExpandRatio: "0.012"` — Image background clear expand ratio
- `scannedImageRegionMinAreaRatio: "0.0025"` — Scanned image region min area
- `scannedImageRegionMaxAreaRatio: "0.72"` — Scanned image region max area
- `scannedImageRegionMaxAspectRatio: "4.8"` — Scanned image region max aspect ratio

### 12. Hardcoded Auto-Concurrency Logic

File: `web/src/lib/run-config.ts` lines 120-147

```typescript
// Hardcoded concurrency values based on mode:
if (settings.pptGenerationMode === "turbo") {
  if (settings.ocrAiChainMode === "direct") return 4
  if (settings.ocrAiChainMode === "layout_block") return 2
}
if (settings.pptGenerationMode === "fast" && settings.ocrAiChainMode === "layout_block") {
  return 2
}
return 1
```

### 13. Hardcoded CSS Arbitrary Values

Many Tailwind arbitrary values are hardcoded inline:
- `text-[11px]`, `text-[10px]`, `text-[9px]` — Font sizes
- `text-[1.3rem]` — Card title size
- `min-h-[148px]`, `min-h-[240px]`, `min-h-[300px]` — Minimum heights
- `max-h-[72dvh]` — Max height for PDF preview
- `max-w-[1440px]`, `max-w-screen-xl`, `max-w-3xl`, `max-w-xl`, `max-w-5xl` — Max widths
- `shadow-[0_18px_44px_rgba(0,0,0,0.16)]` — Custom shadow
- `shadow-[inset_4px_0_0_0_#111111]` — Inset shadow for active row
- `tracking-[0.12em]`, `tracking-[0.14em]`, `tracking-[0.18em]`, `tracking-[0.22em]` — Letter spacing
- `ease-[cubic-bezier(0.16,1,0.3,1)]`, `ease-[cubic-bezier(0.4,0,0.2,1)]` — Custom easing

### 14. Hardcoded String Literals (UI Text)

All UI text is hardcoded in Chinese without i18n support. Examples:
- Error messages: `"加载任务列表失败"`, `"删除失败"`, `"任务已删除"`
- Status labels: `"排队中"`, `"处理中"`, `"已完成"`, `"失败"`, `"已取消"`
- Stage labels: `"上传接收"`, `"队列等待"`, `"解析 PDF"`, `"OCR 识别"`
- Form labels: `"Tesseract 最低置信度（0-100）"`, `"默认 200。仅影响 OCR 输入图"`

### 15. Hardcoded Model Labels

File: `web/src/hooks/use-model-download.ts` lines 189-197

```typescript
const labels: Record<string, string> = {
  pp_doclayout_s: "PP-DocLayout-S",
  pp_doclayout_m: "PP-DocLayout-M",
  pp_doclayout_l: "PP-DocLayout-L",
  pp_doclayout_v3: "PP-DocLayoutV3",
  doclayout_yolo: "DocLayout-YOLO",
  paddleocr: "PaddleOCR",
}
```

### 16. Hardcoded MIME Types & File Extensions

File: `web/src/app/page.tsx` lines 83-89

```typescript
const SUPPORTED_UPLOAD_ACCEPT = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/webp": [".webp"],
} as const
```

## Summary of Categories

| Category | Count | Priority |
|----------|-------|----------|
| Polling intervals/timeouts | 9 | High — should be configurable constants |
| API query limits | 5 | High — inconsistent values (50, 60, 100) |
| localStorage keys | 4 | Medium — should be centralized |
| Hardcoded URLs/ports | 5 | Medium — some have env vars, some don't |
| CSS brand colors | 6 | Medium — should use CSS variables/theme |
| Z-index values | 6 | Medium — should use a z-index scale |
| UI layout constants | 7 | Low — mostly positioning helpers |
| Default settings | 12+ | Low — already in settings.ts but scattered |
| Status colors | 3 patterns | Low — should be centralized |
| UI text strings | 100+ | Low — i18n is a larger effort |

## Existing Config/Constants

The project already has some constants defined:
- `web/src/lib/settings.ts` — Settings types and defaults
- `web/src/lib/api.ts` — `API_ORIGIN_STORAGE_KEY`, `DEFAULT_FALLBACK_ORIGIN`
- `web/src/lib/layout-models.ts` — Layout model registry
- `web/src/lib/job-status.ts` — Job status labels and stage flow

## Caveats / Not Found

- No existing centralized constants file for UI values (colors, z-index, spacing)
- No i18n system in place — all UI text is hardcoded Chinese
- Some values (like polling intervals) are duplicated across multiple files with different values
- CSS arbitrary values are pervasive and would require a design token system to consolidate
