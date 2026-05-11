# Research: Current Authentication System

- **Query**: Understand the existing auth system to plan username/password login addition
- **Scope**: internal
- **Date**: 2026-05-01

## Findings

### Architecture Overview

The project uses a **LinuxDo OAuth-only** authentication system with JWT tokens stored in httponly cookies. There is **no username/password login** currently.

### User Model (`api/app/models/user.py`)

**SQLAlchemy ORM Model** (`UserORM`):
| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | Integer | PK, auto-increment | Internal user ID |
| `linuxdo_id` | Integer | **unique, NOT NULL, indexed** | LinuxDo OAuth identifier |
| `username` | String(255) | NOT NULL | LinuxDo username |
| `name` | String(255) | nullable | Display name |
| `avatar_url` | String(1024) | nullable | Avatar URL |
| `role` | String(20) | NOT NULL, default="user" | "user" or "admin" |
| `trust_level` | Integer | NOT NULL, default=0 | LinuxDo trust level |
| `active` | Boolean | NOT NULL, default=True | Account enabled flag |
| `created_at` | DateTime(tz) | NOT NULL | Auto-set on creation |
| `updated_at` | DateTime(tz) | NOT NULL | Auto-updated |
| `last_login_at` | DateTime(tz) | nullable | Last login timestamp |
| `daily_task_limit` | Integer | NOT NULL, default=10 | Quota |
| `max_file_size_mb` | Float | NOT NULL, default=100.0 | Quota |
| `concurrent_task_limit` | Integer | NOT NULL, default=2 | Quota |

**Key constraint**: `linuxdo_id` is `unique=True, nullable=False`. This means:
- Every user MUST have a `linuxdo_id`
- Adding username/password login requires either: (1) making `linuxdo_id` nullable, or (2) creating a separate user table

**Pydantic Models**:
- `UserResponse` — API response model (has `linuxdo_id: int` required)
- `UserUpdateRequest` — Admin update model (role, active, quotas)
- `AuthCallbackRequest` — OAuth callback (code + state)
- `TokenResponse` — JWT token response
- `RefreshTokenRequest` — Refresh token request

### JWT Token System (`api/app/auth.py`)

**Token Generation**:
- Algorithm: HS256
- Access token TTL: 60 minutes
- Refresh token TTL: 30 days
- Secret: `settings.jwt_secret` (from env var)

**Token Payload**:
```python
{"sub": str(user_id), "role": role, "exp": expire, "type": "access"|"refresh"}
```

**Token Pair Creation** (`create_token_pair`):
- Creates both access and refresh tokens
- Returns: `{access_token, refresh_token, token_type, expires_in}`

**Token Validation** (`decode_token`):
- Decodes JWT with secret
- Returns payload dict or None on error

### OAuth Flow (`api/app/auth.py`)

1. **State Generation** (`generate_state`): Random token stored in Redis with 10-min TTL
2. **Authorization URL** (`get_authorize_url`): Builds LinuxDo OAuth URL with `client_id`, `redirect_uri`, `state`, `scope=user`
3. **Code Exchange** (`exchange_code_for_token`): POST to LinuxDo token endpoint
4. **User Info Fetch** (`fetch_user_info`): GET from LinuxDo API with access token
5. **User Creation** (`get_or_create_user`): Looks up by `linuxdo_id`, creates if not exists

**Race Condition Handling**: In `get_or_create_user`, if `IntegrityError` on insert (another worker inserted same user), it retries the query.

### Auth Endpoints (`api/app/routers/auth.py`)

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/auth/login` | GET | Returns LinuxDo authorization URL |
| `/api/v1/auth/callback` | POST | Handles OAuth callback, sets cookies |
| `/api/v1/auth/me` | GET | Returns current user info |
| `/api/v1/auth/logout` | POST | Clears auth cookies |
| `/api/v1/auth/refresh` | POST | Refreshes access token |
| `/api/v1/auth/quota` | GET | Returns user quota info |

**Cookie Settings** (`_set_auth_cookies`):
- `access_token`: httponly, secure (configurable), samesite=lax, path=/, max_age=3600
- `refresh_token`: httponly, secure (configurable), samesite=lax, path=/, max_age=30 days

### Auth Dependencies (`api/app/dependencies.py`)

- `get_current_user`: Extracts user from JWT cookie, validates token type="access", checks user exists and active
- `get_current_user_optional`: Same but returns None instead of raising 401
- `require_admin`: Checks `user.role == "admin"`

### Frontend Auth (`web/src/`)

**AuthProvider** (`components/auth-provider.tsx`):
- React context provider
- Fetches `/auth/me` on mount to check auth state
- Provides `{user, isLoading, error, refetch, logout}`
- No direct token handling — relies on httponly cookies

**Login Page** (`app/login/page.tsx`):
- Single "使用 LinuxDo 登录" button
- Calls `GET /api/v1/auth/login?origin=...` to get authorization URL
- Redirects to LinuxDo OAuth page
- No username/password form

**Auth Utilities** (`lib/auth.ts`):
- `User` type: `{id, linuxdo_id, username, name, avatar_url, role, trust_level, active, ...}`
- `normalizeUser()`: Validates and normalizes API response
- `isAdmin()`: Checks role
- `getAvatarUrl()`: Builds avatar URL with size

**Auth Callback** (`app/auth/callback/route.ts`):
- Next.js route handler for OAuth callback
- Receives `code` and `state` from LinuxDo redirect
- Calls `POST /api/v1/auth/callback` with code+state
- Sets cookies and redirects to home

### Database (`api/app/database.py`)

- SQLite with WAL mode
- Path: `data/pdf2ppt.db` (configurable via `settings.sqlite_path`)
- Tables created on startup via `init_db()`

### Configuration (`api/app/config.py`)

Relevant auth settings:
- `linuxdo_client_id`: LinuxDo OAuth client ID
- `linuxdo_client_secret`: LinuxDo OAuth client secret
- `linuxdo_redirect_uri`: Default "http://localhost:3000/auth/callback"
- `jwt_secret`: JWT signing secret
- `cookie_secure`: Boolean, default True (set False for HTTP dev)
- `admin_usernames`: Comma-separated LinuxDo usernames for auto-admin

---

## Implications for Username/Password Login

### Required Changes

1. **User Model**:
   - Make `linuxdo_id` nullable (currently `nullable=False`)
   - Add `password_hash` field (String, nullable)
   - Add `email` field (String, nullable, unique)
   - Consider: `auth_method` field to distinguish OAuth vs password users

2. **Auth Module** (`api/app/auth.py`):
   - Add password hashing (bcrypt/argon2)
   - Add password verification function
   - Add `create_user_with_password()` function
   - Modify `get_or_create_user()` to handle both auth methods

3. **Auth Router** (`api/app/routers/auth.py`):
   - Add `POST /api/v1/auth/register` endpoint
   - Add `POST /api/v1/auth/login-password` endpoint
   - Keep OAuth endpoints for backward compatibility

4. **Frontend**:
   - Add login form with username/password fields
   - Add registration form
   - Update login page to offer both OAuth and password options

5. **Dependencies** (`api/app/dependencies.py`):
   - No changes needed — `get_current_user` already works with JWT regardless of auth method

### Key Considerations

- **Backward Compatibility**: Existing OAuth users must continue to work
- **Password Security**: Use bcrypt or argon2 for password hashing
- **Validation**: Email format, password strength requirements
- **Rate Limiting**: Protect login endpoint from brute force
- **Account Linking**: Decide if users can have both OAuth and password auth

---

## Files Found

| File Path | Description |
|---|---|
| `api/app/auth.py` | JWT creation, OAuth flow, user creation |
| `api/app/models/user.py` | User SQLAlchemy model, Pydantic schemas |
| `api/app/routers/auth.py` | Auth API endpoints |
| `api/app/dependencies.py` | Auth dependencies (get_current_user) |
| `api/app/config.py` | App settings including auth config |
| `api/app/database.py` | SQLite database setup |
| `web/src/components/auth-provider.tsx` | Frontend auth context provider |
| `web/src/app/login/page.tsx` | Login page (OAuth only) |
| `web/src/app/auth/callback/route.ts` | OAuth callback handler |
| `web/src/lib/auth.ts` | Frontend auth types and helpers |

## Caveats / Not Found

- No existing password hashing library in the project
- No rate limiting middleware currently implemented
- No email verification system exists
- The `linuxdo_id` field has a UNIQUE constraint that must be made nullable
