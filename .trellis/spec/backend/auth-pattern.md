# Auth Pattern — OAuth + JWT + User Isolation

## 1. Scope / Trigger

- Any feature that requires user identity (login, user-specific data, quotas)
- Any new API endpoint that needs user context
- Any modification to job ownership or access control

## 2. Signatures

### Auth Dependencies (FastAPI)

```python
# api/app/dependencies.py
async def get_current_user(request: Request, db: Session = Depends(get_db)) -> UserORM
async def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[UserORM]
async def require_admin(user: UserORM = Depends(get_current_user)) -> UserORM
```

### Auth API Endpoints

```
GET  /api/v1/auth/login          → Redirect to LinuxDo OAuth
POST /api/v1/auth/callback       → Exchange code for JWT, set cookies
GET  /api/v1/auth/me             → Current user info
POST /api/v1/auth/logout         → Clear auth cookies
POST /api/v1/auth/refresh        → Refresh access token
GET  /api/v1/auth/quota          → User quota info
```

### Admin API Endpoints

```
GET  /api/v1/admin/users         → List all users
GET  /api/v1/admin/users/{id}    → User details
PUT  /api/v1/admin/users/{id}    → Update user (quota, role, status)
GET  /api/v1/admin/users/{id}/tasks → User's tasks
GET  /api/v1/admin/stats         → Dashboard statistics
```

## 3. Contracts

### JWT Cookie Fields

| Cookie | Value | Flags |
|--------|-------|-------|
| `access_token` | JWT (30min) | httponly, secure, samesite=lax |
| `refresh_token` | JWT (7d) | httponly, secure, samesite=lax |

### JWT Payload

```json
{
  "sub": "user_123",
  "type": "access",
  "exp": 1234567890
}
```

### User Model (SQLite)

| Field | Type | Constraints |
|-------|------|-------------|
| id | Integer | PK, autoincrement |
| linuxdo_id | String | unique, indexed |
| username | String | unique |
| name | String | nullable |
| avatar_url | String | nullable |
| role | String | "user" or "admin" |
| trust_level | Integer | 0-4 (from LinuxDo) |
| active | Boolean | default True |
| daily_task_limit | Integer | default 10 |
| max_file_size_mb | Integer | default 100 |
| concurrent_task_limit | Integer | default 2 |

### Environment Variables

| Key | Required | Description |
|-----|----------|-------------|
| `LINUXDO_CLIENT_ID` | Yes | OAuth app client ID |
| `LINUXDO_CLIENT_SECRET` | Yes | OAuth app client secret |
| `LINUXDO_REDIRECT_URI` | Yes | OAuth callback URL |
| `JWT_SECRET` | Yes | Secret for signing JWTs |
| `SQLITE_PATH` | No | SQLite DB path (default: `/app/data/pdf2ppt.db`) |

### Deploy-Mode Rate Limiting

- Global IP-based API rate limiting is a public-deployment protection only.
- `deploy_mode=self` must not throttle normal API usage; self-use deployments are expected to run behind a trusted user boundary.
- `deploy_mode=public` may throttle normal `/api/*` traffic using admin-configured `rate_limit_requests` and `rate_limit_window_seconds` site settings, falling back to env defaults.
- Lightweight model-readiness polling endpoints must not consume the global API quota:
  - `GET /api/v1/models/status`
  - `GET /api/v1/models/download/status`

## 4. Validation & Error Matrix

| Condition | Error Code | HTTP Status |
|-----------|------------|-------------|
| No JWT cookie | `AUTH_REQUIRED` | 401 |
| Invalid/expired JWT | `AUTH_FAILED` | 401 |
| User disabled | `AUTH_FAILED` | 401 |
| Non-admin accessing admin route | `FORBIDDEN` | 403 |
| Quota exceeded | `QUOTA_EXCEEDED` | 429 |
| Public-mode IP request rate exceeded | `rate_limit_exceeded` | 429 |
| Job not owned by user | `JOB_NOT_FOUND` | 404 |

## 5. Good/Base/Bad Cases

### Good: Authenticated user creates job

```
POST /api/v1/jobs
Cookie: access_token=eyJ...
→ 201 Created (job.user_id = current_user.id)
```

### Base: Unauthenticated request

```
GET /api/v1/auth/me
→ 401 {"detail": "Not authenticated"}
```

### Bad: User tries to access another user's job

```
DELETE /api/v1/jobs/{other_user_job_id}
Cookie: access_token=eyJ...
→ 404 {"detail": "Job not found"}
```

## 6. Tests Required

- OAuth state generation/validation (CSRF protection)
- JWT creation and decoding
- User creation from OAuth userinfo
- Job ownership check on get/cancel/delete
- Quota enforcement (daily limit, file size, concurrent)
- Admin role enforcement on admin endpoints

## 7. Wrong vs Correct

### Wrong: Direct user_id from request body

```python
@app.post("/api/v1/jobs")
async def create_job(user_id: int = Body(...)):  # ❌ Client controls user_id
    ...
```

### Correct: User from JWT cookie

```python
@app.post("/api/v1/jobs")
async def create_job(user: UserORM = Depends(get_current_user)):  # ✅ From verified JWT
    job = create_job(..., user_id=user.id)
```

---

## Design Decision: SQLite for User Data

**Context**: Need user persistence without external DB dependency.

**Options Considered**:
1. SQLite (single file, zero config)
2. PostgreSQL (scalable, requires separate service)
3. Redis only (no persistence guarantee)

**Decision**: SQLite — matches single-instance Docker deployment, zero运维.

**Extensibility**: If multi-instance needed, migrate to PostgreSQL (SQLAlchemy ORM makes this easy).
