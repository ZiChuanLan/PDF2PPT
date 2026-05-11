# Research: Job Tracking Flow — Comprehensive Bug Review

- **Query**: Thoroughly review the job tracking flow for subtle bugs
- **Scope**: internal
- **Date**: 2026-05-05

## Findings

### 1. SSE Connection Issues

#### Bug 1.1: SSE Effect Dependency Causes Unnecessary Reconnection Churn

**File**: `web/src/app/page.tsx:441-515`

**What the bug is**: The SSE `useEffect` depends on `fileJobs` (the entire state array). Every time any job status updates via SSE, the `fileJobs` state changes, which triggers the effect to re-run. The effect's cleanup closes ALL existing EventSource connections, and then the effect re-creates connections for all still-active jobs. This means every single SSE message causes a full teardown and reconnection cycle for ALL active jobs.

**What should happen**: SSE connections should be stable — only create new connections when new jobs become active, and close connections only when jobs reach terminal state (which is already handled inside `es.onmessage`).

**What actually happens**: 
1. SSE message arrives for job A → `setFileJobs` updates state
2. `fileJobs` reference changes → useEffect cleanup runs → closes ALL EventSources (including job B, C, etc.)
3. Effect re-runs → creates brand new EventSources for B, C (and A if not terminal)
4. This creates a rapid connect/disconnect cycle that can lose messages

**Impact**: Race conditions, missed SSE events, excessive network connections, potential "连接中断" error messages flashing.

**Suggested fix**: Use `useRef` to track active job IDs and EventSources instead of depending on `fileJobs`. Compare previous vs current active job IDs to only create/close connections as needed. Or use a stable callback pattern that doesn't depend on the full state array.

#### Bug 1.2: SSE `onerror` Shows "连接中断" Even During Normal Auto-Reconnect

**File**: `web/src/app/page.tsx:498-506`

**What the bug is**: When `EventSource.onerror` fires, the code sets `pollError: "连接中断，正在重试..."` on the job. However, `EventSource` auto-reconnects by default — the `onerror` handler fires on temporary network blips, not just permanent disconnections. The error message stays visible until the next successful message clears it (line 469: `pollError: null`).

**What should happen**: Only show disconnection warning after sustained failure, or clear it immediately on reconnection.

**What actually happens**: Brief network hiccups cause the "连接中断" message to flash on screen, which is misleading since the connection recovers automatically.

**Suggested fix**: Add a small delay before showing the error, or track consecutive errors before showing the warning.

#### Bug 1.3: No SSE Connection on Tracking Page — Polling Only

**File**: `web/src/app/tracking/page.tsx:352-394`

**What the bug is**: The tracking page uses REST polling (every 2 seconds) for job status updates instead of SSE. This is inconsistent with the home page which uses SSE. While polling works, it's less efficient and creates unnecessary server load.

**What should happen**: Consistent approach — either both pages use SSE or both use polling.

**What actually happens**: The tracking page polls `/jobs/{jobId}` every 2 seconds, which is less efficient than the SSE approach used on the home page.

**Impact**: Minor — functional but inconsistent. The 2-second polling interval means updates can be delayed up to 2 seconds compared to SSE's near-instant updates.

### 2. Progress Display Issues

#### Bug 2.1: Stage Step Calculation Uses Average Across Multiple Jobs

**File**: `web/src/app/page.tsx:605-628`

**What the bug is**: When multiple files are being converted, the stepped progress indicator (解析 → OCR → 生成 → 完成) uses the AVERAGE flow index across all active jobs. This creates confusing intermediate states — e.g., if one job is at "parsing" (index 1) and another at "generating" (index 4), the average is 2.5, which maps to step 2 (OCR), even though no job is actually at the OCR stage.

**What should happen**: Either show per-job progress, or use the minimum/most-behind job's stage to indicate overall pipeline position.

**What actually happens**: The stepped indicator shows a stage that no job is actually in, which is misleading.

**Impact**: Confusing UX for multi-file conversions.

#### Bug 2.2: Overall Progress Calculation Ignores Failed/Cancelled Jobs

**File**: `web/src/app/page.tsx:555-557`

**What the bug is**: `overallProgress` averages progress across ALL `fileJobs`, including failed ones. A failed job at 0% progress drags down the average, making the progress bar appear stuck even when other jobs are progressing normally.

**What should happen**: Calculate progress only from active and completed jobs, excluding failed/cancelled ones.

**What actually happens**: `fileJobs.reduce((sum, j) => sum + (j.status?.progress || 0), 0) / fileJobs.length` — failed jobs with 0% progress reduce the overall percentage.

### 3. Download Flow Issues

#### Bug 3.1: Download Loads Entire File Into Memory via Blob

**File**: `web/src/app/page.tsx:388-403` and `web/src/app/tracking/page.tsx:275-290`

**What the bug is**: Both download handlers fetch the entire file as a blob (`response.blob()`), create an object URL, trigger a click, then revoke the URL. For large PPTX files (potentially 50-100MB+), this loads the entire file into browser memory at once.

**What should happen**: Use `window.open()` or a direct link to stream the download without buffering in memory.

**What actually happens**: The entire file is buffered in memory as a Blob, which can cause memory pressure or crashes for very large files.

**Impact**: Potential out-of-memory errors for large presentations.

#### Bug 3.2: Download Error Handling Inconsistency

**File**: `web/src/app/page.tsx:388-403`

**What the bug is**: `handleDownload` throws errors that need to be caught by callers. However, in `handleDownloadAll` (line 405-416), individual download failures are caught and toasted, but the function doesn't indicate partial failure to the user beyond individual toasts. If all downloads fail, the user sees N separate error toasts.

**What should happen**: Aggregate errors and show a summary.

**What actually happens**: Multiple rapid toast.error() calls for each failed download.

#### Bug 3.3: Download URL Object Leak on Error

**File**: `web/src/app/page.tsx:395-402`

**What the bug is**: If `response.blob()` succeeds but the subsequent operations fail (e.g., the `a.click()` throws), `window.URL.revokeObjectURL(url)` on line 402 might not execute since it's not in a finally block. Actually, looking more carefully, the code is sequential and there's no try/catch, so if `response.blob()` throws, the URL is never created. But if `a.click()` somehow fails, the URL leaks.

**Impact**: Minor — unlikely in practice but technically a resource leak.

### 4. Job List Polling Race Conditions

#### Bug 4.1: SSE and REST Polling Update Same State Independently

**File**: `web/src/app/page.tsx:441-515` (SSE) and `web/src/app/page.tsx:535-553` (REST polling)

**What the bug is**: The home page has two independent update mechanisms:
1. SSE connections update `fileJobs` state (line 464-476)
2. REST polling updates `jobs` state (line 537, fetchJobs every 4 seconds)

These are separate state variables (`fileJobs` vs `jobs`), but the UI derives `hasActiveJobs` from `fileJobs` and `inFlightJobs` from `jobs`. This means:
- SSE updates `fileJobs` in real-time
- REST polling updates `jobs` every 4 seconds
- The "队列 X · 执行中 Y" badge (line 639) shows data from `jobs` which is up to 4 seconds stale
- The file job list shows data from `fileJobs` which is real-time

**What should happen**: Consistent data source — either both use the same state, or the queue badge also uses real-time data.

**What actually happens**: Two slightly out-of-sync views of the same data.

**Impact**: The queue count badge can show stale numbers while individual job progress is real-time.

#### Bug 4.2: Job List Polling Continues Even When Not Needed

**File**: `web/src/app/page.tsx:535-553`

**What the bug is**: The 4-second job list polling interval runs continuously, even when the user is in the "upload" or "preview" stage where no jobs are active. This creates unnecessary API calls.

**What should happen**: Only poll when there are active jobs or when the user is viewing the converting stage.

**What actually happens**: `/jobs?limit=50` is called every 4 seconds regardless of UI state.

### 5. Terminal State Handling Issues

#### Bug 5.1: Terminal State Toast Logic Has Edge Case

**File**: `web/src/app/page.tsx:518-533`

**What the bug is**: The toast effect compares `newlyCompleted.length === completedCount` (line 522), but `completedCount` is derived from `fileJobs` which includes jobs that were already completed before this session. If the user has 3 completed jobs from a previous session and 1 new job completes, `newlyCompleted` has 4 items and `completedCount` is 4, so the condition passes. But the toast says "全部转换完成！" when only 1 new job completed.

**What should happen**: Track which jobs were completed at the start of the current batch and only toast for newly completed jobs.

**What actually happens**: The toast logic uses `lastTerminalToastRef` to deduplicate, but the "全部转换完成" condition checks `newlyCompleted.length === fileJobs.length`, which could trigger prematurely if some fileJobs have errors.

#### Bug 5.2: Cancelled Job State Not Fully Cleared

**File**: `web/src/app/page.tsx:1467-1471`

**What the bug is**: When a job is cancelled, the UI shows "已取消" text but the job remains in the `fileJobs` array. The `hasActiveJobs` check (line 431-433) correctly excludes cancelled jobs from "active" count, but the `allCompleted` check (line 434-436) doesn't account for cancelled jobs — it only checks for `completed` status or `error`.

**What should happen**: `allCompleted` should be true when all jobs are either completed, failed, OR cancelled.

**What actually happens**: If some jobs are cancelled and others completed, `allCompleted` is false (because cancelled !== completed && cancelled has no error), so the "全部下载" button doesn't appear.

### 6. Cross-Page State Issues

#### Bug 6.1: HOME_ACTIVE_JOB_STORAGE_KEY Defined But Never Used

**File**: `web/src/app/page.tsx:82`

**What the bug is**: The constant `HOME_ACTIVE_JOB_STORAGE_KEY = "ppt-opencode:home:active-job-id"` is defined but never referenced anywhere in the codebase. This appears to be dead code from an incomplete feature — likely intended to persist the active job ID so the tracking page could auto-select it.

**What should happen**: Either implement the cross-page state sharing (save active job ID to localStorage, tracking page reads it) or remove the dead constant.

**What actually happens**: Navigating from home page to tracking page loses context — the user must manually find and select their job.

#### Bug 6.2: No State Sharing Between Home and Tracking Pages

**File**: `web/src/app/page.tsx` and `web/src/app/tracking/page.tsx`

**What the bug is**: When a user submits jobs on the home page and navigates to the tracking page, there's no way for the tracking page to know which jobs were just created. The tracking page loads ALL jobs (up to 60) and the user must manually find their recent jobs.

**What should happen**: The tracking page should auto-select or highlight recently created jobs, or the home page should navigate to `/tracking?job=<jobId>` after submission.

**What actually happens**: User must scroll through the job list to find their recently created jobs.

### 7. Debug Events Issues

#### Bug 7.1: Debug Events Only Available After Terminal State

**File**: `web/src/app/page.tsx:478-491`

**What the bug is**: The SSE handler only fetches full job status (including `debug_events`) when the job reaches a terminal state (completed/failed/cancelled). During processing, the debug panel shows an empty state because SSE events don't include debug events.

**What should happen**: Either include debug events in SSE events, or periodically fetch full status during processing to show real-time debug logs.

**What actually happens**: The debug panel on the home page (line 1537-1566) only shows events after the job completes. The "查看处理日志" button is only visible when `fileJobs.some((j) => j.status?.debug_events?.length)` is true, which only happens after terminal state fetch.

#### Bug 7.2: Debug Events Not Available During Processing on Tracking Page

**File**: `web/src/app/tracking/page.tsx:724-732`

**What the bug is**: The tracking page's debug panel (line 725) shows `trackedJobStatus?.debug_events || []`. The `trackedJobStatus` is fetched via REST polling (every 2 seconds), which DOES include debug events. However, the polling only fetches from `/jobs/{jobId}` which returns the full status including debug events. So this works, but inconsistently with the home page.

**What should happen**: Consistent behavior — both pages should show debug events during processing.

**What actually happens**: Tracking page shows debug events during processing (via polling), home page only shows them after completion (via SSE + fetch).

### 8. Additional Issues

#### Bug 8.1: Race Condition in Preflight Warning

**File**: `web/src/app/page.tsx:265-289`

**What the bug is**: The preflight warning check reads `modelStatus` which is fetched asynchronously. If `modelStatus` is still loading (`isModelStatusLoading` is true), the check is skipped entirely (line 265: `if (modelStatus && !preflightAcknowledged)`). This means a user could submit a job while model status is still loading, potentially using an unavailable provider.

**What should happen**: Wait for model status to load before allowing submission, or show a loading state.

**What actually happens**: If the user clicks "开始转换" before model status loads, the preflight check is bypassed.

#### Bug 8.2: Settings Snapshot Not Updated Before Job Submission

**File**: `web/src/app/page.tsx:248-376`

**What the bug is**: `handleConvertAll` uses `settingsSnapshot` which was loaded on mount and updated via `updateSettingsSnapshot`. However, if the user changes settings in another tab (via the settings page), the snapshot on the home page is stale. The `refreshSettingsSnapshot` is called on window focus (line 539-542), but there's a race window.

**What should happen**: Refresh settings immediately before job submission.

**What actually happens**: Stale settings could be used if the user switched tabs recently.

#### Bug 8.3: File Deduplication Uses Name Only

**File**: `web/src/components/upload-session-provider.tsx:37-46`

**What the bug is**: `addFiles` deduplicates by file name only. If a user uploads two different files with the same name (e.g., from different directories), only the first is kept.

**What should happen**: Deduplicate by a combination of name + size + lastModified, or allow duplicate names.

**What actually happens**: Files with identical names are silently dropped.

## Files Analyzed

| File Path | Description |
|---|---|
| `web/src/app/page.tsx` | Main home page with upload, preview, conversion, and SSE |
| `web/src/app/tracking/page.tsx` | Job tracking page with artifacts and polling |
| `web/src/lib/job-status.ts` | Job status types, normalization, and stage flow |
| `web/src/lib/api.ts` | API client, EventSource creation, error handling |
| `web/src/lib/settings.ts` | Settings types, defaults, and localStorage persistence |
| `web/src/lib/run-config.ts` | Run config resolution, validation, and job config building |
| `web/src/lib/tracking-artifacts.ts` | Artifact page normalization and navigation |
| `web/src/components/job-debug-panel.tsx` | Debug event display component |
| `web/src/components/upload-session-provider.tsx` | Upload session state management |
| `web/src/components/model-status-badge.tsx` | Model status indicator with download UI |
| `web/src/components/download-progress-button.tsx` | Download progress button component |
| `web/src/hooks/use-model-download.ts` | Model download hook with polling |
| `web/src/hooks/use-model-status.ts` | Model status fetch hook |
| `web/src/components/auth-provider.tsx` | Auth context provider |
| `api/app/routers/jobs.py` | Backend job API endpoints including SSE |
| `api/app/models/job.py` | Backend job models (JobEvent, etc.) |

## Summary of Severity

| Severity | Bug ID | Description |
|---|---|---|
| **High** | 1.1 | SSE effect dependency causes connection churn |
| **Medium** | 1.2 | False "连接中断" messages on auto-reconnect |
| **Medium** | 2.1 | Misleading averaged stage indicator for multi-file |
| **Medium** | 2.2 | Failed jobs drag down overall progress |
| **Medium** | 4.1 | SSE and polling show inconsistent data |
| **Medium** | 5.2 | Cancelled jobs block "全部下载" button |
| **Medium** | 7.1 | Debug events unavailable during processing on home page |
| **Medium** | 8.1 | Preflight check bypassed while model status loading |
| **Low** | 1.3 | Tracking page uses polling instead of SSE |
| **Low** | 3.1 | Full file buffered in memory for download |
| **Low** | 3.2 | Multiple error toasts for batch download failures |
| **Low** | 4.2 | Unnecessary polling when no active jobs |
| **Low** | 5.1 | Terminal state toast edge case |
| **Low** | 6.1 | Dead code (HOME_ACTIVE_JOB_STORAGE_KEY) |
| **Low** | 6.2 | No cross-page state sharing |
| **Low** | 7.2 | Inconsistent debug event behavior between pages |
| **Low** | 8.2 | Stale settings on submission |
| **Low** | 8.3 | File deduplication by name only |
