# Research: Frontend Upload & Job Submission Flow

- **Query**: How files are uploaded, jobs created/tracked, error handling, retry, state management
- **Scope**: internal
- **Date**: 2026-05-04

## Findings

### Files Found

| File Path | Description |
|---|---|
| `web/src/app/page.tsx` | Main upload page — 3-stage UI (upload → preview → converting) |
| `web/src/lib/api.ts` | API client with origin resolution, `apiFetch()` wrapper |
| `web/src/lib/job-status.ts` | Job status types, normalizers, stage flow definitions |
| `web/src/lib/run-config.ts` | Settings → JobConfig builder, validation, v1 FormData fallback |
| `web/src/components/upload-session-provider.tsx` | React context for multi-file upload state |
| `api/app/routers/jobs.py` | Backend job endpoints (v1 Form + v2 JSON config) |

---

### 1. File Upload Mechanism

**No chunked/streaming upload.** Files are uploaded as standard `multipart/form-data` in a single request.

- **Frontend** (`page.tsx:317-349`): Uses `FormData` with `file` + `config` (JSON string) fields, sent via `apiFetch("/jobs/v2", { method: "POST", body: formData })`.
- **Backend** (`jobs.py:1314`): `await file.read()` loads the entire file into memory. No streaming or chunked reception.
- **File size limit**: Enforced server-side via `settings.max_file_mb` (`jobs.py:1316-1321`).
- **Supported formats**: PDF, PNG, JPG, JPEG, WebP. Images are converted to single-page PDF server-side (`_write_upload_as_input_pdf`).
- **Multi-file**: Frontend submits all files in parallel via `Promise.all` (`page.tsx:351`). Each file becomes an independent job.

### 2. Job Creation & Tracking

**Creation flow:**
1. Frontend validates settings via `validateRunConfig()` (`run-config.ts:511-571`)
2. Pre-flight model readiness check (warns if OCR models not downloaded)
3. Builds `JobConfig` JSON via `buildJobConfig()` (`run-config.ts:657-806`)
4. POSTs to `/api/v1/jobs/v2` with FormData (file + config JSON)
5. Backend creates job in Redis, returns `{ job_id, status, created_at, expires_at }`

**Job status types** (`job-status.ts:1-3`):
- `pending` → `processing` → `completed` | `failed` | `cancelled`
- Terminal statuses: `{ completed, failed, cancelled }`

**Stage flow** (`job-status.ts:97-106`):
```
queued → parsing → ocr → layout_assist → pptx_generating → packaging → cleanup → done
```

**Polling** (`page.tsx:437-465`):
- `setInterval` every 2 seconds for active (non-terminal) jobs
- Fetches `GET /api/v1/jobs/{job_id}` per active job
- Polling stops when all jobs reach terminal state
- **No SSE/WebSocket usage on frontend** — despite backend having SSE endpoint (`/jobs/{id}/events`)

**Job list refresh** (`page.tsx:485-503`):
- `GET /api/v1/jobs?limit=50` polled every 4 seconds
- Also refreshed on window focus

### 3. Error Handling

**Upload/submit errors** (`page.tsx:340-348`):
- Per-file error state in `FileJobState.error`
- Errors caught per-file in `submitOne()`, not globally
- `normalizeFetchError()` classifies: network failure, abort, generic error
- `readResponseErrorMessage()` parses JSON error body or falls back to text

**Job status fetch errors** (`page.tsx:195-212`):
- Custom `JobStatusFetchError` with `statusCode` and `errorCode`
- Poll errors silently ignored (`page.tsx:455-457` — empty catch)

**Backend error model** (`jobs.py`):
- `AppException` with `ErrorCode` enum, message, details, HTTP status
- Rollback: deletes job metadata + directory on creation failure (`jobs.py:1173-1195`)

### 4. Retry Mechanisms

**No explicit retry on frontend.** If a job submission fails:
- Error is displayed per-file
- User must manually retry by clicking "开始转换" again
- No automatic retry, no exponential backoff

**Backend OCR retries** (`run-config.ts:374`):
- `ocrAiMaxRetries` configurable (0-8), passed to worker
- Only applies to AI OCR API calls, not to job submission

### 5. State Management

**`FileJobState`** (`page.tsx:73-79`): Per-file tracking:
```ts
{
  file: File           // original File object
  jobId: string | null // assigned after submit
  status: JobStatusResponse | null // polled status
  error: string | null // submit error
  isSubmitting: boolean // true during POST
}
```

**`UploadSessionProvider`** (`upload-session-provider.tsx`):
- React context holding `UploadFileEntry[]` (file + page range inputs)
- Deduplication by filename on `addFiles()`
- No persistence — clears on page reload

**Settings** (`page.tsx:160-175`):
- Stored in `localStorage` under `SETTINGS_STORAGE_KEY`
- Loaded on mount, synced on window focus

**Active job ID** (`page.tsx:81`):
- `HOME_ACTIVE_JOB_STORAGE_KEY` constant defined but not actively used for hydration

### 6. Potential Issues

**Memory concerns:**
- Backend loads entire file into memory (`await file.read()`) — no streaming
- Large files (near `max_file_mb` limit) could cause memory pressure on concurrent uploads
- Multi-file parallel upload multiplies memory usage

**Polling inefficiency:**
- 2-second interval per active job × N jobs = N requests every 2s
- No exponential backoff for long-running jobs
- Backend has SSE endpoint but frontend doesn't use it
- Job list also polled every 4s independently

**Race conditions:**
- `fileJobs` state updates use functional `setFileJobs(prev => ...)` — safe for concurrent updates
- Polling effect depends on `fileJobs` in dependency array — causes effect re-run on every status change, creating new intervals
- `mounted` flag prevents stale updates after unmount

**Error recovery:**
- Poll errors silently swallowed — job could be stuck with no user feedback
- No "retry failed" button — user must reset and resubmit all files
- No network reconnection handling

**Download:**
- Creates temporary object URL, clicks programmatically, revokes URL (`page.tsx:385-400`)
- `handleDownloadAll` iterates sequentially, not parallel (`page.tsx:402-412`)

### API Endpoints Summary

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/jobs` | Create job (v1, flat Form params) |
| `POST` | `/api/v1/jobs/v2` | Create job (v2, JSON config) |
| `GET` | `/api/v1/jobs` | List recent jobs |
| `GET` | `/api/v1/jobs/{id}` | Get job status |
| `GET` | `/api/v1/jobs/{id}/events` | SSE stream (unused by frontend) |
| `POST` | `/api/v1/jobs/{id}/cancel` | Cancel job |
| `GET` | `/api/v1/jobs/{id}/download` | Download PPTX |
| `DELETE` | `/api/v1/jobs/{id}` | Delete job + artifacts |

## Caveats / Not Found

- Frontend does not use the SSE endpoint despite it being available
- No upload progress indicator (no XHR progress event or chunked upload)
- `HOME_ACTIVE_JOB_STORAGE_KEY` is defined but hydration logic is not visible in the code
- The `use-model-status` hook was not examined in detail
