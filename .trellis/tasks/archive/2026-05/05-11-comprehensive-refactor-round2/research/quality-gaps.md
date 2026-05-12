# Research: Quality Gaps Audit

- **Query**: Audit quality gaps across six dimensions — accessibility, error handling, spec/docs, config drift, security, test coverage
- **Scope**: Full codebase (internal)
- **Date**: 2026-05-11

## 1. Accessibility

### 1.1 `<main>` Landmarks

| Page File | Has `<main>`? | Notes |
|---|---|---|
| `web/src/app/page.tsx` | ✅ | `<main className="mt-2">` wraps all three stages; also has `<header>` and `sr-only` status region |
| `web/src/app/login/page.tsx` | ✅ | `<main>` wraps loading, auto-login, and login card states |
| `web/src/app/jobs/page.tsx` | ✅ | `<main className="mt-4">` wraps filter tabs, job cards, batch ops |
| `web/src/app/settings/page.tsx` | ❌ | No `<main>` — root is `<div className="min-h-dvh bg-background">` |
| `web/src/app/setup/page.tsx` | ❌ | No `<main>` — root is `<div className="min-h-dvh bg-background">` |
| `web/src/app/tracking/page.tsx` | ❌ | No `<main>` — root is `<div className="min-h-dvh bg-background">` |
| `web/src/app/admin/` pages | ❌ | No `<main>` — consistent pattern of `<div>` root |
| `web/src/app/register/page.tsx` | ❌ | No `<main>` |
| `web/src/app/manage/page.tsx` | ❌ | No `<main>` |

**Finding**: Only 3 of 13 page files have `<main>` landmarks. The rest use generic `<div>` for the page wrapper.

### 1.2 Heading Hierarchy

| Page | H1 | H2 | Notes |
|---|---|---|---|
| `page.tsx` | ❌ | ❌ | No headings at all; uses `<p className="sr-only">` for status, not structure |
| `upload-stage.tsx` | ✅ | ❌ | `<h1 className="font-serif...">PDF2PPT</h1>` — exists in component, renders inside main |
| `login/page.tsx` | ❌ | ❌ | `<CardTitle>用户登录</CardTitle>` — semantic but not an HTML heading |
| `jobs/page.tsx` | ❌ | ❌ | No headings; title "任务记录" is in a `<div>`, not an `<h1>` |
| `settings/page.tsx` | ✅ | ❌ | `<h1>处理设置</h1>` — good, but no sub-headings for sections |
| `setup/page.tsx` | ❌ | ❌ | Step indicator uses `<div>` not headings |
| `tracking/page.tsx` | ❌ | ❌ | No heading structure |

**Finding**: Only 2 of 13 pages have an `<h1>`. Most pages lack any heading hierarchy.

### 1.3 Alt Text & Accessible Names

| Component | Has alt text / aria? | Notes |
|---|---|---|
| `pdf-canvas-preview.tsx:282` | ✅ | `alt="上传预览"` on image |
| `user-menu.tsx:99` | ✅ | `alt={user.username}` on avatar, `aria-expanded`, `aria-haspopup`, `aria-label="用户菜单"` |
| `preview-stage.tsx:213-242` | ✅ | `aria-label` on prev/next/current-preview buttons |
| `workbench-nav.tsx:93` | ✅ | `<nav aria-label="工作台导航">`, `aria-current="page"` on active links |
| `hover-hint.tsx:23` | ✅ | `aria-label={`${label}: ${text}`}` |
| `settings-shared.tsx:43` | ✅ | `aria-hidden` on collapsed sections |
| `ui/select.tsx:12` | ✅ | `aria-invalid:border-destructive` class binding |
| `ui/input.tsx:13` | ✅ | `aria-invalid:border-destructive` class binding |
| **Icon-only buttons everywhere** | ❌ | `ArrowLeftIcon`, `DownloadIcon`, `TrashIcon`, `XIcon`, `CheckIcon`, etc. — never have `aria-label` |
| **Job card checkboxes in jobs/page.tsx** | ❌ | `<input type="checkbox">` has no associated `<label>`, no aria-label |
| **Dropzone in upload-stage.tsx** | ❌ | `<div {...getRootProps()}>` — no role or accessible description |

**Finding**: Some components have ARIA attributes (workbench-nav, user-menu), but icon-only buttons, checkboxes, and interactive controls lack accessible names across the board.

### 1.4 Missing Features
- No skip-to-content link on any page
- No focus management for route changes or dialog opens
- No `aria-live` regions outside homepage's sr-only status paragraph
- PDF preview component has no accessible alternative

---

## 2. Error Handling Consistency

### 2.1 Backend Routers (Python/FastAPI)

All 8 routers follow the same pattern:
```python
try:
    # business logic
except AppException:
    raise  # Re-raise known application exceptions
except Exception as e:
    logger.exception(...)
    raise AppException(
        code=ErrorCode.INTERNAL_ERROR,
        message="Human-readable message",
        details={"error": str(e)},
        status_code=500,
    )
```

**Assessment**: ✅ Consistent. Every router uses `AppException` with structured error codes. No raw `Exception` leaks to clients.

Minor inconsistencies:
- `models.py:519` — `logger.warning` (lowercase w, but generally uses `.warning()`) — uses `exc_info=True` which is inconsistent with `logger.exception()` pattern used elsewhere
- `jobs.py` occasionally catches `Exception` without logging (e.g., in `_sync_rq_cancel_state` cleanup paths)

### 2.2 Frontend Hooks (TypeScript)

| Hook | Pattern | Inconsistency |
|---|---|---|
| `use-settings.ts` | `try { ... } catch { // Silently fail }` — 3 silent failures | ⚠️ Heavily silent — deploy-mode, settings load, auto-save all swallow errors |
| `use-model-download.ts` | `catch { // Silent fail — polling will retry }` | ⚠️ Polling errors silently swallowed; download start/cancel uses toast |
| `use-model-status.ts` | `catch (e) { setError(normalizeFetchError(e, ...)) }` | ✅ Errors surfaced via state |
| `use-sse-job-tracking.ts` | `catch { // JSON parse error — ignore }` + `catch { // Best-effort }` | ⚠️ Both catch blocks silent |
| **page.tsx** | Conditional: `if (!silent) setActionError(...)` | ⚠️ Silent mode suppresses errors from polling; cancel errors just `toast.error()` |

### 2.3 Error Pattern Classification

| Pattern | Count | Risk |
|---|---|---|
| Surfaced to user (toast/state/UI) | ~65% | ✅ |
| Logged to console/logger | ~15% | ✅ |
| Silently swallowed | ~20% | ⚠️ Medium |

**Key concern**: The "silent failure in polling" pattern (used in `use-settings.ts`, `use-model-download.ts`, `use-sse-job-tracking.ts`) can hide systemic issues for hours. No telemetry or error counters exist to surface these.

### 2.4 Error Response Bodies

| Backend Router | Returns structured errors? |
|---|---|
| `jobs.py` | ✅ `AppException` with `code`, `message`, `details` |
| `models.py` | ✅ Same |
| `auth.py` | ✅ Same |
| `admin.py` | ✅ Same |
| `config.py` | ✅ Same |
| `setup.py` | ✅ Same |
| `runtime_config.py` | ✅ Same |

Frontend `api.ts` handles response errors with `readResponseErrorMessage()` which tries JSON body, falls back to text, then fallback string. Consistent pattern. ✅

---

## 3. Spec / Documentation

### 3.1 Spec Files Status

| Spec File | Status | Content |
|---|---|---|
| `.trellis/spec/backend/index.md` | ✅ Filled | Architecture summary, guidelines index (1 entry) |
| `.trellis/spec/backend/auth-pattern.md` | ✅ Filled | Comprehensive — signatures, contracts, error matrix, examples |
| `.trellis/spec/frontend/index.md` | ❌ Placeholder | All 6 guideline files listed as "To fill" |
| `.trellis/spec/frontend/directory-structure.md` | ❌ Empty | "(To be filled by the team)" |
| `.trellis/spec/frontend/component-guidelines.md` | ❌ Empty | Not read — assumed same |
| `.trellis/spec/frontend/hook-guidelines.md` | ❌ Empty | Not read — assumed same |
| `.trellis/spec/frontend/state-management.md` | ❌ Empty | Not read — assumed same |
| `.trellis/spec/frontend/quality-guidelines.md` | ❌ Empty | Not read — assumed same |
| `.trellis/spec/frontend/type-safety.md` | ❌ Empty | Not read — assumed same |
| `.trellis/spec/guides/` | ❌ Empty | No files found — cross-package thinking guides directory is empty |

**Finding**: 1 of 10 spec files has real content. Frontend guidelines are completely empty. The `guides/` directory mentioned in AGENTS.md is empty.

### 3.2 Inline Documentation

- `web/src/lib/constants.ts` — well-documented with JSDoc comments ✅
- `web/src/hooks/use-model-download.ts` — JSDoc on function ✅
- `web/src/hooks/use-model-status.ts` — JSDoc on both exported hooks ✅
- `web/src/hooks/use-settings.ts` — no JSDoc, no inline comments ⚠️
- `web/src/hooks/use-sse-job-tracking.ts` — no JSDoc ⚠️
- `api/app/routers/jobs.py` — extensive docstrings and inline comments ✅
- `api/app/routers/models.py` — docstrings and section separators ✅
- `api/app/routers/runtime_config.py` — full docstrings on endpoints ✅
- No `TODO`, `FIXME`, `HACK`, or `XXX` markers found in routers or web/src — clean ✅

### 3.3 Outdated Documentation

- `Makefile:120-121`: `# Public repo keeps runtime code only.` → says "No repository tests" but `api/tests/` has 20 real test files
- `web/package.json:11`: `"test:unit": "node -e \"console.log('No frontend unit tests are kept in this public repo.')\""` — stub, no real tests

---

## 4. Configuration Drift

### 4.1 Frontend vs Backend Defaults

| Parameter | `web/src/lib/settings.ts` (FE) | `api/app/config.py` (BE) | Drift? |
|---|---|---|---|
| OCR Render DPI | `"200"` (string) | `200` (int) | ❌ No — same value |
| Scanned Render DPI | — | `200` (int) | N/A |
| Job Timeout | — | `3600` (seconds) | ✅ Frontend has matching `DEFAULT_RUNTIME_CONFIG.JOB_TIMEOUT_SECONDS = 3600` |
| OCR Page Timeout | — | `300` (seconds) | ✅ Frontend has matching `DEFAULT_RUNTIME_CONFIG.OCR_PAGE_TIMEOUT_S = 300` |
| OCR Total Timeout | — | `3600` (seconds) | ✅ Matching |
| Max Consecutive Timeouts | — | `2` | ✅ Matching |
| Max File Size | `MAX_FILE_SIZE_BYTES = 100MB` | `max_file_mb: int = 100` | ✅ Matching |
| OCR AI Page Concurrency Max | `8` | `8` | ✅ Matching |
| OCR AI Block Concurrency Max | `8` | `8` | ✅ Matching |
| OCR AI RPM Max | `2000` | `2000` | ✅ Matching |
| OCR AI TPM Max | `2_000_000` | `2_000_000` | ✅ Matching |
| OCR AI Page Concurrency Default | `1` | `1` | ✅ Matching |
| OCR AI Block Concurrency Default | `1` | `1` | ✅ Matching |
| OCR AI RPM Default | `1` | `1` | ✅ Matching |
| OCR AI TPM Default | `1000` | `1000` | ✅ Matching |
| OCR AI Max Retries Default | `0` | `0` | ✅ Matching |
| OCR AI Retry Backoff Base | `8.0` | `8.0` | ✅ Matching |
| OCR AI Rate Limited Min Delay | `2.0` | `2.0` | ✅ Matching |
| OCR Image Region Timeout | `12` | `12` | ✅ Matching |
| PaddleOCR-VL Predict Timeout | `180.0` | `180.0` | ✅ Matching |

### 4.2 .env.example vs config.py Drift

| Parameter | `.env.example` | `config.py` default | Drift? |
|---|---|---|---|
| COOKIE_SECURE | `false` | `True` | ⚠️ **YES** — .env.example says `false` (HTTP dev), config.py defaults to `True`. Devs who copy `.env.example` get insecure behavior by design, but production users who forget the env var get `True` (secure). This is a documentation clarity issue, not a functional bug. |
| JWT_SECRET | `""` (empty, comment says "required") | `""` (empty string) | ✅ Consistent — both are empty placeholder |
| MAX_FILE_MB | `100` | `100` | ✅ Consistent |
| REDIS_URL | `redis://redis:6379/0` | `redis://redis:6379/0` | ✅ Consistent |
| JOB_ROOT_DIR | `/app/data/jobs` | `data/jobs` | ⚠️ Different — .env.example is Docker path, config default is relative |
| SQLITE_PATH | `data/pdf2ppt.db` | `data/pdf2ppt.db` | ✅ Consistent |

**Key drift**: `COOKIE_SECURE` is the only actual discrepancy, and it's by design (dev vs prod).

### 4.3 Hardcoded Values in Code

- `api/app/config.py:16`: `_ADMIN_PLACEHOLDER_PASSWORD = "admin12345678"` — hardcoded fallback
- `web/src/lib/api.ts:12-13`: `DEFAULT_FALLBACK_ORIGIN = "http://localhost:8000"`, `DEFAULT_FALLBACK_PORT = "8000"` — reasonable dev defaults
- `web/src/lib/settings.ts:95`: `SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"` — hardcoded 3rd-party URL (by design — this is the official endpoint)

---

## 5. Security

### 5.1 Hardcoded Secrets & Weak Defaults

| Location | Value | Risk | Notes |
|---|---|---|---|
| `api/app/config.py:16` | `_ADMIN_PLACEHOLDER_PASSWORD = "admin12345678"` | 🔴 High | Default admin password for self-use mode auto-login. Code comment warns to override via `ADMIN_DEFAULT_PASSWORD` env var |
| `.env.example:21` | `WEB_ACCESS_PASSWORD=123456` | 🔴 High | Default web access password. Docs say "change quickly" |
| `.env.example:89` | `JWT_SECRET=` (empty) | 🟡 Medium | Empty JWT secret — documented as "required, production change" |
| `.env.example:87` | `LINUXDO_REDIRECT_URI=http://localhost:3000/auth/callback` | 🟢 Low | Development redirect |

### 5.2 Sensitive Key Handling (Positive)

- API keys explicitly nullified in RQ job kwargs (`api_key=None`, `mineru_api_token=None`, etc.) at `jobs.py:1092,1099-1113` ✅
- Sensitive keys stored separately via `redis_service.store_job_secrets()` ✅
- Admin GET responses mask sensitive values with `••••••••` (both env vars and site settings) ✅
- `api_bearer_token` validation properly handled (not exposed in GET) ✅

### 5.3 Input Validation

| Area | Validation | Notes |
|---|---|---|
| Job creation (`jobs.py`) | ✅ | Pydantic models, file type checking, file size streaming check, disk space check, user quota check |
| User creation (`admin.py`) | ✅ | Password `min_length=8`, username constraints |
| Auth endpoints (`auth.py`) | ✅ | State validation, token decoding |
| Model download (`models.py`) | ✅ | Admin-only (require_admin), model ID validation |
| Frontend file upload | ✅ | `MAX_FILE_SIZE_MB=100` frontend check + file type via dropzone accept |

### 5.4 Rate Limiting

- `api/app/main.py:135-147`: IP-based rate limiting — `check_rate_limit(client_ip, 60, 60)` → 60 requests per 60 seconds per client IP ✅
- Frontend polling intervals are well-distributed (2s, 4s) — won't trigger rate limits ✅
- No account-level brute-force protection on login endpoints ⚠️

### 5.5 Authentication & Authorization

- Admin endpoints: all use `require_admin` dependency ✅
- Job listing: scoped to `user_id` when authenticated ✅
- Job cancellation: checks ownership via `redis_service` ✅
- Auto-login: only in `deploy_mode=self` ✅
- JWT cookies: httponly, samesite=lax, secure (configurable) ✅
- But: No CSRF token protection on state-changing endpoints — relies on samesite cookies ⚠️
- `get_me` endpoint always returns user data for valid JWT — expected behavior ✅

---

## 6. Test Coverage

### 6.1 Backend Tests

**20 real test files exist in `api/tests/`:**

```
test_generator_perf_guards.py
test_scanned_page_polygon_erase.py
test_worker_chain_scoping.py
test_ocr_stage_perf_guards.py
test_ocr_wrap_overrides.py
test_ocr_runtime_routing.py
test_paddle_prewarm_route_integration.py
test_ocr_stage_progress.py
test_job_cleanup.py
test_ocr_capability_routing.py
test_models_router_capabilities.py
test_jobs_upload_route.py
test_mineru_adapter.py
test_job_options_chain_guards.py
test_ocr_manager_route_plumbing.py
test_ai_ocr_local_layout_route.py
test_baidu_doc_adapter.py
test_api_auth_policy.py
test_api_bearer_middleware.py
test_artifact_export_policies.py
test_ai_ocr_prompts.py
test_ai_ocr_client_routes.py
test_ai_ocr_check_route_integration.py
```

**BUT**: `Makefile:120-121` claims "No repository tests are kept in this public branch." — this is **incorrect** and outdated documentation.

### 6.2 Frontend Tests

- `web/package.json:11`: `"test:unit"` is a stub — no actual tests
- No Jest, Vitest, or Testing Library in devDependencies
- **Zero frontend test coverage**

### 6.3 Test Infrastructure

| Aspect | Backend | Frontend |
|---|---|---|
| Test files | 20 real test files | 0 (stub only) |
| Test runner | Python unittest/pytest compatible | None configured |
| Makefile target | `test` → stub (incorrect) | `lint-web` only |
| CI/CD | Not visible in codebase | Not visible |

### 6.4 Coverage Gaps (Backend)

While 20 test files exist, the following areas appear untested based on file names:
- Auth endpoints (`/auth/login`, `/auth/callback`, `/auth/register`) — no test file
- Admin user management (CRUD operations) — no test file
- Setup wizard — no test file
- Runtime config endpoints — no test file
- Model download/cancel/delete — no test file
- Job SSE events — no test file
- Job cancel via RQ — no test file

---

## Summary Matrix

| Dimension | Status | Key Issues |
|---|---|---|
| **Accessibility** | ⚠️ Needs Work | 10/13 pages missing `<main>`, 11/13 missing `<h1>`, icon buttons lack labels |
| **Error Handling** | ⚠️ Needs Work | ~20% of catch blocks silent; polling errors swallowed across 4 hooks |
| **Spec/Docs** | 🔴 Major Gap | 7/8 frontend spec files empty; guides directory empty; Makefile stale |
| **Config Drift** | ✅ Good | 1 minor drift (COOKIE_SECURE), intentional; otherwise perfectly aligned |
| **Security** | ✅ Good | Sensitive keys handled well; rate limiting present; weak defaults flagged |
| **Test Coverage** | ⚠️ Partial | 20 backend tests exist (good) but frontend has zero; Makefile claims none |

---

## Caveats / Not Found

1. **Frontend spec files**: Only `index.md` and `directory-structure.md` were read. The other 4 frontend spec files (`component-guidelines.md`, `hook-guidelines.md`, `state-management.md`, `quality-guidelines.md`, `type-safety.md`) were not opened but are listed as "To fill" in the index. Assumed empty.
2. **Test execution**: Tests were not run — only file existence was checked. Some test files may be broken or stale.
3. **Security audit depth**: Not a full pentest — no SAST, no dependency scan, no runtime testing. Only static code review.
4. **Accessibility**: No automated a11y tooling (axe-core, Lighthouse) was run — audit is code-review only.
5. **Admin/register/manage page files**: Only partially read; assumed same patterns as other pages for `<main>`/heading analysis.
