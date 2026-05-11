# Research: API Layer Architecture

- **Query**: Comprehensive review of API layer in pdf2ppt project
- **Scope**: internal
- **Date**: 2026-05-04

## Findings

### API Endpoint Structure

The API is built with FastAPI and organized into 7 routers under `/api/v1/`:

| Router | Prefix | Purpose |
|---|---|---|
| `jobs.py` | `/api/v1/jobs` | PDF/image upload, job creation, status tracking |
| `auth.py` | `/api/v1/auth` | LinuxDo OAuth, password login, registration |
| `admin.py` | `/api/v1/admin` | User management, invite codes, site settings |
| `config.py` | `/api/v1` | Deploy mode, user preferences |
| `models.py` | `/api/v1/models` | LLM model listing (vision/OCR filtering) |
| `model_status.py` | `/api/v1/models` | Model download/status endpoints |
| `setup.py` | `/api/v1/setup` | First-time setup wizard |

### Authentication & Authorization

**Three auth mechanisms:**

1. **JWT Cookies** (primary) — `access_token` + `refresh_token` in httponly cookies
   - Access token: 60 min TTL
   - Refresh token: 30 day TTL
   - `dependencies.py:get_current_user()` validates JWT from cookie
   - `dependencies.py:get_current_user_optional()` — returns None if unauthenticated

2. **API Bearer Token** — for programmatic `/api/*` access
   - Configured via `API_BEARER_TOKEN` env var
   - Checked in `main.py:request_id_middleware()` for non-auth/admin routes
   - Uses `secrets.compare_digest` for timing-safe comparison

3. **OAuth State** — Redis-backed CSRF protection for LinuxDo OAuth flow
   - 10 minute TTL
   - One-time use (deleted on validation)

**Role-based access:**
- `require_admin()` dependency — guards admin endpoints
- `UserRole` enum: `user`, `admin`
- `is_initial_admin` flag protects the first admin from deactivation

### Request Validation & Error Responses

**Error handling pattern:**
- `AppException` class with `ErrorCode` enum, message, details dict, status_code
- Global exception handlers in `main.py`:
  - `AppException` → structured JSON with code/message/details
  - Generic `Exception` → 500 with `"internal_error"` code

**Validation:**
- Pydantic models for all request/response bodies
- `Form()` parameters with Field constraints (`ge`, `le`, `min_length`, `max_length`)
- Manual validation in business logic (e.g., file type checking, quota limits)

**Standard error codes:**
```
pdf_encrypted, file_too_large, too_many_pages, invalid_pdf,
ocr_failed, conversion_failed, job_not_found, internal_error,
validation_error, auth_required, auth_failed, quota_exceeded, forbidden
```

### File Handling

**Upload flow (`jobs.py:create_job`):**
1. Classify upload by MIME type and extension (PDF, PNG, JPG, JPEG, WEBP)
2. Check file size against `max_file_mb` setting (default 100MB)
3. Images are converted to PDF via Pillow + PyMuPDF
4. Stored in `{job_root_dir}/{job_id}/input.pdf`

**Path safety (`job_paths.py`):**
- `resolve_artifact_file()` validates paths (no `..`, no absolute paths)
- Raises `AppException` on invalid/missing paths
- Job directories created under configurable `job_root_dir`

**Cleanup (`services/job_cleanup.py`):**
- Background daemon runs every 15 minutes (configurable)
- Deletes expired terminal jobs (completed/failed/cancelled)
- TTL: 24 hours default (`job_ttl_minutes`)
- Cleans both on-disk directories and Redis metadata

### Job Queue Management

**Dual backend:**
1. **Redis + RQ** (production) — jobs enqueued to `rq:queue:default`
2. **In-memory** (fallback) — `threading.Thread` with daemon mode

**Job lifecycle:**
```
pending → processing → completed/failed/cancelled
```

**Stages:**
```
upload_received → queued → parsing → ocr → layout_assist →
pptx_generating → packaging → cleanup → done
```

**Features:**
- Per-job debug events (capped at 200, stored in Redis)
- Cancel support via Redis flag + RQ stop command
- Queue position tracking for frontend
- TTL refresh via `refresh_job_ttl()`

### Health Checks & Monitoring

- `GET /health` — returns `{"status": "ok"}` (no auth required)
- `X-Request-ID` middleware — adds request ID to all responses
- Debug events stream progress to frontend

### Security Observations

**Strengths:**
- Bearer token uses timing-safe comparison
- OAuth state is one-time use with TTL
- Path traversal protection in `resolve_artifact_file()`
- Admin cannot deactivate/demote themselves
- Initial admin account protected from deletion

**Potential concerns:**
1. **Bearer token skip paths** — `/api/v1/auth/`, `/api/v1/admin/`, `/api/v1/setup/` are exempted from bearer token check. This is intentional (they use JWT cookies), but means bearer-token-only clients cannot call admin endpoints.

2. **Env file write** — `admin.py:PUT /admin/env` writes directly to `.env` file. No backup mechanism.

3. **Sensitive data in logs** — `api_key` parameter in `create_job` is passed to worker kwargs. Comment mentions RQ description is sanitized, but actual kwargs dict still contains the key.

4. **No rate limiting** — No request rate limiting on any endpoint.

5. **No input sanitization on filenames** — `file.filename` from upload is used directly in path construction, though `Path()` normalization provides some protection.

6. **Auto-login endpoint** — `POST /auth/auto-login` creates tokens without password verification in self-use mode. Guarded by `deploy_mode == "self"` check.

7. **Quota enforcement gap** — `daily_task_limit` and `concurrent_task_limit` exist in user model but are not checked in `create_job` endpoint.

### Key Files

| File Path | Description |
|---|---|
| `api/app/main.py` | FastAPI app, middleware, exception handlers |
| `api/app/auth.py` | OAuth flow, JWT management, password hashing |
| `api/app/api_auth.py` | Bearer token validation |
| `api/app/dependencies.py` | Auth dependencies (get_current_user, require_admin) |
| `api/app/config.py` | Settings from env vars |
| `api/app/routers/jobs.py` | Job CRUD, file upload, OCR check endpoints |
| `api/app/routers/auth.py` | Auth endpoints (login, register, refresh) |
| `api/app/routers/admin.py` | Admin user/settings management |
| `api/app/routers/models.py` | LLM model listing |
| `api/app/routers/model_status.py` | Model download/status |
| `api/app/routers/setup.py` | First-time setup wizard |
| `api/app/routers/config.py` | Deploy mode, user preferences |
| `api/app/models/user.py` | User/InviteCode/Settings ORM + Pydantic models |
| `api/app/models/job.py` | Job status/stage enums + response models |
| `api/app/models/error.py` | ErrorCode enum, AppException, ErrorResponse |
| `api/app/services/redis_service.py` | Redis-backed job metadata store |
| `api/app/services/job_cleanup.py` | Expired job cleanup daemon |
| `api/app/job_paths.py` | Job directory path resolution |

## Caveats / Not Found

- Worker implementation (`worker.py`) was not fully reviewed — focuses on job processing pipeline
- OCR provider implementations (`convert/ocr/`) not deeply examined
- No OpenAPI schema generation or API versioning strategy found
- No request/response logging middleware (only exception logging)
