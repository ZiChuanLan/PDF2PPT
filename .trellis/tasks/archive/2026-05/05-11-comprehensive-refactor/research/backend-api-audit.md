# Research: Backend API Surface Audit

- **Query**: Audit the complete backend API surface of pdf2ppt
- **Scope**: internal
- **Date**: 2026-05-11

## Findings

---

## 1. Router Registration & Prefix Conflicts

### Router Registration (api/app/main.py:89-97)

| Router Variable | Router File | Prefix | Tags |
|---|---|---|---|
| `jobs_router` | `api/app/routers/jobs.py:71` | `/api/v1/jobs` | `jobs` |
| `models_router` | `api/app/routers/models.py:14` | `/api/v1/models` | `models` |
| `model_status_router` | `api/app/routers/model_status.py:36` | `/api/v1/models` | `models` |
| `auth_router` | `api/app/routers/auth.py:40` | `/api/v1/auth` | `auth` |
| `admin_router` | `api/app/routers/admin.py:34` | `/api/v1/admin` | `admin` |
| `config_router` | `api/app/routers/config.py:19` | `/api/v1` | `config` |
| `runtime_config_router` | `api/app/routers/runtime_config.py:25` | `/api/v1/config` | `config` |
| `setup_router` | `api/app/routers/setup.py:40` | `/api/v1/setup` | `setup` |

### ⚠️ Route Prefix Conflict

**Both `models_router` and `model_status_router` use prefix `/api/v1/models` and tags `["models"]`.**

| Router | File | Prefix |
|---|---|---|
| `models_router` | `models.py:14` | `/api/v1/models` |
| `model_status_router` | `model_status.py:36` | `/api/v1/models` |

These do **not** currently produce HTTP-level conflicts because their actual sub-paths are disjoint. However, having two separate `APIRouter` instances with the same prefix is atypical and risks future route collisions.

**No duplicate or conflicting HTTP routes found.** All verb+path combinations are unique across routers.

---

## 2. Authentication Model

### Middleware-level (api/app/main.py:100-128)

A request-id middleware checks bearer token for `/api/*` routes:

- **Skip paths** (bearer token NOT checked): `/api/v1/auth/`, `/api/v1/admin/`, `/api/v1/setup/`
- **Needs bearer**: All other `/api/*` paths — but only enforced when `api_bearer_token` is configured (non-empty env var)

### Dependency-level

Three FastAPI dependency functions (`api/app/dependencies.py`):

| Dependency | Auth Mechanism | Returns | Used For |
|---|---|---|---|
| `get_current_user` | JWT from `access_token` cookie | `UserORM` (401 if missing/invalid) | Authenticated endpoints |
| `get_current_user_optional` | JWT from `access_token` cookie | `UserORM \| None` | Optional auth (jobs can be anonymous) |
| `require_admin` | Chains `get_current_user` + role check | `UserORM` (403 if not admin) | Admin-only endpoints |

---

## 3. Rate Limiting

Middleware-level (`api/app/main.py:131-149`):

- Applied to all `/api/*` paths (excludes `/health` and non-API paths)
- Per-client-IP rate limit using Redis service
- Returns 429 with `Retry-After` header when exceeded
- Configurable via `rate_limit_requests` and `rate_limit_window_seconds` settings

---

## 4. Error Response Format

### AppException Model (api/app/models/error.py:35-56)

```python
class AppException(Exception):
    code: str        # ErrorCode enum value (or raw string)
    message: str     # Human-readable message
    details: dict    # Optional diagnostic payload
    status_code: int # HTTP status (default 400)
```

### Error Response JSON Shape

```json
{
    "code": "validation_error",
    "message": "Human-readable error message",
    "details": { "key": "value" }  // optional, null if not provided
}
```

### Error Code Enum (api/app/models/error.py:9-24)

| Code | String Value | Typical HTTP Status |
|---|---|---|
| `PDF_ENCRYPTED` | `"pdf_encrypted"` | 400 |
| `FILE_TOO_LARGE` | `"file_too_large"` | 400 |
| `TOO_MANY_PAGES` | `"too_many_pages"` | 400 |
| `INVALID_PDF` | `"invalid_pdf"` | 400 |
| `OCR_FAILED` | `"ocr_failed"` | 400/500 |
| `CONVERSION_FAILED` | `"conversion_failed"` | 400/500 |
| `JOB_NOT_FOUND` | `"job_not_found"` | 404 |
| `INTERNAL_ERROR` | `"internal_error"` | 500 |
| `VALIDATION_ERROR` | `"validation_error"` | 400 |
| `AUTH_REQUIRED` | `"auth_required"` | 401 |
| `AUTH_FAILED` | `"auth_failed"` | 401 |
| `QUOTA_EXCEEDED` | `"quota_exceeded"` | 400 |
| `FORBIDDEN` | `"forbidden"` | 403 |

**Unhandled exceptions** → generic `{"code": "internal_error", "message": "An internal error occurred"}` with status 500 (`main.py:166-177`).

---

## 5. Complete Endpoint Catalog

---

### 5.1 Health & Debug

#### `GET /health`
- **File**: `api/app/main.py:180`
- **Method**: GET
- **Auth**: Public (no auth required)
- **Query Params**: None
- **Request Body**: None
- **Response** (200): `{"status": "ok"}`
- **Notes**: Used for health checks. Excluded from rate limiting.

#### `GET /test-error`
- **File**: `api/app/main.py:188`
- **Method**: GET
- **Auth**: Public
- **Query Params**: None
- **Request Body**: None
- **Response** (400): ErrorResponse with code=`pdf_encrypted`, message=`"Test: PDF is password-protected"`, details=`{"test": true}`
- **Notes**: Only registered when `LOG_LEVEL=DEBUG`.

---

### 5.2 Setup (`/api/v1/setup`)

Router: `api/app/routers/setup.py:40`, prefix=`/api/v1/setup`, tags=`["setup"]`

#### `GET /api/v1/setup/status`
- **File**: `setup.py:50`
- **Method**: GET
- **Auth**: Public (no auth)
- **Query Params**: None
- **Request Body**: None
- **Response** (200): `{"needs_setup": bool}` — `true` if no users exist in DB
- **Notes**: Check if initial setup wizard is needed.

#### `POST /api/v1/setup/complete`
- **File**: `setup.py:60`
- **Method**: POST
- **Auth**: Public (guarded by user count check)
- **Request Body** (JSON):
  ```json
  {
    "deploy_mode": "self|public",       // required, pattern ^(self|public)$
    "username": "string",               // required, min 3, max 50
    "password": "string"                // required, min 8, max 100
  }
  ```
- **Response** (200):
  ```json
  {
    "user": { UserResponse },
    "token_type": "bearer",
    "expires_in": 3600,
    "access_token": "string",
    "refresh_token": "string"
  }
  ```
- **Notes**: Only allowed when `needs_setup=true` (no users exist). Creates admin user, sets deploy_mode in site_settings. Sets `access_token` and `refresh_token` cookies.

---

### 5.3 Auth (`/api/v1/auth`)

Router: `api/app/routers/auth.py:40`, prefix=`/api/v1/auth`, tags=`["auth"]`

#### `GET /api/v1/auth/login`
- **File**: `auth.py:43`
- **Method**: GET
- **Auth**: Public
- **Query Params**:
  | Param | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `origin` | `str` | No | `None` | Frontend origin for dynamic redirect_uri |
- **Request Body**: None
- **Response** (200):
  ```json
  {
    "authorize_url": "https://linux.do/...",
    "state": "random-state-string"
  }
  ```
- **Notes**: Initiates LinuxDo OAuth login flow. Returns authorization URL.

#### `POST /api/v1/auth/callback`
- **File**: `auth.py:59`
- **Method**: POST
- **Auth**: Public
- **Request Body** (JSON):
  ```json
  {
    "code": "string",       // required - OAuth authorization code
    "state": "string",      // required - OAuth state parameter
    "origin": "string|null" // optional - frontend origin
  }
  ```
- **Response** (200):
  ```json
  {
    "user": { UserResponse },
    "token_type": "bearer",
    "expires_in": 3600,
    "access_token": "string",
    "refresh_token": "string"
  }
  ```
- **Notes**: Handles OAuth callback. Sets JWT cookies (`access_token` 1h, `refresh_token` 30d).

#### `GET /api/v1/auth/me`
- **File**: `auth.py:132`
- **Method**: GET
- **Auth**: `get_current_user` (JWT cookie required)
- **Query Params**: None
- **Request Body**: None
- **Response** (200): `UserResponse` object
  ```json
  {
    "id": 1,
    "linuxdo_id": null,
    "username": "string",
    "name": "",
    "avatar_url": null,
    "role": "user|admin",
    "trust_level": 0,
    "active": true,
    "is_initial_admin": false,
    "created_at": "datetime",
    "last_login_at": null,
    "daily_task_limit": 10,
    "max_file_size_mb": 100.0,
    "concurrent_task_limit": 2
  }
  ```

#### `POST /api/v1/auth/logout`
- **File**: `auth.py:140`
- **Method**: POST
- **Auth**: Public
- **Query Params**: None
- **Request Body**: None
- **Response** (200): `{"message": "Logged out successfully"}`
- **Notes**: Clears `access_token` and `refresh_token` cookies.

#### `POST /api/v1/auth/refresh`
- **File**: `auth.py:150`
- **Method**: POST
- **Auth**: Public (validates refresh token)
- **Request Body** (JSON, optional):
  ```json
  {
    "refresh_token": "string"   // required if not in cookie
  }
  ```
- **Cookies**: Reads `refresh_token` cookie as fallback
- **Response** (200):
  ```json
  {
    "token_type": "bearer",
    "expires_in": 3600
  }
  ```
- **Notes**: Issues new `access_token` and `refresh_token` cookies. Validates refresh token type.

#### `GET /api/v1/auth/quota`
- **File**: `auth.py:209`
- **Method**: GET
- **Auth**: `get_current_user` (JWT cookie required)
- **Query Params**: None
- **Request Body**: None
- **Response** (200):
  ```json
  {
    "daily_task_limit": 10,
    "max_file_size_mb": 100.0,
    "concurrent_task_limit": 2,
    "tasks_today": 5,
    "active_tasks": 2
  }
  ```

#### `POST /api/v1/auth/register`
- **File**: `auth.py:251`
- **Method**: POST
- **Auth**: Public
- **Request Body** (JSON):
  ```json
  {
    "invite_code": "string",   // required
    "username": "string",      // required, min 3, max 50
    "password": "string"       // required, min 8, max 100
  }
  ```
- **Response** (200):
  ```json
  {
    "user": { UserResponse },
    "token_type": "bearer",
    "expires_in": 3600
  }
  ```
- **Notes**: Creates user with password. Requires valid invite code. Sets JWT cookies.

#### `POST /api/v1/auth/login-password`
- **File**: `auth.py:292`
- **Method**: POST
- **Auth**: Public
- **Request Body** (JSON):
  ```json
  {
    "username": "string",   // required
    "password": "string"    // required
  }
  ```
- **Response** (200):
  ```json
  {
    "user": { UserResponse },
    "token_type": "bearer",
    "expires_in": 3600
  }
  ```
- **Notes**: Password-based login. Sets JWT cookies.

#### `POST /api/v1/auth/auto-login`
- **File**: `auth.py:320`
- **Method**: POST
- **Auth**: Public (guarded by deploy_mode check)
- **Query Params**: None
- **Request Body**: None
- **Response** (200):
  ```json
  {
    "user": { UserResponse },
    "token_type": "bearer",
    "expires_in": 3600
  }
  ```
- **Notes**: Only works in `deploy_mode=self`. Auto-logs in as first admin user. Requires at least one user to exist. Sets JWT cookies.

#### `POST /api/v1/auth/change-password`
- **File**: `auth.py:378`
- **Method**: POST
- **Auth**: `get_current_user` (JWT cookie required)
- **Request Body** (JSON):
  ```json
  {
    "old_password": "string",   // required
    "new_password": "string"    // required
  }
  ```
- **Response** (200): `{"message": "密码修改成功"}`

---

### 5.4 Config (`/api/v1`, `/api/v1/config`)

Two routers under the `config` tag (config.py + runtime_config.py).

#### `GET /api/v1/config/deploy-mode`
- **File**: `config.py:22`
- **Method**: GET
- **Auth**: Public
- **Query Params**: None
- **Request Body**: None
- **Response** (200): `{"mode": "self|public"}` — reads from site_settings DB, falls back to env var.

#### `GET /api/v1/user/preferences`
- **File**: `config.py:33`
- **Method**: GET
- **Auth**: `get_current_user` (JWT cookie required)
- **Response** (200): `{"preferences": {"key": "value", ...}}`

#### `PUT /api/v1/user/preferences`
- **File**: `config.py:48`
- **Method**: PUT
- **Auth**: `get_current_user` (JWT cookie required)
- **Request Body** (JSON): `{"preferences": {"key": "value", ...}}`
- **Response** (200): `{"updated": ["key1", "key2"]}`

#### `GET /api/v1/config/runtime`
- **File**: `runtime_config.py:199`
- **Method**: GET
- **Auth**: `require_admin` (admin JWT cookie required)
- **Response** (200):
  ```json
  {
    "config": {
      "JOB_TIMEOUT_SECONDS": 3600,
      "OCR_PAGE_TIMEOUT_S": 300,
      "OCR_TOTAL_TIMEOUT_S": 3600,
      "OCR_PADDLE_VL_PREDICT_TIMEOUT_S": 180.0,
      "OCR_AI_RETRY_BACKOFF_BASE_S": 8.0,
      "OCR_AI_RATE_LIMITED_MIN_DELAY_S": 2.0,
      "ENABLE_LAYOUT_ASSIST": false,
      "SCANNED_RENDER_DPI": 200,
      "OCR_AI_PAGE_CONCURRENCY_MAX": 8,
      "OCR_AI_BLOCK_CONCURRENCY_MAX": 8,
      "OCR_AI_RPM_MAX": 2000,
      "OCR_AI_TPM_MAX": 2000000,
      "OCR_AI_MAX_RETRIES_MAX": 8,
      "OCR_AI_PAGE_CONCURRENCY_DEFAULT": 1,
      "OCR_AI_BLOCK_CONCURRENCY_DEFAULT": 1,
      "OCR_AI_RPM_DEFAULT": 1,
      "OCR_AI_TPM_DEFAULT": 1000,
      "OCR_AI_MAX_RETRIES_DEFAULT": 0,
      "OCR_MAX_CONSECUTIVE_TIMEOUTS": 2,
      "OCR_IMAGE_REGION_TIMEOUT_S": 12
    },
    "message": "Current runtime configuration"
  }
  ```
- **Notes**: Reads from live Settings object (memory). May differ from `.env` file.

#### `PUT /api/v1/config/runtime`
- **File**: `runtime_config.py:211`
- **Method**: PUT
- **Auth**: `require_admin` (admin JWT cookie required)
- **Request Body** (JSON): Same `RuntimeConfigValues` shape as GET response (all fields optional—only provided fields are updated).
- **Response** (200):
  ```json
  {
    "config": { RuntimeConfigValues },
    "message": "Runtime configuration updated. Restart server for changes to take effect."
  }
  ```
- **Notes**: Writes to `.env` file. Changes require server restart. Creates `.env.bak` backup.

---

### 5.5 Models (`/api/v1/models`) — ⚠️ TWO ROUTERS SHARE THIS PREFIX

#### Router 1: `models.py` (Model Listing)

##### `POST /api/v1/models`
- **File**: `models.py:367`
- **Method**: POST
- **Auth**: Public (API key required in body)
- **Request Body** (JSON):
  ```json
  {
    "provider": "openai",           // default: "openai", supported: auto, openai, siliconflow, deepseek, ppio, novita, claude
    "api_key": "sk-...",            // required
    "base_url": "https://...",      // optional
    "capability": "all"             // default: "all", options: all, vision, ocr
  }
  ```
- **Response** (200): `{"models": ["model-id-1", "model-id-2", ...]}`
- **Notes**: Lists models from the selected provider. `capability=vision` filters to vision-capable models. `capability=ocr` filters to dedicated OCR models only. `provider=auto` infers provider from base_url.

#### Router 2: `model_status.py` (Model Status & Downloads)

##### `GET /api/v1/models/status`
- **File**: `model_status.py:329`
- **Method**: GET
- **Auth**: Public (unauthenticated)
- **Response** (200):
  ```json
  {
    "local": {
      "tesseract": { "ready": true, "issues": [], "provider": null, "configured": true },
      "paddleocr": { "ready": false, "issues": ["not_downloaded"], ... },
      "pp_doclayout_v3": { "ready": true, "issues": [], "provider": "paddlex", "configured": true },
      "pp_doclayout_s": { ... },
      "pp_doclayout_m": { ... },
      "pp_doclayout_l": { ... },
      "doclayout_yolo": { ... }
    },
    "remote": {
      "aiocr": { "ready": true, "issues": [], "provider": null, "configured": true },
      "baidu_doc": { "ready": false, "issues": ["api_key_missing", "secret_key_missing"], ... },
      "mineru": { "ready": false, "issues": ["api_token_missing"], ... }
    }
  }
  ```

##### `POST /api/v1/models/download`
- **File**: `model_status.py:513`
- **Method**: POST
- **Auth**: `require_admin` (admin JWT cookie required)
- **Request Body** (JSON):
  ```json
  {
    "model": "pp_doclayout_v3|paddleocr|..."   // required
  }
  ```
- **Response** (200):
  ```json
  {
    "ok": true,
    "model": "pp_doclayout_v3",
    "message": "PP-DocLayout V3 开始下载",
    "status": "downloading"
  }
  ```
- **Notes**: Triggers background download. Supported: `pp_doclayout_v3`, `pp_doclayout_s`, `pp_doclayout_m`, `pp_doclayout_l`, `doclayout_yolo`, `paddleocr`. Returns immediately.

##### `GET /api/v1/models/download/status`
- **File**: `model_status.py:607`
- **Method**: GET
- **Auth**: Public (unauthenticated)
- **Response** (200):
  ```json
  {
    "downloads": {
      "pp_doclayout_v3": {
        "model_id": "pp_doclayout_v3",
        "status": "downloading|completed|failed|cancelled",
        "progress": 0.45,       // null for paddleocr
        "message": "下载中...",
        "started_at": 1700000000.0
      }
    }
  }
  ```
- **Notes**: Auto-cleans expired entries (>5 min after completion/failure/cancel).

##### `POST /api/v1/models/download/cancel`
- **File**: `model_status.py:641`
- **Method**: POST
- **Auth**: `require_admin` (admin JWT cookie required)
- **Request Body** (JSON):
  ```json
  {
    "model": "pp_doclayout_v3"   // required
  }
  ```
- **Response** (200):
  ```json
  {
    "ok": true,
    "model": "pp_doclayout_v3",
    "message": "取消请求已发送"
  }
  ```

##### `POST /api/v1/models/delete`
- **File**: `model_status.py:769`
- **Method**: POST
- **Auth**: `require_admin` (admin JWT cookie required)
- **Request Body** (JSON):
  ```json
  {
    "model": "pp_doclayout_v3"   // required
  }
  ```
- **Response** (200):
  ```json
  {
    "success": true,
    "model": "pp_doclayout_v3",
    "message": "已删除 PP-DocLayout V3 缓存"
  }
  ```
- **Notes**: Deletes model from local cache. Refuses if model is currently downloading.

---

### 5.6 Jobs (`/api/v1/jobs`)

Router: `api/app/routers/jobs.py:71`, prefix=`/api/v1/jobs`, tags=`["jobs"]`

#### `GET /api/v1/jobs`
- **File**: `jobs.py:602`
- **Method**: GET
- **Auth**: `get_current_user_optional` (optional JWT cookie)
- **Query Params**:
  | Param | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `limit` | `int` | No | `50` | Max jobs to return (1-200) |
- **Response** (200):
  ```json
  {
    "jobs": [
      {
        "job_id": "uuid-string",
        "user_id": 1,
        "status": "pending|processing|completed|failed|cancelled",
        "stage": "upload_received|queued|parsing|ocr|layout_assist|pptx_generating|packaging|cleanup|done",
        "progress": 50,
        "created_at": "datetime",
        "expires_at": "datetime",
        "message": "Processing...",
        "error": null,
        "queue_position": 3,       // 1-based, null if not in queue
        "queue_state": "queued|running|waiting|done"
      }
    ],
    "queue_size": 5,
    "returned": 10
  }
  ```
- **Notes**: If authenticated, only returns user's own jobs. RQ queue metadata is polled for accurate queue positions.

#### `POST /api/v1/jobs` — Legacy Form-based creation
- **File**: `jobs.py:685`
- **Method**: POST
- **Auth**: `get_current_user_optional` (optional JWT cookie)
- **Request**: `multipart/form-data`
  - **Required File**:
    | Field | Type | Description |
    |---|---|---|
    | `file` | `UploadFile` | PDF or image file to convert |

  - **Form Fields** (all optional unless noted):
    | Field | Type | Default | Description |
    |---|---|---|---|
    | `enable_ocr` | `bool` | `false` | Enable OCR for scanned PDFs |
    | `retain_process_artifacts` | `bool` | `false` | Keep debug artifacts |
    | `remove_footer_notebooklm` | `bool` | `false` | Remove NotebookLM footer |
    | `text_erase_mode` | `str` | `"fill"` | `smart` or `fill` |
    | `enable_layout_assist` | `bool` | `false` | **Deprecated** |
    | `layout_assist_apply_image_regions` | `bool` | `false` | **Deprecated** |
    | `parse_provider` | `str` | `"local"` | `local`, `baidu_doc`, `mineru`, `v2` |
    | `provider` | `str` | `"openai"` | LLM provider |
    | `api_key` | `str` | `null` | API key for AI services |
    | `baidu_doc_parse_type` | `str` | `"paddle_vl"` | `general` or `paddle_vl` |
    | `base_url` | `str` | `null` | OpenAI-compatible base URL |
    | `model` | `str` | `null` | Model identifier |
    | `page_start` | `int` | `null` | 1-based start page |
    | `page_end` | `int` | `null` | 1-based end page |
    | `mineru_api_token` | `str` | `null` | MinerU API token |
    | `mineru_base_url` | `str` | `null` | MinerU base URL |
    | `mineru_model_version` | `str` | `"vlm"` | MinerU model version |
    | `mineru_enable_formula` | `bool` | `true` | Enable formula recognition |
    | `mineru_enable_table` | `bool` | `true` | Enable table recognition |
    | `mineru_language` | `str` | `null` | Language hint (ch, en) |
    | `mineru_is_ocr` | `bool` | `null` | Per-file OCR switch |
    | `mineru_hybrid_ocr` | `bool` | `false` | **Deprecated** |
    | `ocr_provider` | `str` | `"auto"` | OCR provider |
    | `ocr_baidu_app_id` | `str` | `null` | Baidu OCR App ID |
    | `ocr_baidu_api_key` | `str` | `null` | Baidu OCR API key |
    | `ocr_baidu_secret_key` | `str` | `null` | Baidu OCR secret key |
    | `ocr_tesseract_min_confidence` | `float` | `null` | 0-100 |
    | `ocr_tesseract_language` | `str` | `null` | e.g. `eng`, `chi_sim` |
    | `ocr_ai_api_key` | `str` | `null` | AI OCR API key |
    | `ocr_ai_provider` | `str` | `"auto"` | AI OCR vendor |
    | `ocr_ai_base_url` | `str` | `null` | AI OCR base URL |
    | `ocr_ai_model` | `str` | `null` | AI OCR model name |
    | `ocr_ai_chain_mode` | `str` | `"direct"` | `direct`, `doc_parser`, `layout_block` |
    | `ocr_ai_layout_model` | `str` | `"pp_doclayout_v3"` | Layout model for layout_block |
    | `ocr_ai_prompt_preset` | `str` | `"auto"` | Prompt preset |
    | `ocr_ai_direct_prompt_override` | `str` | `null` | Prompt override |
    | `ocr_ai_layout_block_prompt_override` | `str` | `null` | Layout block prompt override |
    | `ocr_ai_image_region_prompt_override` | `str` | `null` | Image region prompt override |
    | `ocr_paddle_vl_docparser_max_side_px` | `int` | `null` | 0-6000 |
    | `ocr_ai_page_concurrency` | `int` | `1` | 1-8 |
    | `ocr_ai_block_concurrency` | `int` | `null` | 1-8 |
    | `ocr_ai_requests_per_minute` | `int` | `null` | 1-2000 |
    | `ocr_ai_tokens_per_minute` | `int` | `null` | 1-2000000 |
    | `ocr_ai_max_retries` | `int` | `0` | 0-8 |
    | `ocr_render_dpi` | `int` | `null` | 72-400 |
    | `ocr_geometry_mode` | `str` | `"auto"` | **Deprecated** |
    | `scanned_page_mode` | `str` | `"segmented"` | `segmented` or `fullpage` |
    | `ppt_generation_mode` | `str` | `"standard"` | `standard`, `fast`, `turbo` |
    | `image_bg_clear_expand_min_pt` | `float` | `null` | Min expansion (pt) |
    | `image_bg_clear_expand_max_pt` | `float` | `null` | Max expansion (pt) |
    | `image_bg_clear_expand_ratio` | `float` | `null` | Expansion ratio |
    | `scanned_image_region_min_area_ratio` | `float` | `null` | Min page-area ratio |
    | `scanned_image_region_max_area_ratio` | `float` | `null` | Max page-area ratio |
    | `scanned_image_region_max_aspect_ratio` | `float` | `null` | Max aspect ratio |
    | `ocr_ai_linebreak_assist` | `bool` | `null` | Line-break post-process |
    | `ocr_strict_mode` | `bool` | `true` | Strict OCR quality mode |

- **Response** (200):
  ```json
  {
    "job_id": "uuid-string",
    "status": "pending",
    "created_at": "datetime",
    "expires_at": "datetime"
  }
  ```
- **Notes**: 60+ form fields. Validates file type (PDF/PNG/JPG/WEBP). Checks disk space, user quotas (concurrent + daily). Sensitive keys (api_key, mineru_api_token, OCR keys) stored separately in Redis. File streamed to disk in 1MB chunks. Max file size checked during streaming.

#### `POST /api/v1/jobs/v2` — Structured JSON-based creation
- **File**: `jobs.py:1202`
- **Method**: POST
- **Auth**: `get_current_user_optional` (optional JWT cookie)
- **Request**: `multipart/form-data`
  | Field | Type | Required | Description |
  |---|---|---|---|
  | `file` | `UploadFile` | Yes | PDF or image file |
  | `config` | `str` (Form) | Yes | JSON-encoded `JobConfig` object |
- **Request Body (**`config`** field, JSON-decoded):**
  See `api/app/schemas/job_config.py:327` for full `JobConfig` schema with sub-models:
  - `JobConfig.enable_ocr: bool`
  - `JobConfig.retain_process_artifacts: bool`
  - `JobConfig.remove_footer_notebooklm: bool`
  - `JobConfig.parse: ParseConfig` (provider, mineru, baidu_doc)
  - `JobConfig.ocr: OcrConfig` (provider, ai, baidu, tesseract, render_dpi, strict_mode)
  - `JobConfig.llm: LlmConfig` (provider, api_key, base_url, model)
  - `JobConfig.ppt: PptConfig` (generation_mode, text_erase_mode, scanned_page_mode, image_regions)
  - `JobConfig.page_range: PageRangeConfig` (start, end)
- **Response** (200): Same `JobCreateResponse` as above.
- **Notes**: Newer endpoint that replaces 60+ flat Form() params with structured JSON. Internally converts to same flat kwargs format.

#### `GET /api/v1/jobs/{job_id}`
- **File**: `jobs.py:1459`
- **Method**: GET
- **Auth**: `get_current_user_optional` (optional JWT cookie)
- **Path Params**:
  | Param | Type | Description |
  |---|---|---|
  | `job_id` | `str` | UUID job identifier |
- **Response** (200):
  ```json
  {
    "job_id": "uuid",
    "user_id": 1,
    "status": "processing",
    "stage": "ocr",
    "progress": 50,
    "created_at": "datetime",
    "expires_at": "datetime",
    "message": "Processing page 3...",
    "error": null,
    "debug_events": [
      {
        "seq": 1,
        "timestamp": "datetime",
        "level": "info",
        "message": "OCR started",
        "source": "ocr",
        "stage": "ocr",
        "progress": 40
      }
    ]
  }
  ```
- **Notes**: Ownership check: authenticated users can only view their own jobs (403 if mismatched).

#### `GET /api/v1/jobs/{job_id}/events` — SSE Stream
- **File**: `jobs.py:1564`
- **Method**: GET
- **Auth**: Public (no auth check on SSE endpoint)
- **Path Params**: `job_id: str`
- **Response**: `text/event-stream` (SSE)
- **SSE Event Format**: Each event is `data: <JSON>\n\n` where JSON is a `JobEvent`:
  ```json
  {
    "job_id": "uuid",
    "status": "processing",
    "stage": "ocr",
    "progress": 50,
    "message": "OCR page 3...",
    "error": null
  }
  ```
- **SSE Event Types / States**:
  | Event | When Emitted |
  |---|---|
  | `JobEvent` with status=`failed`, error code=`job_not_found` | Immediately if job not found in Redis |
  | `JobEvent` on any state change | status, stage, progress, or message changed |
  | Stream closes | When status reaches `completed`, `failed`, or `cancelled` |
- **Polling**: Polls Redis every 500ms. Deduplicates (only emits on change).
- **Notes**: Uses `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` headers.

#### `POST /api/v1/jobs/{job_id}/cancel`
- **File**: `jobs.py:1583`
- **Method**: POST
- **Auth**: `get_current_user_optional` (optional JWT cookie)
- **Path Params**: `job_id: str`
- **Response** (200):
  ```json
  {
    "job_id": "uuid",
    "status": "cancelled",
    "message": "Cancellation requested"
  }
  ```
- **Notes**: Only pending/processing jobs can be cancelled. Ownership check. Sets RQ cancel flag, Redis cancel flag, updates job status to cancelled with progress=100.

#### `DELETE /api/v1/jobs/{job_id}`
- **File**: `jobs.py:1643`
- **Method**: DELETE
- **Auth**: `get_current_user_optional` (optional JWT cookie)
- **Path Params**: `job_id: str`
- **Response** (200):
  ```json
  {
    "job_id": "uuid",
    "status": "deleted",
    "artifacts_deleted": true
  }
  ```
- **Notes**: Only terminal (non-pending/processing) jobs can be deleted. Removes on-disk artifacts (`shutil.rmtree`) AND Redis metadata. Ownership check.

#### `GET /api/v1/jobs/{job_id}/download`
- **File**: `jobs.py:1704`
- **Method**: GET
- **Auth**: Public (no explicit auth check on download)
- **Path Params**: `job_id: str`
- **Response** (200): `FileResponse` — `application/vnd.openxmlformats-officedocument.presentationml.presentation` with filename `converted_{job_id}.pptx`
- **Notes**: Only completed jobs. Returns 404 if job not found, 400 if not completed, 500 if output file missing.

#### `GET /api/v1/jobs/{job_id}/artifacts`
- **File**: `jobs.py:1743`
- **Method**: GET
- **Auth**: Public (no explicit auth)
- **Path Params**: `job_id: str`
- **Response** (200):
  ```json
  {
    "job_id": "uuid",
    "status": "completed",
    "artifacts_retained": true,
    "source_pdf_url": "/api/v1/jobs/uuid/artifacts/file?path=input.pdf",
    "original_images": [
      { "page_index": 0, "path": "artifacts/page_renders/page-0000.png", "url": "/api/v1/jobs/uuid/artifacts/file?path=..." }
    ],
    "cleaned_images": [ ... ],
    "final_preview_images": [ ... ],
    "ocr_overlay_images": [ ... ],
    "layout_before_images": [ ... ],
    "layout_after_images": [ ... ],
    "available_pages": [0, 1, 2]
  }
  ```

#### `GET /api/v1/jobs/{job_id}/artifacts/file`
- **File**: `jobs.py:1829`
- **Method**: GET
- **Auth**: Public
- **Path Params**: `job_id: str`
- **Query Params**:
  | Param | Type | Required | Description |
  |---|---|---|---|
  | `path` | `str` | Yes | Artifact relative path under job directory |
- **Response** (200): `FileResponse` — serves the artifact file directly.
- **Notes**: Uses `_safe_artifact_path()` to prevent path traversal.

#### `POST /api/v1/jobs/ocr/local/check`
- **File**: `jobs.py:276`
- **Method**: POST
- **Auth**: Public
- **Request Body** (JSON):
  ```json
  {
    "provider": "tesseract",    // default "tesseract", options: tesseract, paddle, tesseract_models, paddle_models
    "language": null            // optional, e.g. "chi_sim+eng" for tesseract, "ch" for paddle
  }
  ```
- **Response** (200):
  ```json
  {
    "ok": true,
    "check": {
      "provider": "tesseract",
      "requested_language": "chi_sim+eng",
      "requested_languages": ["chi_sim", "eng"],
      "python_package_available": true,
      "binary_available": true,
      "version": "5.0.0",
      "available_languages": ["eng", "chi_sim"],
      "missing_languages": [],
      "model_root_dir": "/usr/share/tesseract-ocr/5/tessdata",
      "required_models": [],
      "found_models": [],
      "missing_models": [],
      "model_files": [],
      "issues": [],
      "ready": true,
      "message": "Tesseract 5.0.0 ready (eng, chi_sim)"
    }
  }
  ```

#### `POST /api/v1/jobs/ocr/ai/check`
- **File**: `jobs.py:510`
- **Method**: POST
- **Auth**: Public
- **Request Body** (JSON):
  ```json
  {
    "provider": "auto",                     // default "auto"
    "api_key": "sk-...",                    // required
    "base_url": null,                       // optional
    "model": "gpt-4o-mini",                 // required
    "ocr_ai_chain_mode": "direct",          // default "direct"
    "ocr_ai_layout_model": "pp_doclayout_v3", // default
    "ocr_ai_prompt_preset": "auto",         // default
    "ocr_ai_direct_prompt_override": null,  // optional, max 6000 chars
    "ocr_ai_layout_block_prompt_override": null,  // optional, max 6000 chars
    "ocr_ai_image_region_prompt_override": null,  // optional, max 6000 chars
    "ocr_paddle_vl_docparser_max_side_px": null,  // 0-6000
    "ocr_ai_block_concurrency": null,       // 1-8
    "ocr_ai_requests_per_minute": null,     // 1-2000
    "ocr_ai_tokens_per_minute": null,       // 1-2,000,000
    "ocr_ai_max_retries": null              // 0-8
  }
  ```
- **Response** (200):
  ```json
  {
    "ok": true,
    "check": {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "base_url": null,
      "route_kind": "direct",
      "elapsed_ms": 1234,
      "items_count": 6,
      "valid_bbox_items": 5,
      "ready": true,
      "message": "模型可返回有效 bbox OCR 结果",
      "error": null,
      "sample_items": [
        {
          "text": "PPT OpenCode OCR Check",
          "bbox": [104.0, 116.0, 800.0, 180.0],
          "confidence": 0.95
        }
      ]
    }
  }
  ```
- **Notes**: Creates a synthetic probe image (`PPT OpenCode OCR Check` with test text), sends it to the AI OCR model and checks if valid bbox results are returned. Runs in thread to not block event loop.

---

### 5.7 Admin (`/api/v1/admin`)

Router: `api/app/routers/admin.py:34`, prefix=`/api/v1/admin`, tags=`["admin"]`

All endpoints require `require_admin` (JWT cookie with admin role).

#### `GET /api/v1/admin/users`
- **File**: `admin.py:37`
- **Method**: GET
- **Auth**: `require_admin`
- **Query Params**:
  | Param | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `limit` | `int` | No | `50` | 1-200 |
  | `offset` | `int` | No | `0` | >=0 |
- **Response** (200): `{"users": [UserResponse, ...], "total": 42}`

#### `GET /api/v1/admin/users/{user_id}`
- **File**: `admin.py:59`
- **Method**: GET
- **Auth**: `require_admin`
- **Path Params**: `user_id: int`
- **Response** (200): `UserResponse`

#### `PUT /api/v1/admin/users/{user_id}`
- **File**: `admin.py:76`
- **Method**: PUT
- **Auth**: `require_admin`
- **Path Params**: `user_id: int`
- **Request Body** (JSON):
  ```json
  {
    "role": "user|admin",           // optional
    "active": true,                 // optional
    "daily_task_limit": 10,         // optional, 0-1000
    "max_file_size_mb": 100.0,      // optional, 0-10000
    "concurrent_task_limit": 2      // optional, 0-100
  }
  ```
- **Response** (200): `UserResponse`
- **Notes**: Cannot deactivate or demote own account.

#### `DELETE /api/v1/admin/users/{user_id}`
- **File**: `admin.py:139`
- **Method**: DELETE
- **Auth**: `require_admin`
- **Path Params**: `user_id: int`
- **Response** (200): `UserResponse` (with `active: false`)
- **Notes**: Soft delete (sets `active=False`). Cannot delete own account or initial admin.

#### `POST /api/v1/admin/users`
- **File**: `admin.py:176`
- **Method**: POST
- **Auth**: `require_admin`
- **Request Body** (JSON):
  ```json
  {
    "username": "string",   // required
    "password": "string",   // required
    "role": "user"          // default "user"
  }
  ```
- **Response** (200): `UserResponse`

#### `POST /api/v1/admin/users/{user_id}/reset-password`
- **File**: `admin.py:195`
- **Method**: POST
- **Auth**: `require_admin`
- **Path Params**: `user_id: int`
- **Request Body** (JSON):
  ```json
  {
    "new_password": "string"   // required, min 8, max 100
  }
  ```
- **Response** (200): `{"message": "密码已重置"}`

#### `POST /api/v1/admin/users/batch-delete`
- **File**: `admin.py:221`
- **Method**: POST
- **Auth**: `require_admin`
- **Request Body** (JSON):
  ```json
  {
    "user_ids": [1, 2, 3]   // required
  }
  ```
- **Response** (200): `{"deleted": 2, "skipped": 1}`
- **Notes**: Skips admin's own ID and initial admin accounts.

#### `GET /api/v1/admin/users/{user_id}/tasks`
- **File**: `admin.py:250`
- **Method**: GET
- **Auth**: `require_admin`
- **Path Params**: `user_id: int`
- **Query Params**:
  | Param | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `limit` | `int` | No | `50` | 1-200 |
- **Response** (200):
  ```json
  {
    "user_id": 1,
    "username": "admin",
    "tasks": [
      { "job_id": "uuid", "status": "completed", "created_at": "datetime", "message": "Done" }
    ],
    "total": 5
  }
  ```

#### `GET /api/v1/admin/stats`
- **File**: `admin.py:291`
- **Method**: GET
- **Auth**: `require_admin`
- **Response** (200):
  ```json
  {
    "users": { "total": 10, "active": 8, "admins": 2 },
    "jobs": { "total": 150, "pending": 3, "processing": 2, "completed": 140, "failed": 5 }
  }
  ```

#### `POST /api/v1/admin/invites`
- **File**: `admin.py:326`
- **Method**: POST
- **Auth**: `require_admin`
- **Query Params**:
  | Param | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `expires_in_days` | `int` | No | `7` | 1-30 |
- **Response** (200): `InviteCodeResponse` (id, code, created_by, used_by, expires_at, used_at, created_at)

#### `GET /api/v1/admin/invites`
- **File**: `admin.py:345`
- **Method**: GET
- **Auth**: `require_admin`
- **Query Params**:
  | Param | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `limit` | `int` | No | `50` | 1-200 |
  | `offset` | `int` | No | `0` | >=0 |
- **Response** (200): `{"invites": [InviteCodeResponse, ...], "total": 5}`

#### `GET /api/v1/admin/env`
- **File**: `admin.py:460`
- **Method**: GET
- **Auth**: `require_admin`
- **Response** (200):
  ```json
  {
    "vars": [
      { "key": "JWT_SECRET", "value": "••••••••", "is_sensitive": true },
      { "key": "LOG_LEVEL", "value": "INFO", "is_sensitive": false }
    ],
    "raw": "JWT_SECRET=••••••••\nLOG_LEVEL=INFO\n"
  }
  ```
- **Notes**: Sensitive keys (jwt_secret, linuxdo_client_secret, api_bearer_token, web_access_password) are masked.

#### `PUT /api/v1/admin/env`
- **File**: `admin.py:476`
- **Method**: PUT
- **Auth**: `require_admin`
- **Request Body** (JSON):
  ```json
  {
    "vars": { "LOG_LEVEL": "DEBUG", "JWT_SECRET": "••••••••" }
  }
  ```
- **Response** (200): Updated `EnvVarsResponse` (same shape as GET)
- **Notes**: Creates `.env.bak` backup. Masked sensitive values (••••••••) are NOT overwritten. Changes require server restart.

#### `GET /api/v1/admin/site-settings`
- **File**: `admin.py:537`
- **Method**: GET
- **Auth**: `require_admin`
- **Response** (200): `{"key1": "value1", "openai_api_key": "••••••••", ...}`
- **Notes**: Sensitive setting keys (openai_api_key, claude_api_key, mineru_api_token, ocr_baidu_api_key, ocr_baidu_secret_key, ocr_ai_api_key) are masked.

#### `PUT /api/v1/admin/site-settings`
- **File**: `admin.py:553`
- **Method**: PUT
- **Auth**: `require_admin`
- **Request Body** (JSON):
  ```json
  {
    "settings": { "openai_api_key": "sk-real-key", "custom_setting": "value" }
  }
  ```
- **Response** (200): `{"updated": ["openai_api_key", "custom_setting"]}`
- **Notes**: Masked sensitive values (••••••••) are skipped. Settings stored in `site_settings` DB table.

#### `GET /api/v1/admin/cache/status`
- **File**: `admin.py:596`
- **Method**: GET
- **Auth**: `require_admin`
- **Response** (200):
  ```json
  {
    "paddle_cache_mb": 245.3,
    "paddle_cache_files": 12
  }
  ```

#### `POST /api/v1/admin/cache/clear`
- **File**: `admin.py:606`
- **Method**: POST
- **Auth**: `require_admin`
- **Response** (200): `{"cleared": 2}` — number of cache dirs removed
- **Notes**: Clears `~/.paddlex/official_models` and `~/.paddleocr`.

---

## 6. Summary Statistics

| Router | Endpoints | Auth Required |
|---|---|---|
| Health/Debug | 2 (1 debug-only) | Public |
| Setup | 2 | Public (guarded) |
| Auth | 9 | Mixed (2 require JWT) |
| Config | 2 (user prefs) | 2 require JWT |
| Runtime Config | 2 | Admin only |
| Models (listing) | 1 | Public |
| Model Status | 5 | 3 admin, 2 public |
| Jobs | 11 | Optional auth (public with ownership checks) |
| Admin | 15 | Admin only |
| **Total** | **49** | |

---

## 7. Notable Findings

### 7.1 Shared Router Prefix
`models.py` and `model_status.py` both use `prefix="/api/v1/models"` and `tags=["models"]`. While no HTTP-level route conflict currently exists, having two separate `APIRouter` instances with identical prefixes is an anti-pattern. Consider merging into one router or using distinct prefixes.

### 7.2 Same-Router Prefix Potential Conflict (config vs runtime_config)
`config.py:19` uses `prefix="/api/v1"` while `runtime_config.py:25` uses `prefix="/api/v1/config"`. These don't conflict, but `config_router` could accidentally shadow future top-level `/api/v1/*` routes since its prefix is the root.

### 7.3 All Endpoints Have Route Decorators
No endpoints registered but lacking a route decorator were found. All endpoints in all 8 router files have explicit `@router.<method>(...)` decorators.

### 7.4 No Duplicate HTTP Routes
Every `(method, path)` pair across all routers is unique. No conflicting routes.

### 7.5 Deprecated Form Fields in create_job
The legacy `POST /api/v1/jobs` endpoint has 3 deprecated Form fields:
- `enable_layout_assist` — always forced to `False` server-side
- `layout_assist_apply_image_regions` — always forced to `False` server-side
- `mineru_hybrid_ocr` — always forced to `False` server-side
- `ocr_geometry_mode` — always forced to `"auto"` server-side

The `POST /api/v1/jobs/v2` endpoint also hardcodes these to `False`/`"auto"` in `to_worker_kwargs()`.

### 7.6 Sensitive Key Handling
Sensitive API keys (api_key, mineru_api_token, OCR keys) are:
1. Accepted via Form fields in job creation
2. Stored separately in Redis via `store_job_secrets()` (not in RQ job kwargs)
3. Set to `None` in the kwargs passed to the worker process
4. The worker retrieves them from Redis via `get_job_secrets()`

### 7.7 SSE Endpoint Has No Auth Check
The SSE streaming endpoint `GET /api/v1/jobs/{job_id}/events` has no authentication check. Anyone who knows a job_id can stream its progress events. This is consistent with the artifact download endpoint but may be intentional for frontend embedding.

### 7.8 Scope Discovery
All routers are auto-discovered and registered in `api/app/main.py:89-97` via explicit imports from `api/app/routers/__init__.py`.

---

## Caveats / Not Found

- The `api_auth.py` module referenced in `main.py` was not read — it validates bearer tokens for API access (non-auth/admin paths). Its exact implementation was not reviewed but is not an endpoint.
- Internal middleware functions (request ID, rate limiting, bearer token check, exception handlers) were documented but their full implementation details are in `main.py`.
- The `redis_service.py` module that backs job CRUD was not read — it is not an endpoint file.
