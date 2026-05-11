# Research: Dual Redis Backend Architecture

- **Query**: Trace all `is_memory_backend()` call sites, map `_InMemoryRedis` implementation, document RQ worker vs inline thread paths, identify bugs
- **Scope**: internal
- **Date**: 2026-05-10

## 1. `is_memory_backend()` — All Call Sites

### Definition

| File | Line | Description |
|---|---|---|
| `api/app/services/redis_service.py` | 127–129 | **Definition**: returns `self._memory_backend` (set to `True` when `redis_url` starts with `memory://` or when real Redis ping fails) |

### Call Sites (production code)

| # | File | Line | Context | Behavior Change | Can Abstract? |
|---|---|---|---|---|---|
| 1 | `api/app/routers/jobs.py` | 217 | `_sync_rq_cancel_state()` | **Early return**. When memory backend, skips all RQ cancel sync (RQ doesn't exist). | Yes — this guard is correct but could be handled by a NullJobQueue |
| 2 | `api/app/routers/jobs.py` | 597 | `list_jobs()` — queue metadata polling | **Skips RQ queue/registry polls**. When memory backend, `queue_job_ids` and `started_job_ids` stay empty, so all queue_state defaults to "waiting"/"done". | Yes |
| 3 | `api/app/routers/jobs.py` | 1084 | `create_job()` (v1) — job dispatch fork | **Branches: inline thread vs RQ enqueue**. Memory backend → `threading.Thread(..., daemon=True).start()`. Real Redis → `queue.enqueue("app.worker.process_pdf_job", ...)`. | Yes — this is the core dual-path fork |
| 4 | `api/app/routers/jobs.py` | 1482 | `create_job_v2()` (v2) — job dispatch fork | **Same fork as #3**, but for v2 structured config endpoint. | Yes — identical pattern |

### Test mock

| File | Line | Description |
|---|---|---|
| `api/tests/test_jobs_upload_route.py` | 36–37 | `_FakeRedisService.is_memory_backend()` always returns `True` |

---

## 2. `_InMemoryRedis` Implementation Map

**Location**: `api/app/services/redis_service.py`, lines 34–90  
**Singleton**: `_memory_redis` at line 93, created once at import time

### Implemented Methods

| Method | Lines | Behavior |
|---|---|---|
| `__init__` | 44–46 | Creates `threading.RLock` and empty `dict[str, _MemValue]` |
| `_purge_if_expired` | 48–54 | Deletes key if TTL expired (lazy, called only on `get`/`keys`) |
| `setex(key, ttl, value)` | 56–63 | Stores `_MemValue(value, expires_at_epoch)` |
| `get(key)` | 65–69 | Returns value or `None`; purges expired entries |
| `delete(*keys)` | 71–74 | Removes keys from dict |
| `keys(pattern)` | 76–90 | Only prefix-`*` matching; exact-key lookup fallback |

### Missing vs Real Redis (`redis` library)

| Real Redis Method | Used by | Impact on Memory Backend |
|---|---|---|
| `pipeline()` | `check_rate_limit()` (line 454, 461) | **BUG**: `_InMemoryRedis` has no `pipeline()` method. `check_rate_limit()` calls `self.redis_client.pipeline()`, which raises `AttributeError`. Caught by `except Exception` on line 465 → silently returns `(True, max_requests)`. **Rate limiting is silently disabled on memory backend.** |
| `incr(key)` | `check_rate_limit()` via pipeline | Would fail if pipeline worked |
| `ttl(key)` | `check_rate_limit()` via pipeline | Would fail if pipeline worked |
| `lrange(key, start, end)` | `jobs.py:600` (`list_jobs`) | Gated by `is_memory_backend()` guard — safe |
| `zrange(key, start, end)` | `jobs.py:602` (`list_jobs`) | Gated by `is_memory_backend()` guard — safe |
| `ping()` | `redis_service.py:116` | Not called on memory backend (early return at line 105–107) |
| `{scard, sadd, srem}` | Not used by this project | Not an issue |
| `{hset, hget, hdel}` | Not used by this project | Not an issue |
| `scan` | Not used by this project | Not an issue |

### Edge Cases Where In-Memory Behavior Differs

1. **Lazy expiration**: Real Redis removes expired keys atomically at access time. `_InMemoryRedis` purges only on `get()` and `keys()`, but NOT on `setex()` with identical key (which would overwrite anyway — actually ok). Not a problem currently because `setex` always overwrites.

2. **Thread safety scope**: `_InMemoryRedis` uses a single `RLock` per operation. Real Redis is per-key atomic. Multiple `keys()` + `get()` calls (as in `get_all_job_ids()`) are not atomic on memory backend, but this is acceptable since jobs are immutable-ish once created.

3. **Persistence**: In-memory data is lost on process restart. Real Redis survives restarts. This is by design for local QA mode.

4. **`keys()` pattern matching**: Only prefix-`*` supported. Real Redis supports `keys("job:*")` glob patterns. The codebase uses `keys("job:*")` which works because only trailing `*` is used.

5. **`delete_job()` atomicity** (line 400–404): Calls three separate `delete()` operations. On real Redis, these are three separate DEL commands. On memory backend, they are three separate lock acquire/release cycles — a thread could observe the key partially deleted between `_job_key` and `_cancel_key` deletion. Low risk in practice.

---

## 3. RQ Worker Enqueue Path vs Inline Thread Path

### Enqueue Fork Points

Both forks live in `jobs.py`:

- **Line 1084** (`create_job` v1 endpoint)
- **Line 1482** (`create_job_v2` v2 endpoint)

### Memory Backend (Inline Thread) Path

```python
threading.Thread(
    target=process_pdf_job,
    kwargs={"job_id": job_id, ... all kwargs with None for secrets ...},
    daemon=True,
).start()
```

### Real Redis (RQ Enqueue) Path

```python
redis_conn = get_redis_connection()
queue = Queue(connection=redis_conn)
queue.enqueue(
    "app.worker.process_pdf_job",
    job_id,              # positional arg (RQ reserves `job_id` kwarg)
    ... all kwargs ...,
    job_id=job_id,        # RQ job id (separate from our conversion job_id)
    description=f"process_pdf_job(job_id={job_id})",
)
```

### How `process_pdf_job()` Gets Invoked

| Aspect | Memory Backend (Inline Thread) | Real Redis (RQ Worker) |
|---|---|---|
| **Caller** | `threading.Thread` directly | RQ Worker process (`run_worker()` → `worker.work()`) |
| **Secrets retrieval** | Secrets stored in Redis then retrieved by `_retrieve_job_secrets()` inside `process_pdf_job()` (line 301). Since inline thread also runs `process_pdf_job`, secrets retrieval is identical. | Same: `_retrieve_job_secrets()` called inside `process_pdf_job()` (line 301). |
| **job_id in args** | Passed as kwarg `job_id=job_id` | Passed as positional arg (line 1159: `job_id`) because RQ reserves `job_id` kwarg for its own use |
| **Job timeout** | None — thread runs until completion or server crash | RQ's `job_timeout` parameter configured per job |
| **Concurrency** | Unlimited — each request spawns a new thread | Controlled by RQ worker count (typically 1 per worker process) |

### Error Handling Differences

| Scenario | Memory Backend (Inline Thread) | Real Redis (RQ Worker) |
|---|---|---|
| **Job crashes** | `process_pdf_job` catches `Exception` on line 1118, updates job status to `failed` in Redis. No external monitor. | Same exception handler inside `process_pdf_job`. RQ also catches exceptions and marks job as failed. |
| **Worker crashes** | Thread dies silently (`daemon=True`). Job stuck at "processing" forever. No recovery mechanism. | RQ worker process crashes → RQ requeues or marks failed based on `failure_ttl`. Surviving workers continue. |
| **Server restart** | All in-flight threads killed. Jobs stuck in "processing" state. | RQ persists job queue in Redis. Workers reconnect and continue after restart. |
| **Cancel during processing** | `_set_processing_progress` and `_abort_if_cancelled` check `redis_service.is_cancelled(job_id)`. Cancel flag set via `set_cancel_flag()`. Works. | Same cancel-check mechanism inside `process_pdf_job`. Additionally, `_sync_rq_cancel_state()` sends `send_stop_job_command()` (line 242) to signal RQ worker. |
| **Cancel during queuing** | No queuing — job starts immediately. Cancel request may race with job start. `_sync_rq_cancel_state()` early-returns (line 217–218). | `_sync_rq_cancel_state()` cancels the RQ job in queue (line 233–235). Prevention is stronger. |

### Concurrency Behavior Differences

| Aspect | Memory Backend | Real Redis |
|---|---|---|
| **Queue semantics** | No queue. Fire-and-forget thread per request. | FIFO queue. Jobs wait for worker availability. |
| **Throttling** | User quotas checked (concurrent/daily), but no global throttle. N concurrent requests = N simultaneous threads. | Quotas checked + RQ worker count limits actual concurrency. |
| **Resource contention** | N jobs compete for CPU/GPU without coordination. | Controlled by worker count and queue order. |

---

## 4. Proposed Unified `JobRunner` Abstraction

### Interface Design

```python
class JobRunner(ABC):
    """Abstracts how a job is dispatched for execution."""

    @abstractmethod
    def submit(self, job_id: str, **kwargs: Any) -> None:
        """Submit a job for asynchronous execution."""

    @abstractmethod
    def cancel(self, job_id: str, status: JobStatus) -> None:
        """Signal the runner to cancel a job."""

    @abstractmethod
    def get_queue_metadata(self) -> dict[str, Any]:
        """Return queue state for frontend polling (optional)."""

    def is_available(self) -> bool:
        """Check if this runner is usable."""
        return True
```

### Concrete Implementations

| Class | Description |
|---|---|
| `RqJobRunner` | Wraps RQ `Queue.enqueue()` + `send_stop_job_command` cancel. `queue_metadata` returns `rq:queue:default` and `rq:registry:started:default`. |
| `InlineThreadJobRunner` | Wraps `threading.Thread(target=process_pdf_job, daemon=True).start()`. Cancel is no-op for enqueue (job runs immediately). `queue_metadata` returns `{}`. |

### Code Paths That Collapse

| Current Location | Lines | Collapses Into |
|---|---|---|
| `jobs.py:1084–1150` (v1 create_job fork) | ~67 lines | `job_runner.submit(job_id, **kwargs)` |
| `jobs.py:1482–1497` (v2 create_job_v2 fork) | ~16 lines | `job_runner.submit(job_id, **kwargs)` |
| `jobs.py:214–252` (`_sync_rq_cancel_state`) | ~39 lines | `job_runner.cancel(job_id, status)` |
| `jobs.py:597–621` (list_jobs RQ metadata) | ~25 lines | `job_runner.get_queue_metadata()` |

### Estimated LOC Reduction

- Remove: ~147 lines of `is_memory_backend()` branching across 4 call sites
- Add: ~60 lines for `JobRunner` ABC + 2 concrete implementations + factory
- Net reduction: **~87 lines**
- Complexity reduction: Eliminates 4 conditional branches that must stay in sync

---

## 5. Identified Bugs & Subtle Issues

### BUG 1: Rate Limiting Silently Disabled on Memory Backend (HIGH)

**Location**: `api/app/services/redis_service.py`, lines 442–467

`check_rate_limit()` calls `self.redis_client.pipeline()` (lines 454, 461). `_InMemoryRedis` does NOT implement `pipeline()`. The `AttributeError` is caught by the blanket `except Exception` on line 465, which logs a warning and returns `(True, max_requests)` — allowing ALL requests.

**Impact**: In local QA mode (`REDIS_URL=memory://`), IP-based rate limiting is completely non-functional. Every request passes through, including during automated testing. This is masked because tests use fake services. But if a real load test hits a memory-mode server, rate limiting won't throttle anything.

**Fix options**:
- Implement a simple `Pipeline` class in `_InMemoryRedis` (add `incr`, `ttl`, `execute`)
- Or add `is_memory_backend()` guard to `check_rate_limit()` to use a simpler counting strategy
- Or catch `AttributeError` specifically and handle gracefully

### BUG 2: Stuck Jobs on Server Restart in Memory Mode (MEDIUM)

**Location**: `api/app/routers/jobs.py`, line 1085 – `daemon=True`

When the server restarts with memory backend, all in-flight daemon threads are killed by the OS. Jobs remain in `processing` status in the in-memory Redis (which is also lost on restart). On restart with memory backend, the state is clean-slate — but if a job was processing during crash, the user sees "not found" with no failure notification.

**Real Redis mitigates this**: RQ retries failed jobs, and job state persists across worker restarts. Memory mode has no equivalent.

### BUG 3: Cancel Race Condition in Memory Mode (LOW-MEDIUM)

**Location**: Jobs `jobs.py:217` (cancel) and `jobs.py:1085` (create)

Sequence:
1. User creates job → daemon thread starts immediately (line 1085)
2. User cancels job before thread checks `is_cancelled()` → `_sync_rq_cancel_state()` returns early (line 218), `set_cancel_flag()` is set (line 1697)
3. Thread picks up job, reads secrets, and at line 396 checks `is_cancelled(job_id)` → detects cancel → returns

This actually works because the cancel flag is set BEFORE the thread checks. But the timing window is tiny and the cancel flag is the ONLY mechanism — unlike real Redis mode where RQ can also cancel the queued job before it starts.

### ISSUE 4: No Concurrency Limiting in Memory Mode (LOW)

Memory mode has no worker pool or queue. If a user sends 50 concurrent requests, 50 threads will run simultaneously. Real Redis mode has a bounded RQ worker pool. The user quotas (concurrent/daily task limits) do provide some protection, but only for authenticated users. Unauthenticated requests in memory mode have no protection at all.

### ISSUE 5: `keys()` Method Edge Case in Memory Backend (LOW)

`_InMemoryRedis.keys()` at line 76-90 handles prefix-`*` matching by stripping the `*` and checking `str.startswith(prefix)`. For a pattern like `job:*`, prefix becomes `job:`, which matches `job:abc`, `job:abc:cancel`, and `job:abc:secrets`. The `get_all_job_ids()` method at line 406-418 handles this by filtering out `:cancel` and `:secrets` keys. This works, but it means `keys()` returns MORE results than real Redis (which does glob matching, not just prefix). For `job:*` this is fine. But if someone later uses `keys("rl:12*")` expecting glob behavior, they'd get wrong results.

---

## 6. Summary of Key Files

| File | Lines | Role |
|---|---|---|
| `api/app/services/redis_service.py` | 502 | Defines `RedisService`, `_InMemoryRedis`, `is_memory_backend()`, `check_rate_limit()` |
| `api/app/worker.py` | 1178 | `process_pdf_job()`, `run_worker()`, RQ worker bootstrap |
| `api/app/routers/jobs.py` | 1909 | Job CRUD endpoints, enqueue/cancel forks, queue metadata polling |
| `api/app/main.py` | 195 | Rate limit middleware (calls `check_rate_limit`) |
| `api/tests/test_jobs_upload_route.py` | 173 | Test mock with `_FakeRedisService` |
| `api/app/config.py` | ~110 | `redis_url` default: `"redis://redis:6379/0"` |

---

## Caveats

- The `check_rate_limit` pipeline bug (BUG 1) is the most actionable finding. It silently breaks rate limiting in the entire memory backend mode.
- The `_InMemoryRedis` class lacks `pipeline()`, `incr()`, `ttl()`, `lrange()`, `zrange()`. Of these, only `pipeline()` (and its chained `incr`/`ttl`) is actually invoked on the memory backend path via `check_rate_limit()`.
- The cancellation mechanism works in both paths because `is_cancelled()` and `set_cancel_flag()` use `get()` and `setex()` which are implemented. The RQ-specific cancel sync is correctly gated.
- The secrets storage/retrieval flow is identical in both paths (via `store_job_secrets`/`get_job_secrets`), which is good design.
