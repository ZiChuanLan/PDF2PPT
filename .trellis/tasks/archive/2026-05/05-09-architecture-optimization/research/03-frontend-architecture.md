# Research: Frontend Architecture

- **Query**: Deep exploration of the PDF2PPT frontend architecture
- **Scope**: internal
- **Date**: 2026-05-09

## Findings

### 1. App Structure & Routing (Next.js 16 App Router)

The frontend is a **Next.js 16 App Router** project under `web/`. Key dependencies: `react 19.2.3`, `next 16.1.6`, `tailwindcss 4`, `pdfjs-dist 5.4.624`, `react-dropzone`, `sonner` (toast), `lucide-react` (icons).

**File**: `web/src/app/layout.tsx` (lines 1-43)

Root layout wraps all pages in:
1. `ThemeProvider` (light-only, no dark mode switching)
2. `AuthProvider` — React Context for user auth state
3. `UploadSessionProvider` — React Context for file upload state
4. `WorkbenchNav` — sticky top navigation bar
5. `Toaster` (sonner) — toast notifications

**Page Routes (all `"use client"` — no SSR data fetching)**:

| Route | File | Purpose |
|---|---|---|
| `/` | `web/src/app/page.tsx` (~2000 lines) | Main home page: upload, preview, convert |
| `/settings` | `web/src/app/settings/page.tsx` (~1400+ lines) | Configuration/settings page |
| `/jobs` | `web/src/app/jobs/page.tsx` (448 lines) | Job list management (history) |
| `/tracking` | `web/src/app/tracking/page.tsx` (1042 lines) | Job tracking & artifact comparison |
| `/login` | `web/src/app/login/page.tsx` | Login page |
| `/register` | `web/src/app/register/page.tsx` | Registration page |
| `/setup` | `web/src/app/setup/page.tsx` | Initial setup wizard |
| `/manage` | `web/src/app/manage/page.tsx` | User self-management |
| `/admin` | `web/src/app/admin/page.tsx` | Admin panel |
| `/admin/users/[id]` | `web/src/app/admin/users/[id]/page.tsx` | Admin user detail |
| `/admin/invites` | `web/src/app/admin/invites/page.tsx` | Admin invite management |
| `/admin/env` | `web/src/app/admin/env/page.tsx` | Admin environment |
| `/admin/site-settings` | `web/src/app/admin/site-settings/page.tsx` | Admin site settings |
| `/auth/callback` | `web/src/app/auth/callback/route.ts` | OAuth callback (server route) |

**Navigation**: `WorkbenchNav` (`web/src/components/workbench-nav.tsx`) — sticky top bar with 4 tabs: 首页, 任务记录, 跟踪, 设置. Plus an admin/manage tab for authorized users. Nav reads deploy mode from `/api/v1/config/deploy-mode`.

### 2. Middleware & API Proxy

**File**: `web/src/middleware.ts` (77 lines)

Middleware enforces:
- **Auth gate**: Redirects unauthenticated users to `/login` (with `next` redirect param)
- **API routes**: Forwards `access_token` cookie; injects `API_BEARER_TOKEN` env var as `Authorization` header if present
- **Bypass paths**: `/health`, `/login`, `/register`, `/setup`, `/auth/*`, `/api/v1/auth/*`, `/api/v1/setup/*`, `/api/v1/config/*`

**File**: `web/next.config.mjs` (33 lines)

Next.js rewrites proxy ALL `/api/*` and `/health` requests to the backend (internal API origin, defaults to `http://api:8000`). This means the browser calls `/api/v1/...` (same-origin), and Next.js proxies to the backend server — avoiding CORS issues.

### 3. API Client Layer

**File**: `web/src/lib/api.ts` (328 lines)

Core API functions:

- **`apiFetch(path, init?)`** (line 250-258): Primary fetch wrapper. Uses **same-origin proxy** (`/api/v1${path}`) with `credentials: "same-origin"`. No custom timeout mechanism in the fetch itself.

- **API origin resolution** (lines 60-234): Complex multi-step discovery:
  1. Check localStorage for manual override (`ppt_opencode_api_origin`)
  2. Check `NEXT_PUBLIC_API_URL` env var
  3. Auto-detect by probing port 8000, 8001 on localhost/127.0.0.1
  4. Fallback to `http://localhost:8000`
  - `probeApiOrigin()` (line 168) pings `${origin}/health` with a **1200ms** hardcoded timeout using `AbortController`.

- **`createJobEventSource(jobId)`** (line 260-262): Creates an `EventSource` at `/api/v1/jobs/${jobId}/events` for SSE streaming.

- **`normalizeFetchError()`** (lines 311-328): Error normalization with special handling for `AbortError` and network failures.

- **`readResponseErrorMessage()`** (lines 281-309): Reads error body (JSON or text), handles HTML responses (proxy errors).

**Key observations**:
- No `API_REQUEST_TIMEOUT_MS` is actually enforced in `apiFetch()` — the constant `s declared in `constants.ts` (30s) but not used by `fetch()` calls.
- SSE `EventSource` has **no custom reconnection logic** — relies entirely on browser defaults. The `SSE_RECONNECT_BASE_MS` constant (1000ms) is declared but never actually used in the code.

### 4. State Management

**Pattern**: React Context + `useState`/`useCallback` hooks. No external state management library (Redux, Zustand, etc.).

**Three Context Providers** (nested in layout):

1. **`AuthProvider`** (`web/src/components/auth-provider.tsx`, 89 lines)
   - State: `user`, `isLoading`, `error`
   - Fetches `/api/v1/auth/me` on mount, retries once on 401 with 500ms delay
   - Provides `logout()` which clears state and redirects to `/login`

2. **`UploadSessionProvider`** (`web/src/components/upload-session-provider.tsx`, 91 lines)
   - State: `files[]`, `pageStartInput`, `pageEndInput`
   - Manages uploaded file list with deduplication by filename
   - Provides `addFiles()`, `removeFile()`, `clearUpload()`

3. **ThemeProvider** — from `next-themes`, light-only

**Page-level state** (each page is a client component with its own state):

- **Home page** (`page.tsx`): Complex state with ~12 useState hooks managing file jobs, queue, settings snapshot, preview state, action errors, etc. Combined with `useUploadSession()`, `useAuth()`, `useModelStatus()` hooks.
- **Settings page**: Uses `useSettings()` hook which manages Settings state with auto-save debounce (500ms) to localStorage or API.
- **Jobs page**: Simple state for job list, filter, selection.
- **Tracking page**: Complex state for job records, tracked job artifacts, page navigation, comparison slider.

### 5. Conversion Job Flow (Upload → Submit → Wait → Download)

**File**: `web/src/app/page.tsx` (the main orchestrator)

**5.1 Upload Stage** (lines 687-807):
- `react-dropzone` with accept filter (PDF, PNG, JPG, WebP)
- Frontend file size check: **100MB hardcoded limit** (line 230)
- On drop → calls `addFiles()` to UploadSessionProvider
- Transitions to "preview" stage

**5.2 Preview Stage** (lines 811-965):
- Dual-column layout: PDF canvas preview (left) + config panel (right)
- PDF rendering via `PdfCanvasPreview` component using `pdfjs-dist` with Web Worker
- Config options: page range, PPT generation mode (turbo/fast/standard), parse engine, OCR provider
- Pre-flight check: validates model readiness and warns before submission

**5.3 Submit Stage** (lines 269-398, `handleConvertAll`):
1. Validates config with `validateRunConfig()`
2. Pre-flight model readiness check
3. Creates `FileJobState[]` for all files
4. For each file: POST `FormData` to `/api/v1/jobs/v2` with file + JSON config
5. Uses `Promise.all()` for parallel submission
6. Shows toast with success/failure counts

**5.4 Wait/Track Stage** (lines 475-547):
- **SSE for active jobs**: `useEffect` creates `EventSource` connections for all non-terminal jobs
  - On `onmessage`: parses `{status, stage, progress, message, error}` and updates `fileJobs` state
  - On terminal status: fetches full status via REST (`fetchJobStatus`) then closes EventSource
  - On `onerror`: shows "连接中断，正在重试..." message — **relies on browser auto-reconnect only**
- **Fallback polling for job list**: `setInterval` every `JOB_LIST_POLL_INTERVAL_MS` (4000ms) fetches `/api/v1/jobs?limit=50`
- **Window focus**: Re-fetches jobs and settings on window focus

**5.5 Download Stage** (lines 410-438):
- Single download: `apiFetch(/jobs/${jobId}/download)` → blob → `URL.createObjectURL` → programmatic `<a>` click
- Bulk download: `Promise.allSettled()` over all completed jobs
- Filename format: `output-${jobId.slice(0, 8)}.pptx`

### 6. SSE Implementation Details

**File**: `web/src/app/page.tsx`, lines 462-547

- **Trigger**: `useEffect` watches `activeJobIdsKey` — a memoized comma-separated string of non-terminal job IDs
- **Lifecycle**: Creates `Map<string, EventSource>`, one per active job
- **Message handling**: Parses JSON, merges into `fileJobs` state via functional update
- **Terminal handling**: On terminal status, fetches full response (to get `debug_events`), then closes EventSource
- **Error handling**: `es.onerror` sets `pollError: "连接中断，正在重试..."` and waits for browser auto-reconnect
- **Cleanup**: Closes all EventSources on effect cleanup

**Key concern**: No custom reconnection backoff. `SSE_RECONNECT_BASE_MS = 1000` constant exists but is **never used**. The browser's default EventSource reconnection is used, which typically uses a ~3s delay with no backoff strategy.

### 7. Polling Intervals (All Hardcoded)

**File**: `web/src/lib/constants.ts` (70 lines)

| Constant | Value | Where Used | Purpose |
|---|---|---|---|
| `JOB_POLL_INTERVAL_MS` | 2000ms | Tracking page (line 389) | Active job status polling |
| `JOB_LIST_POLL_INTERVAL_MS` | 4000ms | Home page (line 578), Jobs page (line 96) | Job list refresh |
| `MODEL_DOWNLOAD_POLL_INTERVAL_MS` | 2000ms | Declared, not used in hook | Model download progress polling |
| `MODEL_STATUS_POLL_INTERVAL_MS` | 4000ms | Declared, not actively polled | Model status refetch |
| `SETTINGS_AUTO_SAVE_DEBOUNCE_MS` | 3000ms | Declared, actual debounce is 500ms in useSettings | Settings auto-save |
| `SSE_RECONNECT_BASE_MS` | 1000ms | **NEVER USED** | Intended for SSE backoff |
| `AUTH_REFRESH_CHECK_MS` | 300000ms (5min) | Not actively used | Auth token refresh |
| `API_REQUEST_TIMEOUT_MS` | 30000ms | **NEVER ENFORCED** | Intended for API fetch timeout |
| `TOAST_DURATION_MS` | 4000ms | Not actively configured | Toast auto-dismiss |

**Key observations**:
- The tracking page uses a **hardcoded 3000ms** (line 343) instead of `JOB_POLL_INTERVAL_MS` — inconsistency.
- Model download hook (`use-model-download.ts`) uses a **hardcoded 1000ms** interval (line 87) instead of using `MODEL_DOWNLOAD_POLL_INTERVAL_MS`.
- `API_REQUEST_TIMEOUT_MS` (30s) is declared but never passed to `fetch()` — no request timeout exists.

### 8. Settings/Configuration System

**File**: `web/src/lib/settings.ts` (587 lines)

- **93 configurable fields** in the `Settings` type (line 34-93)
- **Storage**: `localStorage` under key `pdf-to-ppt.settings.v1` in self-hosted mode; `PUT /api/v1/user/preferences` in public mode
- **Backward compatibility**: Extensive migration logic in `loadStoredSettings()` handles legacy keys, renamed fields, and provider changes
- **Auto-save**: `useSettings` hook debounces saves by **500ms** (line 119) in self-hosted mode, making PUT requests for non-sensitive keys in public mode
- **Sensitive keys**: `openaiApiKey`, `claudeApiKey`, `mineruApiToken`, `ocrBaiduApiKey`, `ocrBaiduSecretKey`, `ocrAiApiKey` are excluded from public-mode server sync

**Main page integration** (lines 126, 172-187):
- Home page maintains its own `settingsSnapshot` via `refreshSettingsSnapshot()` from localStorage
- Changes made inline on home page update localStorage AND the snapshot
- Settings page uses full `useSettings()` hook with auto-save

### 9. Model Status System

**File**: `web/src/hooks/use-model-status.ts` (134 lines)

- **`useModelStatus()`**: Fetches `GET /api/v1/models/status` on mount, returns `{local, remote}` readiness status
- **`useEffectiveModelStatus()`**: Merges backend status with frontend localStorage API keys for remote providers (AIOCR, Baidu, MinerU) — accounts for self-hosted users whose keys are only in localStorage
- **No auto-polling**: Hook fetches once on mount; callers manually trigger `refetch()` on settings save or model download completion

**File**: `web/src/hooks/use-model-download.ts` (198 lines)

- Manages model download lifecycle: start, cancel, progress polling
- **Polls every 1000ms** while any download is active
- Detects completion/failure/cancellation and fires callbacks

**File**: `web/src/components/model-status-badge.tsx` (480 lines)

- Renders colored dot indicator (green/amber/red) with Portal-based details panel
- Shows per-provider readiness, issues, download buttons, config links
- Groups providers into: Local Models, Layout Models, Remote APIs

### 10. UI Components Inventory

**File**: `web/src/components/`

| Component | File | Purpose |
|---|---|---|
| `AuthProvider` | `auth-provider.tsx` | React Context for auth state |
| `UploadSessionProvider` | `upload-session-provider.tsx` | React Context for upload state |
| `WorkbenchNav` | `workbench-nav.tsx` | Sticky top navigation bar |
| `UserMenu` | `user-menu.tsx` | User dropdown menu |
| `ThemeProvider` | `theme-provider.tsx` | Theme wrapper |
| `PdfCanvasPreview` | `pdf-canvas-preview.tsx` | PDF page rendering via pdfjs-dist |
| `JobDebugPanel` | `job-debug-panel.tsx` | Debug event log display |
| `ModelStatusBadge` | `model-status-badge.tsx` | Model readiness indicator with portal details |
| `DownloadProgressButton` | `download-progress-button.tsx` | Download button with progress bar |
| UI Primitives | `ui/badge.tsx`, `ui/button.tsx`, `ui/card.tsx`, `ui/hover-hint.tsx`, `ui/input.tsx`, `ui/progress.tsx`, `ui/select.tsx`, `ui/sonner.tsx` | Reusable base components |

### 11. Lib Utilities

| File | Purpose |
|---|---|
| `web/src/lib/constants.ts` | Centralized constants (polling intervals, API limits, timeouts) |
| `web/src/lib/api.ts` | API client with origin resolution, fetch wrapper, SSE factory |
| `web/src/lib/settings.ts` | Settings type definition, defaults, localStorage load/save with migration |
| `web/src/lib/run-config.ts` | Settings → JobConfig mapping, validation, OCR state resolution |
| `web/src/lib/job-status.ts` | Job type definitions, normalization, stage flow definitions |
| `web/src/lib/auth.ts` | User type, normalization, admin check |
| `web/src/lib/tracking-artifacts.ts` | Artifact page navigation helpers |
| `web/src/lib/layout-models.ts` | Layout model definitions |
| `web/src/lib/utils.ts` | `cn()` utility (clsx + tailwind-merge) |

### 12. Performance / UX Observations

1. **No request timeouts**: `apiFetch()` has no timeout mechanism. A hung backend connection will wait indefinitely for the browser's default timeout.

2. **SSE reconnection is passive**: No custom reconnection logic with backoff. On error, just shows "连接中断" and waits for browser EventSource default reconnection (~3s fixed delay).

3. **Main page is ~2000 lines**: Heavy single-file component with ~30 hooks and complex inline logic. No extraction into custom hooks or sub-components.

4. **PDF rendering is client-side only**: `PdfCanvasPreview` loads pdfjs-dist (~2MB+) dynamically and renders via canvas. No server-side PDF processing.

5. **No request deduplication**: Multiple rapid settings changes trigger separate PUT requests; debounce is only 500ms.

6. **No loading skeletons**: Most pages use simple spinner/text loading states rather than skeleton screens.

7. **No offline support**: No service worker, no PWA. Requires active backend connection.

8. **Job submission uses v2 endpoint** (`POST /api/v1/jobs/v2`) with JSON config in FormData, but `createJobFormData()` for v1 still exists as fallback.

9. **Tracking page has its own hardcoded 3000ms poll interval** (line 343), not using `JOB_POLL_INTERVAL_MS` constant from `constants.ts`.

10. **Model download hook has hardcoded 1000ms poll** (line 87), not using `MODEL_DOWNLOAD_POLL_INTERVAL_MS`.

## Caveats / Not Found

- No WebSocket usage — SSE is the only real-time mechanism
- No React Query / SWR — all data fetching is manual via `useEffect` + `useState`
- No unit tests for frontend (test script is a no-op placeholder: `"No frontend unit tests are kept in this public repo."`)
- The `API_REQUEST_TIMEOUT_MS` constant exists but is never passed to any `fetch()` call
- `SSE_RECONNECT_BASE_MS` is declared but never referenced in any SSE reconnection code
