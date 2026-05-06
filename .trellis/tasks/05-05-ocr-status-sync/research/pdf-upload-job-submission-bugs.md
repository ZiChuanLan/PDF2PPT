# Research: PDF Upload & Job Submission Flow — Bug Analysis

- **Query**: Thoroughly review the PDF upload and job submission flow for subtle bugs
- **Scope**: internal (code review)
- **Date**: 2026-05-05

## Files Analyzed

| File Path | Description |
|---|---|
| `web/src/app/page.tsx` | Main page component with file upload, preview, and job submission |
| `web/src/lib/run-config.ts` | Config building and validation for job submission |
| `web/src/lib/api.ts` | API client utilities (fetch, SSE, error handling) |
| `web/src/lib/job-status.ts` | Job status types and normalization |
| `web/src/lib/settings.ts` | Settings types, defaults, and localStorage persistence |
| `web/src/components/upload-session-provider.tsx` | Upload session state management |
| `api/app/routers/jobs.py` | Backend job creation endpoints (v1 and v2) |
| `api/app/schemas/job_config.py` | Pydantic schema for structured job config |
| `api/app/job_options.py` | Backend validation and normalization of job options |
| `web/next.config.mjs` | Next.js rewrites for API proxy |

---

## Bug #1: Preview File Index Out-of-Bounds After Removal

**File**: `web/src/app/page.tsx`  
**Lines**: 836-839

**What happens**:
```tsx
onClick={() => {
  removeFile(index)
  if (previewFileIndex >= fileCount - 1) {
    setPreviewFileIndex(Math.max(0, fileCount - 2))
  }
}}
```

**The bug**: `removeFile(index)` triggers an async state update via `setFiles(prev => prev.filter(...))`. The `fileCount` used in the guard `previewFileIndex >= fileCount - 1` is still the **old** count (before removal). So if you have 3 files and remove index 0, `fileCount` is still 3, and the condition `previewFileIndex >= 2` may not trigger when it should.

**What should happen**: The `previewFileIndex` adjustment should happen inside the `removeFile` callback or be derived from the new file count after removal.

**Impact**: After removing a file, `previewFileIndex` may point to an out-of-bounds index, causing `currentPreviewFile` to be `undefined`. The preview breaks silently.

**Suggested fix**: Move the index adjustment into the `removeFile` callback in the provider, or use `useEffect` to clamp `previewFileIndex` when `fileCount` changes.

---

## Bug #2: Duplicate File Names Silently Skipped

**File**: `web/src/components/upload-session-provider.tsx`  
**Lines**: 36-46

**What happens**:
```tsx
const addFiles = React.useCallback((newFiles: File[]) => {
  setFiles((prev) => {
    const existingNames = new Set(prev.map((e) => e.file.name))
    const entries: UploadFileEntry[] = []
    for (const f of newFiles) {
      if (!existingNames.has(f.name)) {
        entries.push({ file: f, pageStartInput: "", pageEndInput: "" })
        existingNames.add(f.name)
      }
    }
    return [...prev, ...entries]
  })
}, [])
```

**The bug**: Files are deduplicated by **name only**, not by content. Two different PDFs with the same filename (e.g., from different directories) will have the second one silently dropped. The user gets no feedback that a file was rejected.

**What should happen**: Either deduplicate by content hash, or warn the user when a duplicate name is detected. At minimum, show a toast: "文件 xxx 已存在，已跳过".

**Impact**: User thinks they uploaded 5 files but only 4 are processed. Silent data loss.

---

## Bug #3: No Frontend File Size Validation

**File**: `web/src/app/page.tsx`  
**Lines**: 215-229 (onDrop handler)

**What happens**: The `onDrop` callback accepts files without checking size. The backend validates `max_file_mb` (line 1025 in jobs.py) but only after the file is fully uploaded. For large files (e.g., 200MB PDF), the user waits for the entire upload to complete before getting an error.

**What should happen**: Check `file.size` in `onDrop` and warn immediately if it exceeds the limit. The limit could be fetched from the backend or hardcoded as a reasonable default (e.g., 100MB).

**Impact**: Poor UX — user waits minutes for upload only to get rejected. Wasted bandwidth.

---

## Bug #4: SSE Effect Dependency Causes Infinite Reconnection Loop

**File**: `web/src/app/page.tsx`  
**Lines**: 441-515

**What happens**:
```tsx
React.useEffect(() => {
  // ... creates EventSource for each active job
  return () => {
    mounted = false
    for (const es of sources.values()) {
      es.close()
    }
  }
}, [fileJobs, fetchJobStatus])
```

**The bug**: The effect depends on `fileJobs` (the entire array). Every time `setFileJobs` is called inside the SSE `onmessage` handler (line 464), it triggers a re-render, which causes the effect to re-run, which closes all existing EventSources and creates new ones. This creates a reconnect loop.

**What should happen**: The effect should depend only on the list of active job IDs (a stable reference), not the entire `fileJobs` array. Extract `activeJobIds` as a memoized value and use that as the dependency.

**Impact**: Every SSE message causes all connections to be torn down and recreated. This leads to missed events, flickering UI, and excessive network requests.

**Suggested fix**:
```tsx
const activeJobIds = React.useMemo(() => 
  fileJobs
    .filter(j => j.jobId && !j.isSubmitting && (!j.status || !TERMINAL_JOB_STATUSES.has(j.status.status)))
    .map(j => j.jobId!)
    .join(','),
  [fileJobs]
)

React.useEffect(() => {
  // ... use activeJobIds as dependency
}, [activeJobIds, fetchJobStatus])
```

---

## Bug #5: Page Range Validation Allows Asymmetric Input

**File**: `web/src/app/page.tsx`  
**Lines**: 293-301

**What happens**:
```tsx
if (effectiveUsePageRange && ((pageStart && !pageEnd) || (!pageStart && pageEnd))) {
  setActionError("页码范围请同时填写起始页和结束页")
  return
}
```

**The bug**: The condition uses `pageStart && !pageEnd` which is falsy when `pageStart === 0`. However, `toIntOrUndefined` (line 99) returns `undefined` for values ≤ 0, so this specific case is handled. But the validation logic is fragile — it relies on `undefined` being falsy rather than explicitly checking for `undefined`.

**What should happen**: Use explicit `pageStart !== undefined && pageEnd === undefined` checks for clarity and robustness.

**Impact**: Low — currently works by accident due to `toIntOrUndefined` behavior, but could break if the helper changes.

---

## Bug #6: Config Build Missing `ocrProvider` for Local OCR Mode

**File**: `web/src/lib/run-config.ts`  
**Lines**: 313-408 (`resolveRunConfig`)

**What happens**: When `parseEngineMode` is `local_ocr`, the `effectiveOcrProvider` is set to `selectedOcrProvider` which comes from `normalizeVisibleOcrProvider`. But if the user has `ocrProvider` set to an invalid value in localStorage (e.g., from a corrupted settings migration), it falls back to `"machine"` (line 180). The config is then sent to the backend with `ocr_provider: "machine"`.

**The bug**: The backend's `validate_and_normalize_job_options` (job_options.py line 473) checks `if normalized_parse_provider == "local" and normalized_ocr_provider in {"aiocr", "paddle"}` but doesn't validate that `"machine"` is actually available on the server. If Tesseract is not installed, the job will fail at runtime.

**What should happen**: The frontend's preflight check (line 265-288) should verify that the selected OCR provider is actually ready before allowing submission.

**Impact**: User submits job, waits, then gets a failure. The preflight check exists but only checks for `paddleocr` and `tesseract` readiness, not `machine` mode specifically.

---

## Bug #7: `readResponseErrorMessage` Consumes Response Body Twice

**File**: `web/src/lib/api.ts`  
**Lines**: 281-309

**What happens**:
```tsx
export async function readResponseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json()  // First consumption
    // ...
  } catch {
    // Fall through to text parsing.
  }
  try {
    const text = await response.text()  // Second consumption
    // ...
  } catch { }
}
```

**The bug**: `Response.body` can only be consumed once. If `response.json()` succeeds, `response.text()` will throw because the body is already consumed. If `response.json()` fails (e.g., response is plain text), the catch block falls through to `response.text()`, which works. But if `response.json()` succeeds but the body isn't valid JSON, it throws and falls through correctly.

**What should happen**: Clone the response before consuming: `const clone = response.clone()`. Use `clone.json()` in the first try and `response.text()` in the second.

**Impact**: Medium — error messages may be lost if the response is valid JSON but `body.message` is empty. The fallback text path will fail silently.

---

## Bug #8: Settings Snapshot Not Updated on Window Focus

**File**: `web/src/app/page.tsx`  
**Lines**: 535-553

**What happens**:
```tsx
React.useEffect(() => {
  refreshSettingsSnapshot()
  void fetchJobs(false)

  const onFocus = () => {
    refreshSettingsSnapshot()
    void fetchJobs(true)
  }

  window.addEventListener("focus", onFocus)
  // ...
}, [fetchJobs, refreshSettingsSnapshot])
```

**The bug**: `refreshSettingsSnapshot` is a `useCallback` with empty deps (line 161-163), so it's stable. But `settingsSnapshot` is used in `handleConvertAll` (line 258) which captures it via closure. If the user changes settings in another tab, the `onFocus` handler updates the snapshot, but the `handleConvertAll` callback still has the old snapshot in its closure until the next render.

**What should happen**: Use a ref for settings or ensure `handleConvertAll` reads from the latest state. This is a React closure stale-state issue.

**Impact**: Low — the user would need to switch tabs, change settings, switch back, and immediately click "convert" in the same render cycle. Unlikely but possible.

---

## Bug #9: Job Submission Race Condition with `successCount`/`failCount`

**File**: `web/src/app/page.tsx`  
**Lines**: 317-354

**What happens**:
```tsx
let successCount = 0
let failCount = 0

const submitOne = async (entry: FileJobState, index: number) => {
  try {
    // ... submit
    successCount++
  } catch {
    // ... error
    failCount++
  }
}

await Promise.all(uploadFiles.map((_, i) => submitOne(initialJobs[i], i)))
```

**The bug**: `successCount` and `failCount` are local variables mutated inside async callbacks. While `Promise.all` waits for all to complete, the mutations are not atomic. In JavaScript's single-threaded model this is safe, but the pattern is fragile and could break if refactored to use parallel workers.

**What should happen**: Use `Promise.allSettled` and count results from the returned array:
```tsx
const results = await Promise.allSettled(uploadFiles.map((_, i) => submitOne(initialJobs[i], i)))
const successCount = results.filter(r => r.status === 'fulfilled').length
const failCount = results.filter(r => r.status === 'rejected').length
```

**Impact**: Low — currently works due to JS single-threading, but is a code smell.

---

## Bug #10: SSE `onmessage` Handler Doesn't Validate Data Shape

**File**: `web/src/app/page.tsx`  
**Lines**: 454-496

**What happens**:
```tsx
es.onmessage = async (event) => {
  try {
    const data = JSON.parse(event.data)
    const status = data.status as JobStatusValue
    const stage = data.stage as string
    const progress = data.progress as number
    // ...
  } catch {
    // JSON parse error — ignore
  }
}
```

**The bug**: The handler casts `data.status`, `data.stage`, etc. directly without validation. If the backend sends malformed data (e.g., `status: "unknown"`), it gets stored in state and could cause UI issues. The `normalizeJobStatusValue` function exists in `job-status.ts` but isn't used here.

**What should happen**: Validate each field using the existing normalizers:
```tsx
const status = normalizeJobStatus(data.status) // from job-status.ts
const stage = typeof data.stage === 'string' ? data.stage : 'unknown'
const progress = typeof data.progress === 'number' ? Math.max(0, Math.min(100, data.progress)) : 0
```

**Impact**: Medium — invalid backend data could corrupt UI state. The `JOB_STAGE_LABELS` lookup (line 1394) would show `undefined` for unknown stages.

---

## Bug #11: `handleDownload` Creates Object URL Without Error Handling

**File**: `web/src/app/page.tsx`  
**Lines**: 388-403

**What happens**:
```tsx
const handleDownload = React.useCallback(async (targetJobId: string) => {
  const response = await apiFetch(`/jobs/${targetJobId}/download`)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.message || `下载失败（HTTP ${response.status}）`)
  }
  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `output-${targetJobId.slice(0, 8)}.pptx`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}, [])
```

**The bug**: If `response.blob()` fails (e.g., network interruption during download), the object URL is never created and the function throws. But if `createObjectURL` succeeds and then `a.click()` triggers a navigation (some browsers do this for large files), the `revokeObjectURL` call may run before the download starts.

**What should happen**: Wrap in try/finally to ensure cleanup:
```tsx
let url: string | null = null
try {
  const blob = await response.blob()
  url = window.URL.createObjectURL(blob)
  // ... create link and click
} finally {
  if (url) window.URL.revokeObjectURL(url)
}
```

**Impact**: Low — mostly affects edge cases with very large files or flaky networks.

---

## Bug #12: `buildJobConfig` Sends Empty `ocr.provider` for Non-Local Modes

**File**: `web/src/lib/run-config.ts`  
**Lines**: 710-714

**What happens**:
```tsx
config.ocr = {
  provider: run.effectiveOcrProvider,
  render_dpi: toFinitePositiveIntOrNull(settings.ocrRenderDpi) ?? undefined,
  strict_mode: Boolean(settings.ocrStrictMode),
}
```

**When `parseProvider` is `"mineru"` or `"baidu_doc"`**: `effectiveOcrProvider` is set to `"auto"` (from `normalizeVisibleOcrProvider`), which is correct. But the `ocr` object is always created, even when OCR is not used (e.g., MinerU handles its own parsing).

**The bug**: The backend receives `ocr.provider: "auto"` even for MinerU jobs. The backend's `to_worker_kwargs()` (job_config.py line 410) passes this through. While the worker should ignore it, it's unnecessary noise that could confuse debugging.

**What should happen**: Only include `config.ocr` when `parseProvider === "local"`.

**Impact**: Very low — cosmetic/debugging issue only.

---

## Bug #13: `allCompleted` Logic Includes Error State as "Completed"

**File**: `web/src/app/page.tsx`  
**Lines**: 434-436

**What happens**:
```tsx
const allCompleted = fileJobs.length > 0 && fileJobs.every(
  (j) => j.status?.status === "completed" || j.error
)
```

**The bug**: A job with `j.error` (submission failure) is treated as "completed" for the `allCompleted` flag. This means the "全部下载" button appears even when some jobs failed to submit. The `handleDownloadAll` function (line 405) filters for `status === "completed"`, so it won't actually try to download failed jobs, but the UI is misleading.

**What should happen**: Separate the concepts:
```tsx
const allTerminal = fileJobs.length > 0 && fileJobs.every(
  (j) => j.status?.status === "completed" || j.error || j.status?.status === "failed" || j.status?.status === "cancelled"
)
const allCompleted = fileJobs.length > 0 && fileJobs.every(j => j.status?.status === "completed")
```

**Impact**: Low — UI shows "全部下载" button when it shouldn't, but clicking it does nothing harmful.

---

## Bug #14: No Cleanup of Job Directory on Frontend Reset

**File**: `web/src/app/page.tsx`  
**Lines**: 418-429 (`handleResetAll`)

**What happens**:
```tsx
const handleResetAll = React.useCallback(() => {
  clearUpload()
  setFileJobs([])
  setActionError(null)
  // ...
}, [clearUpload, setPageEndInput, setPageStartInput])
```

**The bug**: Resetting clears frontend state but doesn't cancel or clean up any in-progress jobs. If the user clicks "重新选择文件" while jobs are still processing, those jobs continue running on the backend but the frontend loses track of them.

**What should happen**: Either:
1. Disable the reset button while jobs are active (already done — `hasActiveJobs` disables the back button in converting stage), OR
2. Cancel all active jobs before resetting

**Impact**: Low — the back button is already disabled during active jobs. But if the user navigates away (e.g., to settings) and comes back, the jobs are lost from the UI but still running.

---

## Bug #15: `HOME_ACTIVE_JOB_STORAGE_KEY` Defined But Never Used

**File**: `web/src/app/page.tsx`  
**Line**: 82

**What happens**:
```tsx
const HOME_ACTIVE_JOB_STORAGE_KEY = "ppt-opencode:home:active-job-id"
```

**The bug**: This constant is defined but never referenced anywhere in the code. It appears to be leftover from a previous implementation that persisted the active job ID to localStorage for recovery after page navigation.

**What should happen**: Either implement job recovery (load active job from localStorage on mount) or remove the dead code.

**Impact**: None — dead code, but indicates an incomplete feature.

---

## Bug #16: Backend v2 Endpoint Missing User Quota Checks

**File**: `api/app/routers/jobs.py`  
**Lines**: 1280-1520 (`create_job_v2`)

**What happens**: The v1 endpoint (line 683-1277) checks:
1. Concurrent task limit (line 1049-1059)
2. Daily task limit (line 1062-1072)

But the v2 endpoint (line 1280-1520) does **not** perform these checks. It goes straight from file validation to job creation.

**What should happen**: Add the same quota checks to the v2 endpoint.

**Impact**: High — users can bypass rate limits by using the v2 API directly. The frontend uses v2 (line 325), so all frontend submissions bypass quota checks.

---

## Bug #17: SSE Events Don't Include `debug_events`

**File**: `api/app/routers/jobs.py`  
**Lines**: 1565-1644 (`job_event_generator`)

**What happens**: The SSE endpoint (line 1628) streams `JobEvent` objects that include `status`, `stage`, `progress`, `message`, and `error`. But `debug_events` is not included in the streaming events — it's only available via the REST endpoint `GET /jobs/{job_id}`.

**The bug**: The frontend's SSE handler (page.tsx line 470) creates a partial `JobStatusResponse` from SSE data, but `debug_events` is always empty. Only when the job reaches terminal state does it fetch the full response (line 480-489) which includes debug events.

**What should happen**: This is actually by design (debug events can be large), but the frontend should indicate that debug events are not available during streaming. Currently, the debug panel shows "no events" until the job completes.

**Impact**: Low — UX issue, not a bug. Users can't see debug events in real-time.

---

## Bug #18: `normalizeJobListItem` Returns `null` for Valid But Empty Job IDs

**File**: `web/src/lib/job-status.ts`  
**Lines**: 180-208

**What happens**:
```tsx
export function normalizeJobListItem(row: unknown): JobListItem | null {
  if (!row || typeof row !== "object") return null
  const jobId = typeof (row as { job_id?: unknown }).job_id === "string" ? (row as { job_id: string }).job_id : ""
  if (!jobId) return null
  // ...
}
```

**The bug**: If `job_id` is an empty string `""`, the function returns `null`. But the backend could theoretically return a job with an empty ID (though this shouldn't happen in practice). More importantly, if the backend returns `job_id: 0` (number) or `job_id: null`, it's silently dropped without any logging.

**What should happen**: Log a warning when a job item is skipped due to missing/invalid ID.

**Impact**: Very low — defensive coding, but silent failures make debugging harder.

---

## Summary of Severity

| # | Bug | Severity | File |
|---|---|---|---|
| 1 | Preview index out-of-bounds after removal | **Medium** | page.tsx:836 |
| 2 | Duplicate files silently skipped | **Medium** | upload-session-provider.tsx:36 |
| 3 | No frontend file size validation | **Medium** | page.tsx:215 |
| 4 | SSE effect infinite reconnection loop | **High** | page.tsx:441 |
| 5 | Page range validation fragility | **Low** | page.tsx:293 |
| 6 | Missing OCR provider availability check | **Medium** | run-config.ts:313 |
| 7 | Response body consumed twice | **Medium** | api.ts:281 |
| 8 | Settings snapshot stale closure | **Low** | page.tsx:535 |
| 9 | Race condition in success/fail counting | **Low** | page.tsx:317 |
| 10 | SSE data not validated | **Medium** | page.tsx:454 |
| 11 | Download object URL cleanup | **Low** | page.tsx:388 |
| 12 | Unnecessary OCR config for non-local modes | **Very Low** | run-config.ts:710 |
| 13 | `allCompleted` includes errors | **Low** | page.tsx:434 |
| 14 | Reset doesn't clean up backend jobs | **Low** | page.tsx:418 |
| 15 | Dead constant `HOME_ACTIVE_JOB_STORAGE_KEY` | **None** | page.tsx:82 |
| 16 | v2 endpoint missing quota checks | **High** | jobs.py:1280 |
| 17 | SSE events missing debug_events | **Low** | jobs.py:1565 |
| 18 | Silent null for invalid job IDs | **Very Low** | job-status.ts:180 |

## Critical Issues Requiring Immediate Attention

1. **Bug #4 (SSE infinite reconnect loop)**: This causes excessive network requests and UI flickering on every SSE message. Should be fixed by memoizing the active job IDs dependency.

2. **Bug #16 (v2 endpoint missing quota checks)**: This is a security/correctness issue. All frontend submissions go through v2, so no rate limiting is enforced. The fix is to add the same quota checks from the v1 endpoint.

3. **Bug #1 (Preview index out-of-bounds)**: Causes broken preview after file removal. Common user action that triggers a visible bug.
