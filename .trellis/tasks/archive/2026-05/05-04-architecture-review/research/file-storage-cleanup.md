# Research: File Storage and Cleanup Mechanisms

- **Query**: Where are uploaded files stored, processed artifacts stored, temporary file cleanup, job expiration, data retention, disk space management, potential issues
- **Scope**: internal
- **Date**: 2026-05-04

## Findings

### Storage Architecture Overview

The project uses a **per-job directory model** under a configurable root. Each job gets a UUID-named directory containing all its artifacts.

### 1. Where Uploaded Files Are Stored

**Location**: `{JOB_ROOT_DIR}/{job_id}/input.pdf`

- Default `JOB_ROOT_DIR`: `api/data/jobs` (relative to api/ directory)
- Configurable via `JOB_ROOT_DIR` env var (`api/app/config.py:28`)
- Path resolution: `api/app/job_paths.py:18-34` — absolute paths used as-is, relative resolved under `api/`

**Upload flow** (`api/app/routers/jobs.py:1000-1008`):
1. User uploads PDF or image via `POST /api/v1/jobs`
2. Content read into memory (`await file.read()`)
3. Size checked against `MAX_FILE_MB` (default 100MB)
4. Job directory created: `ensure_job_dir(job_id)`
5. Written to `{job_dir}/input.pdf`
6. Images are converted to PDF first via `_write_upload_as_input_pdf()`

**File size limit**: `MAX_FILE_MB` = 100MB default (`config.py:14`), per-user override via `User.max_file_size_mb` (`models/user.py:56`)

### 2. Where Processed Artifacts Are Stored

**Location**: `{JOB_ROOT_DIR}/{job_id}/`

| Path | Description | Created By |
|---|---|---|
| `input.pdf` | Uploaded/normalized input | `routers/jobs.py:1002` |
| `output.pptx` | Final PPTX output | `worker.py:255` |
| `ir.json` | Final intermediate representation | `worker.py:907` |
| `ir.parsed.json` | Parsed IR (before OCR) | `worker.py:623` |
| `artifacts/` | Debug/process artifacts directory | `worker.py:257-258` |
| `artifacts/ocr/` | OCR debug data + overlay images | `worker.py:507` |
| `artifacts/ocr/ocr_debug.json` | OCR debug payload | `worker.py:509` |
| `artifacts/page_renders/` | Page render PNGs | worker_helpers |
| `artifacts/final_preview/` | Final preview PNGs | worker_helpers |
| `artifacts/layout_assist/` | Layout before/after PNGs | worker_helpers |
| `artifacts/mineru/` | MinerU adapter artifacts | `worker.py:584` |
| `artifacts/baidu_doc/` | Baidu doc adapter artifacts | `worker.py:607` |

**Artifact export is gated by perf policies** (`perf_policies.py`):
- `export_ocr_overlay_images`: default `False`
- `export_layout_assist_debug_images`: default `False`
- `export_final_preview_images`: default `False`
- Large documents may skip exports automatically

### 3. Temporary File Cleanup

#### 3a. Process Artifacts Cleanup (per-job, immediate)

**File**: `api/app/services/job_cleanup.py:27-35`

```python
def cleanup_job_process_artifacts(job_dir: Path) -> bool:
    artifacts_dir = Path(job_dir) / "artifacts"
    if not artifacts_dir.exists():
        return False
    shutil.rmtree(artifacts_dir)
    return True
```

**Trigger**: Worker `finally` block (`worker.py:986-997`):
- Runs after every job (success, failure, cancellation)
- Only if `retain_process_artifacts=False` (default)
- Deletes entire `artifacts/` subdirectory
- `output.pptx`, `input.pdf`, `ir.json` are **NOT** cleaned here — they persist until TTL expiry

#### 3b. AI OCR Probe Temp Files

**File**: `api/app/routers/jobs.py:326-327, 496-498`

- Creates temp PNG via `tempfile.mkstemp(prefix="ai-ocr-probe-", suffix=".png")`
- Cleaned up in `finally` block: `image_path.unlink(missing_ok=True)`
- **Well-handled** — no leak risk

#### 3c. AI Client Temp Images

**File**: `api/app/convert/ocr/ai_client.py:1586, 1918`

- Creates temp images for downscaling via `tempfile.gettempdir()`
- Cleaned via `temp_image_path.unlink(missing_ok=True)`
- **Well-handled** — no leak risk

#### 3d. LLM Adapter Temp Files

**File**: `api/app/convert/llm_adapter.py:371`

- `tmp.unlink(missing_ok=True)` — cleaned up

### 4. Job Expiration and Data Retention

#### 4a. TTL Mechanism

**Configuration** (`config.py:18-20`):
- `JOB_TTL_MINUTES`: default **1440** (24 hours)
- `JOB_CLEANUP_INTERVAL_MINUTES`: default **15** (sweep every 15 min)

**Redis TTL** (`redis_service.py:101, 139-148`):
- Each job metadata stored with `setex(key, ttl_seconds, value)`
- `expires_at` field in Job model synced with Redis TTL
- TTL refreshed on each `_persist_job()` call (status updates, debug events)
- Worker calls `_refresh_job_ttl()` during long-running stages (`worker.py:503-504`)

#### 4b. Cleanup Daemon

**File**: `api/app/services/job_cleanup.py:124-162`

- Started in `main.py:56` during app lifespan
- Background daemon thread (`job-cleanup-daemon`)
- Runs every `JOB_CLEANUP_INTERVAL_MINUTES` (15 min default)
- Scans all job directories under `JOB_ROOT_DIR`

**Cleanup logic** (`cleanup_expired_jobs`, lines 38-121):
1. For each directory in job root:
   - If Redis metadata exists: check `job.status` is terminal (completed/failed/cancelled) AND `expires_at <= now`
   - If no Redis metadata: fallback to file `st_mtime` check against TTL cutoff
2. If expired: `shutil.rmtree(job_dir)` — deletes entire job directory
3. Then `redis_service.delete_job(job_id)` — removes Redis metadata

#### 4c. Manual Delete

**Endpoint**: `DELETE /api/v1/jobs/{job_id}` (`routers/jobs.py:1585-1643`)
- Users can delete their own terminal jobs
- Deletes both on-disk directory and Redis metadata
- Cannot delete pending/processing jobs (must cancel first)

### 5. Docker Volumes and Mount Points

**Production** (`docker-compose.yml`):
- `api-data:/app/data` — shared between api and worker containers
- `paddlex-cache:/root/.paddlex` — PaddleOCR model cache
- `paddle-cache:/root/.cache/paddle` — Paddle framework cache

**Development** (`docker-compose.dev.yml`):
- Source code mounted directly (`./api:/app`)
- `api-data` volume NOT mounted (uses local filesystem)
- Same paddle cache volumes

**Hosted** (`docker-compose.hosted.yml`):
- `api-data:/app/data` — single container mode
- Same paddle cache volumes

**Key observation**: `api-data` is a Docker named volume. Job data lives at `/app/data/jobs/` inside the container. This means:
- Data persists across container restarts
- Data is NOT directly accessible from host (unless bind mount is added)
- Docker volume cleanup requires `docker volume rm` — not handled by the app

### 6. Potential Issues

#### 6a. Race Condition: Cleanup Daemon vs Active Jobs

**Risk**: Low but present.

The cleanup daemon checks `job.status` from Redis and `expires_at`. If a job is still processing but its Redis metadata expires (TTL not refreshed), the daemon could:
1. Find the directory exists
2. Find no Redis metadata (expired)
3. Fall back to `st_mtime` check
4. If `st_mtime` is old enough, delete the directory while worker is still writing

**Mitigation**: Worker calls `_refresh_job_ttl()` during long stages, and the default TTL is 24h. But if a job hangs for 24h without any progress update or heartbeat, the directory could be deleted.

**Affected code**: `job_cleanup.py:96-100` — fallback to `st_mtime` when no Redis metadata

#### 6b. Orphaned Directories from Crashed Workers

**Scenario**: Worker crashes mid-job, never reaches `finally` block cleanup. Redis metadata expires. Cleanup daemon deletes directory based on `st_mtime`.

**Risk**: Low — the daemon handles this via the `st_mtime` fallback. But there's a gap: if the worker crashes and the directory `st_mtime` is recent (within TTL), the directory persists until TTL expires. This is actually correct behavior.

#### 6c. No Disk Space Monitoring

**Finding**: No disk space checks anywhere in the codebase. No alerts when disk is full. No pre-upload disk space validation.

**Impact**: If disk fills up:
- `write_bytes()` / `save()` calls will raise `OSError`
- Worker will crash with unhandled exception
- Job marked as failed with generic error

#### 6d. In-Memory Upload Before Writing

**Code**: `routers/jobs.py:991` — `content = await file.read()`

The entire file is read into memory before writing to disk. For large files (up to 100MB), this could cause memory pressure under concurrent uploads.

#### 6e. No Cleanup of Paddle/ML Model Caches

**Volumes**: `paddlex-cache` and `paddle-cache` grow over time as models are downloaded. No cleanup mechanism exists for these caches. They persist indefinitely.

#### 6f. Cancel Key TTL Sync

**Code**: `redis_service.py:351-355` — cancel flag uses same `ttl_seconds` as job metadata. If job TTL is refreshed but cancel flag isn't, the cancel flag could expire while the job is still active. However, cancel flags are only set for jobs being cancelled (terminal), so this is not a real issue.

#### 6g. Worker Artifact Cleanup vs User Download Window

**Timeline**:
1. Job completes → `artifacts/` deleted immediately (unless `retain_process_artifacts=True`)
2. `output.pptx` and `input.pdf` persist until TTL (24h)
3. User downloads PPTX

**Risk**: None for PPTX download. But if user wants to view debug artifacts after completion, they're already gone (unless `retain_process_artifacts` was set).

#### 6h. `ir.parsed.json` Not Cleaned

**Code**: `worker.py:623` — writes `ir.parsed.json` but never cleans it up. It persists until TTL expiry alongside `ir.json`. Minor disk waste.

### Files Found

| File Path | Description |
|---|---|
| `api/app/services/job_cleanup.py` | Core cleanup logic: artifact cleanup + expired job daemon |
| `api/app/job_paths.py` | Job directory path resolution |
| `api/app/config.py:14-28` | Storage config: max_file_mb, job_ttl_minutes, job_root_dir |
| `api/app/services/redis_service.py` | Redis TTL management, job CRUD |
| `api/app/routers/jobs.py:990-1010` | Upload flow and job creation |
| `api/app/routers/jobs.py:1585-1643` | Manual job deletion endpoint |
| `api/app/routers/jobs.py:1646-1682` | Download endpoint |
| `api/app/worker.py:253-258, 986-997` | Worker artifact creation and cleanup |
| `api/app/main.py:51-64` | Cleanup daemon lifecycle |
| `api/app/perf_policies.py` | Artifact export gating |
| `api/app/convert/ocr/ai_client.py:1586, 1918` | Temp file handling in AI OCR |
| `docker-compose.yml:43-47, 72-75` | Volume mounts (api-data, paddle caches) |
| `docker-compose.dev.yml` | Dev volume mounts |
| `docker-compose.hosted.yml` | Hosted mode volume mounts |

### Related Specs

- `.trellis/spec/backend/index.md` — backend spec index
- `.trellis/spec/frontend/index.md` — frontend spec index

## Caveats / Not Found

- No cron/scheduled tasks found — cleanup is purely daemon-thread based
- No disk space monitoring or alerting
- No per-user storage quotas (only per-file size limit)
- Paddle model cache cleanup is completely absent
- The `st_mtime` fallback in cleanup daemon assumes filesystem timestamps are reliable, which may not hold in all container/orchestration environments
