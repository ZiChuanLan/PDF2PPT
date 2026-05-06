# Research: Frontend Polling & Backend SSE Analysis

- **Query**: Analyze frontend polling mechanism, backend SSE endpoint, API client, download logic, and upload logic
- **Scope**: internal
- **Date**: 2026-05-05

## Findings

### 1. Frontend Polling (`web/src/app/page.tsx`)

**Two separate polling loops exist:**

#### Active Job Polling (lines 437–465)
- Uses `setInterval` with **2000ms** interval
- Filters `fileJobs` for active jobs: `j.jobId && j.isSubmitting === false && (!j.status || !TERMINAL_JOB_STATUSES.has(j.status.status))`
- Calls `fetchJobStatus(jid)` for each active job sequentially in a `for` loop
- Updates `fileJobs` state via `setFileJobs` on success
- **Error handling**: empty `catch {}` — all poll errors are silently swallowed (line 456)
- Cleanup: `window.clearInterval(timer)` on unmount via `mounted` flag

```typescript
// Lines 444-458
const timer = window.setInterval(async () => {
  if (!mounted) return
  for (const jid of activeJobIds) {
    try {
      const status = await fetchJobStatus(jid)
      if (!mounted) return
      setFileJobs((prev) => prev.map((j) => j.jobId === jid ? { ...j, status } : j))
    } catch {
      // ignore poll errors
    }
  }
}, 2000)
```

#### Job List Polling (lines 485–503)
- Uses `setInterval` with **4000ms** interval
- Calls `fetchJobs(true)` (silent mode)
- Also triggers on `window.focus` event
- Fetches `GET /jobs?limit=50`

#### `fetchJobStatus` (lines 195–212)
- Calls `GET /jobs/{jobId}` via `apiFetch`
- Throws on non-OK response with status code and error code
- Normalizes response via `normalizeJobStatusResponse(body)`
- Returns `JobStatusResponse` type

### 2. Backend SSE Endpoint (`api/app/routers/jobs.py`)

**Endpoint**: `GET /api/v1/jobs/{job_id}/events` (line 1596)

#### `job_event_generator` (lines 1533–1593)
- Async generator that polls Redis every **500ms**
- Sends SSE events only when something changes (status, stage, progress, message)
- Stops streaming when job reaches terminal state (completed, failed, cancelled)
- Uses `JobEvent` model for serialization

**Event format**: `data: {JSON}\n\n`

**JobEvent fields** (from `api/app/models/job.py:294`):
```python
class JobEvent(BaseModel):
    job_id: str
    status: JobStatus        # pending | processing | completed | failed | cancelled
    stage: JobStage          # upload_received | queued | parsing | ocr | layout_assist | pptx_generating | packaging | cleanup | done
    progress: int            # 0-100
    message: Optional[str] = None
    error: Optional[dict[str, Any]] = None
```

**Response headers** (lines 1604–1611):
```python
return StreamingResponse(
    job_event_generator(job_id),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # Disable nginx buffering
    },
)
```

**Key difference from polling**: SSE does NOT include `debug_events` or `created_at`/`expires_at` — those are only in the REST `GET /jobs/{id}` response (`JobStatusResponse`).

### 3. Frontend API Client (`web/src/lib/api.ts`)

**No SSE/EventSource support exists.** The file contains:
- `apiFetch(path, init)` — standard fetch wrapper using same-origin proxy (`/api/v1/...`)
- Origin resolution logic (probes multiple candidates)
- Error handling utilities (`normalizeFetchError`, `readResponseErrorMessage`)

No `EventSource`, `text/event-stream`, or SSE-related code anywhere in the frontend codebase (confirmed by grep).

### 4. Download Logic

#### `handleDownload` (page.tsx lines 385–400)
- Calls `GET /jobs/{jobId}/download` via `apiFetch`
- Creates blob URL, triggers download via dynamically created `<a>` element
- Filename: `output-{jobId.slice(0,8)}.pptx`

#### `handleDownloadAll` (page.tsx lines 402–412)
- Filters `fileJobs` for completed jobs with jobId
- Iterates sequentially, calling `handleDownload` for each
- Catches per-file errors and shows toast

```typescript
const handleDownloadAll = React.useCallback(async () => {
  const completedJobs = fileJobs.filter((j) => j.status?.status === "completed" && j.jobId)
  if (completedJobs.length === 0) return
  for (const job of completedJobs) {
    try {
      await handleDownload(job.jobId!)
    } catch (e) {
      toast.error(`${job.file.name}: ${normalizeFetchError(e, "下载失败")}`)
    }
  }
}, [fileJobs, handleDownload])
```

### 5. Upload Logic

**Location**: `handleConvertAll` in page.tsx (lines 246–373)

**Flow**:
1. Validates user auth, settings, page range
2. Creates `FileJobState[]` array from `uploadFiles`
3. For each file, submits via `POST /jobs/v2` with `FormData`:
   - `file`: the File object
   - `config`: JSON-encoded `JobConfig` (from `buildJobConfig`)
4. All submissions run in parallel via `Promise.all`
5. On success, updates `fileJobs` with returned `job_id`
6. Triggers `fetchJobs(true)` to refresh job list

```typescript
const formData = new FormData()
formData.append("file", entry.file)
formData.append("config", JSON.stringify(jobConfig))
const response = await apiFetch("/jobs/v2", {
  method: "POST",
  body: formData,
})
```

**No upload progress tracking**: The `apiFetch` call uses standard `fetch` with no `XMLHttpRequest` or progress event support. Large files have no progress indication during upload.

### 6. Other Pages with Polling

#### Jobs Page (`web/src/app/jobs/page.tsx`)
- Polls `GET /jobs?limit=50` every **4000ms** (line 95)
- Also on focus + manual refresh

#### Tracking Page (`web/src/app/tracking/page.tsx`)
- Polls `GET /jobs?limit=50` every **4000ms** (line 340)
- Also polls job artifacts for the tracked job

## Key Observations

1. **SSE endpoint exists but is unused** — backend has `GET /{job_id}/events` but no frontend code connects to it
2. **Polling is duplicated** across 3 pages (page.tsx, jobs/page.tsx, tracking/page.tsx)
3. **Silent error swallowing** — active job polling catches and ignores all errors
4. **SSE event model lacks `debug_events`** — would need extension if debug logs should stream via SSE
5. **No upload progress** — `fetch` API doesn't expose upload progress events
6. **apiFetch uses same-origin proxy** — SSE via `EventSource` would need the same proxy path (`/api/v1/jobs/{id}/events`)

## Files Found

| File Path | Description |
|---|---|
| `web/src/app/page.tsx` | Main page with polling (lines 437-465), download (385-412), upload (246-373) |
| `api/app/routers/jobs.py` | SSE endpoint (lines 1533-1612), job CRUD |
| `api/app/models/job.py` | JobEvent model (line 294), JobStatusResponse (line 253) |
| `web/src/lib/api.ts` | API client — no SSE support |
| `web/src/lib/job-status.ts` | Job type definitions and normalizers |
| `web/src/components/upload-session-provider.tsx` | Upload session state management |
| `web/src/app/jobs/page.tsx` | Jobs list page with 4s polling |
| `web/src/app/tracking/page.tsx` | Tracking page with 4s polling |

## Caveats / Not Found

- No existing `EventSource` usage anywhere in the frontend
- SSE endpoint's `JobEvent` doesn't include `debug_events` — may need schema extension
- The Next.js rewrite config (`/api/*` → backend) would need to support SSE streaming — need to verify
