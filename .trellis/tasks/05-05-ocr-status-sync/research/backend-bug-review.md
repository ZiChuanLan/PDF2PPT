# Research: Backend API & Worker Bug Review

- **Query**: Thorough review of backend API and worker code for subtle bugs
- **Scope**: internal
- **Date**: 2026-05-05

## Findings

### Files Reviewed

| File Path | Description |
|---|---|
| `api/app/routers/jobs.py` | Job creation, status, SSE, cancel, download, artifacts endpoints |
| `api/app/worker.py` | Background PDF-to-PPT processing worker |
| `api/app/services/redis_service.py` | Redis/in-memory job metadata storage |
| `api/app/services/job_cleanup.py` | Expired job cleanup daemon |
| `api/app/job_paths.py` | Job directory resolution helpers |
| `api/app/schemas/job_config.py` | Structured job config (v2 endpoint) |
| `api/app/config.py` | Application settings |
| `api/app/job_options.py` | Job option validation and normalization |
| `api/app/worker_helpers/guarded.py` | Blocking call with cancel/heartbeat guards |
| `api/app/worker_helpers/ocr_stage.py` | OCR processing stage |
| `api/app/worker_helpers/ppt_stage.py` | PPT generation stage |
| `api/app/worker_helpers/ocr_runtime.py` | OCR runtime setup |
| `api/app/dependencies.py` | Auth dependencies |
| `api/app/main.py` | FastAPI app setup, middleware |
| `api/app/models/job.py` | Job data models |
| `api/app/models/error.py` | Error models |
| `api/app/utils/concurrency.py` | Thread timeout helper |

---

## Bug #1: Race Condition in Quota Enforcement (create_job)

**File**: `api/app/routers/jobs.py`, lines 1046–1074
**Severity**: Medium

**What the bug is**: The concurrent task limit check (`count_active_jobs_for_user`) and daily task limit check (`count_daily_jobs_for_user`) are performed BEFORE `redis_service.create_job()` at line 1074. Between the check and the creation, another concurrent request can pass the same check and also create a job, allowing the user to exceed their quota.

**What should happen**: The quota check and job creation should be atomic, or the check should happen after creation with rollback on violation.

**What actually happens**: Two concurrent requests can both read `active_jobs < limit`, both pass, and both create jobs, exceeding the limit by 1 (or more under high concurrency).

**Suggested fix**: Use Redis `MULTI/EXEC` transaction to atomically check-and-increment, or use a distributed lock, or check-and-create in a single Lua script.

---

## Bug #2: O(n) Full Scan for Quota Checks (Performance)

**File**: `api/app/services/redis_service.py`, lines 420–440
**Severity**: High (Performance)

**What the bug is**: `count_active_jobs_for_user()` and `count_daily_jobs_for_user()` both call `get_all_job_ids()` which does `keys("job:*")`, then loads and deserializes EVERY job to filter by user. This is O(n) where n = total number of jobs in Redis.

**What should happen**: Use Redis sets or sorted sets indexed by user_id to count jobs in O(1) or O(log n).

**What actually happens**: With hundreds or thousands of jobs, every new job creation triggers loading all existing jobs from Redis. This gets worse over time as the job count grows.

**Suggested fix**: Maintain a Redis set `user:{user_id}:active_jobs` and sorted set `user:{user_id}:daily_jobs` that are updated on job create/complete/fail/cancel.

---

## Bug #3: get_all_job_ids Returns Non-Job Keys

**File**: `api/app/services/redis_service.py`, lines 406–418
**Severity**: Low

**What the bug is**: `get_all_job_ids()` uses `keys("job:*")` which matches `job:{id}`, `job:{id}:cancel`, and `job:{id}:secrets`. The filter `":cancel" not in key_str and ":secrets" not in key_str` is fragile — any future key format like `job:{id}:metadata` would leak through.

**What should happen**: Use a dedicated Redis set to track all job IDs, or use a more specific key pattern like `keys("job:*")` with regex `^job:[a-f0-9-]+$` to match only UUID-formatted job IDs.

**What actually happens**: Currently works but is fragile against future key additions.

---

## Bug #4: Secrets Not Cleaned Up on Worker Completion

**File**: `api/app/worker.py`, lines 990–1042 (finally block)
**Severity**: Medium (Security)

**What the bug is**: The worker's `finally` block cleans up the processing marker and process artifacts, but never calls `redis_service.delete_job_secrets(job_id)`. Secrets (API keys for OpenAI, Baidu, MinerU, etc.) remain in Redis until the job TTL expires.

**What should happen**: Delete secrets immediately after the worker finishes (success or failure), since they are no longer needed.

**What actually happens**: API keys persist in Redis for the full job TTL (default 24 hours) after job completion, increasing the window for secret exposure.

**Suggested fix**: Add `redis_service.delete_job_secrets(job_id)` in the worker's `finally` block.

---

## Bug #5: SSE Endpoint Has No Authentication

**File**: `api/app/routers/jobs.py`, lines 1628–1644
**Severity**: Medium (Security)

**What the bug is**: The `stream_job_events` endpoint at `GET /{job_id}/events` has no `current_user` dependency. Anyone who knows or guesses a job_id can subscribe to real-time progress events for that job.

**What should happen**: The endpoint should verify that the requester owns the job (same as `get_job_status` does with `current_user`).

**What actually happens**: Job progress events (including error messages and stage information) are accessible to any unauthenticated client with the job_id.

**Suggested fix**: Add `current_user=Depends(get_current_user_optional)` and check ownership like other endpoints do.

---

## Bug #6: In-Memory Backend Keys() Pattern Match is Incomplete

**File**: `api/app/services/redis_service.py`, lines 76–91
**Severity**: Low

**What the bug is**: The `_InMemoryRedis.keys()` method only handles patterns ending with `*` (prefix match). A pattern like `job:*:cancel` would not work. While the current code only uses `keys("job:*")`, this is a latent incompatibility with Redis behavior.

**What should happen**: Support at least basic glob patterns or document the limitation clearly.

**What actually happens**: Works for current usage but could break if someone adds `keys("job:*:cancel")`.

---

## Bug #7: Job Cleanup Daemon Can Delete Active Jobs if Redis Metadata is Lost

**File**: `api/app/services/job_cleanup.py`, lines 86–103
**Severity**: Low

**What the bug is**: When `redis_service.get_job()` returns `None` (metadata expired or Redis lost it), the cleanup falls back to mtime-based deletion. The `.processing` marker check at line 100 protects against this, BUT the marker is written at worker start and deleted in `finally`. If the worker process crashes hard (SIGKILL, OOM), the marker might not be written yet (race between marker write at worker.py:287 and the cleanup sweep).

**What should happen**: The processing marker should be written before any work begins (it already is at line 287), and the cleanup should have a generous grace period for mtime-based fallback.

**What actually happens**: In practice, the marker is written early, so this is mostly safe. The edge case is if the cleanup daemon runs in the exact window between job creation and marker write.

---

## Bug #8: File Size Check During Streaming Reads Past Limit

**File**: `api/app/routers/jobs.py`, lines 1017–1033
**Severity**: Low

**What the bug is**: During streaming upload, the code reads chunks and checks `file_size > settings.max_file_mb * 1024 * 1024` AFTER writing each chunk. If a chunk pushes the total past the limit, the file is unlinked and an exception raised. However, the check at line 1025 happens AFTER `f.write(chunk)` at line 1033 — wait, actually looking again:

```python
while True:
    chunk = await file.read(chunk_size)
    if not chunk:
        break
    file_size += len(chunk)
    if file_size > settings.max_file_mb * 1024 * 1024:
        f.close()
        input_path.unlink(missing_ok=True)
        raise AppException(...)
    f.write(chunk)
```

The check happens BEFORE the write. So the file on disk won't exceed the limit, but `file_size` already includes the oversized chunk. This is actually correct behavior — it rejects the upload before writing the oversized chunk. Not a bug.

**Verdict**: Not a bug, just noting the pattern for completeness.

---

## Bug #9: Cancel Race — Worker Can Overwrite Cancelled Status

**File**: `api/app/routers/jobs.py`, lines 1684–1696 and `api/app/services/redis_service.py`, lines 273–289
**Severity**: Low (Mitigated)

**What the bug is**: When `cancel_job` is called:
1. It sets the cancel flag in Redis
2. It calls `update_job(status=cancelled)` 

The `update_job` method has a terminal state guard (line 288): if the job is already in a terminal state and the new status differs, it's a no-op. However, if the worker is mid-processing and hasn't checked the cancel flag yet, it could call `update_job(status=processing)` AFTER the cancel endpoint sets `status=cancelled`. The terminal state guard at line 288 checks `job.status in _TERMINAL_JOB_STATUSES` — `cancelled` IS in that set, so the worker's update would be blocked. This is actually correct.

**Verdict**: Not a bug — the terminal state guard correctly prevents this race. The worker's `_set_processing_progress` will see the job is cancelled on its next `is_cancelled()` check.

---

## Bug #10: v2 Endpoint Missing Quota Check

**File**: `api/app/routers/jobs.py`, lines 1442–1445
**Severity**: Medium

**What the bug is**: The v2 endpoint (`POST /v2`) creates a job at line 1444 WITHOUT checking user quotas (concurrent task limit and daily task limit). The v1 endpoint checks these at lines 1047–1072.

**What should happen**: Both endpoints should enforce the same quota checks.

**What actually happens**: A user can bypass quota limits by using the v2 endpoint instead of v1.

**Suggested fix**: Add the same quota check logic from `create_job` to `create_job_v2`.

---

## Bug #11: RedisService Singleton Never Reconnects

**File**: `api/app/services/redis_service.py`, lines 96–126 and 487–496
**Severity**: Medium (Operational)

**What the bug is**: `RedisService.__init__` tries to connect to Redis once at construction time. If Redis is temporarily unavailable, it falls back to in-memory mode permanently. The singleton (`get_redis_service()`) never retries Redis.

**What should happen**: Periodically retry Redis connection, or at least provide a way to reset the singleton.

**What actually happens**: If Redis is briefly down during app startup, ALL jobs are stored in-memory (volatile, lost on restart) for the entire app lifetime.

**Suggested fix**: Add a health check that periodically pings Redis and re-initializes the client if it becomes available, or use `reset_redis_service()` in a health check loop.

---

## Bug #12: Disk Space Check Uses Wrong Path for v2 Endpoint

**File**: `api/app/routers/jobs.py`, lines 1373–1387
**Severity**: Low

**What the bug is**: In the v2 endpoint, `Path(settings.job_root_dir)` is used to check disk space (line 1375). If `job_root_dir` is relative, this creates a path relative to the current working directory, which may differ from how `job_paths.py` resolves it (relative to `_API_ROOT`).

**What should happen**: Use `get_job_root_dir()` from `job_paths.py` instead of `Path(settings.job_root_dir)`.

**What actually happens**: If the working directory differs from the API root, the disk space check might check the wrong filesystem.

**Suggested fix**: Replace `Path(settings.job_root_dir)` with `get_job_root_dir()` at line 1375. Note: the same pattern exists in v1 at line 993.

---

## Bug #13: Rate Limiter Pipeline Error Not Handled

**File**: `api/app/services/redis_service.py`, lines 442–467
**Severity**: Low

**What the bug is**: In `check_rate_limit`, if `self.redis_client.pipeline()` raises (e.g., Redis connection lost mid-request), the exception is caught by the outer `except Exception` which returns `(True, max_requests)` — allowing the request. This is the correct fail-open behavior, but the `_InMemoryRedis` class doesn't implement `pipeline()` or `incr()`, so rate limiting silently passes through for in-memory backends.

**What should happen**: The in-memory backend should support rate limiting or document the limitation.

**What actually happens**: Rate limiting is effectively disabled for in-memory backends (local dev mode), which is acceptable but undocumented.

---

## Summary of Critical Issues

| # | Bug | Severity | File |
|---|---|---|---|
| 1 | Race condition in quota enforcement | Medium | jobs.py:1046-1074 |
| 2 | O(n) full scan for quota checks | High (Perf) | redis_service.py:420-440 |
| 4 | Secrets not cleaned up on worker completion | Medium (Sec) | worker.py:990-1042 |
| 5 | SSE endpoint has no authentication | Medium (Sec) | jobs.py:1628-1644 |
| 10 | v2 endpoint missing quota check | Medium | jobs.py:1442-1445 |
| 11 | RedisService singleton never reconnects | Medium (Ops) | redis_service.py:96-126 |
| 12 | Disk space check uses wrong path | Low | jobs.py:1373-1387, 991-1005 |
