# Research: Frontend API Audit

- **Query**: Audit ALL frontend API calls — URL, method, location, request/response, error handling
- **Scope**: internal
- **Date**: 2026-05-11

## Findings

### Architecture Overview

- **Centralized fetch**: `web/src/lib/api.ts` provides `apiFetch()` which proxies through `/api/v1/...` (Next.js rewrite → `${INTERNAL_API_ORIGIN}/api/:path*`). Timeout via `AbortController` at 30s.
- **Proxy config**: `web/next.config.mjs` rewrites `/api/:path*` → `${INTERNAL_API_ORIGIN}/api/:path*` (default `http://api:8000`). Also rewrites `/health` → `${INTERNAL_API_ORIGIN}/health`.
- **Middleware**: `web/src/middleware.ts` enforces auth cookie for all `/api/*` paths except `/api/v1/auth/`, `/api/v1/setup/`, `/api/v1/config/`. Injects `API_BEARER_TOKEN` env var into proxied requests if user has auth cookie but no `Authorization` header.
- **Direct cross-origin probing**: `api.ts` `probeApiOrigin()` calls `${origin}/health` directly (not via `/api/v1/` proxy) to test candidates. This is used for auto-detection of the backend API origin.
- **SSE**: `createJobEventSource()` in `api.ts` creates `EventSource("/api/v1/jobs/${jobId}/events")`.

---

### ALL API Calls

#### 1. `GET /health` (direct cross-origin probe)

| Field | Detail |
|---|---|
| **URL** | `${candidateOrigin}/health` |
| **Method** | GET |
| **File:line** | `web/src/lib/api.ts:177` — `probeApiOrigin()` |
| **Body/Params** | None |
| **Success** | Returns `true` if response JSON has `{status: "ok"}` or any 2xx |
| **Error** | Returns `false` on fetch failure, non-2xx, or timeout (1200ms) |
| **Classification** | ✅ Working — clean error handling (returns boolean, caller loops candidates) |

---

#### 2. `GET /api/v1/auth/me`

| Field | Detail |
|---|---|
| **URL** | `/auth/me` (via `apiFetch` → `/api/v1/auth/me`) |
| **Method** | GET |
| **File:line** | `web/src/components/auth-provider.tsx:28` — `fetchUser()` |
| **Body/Params** | None |
| **Success** | Parses JSON, calls `normalizeUser()`, stores in context |
| **Error** | On 401: retries once with 500ms delay. On second 401: sets `user=null` silently. Other errors: silent fail → `user=null` |
| **Classification** | ✅ Working — retry logic for 401, graceful degradation |

---

#### 3. `POST /api/v1/auth/logout`

| Field | Detail |
|---|---|
| **URL** | `/auth/logout` |
| **Method** | POST |
| **File:line** | `web/src/components/auth-provider.tsx:56` — `logout()`; also `web/src/app/admin/site-settings/page.tsx:93` |
| **Body/Params** | None |
| **Success** | Sets `localStorage userLoggedOut=true`, clears user, redirects to `/login` |
| **Error** | Silent catch — ignores logout errors |
| **Classification** | ⚠️ Missing error handling — errors are swallowed silently (acceptable for logout, but user gets no feedback if logout fails server-side) |

---

#### 4. `POST /api/v1/auth/auto-login`

| Field | Detail |
|---|---|
| **URL** | `/auth/auto-login` |
| **Method** | POST |
| **File:line** | `web/src/app/login/page.tsx:110` — auto-login effect |
| **Body/Params** | None |
| **Success** | Refetches user, redirects to `next` param or `/` |
| **Error** | Silent catch — shows normal login form |
| **Classification** | ✅ Working — graceful fallback to login form |

---

#### 5. `POST /api/v1/auth/login-password`

| Field | Detail |
|---|---|
| **URL** | `/auth/login-password` |
| **Method** | POST |
| **File:line** | `web/src/app/login/page.tsx:155` — `handlePasswordLogin()` |
| **Body/Params** | `{username: string, password: string}` |
| **Success** | Shows toast "登录成功", removes logout flag, refetches user, redirects to `/` |
| **Error** | Displays error message from `readResponseErrorMessage()` inline in form |
| **Classification** | ✅ Working — proper error extraction and display |

---

#### 6. `GET /api/v1/auth/login?origin=<encoded>`

| Field | Detail |
|---|---|
| **URL** | `/auth/login?origin=<encoded>` |
| **Method** | GET |
| **File:line** | `web/src/app/login/page.tsx:186` — `handleLinuxdoLogin()` |
| **Body/Params** | Query param: `origin` (encoded `window.location.origin`) |
| **Success** | Redirects to `data.authorize_url` (external OAuth) |
| **Error** | Toast error "登录失败", resets redirecting state |
| **Classification** | ✅ Working — but note: error handling for invalid `authorize_url` is present |

---

#### 7. `POST /api/v1/auth/register`

| Field | Detail |
|---|---|
| **URL** | `/auth/register` |
| **Method** | POST |
| **File:line** | `web/src/app/register/page.tsx:73` — `handleRegister()` |
| **Body/Params** | `{invite_code: string, username: string, password: string}` |
| **Success** | Toast "注册成功，已自动登录", refetches user, redirects to `/` |
| **Error** | Displays error inline in form via `readResponseErrorMessage()` |
| **Classification** | ✅ Working — proper validation before submit, proper error display |

---

#### 8. `POST /api/v1/auth/change-password`

| Field | Detail |
|---|---|
| **URL** | `/auth/change-password` |
| **Method** | POST |
| **File:line** | `web/src/app/manage/page.tsx:60` — `handleChangePassword()` |
| **Body/Params** | `{old_password: string, new_password: string}` |
| **Success** | Toast "密码修改成功", clears inputs |
| **Error** | Displays error inline, falls back to `errorData?.message` |
| **Classification** | ✅ Working |

---

#### 9. `GET /api/v1/config/deploy-mode`

| Field | Detail |
|---|---|
| **URL** | `/config/deploy-mode` |
| **Method** | GET |
| **File:line** | `web/src/hooks/use-settings.ts:55`, `web/src/app/login/page.tsx:72` (×2), `web/src/components/user-menu.tsx:22`, `web/src/components/workbench-nav.tsx:55` |
| **Body/Params** | None |
| **Success** | Reads `data.mode` |
| **Error** | Falls back to `"self"` silently |
| **Classification** | ✅ Working — called from 5 locations with consistent fallback. **Note**: potential redundancy — login page calls it twice (once in deploy-mode effect, once in auto-login effect). |

---

#### 10. `GET /api/v1/config/runtime`

| Field | Detail |
|---|---|
| **URL** | `/config/runtime` |
| **Method** | GET |
| **File:line** | `web/src/app/settings/page.tsx:383` — `RuntimeConfigSection` |
| **Body/Params** | None |
| **Success** | Sets `config` state from `data.config` |
| **Error** | Sets error state via `normalizeFetchError()` |
| **Classification** | ✅ Working |

---

#### 11. `PUT /api/v1/config/runtime`

| Field | Detail |
|---|---|
| **URL** | `/config/runtime` |
| **Method** | PUT |
| **File:line** | `web/src/app/settings/page.tsx:404` — `handleSave()` |
| **Body/Params** | `RuntimeConfig` object (all fields) |
| **Success** | Toast "运行时配置已保存。重启服务后生效。" |
| **Error** | Toast + inline error display |
| **Classification** | ✅ Working |

---

#### 12. `GET /api/v1/setup/status`

| Field | Detail |
|---|---|
| **URL** | `/setup/status` |
| **Method** | GET |
| **File:line** | `web/src/app/login/page.tsx:95`, `web/src/app/setup/page.tsx:73` |
| **Body/Params** | None |
| **Success** | Checks `data.needs_setup` |
| **Error** | Login page: silent catch. Setup page: assumes `needs_setup=true` on error |
| **Classification** | ✅ Working |

---

#### 13. `POST /api/v1/setup/complete`

| Field | Detail |
|---|---|
| **URL** | `/setup/complete` |
| **Method** | POST |
| **File:line** | `web/src/app/setup/page.tsx:100` — `handleCreateAdmin()` |
| **Body/Params** | `{deploy_mode: string, username: string, password: string}` |
| **Success** | Refetches user, fetches model status |
| **Error** | Sets error state, steps back to form (step 2) |
| **Classification** | ✅ Working |

---

#### 14. `GET /api/v1/user/preferences`

| Field | Detail |
|---|---|
| **URL** | `/user/preferences` |
| **Method** | GET |
| **File:line** | `web/src/hooks/use-settings.ts:82` — public mode settings load |
| **Body/Params** | None |
| **Success** | Merges `prefData.preferences` with defaults |
| **Error** | Falls back to defaults silently |
| **Classification** | ✅ Working |

---

#### 15. `PUT /api/v1/user/preferences`

| Field | Detail |
|---|---|
| **URL** | `/user/preferences` |
| **Method** | PUT |
| **File:line** | `web/src/hooks/use-settings.ts:123` (auto-save), `use-settings.ts:148` (manual save) |
| **Body/Params** | `{preferences: Record<string, string>}` (non-sensitive keys only) |
| **Success** | Sets `lastSavedAt` timestamp |
| **Error** | Silent catch (auto-save retries on next change; manual save silently ignores) |
| **Classification** | ⚠️ Missing error handling — manual `save()` call at line 148 catches errors silently. User may think settings were saved when they weren't. |

---

#### 16. `GET /api/v1/models/status`

| Field | Detail |
|---|---|
| **URL** | `/models/status` |
| **Method** | GET |
| **File:line** | `web/src/hooks/use-model-status.ts:38` — `refetch()`; `web/src/app/setup/page.tsx:58,121`; `web/src/app/settings/page.tsx:718` (via `useModelStatus()` hook) |
| **Body/Params** | None |
| **Success** | Sets `data` state as `ModelStatusResponse` |
| **Error** | Sets `error` state via `normalizeFetchError()` |
| **Classification** | ✅ Working — used by `useModelStatus` hook and directly in setup page |

---

#### 17. `GET /api/v1/models/download/status`

| Field | Detail |
|---|---|
| **URL** | `/models/download/status` |
| **Method** | GET |
| **File:line** | `web/src/hooks/use-model-download.ts:50` — `fetchStatus()` |
| **Body/Params** | None |
| **Success** | Updates `downloads` state, fires callbacks for completed/failed/cancelled |
| **Error** | Silent catch — polling will retry |
| **Classification** | ✅ Working — acceptable for polling pattern |

---

#### 18. `POST /api/v1/models/download`

| Field | Detail |
|---|---|
| **URL** | `/models/download` |
| **Method** | POST |
| **File:line** | `web/src/hooks/use-model-download.ts:117` — `startDownload()` |
| **Body/Params** | `{model: string}` |
| **Success** | Returns `true`, immediately fetches status |
| **Error** | Toast error via `normalizeFetchError()`, returns `false` |
| **Classification** | ✅ Working |

---

#### 19. `POST /api/v1/models/download/cancel`

| Field | Detail |
|---|---|
| **URL** | `/models/download/cancel` |
| **Method** | POST |
| **File:line** | `web/src/hooks/use-model-download.ts:141` — `cancelDownload()` |
| **Body/Params** | `{model: string}` |
| **Success** | Returns `true` |
| **Error** | Toast error, returns `false` |
| **Classification** | ✅ Working |

---

#### 20. `POST /api/v1/models/delete`

| Field | Detail |
|---|---|
| **URL** | `/models/delete` |
| **Method** | POST |
| **File:line** | `web/src/components/model-status-badge.tsx:172` — `handleDelete()` (inside `ProviderRow`) |
| **Body/Params** | `{model: string}` |
| **Success** | Toast success with server message, calls `onStatusChange()` callback |
| **Error** | Toast error via `normalizeFetchError()` |
| **Classification** | ✅ Working — confirmation dialog before delete |

---

#### 21. `POST /api/v1/models`

| Field | Detail |
|---|---|
| **URL** | `/models` |
| **Method** | POST |
| **File:line** | `web/src/app/settings/page.tsx:1065` — OCR model list fetch |
| **Body/Params** | `{provider: string, api_key: string, capability: string, base_url?: string}` + `AbortController` signal |
| **Success** | Sets `ocrModelOptions` from `body.models` (filtered to strings) |
| **Error** | Sets `ocrModelError` via `normalizeFetchError()`, clears options |
| **Classification** | ✅ Working — debounced (400ms), aborts on dependency change |

---

#### 22. `GET /api/v1/jobs?limit=N`

| Field | Detail |
|---|---|
| **URL** | `/jobs?limit=<N>` |
| **Method** | GET |
| **File:line** | `web/src/app/page.tsx:183` (limit=50), `web/src/app/jobs/page.tsx:76` (limit=50), `web/src/app/tracking/page.tsx:200` (limit=60) |
| **Body/Params** | Query: `limit` |
| **Success** | Normalizes response via `normalizeJobListResponse()`, updates job state |
| **Error** | Silent on `silent=true`, otherwise sets error state via `normalizeFetchError()` |
| **Classification** | ✅ Working — multiple consumers with consistent pattern |

---

#### 23. `POST /api/v1/jobs/v2`

| Field | Detail |
|---|---|
| **URL** | `/jobs/v2` |
| **Method** | POST |
| **File:line** | `web/src/app/page.tsx:339` — `submitOne()` inside `handleConvertAll()` |
| **Body/Params** | `FormData` with `file` (File) and `config` (JSON string from `buildJobConfig()`) |
| **Success** | Extracts `job_id` from response, updates fileJobs state, increments successCount |
| **Error** | Calls `normalizeFetchError()`, sets fileJobs error, increments failCount |
| **Classification** | ✅ Working — proper error extraction, batch submit with `Promise.all` |

---

#### 24. `GET /api/v1/jobs/:jobId`

| Field | Detail |
|---|---|
| **URL** | `/jobs/<jobId>` |
| **Method** | GET |
| **File:line** | `web/src/app/page.tsx:200` — `fetchJobStatus()`; `web/src/app/tracking/page.tsx:265` — `fetchTrackedJobStatus()` |
| **Body/Params** | None |
| **Success** | Normalizes via `normalizeJobStatusResponse()` |
| **Error** | Throws `JobStatusFetchError` with statusCode and errorCode |
| **Classification** | ✅ Working — structured error type with HTTP status and error code |

---

#### 25. `DELETE /api/v1/jobs/:jobId`

| Field | Detail |
|---|---|
| **URL** | `/jobs/<jobId>` |
| **Method** | DELETE |
| **File:line** | `web/src/app/jobs/page.tsx:138` — `handleDelete()`; `web/src/app/tracking/page.tsx:300` — `handleDeleteJobById()` |
| **Body/Params** | None |
| **Success** | Toast "任务已删除", refetches job list |
| **Error** | Toast error. Jobs page: `normalizeFetchError()`. Tracking page: parses body for message. |
| **Classification** | ✅ Working — confirmation dialog before delete |

---

#### 26. `POST /api/v1/jobs/:jobId/cancel`

| Field | Detail |
|---|---|
| **URL** | `/jobs/<jobId>/cancel` |
| **Method** | POST |
| **File:line** | `web/src/app/page.tsx:394` — `handleCancelJob()`; `web/src/app/jobs/page.tsx:185` — `handleCancel()` |
| **Body/Params** | None |
| **Success** | Toast "已发送取消请求" / "已发送取消请求", refetches |
| **Error** | Toast error |
| **Classification** | ✅ Working — jobs page checks `response.ok` and extracts message, home page just uses generic fallback |

---

#### 27. `GET /api/v1/jobs/:jobId/download`

| Field | Detail |
|---|---|
| **URL** | `/jobs/<jobId>/download` |
| **Method** | GET |
| **File:line** | `web/src/app/page.tsx:403` — `handleDownload()`; `web/src/app/jobs/page.tsx:198` — `handleDownload()`; `web/src/app/tracking/page.tsx:277` — `handleDownloadByJobId()` |
| **Body/Params** | None |
| **Success** | Creates blob URL, triggers download via `<a>` click |
| **Error** | Extracts error from JSON body or HTTP status, throws Error |
| **Classification** | ⚠️ Duplicated — same download logic exists in 3 files (page.tsx, jobs/page.tsx, tracking/page.tsx). Could be extracted to a shared hook or utility. |

---

#### 28. `GET /api/v1/jobs/:jobId/artifacts`

| Field | Detail |
|---|---|
| **URL** | `/jobs/<jobId>/artifacts` |
| **Method** | GET |
| **File:line** | `web/src/app/tracking/page.tsx:226` — `fetchJobArtifacts()` |
| **Body/Params** | None |
| **Success** | Sets `trackedArtifacts` state with normalized artifact pages |
| **Error** | Sets `trackedArtifactsError` via `normalizeFetchError()`, clears artifacts |
| **Classification** | ✅ Working |

---

#### 29. `GET /api/v1/jobs/:jobId/events` (SSE)

| Field | Detail |
|---|---|
| **URL** | `/jobs/<jobId>/events` |
| **Method** | SSE (EventSource) |
| **File:line** | `web/src/lib/api.ts:293` — `createJobEventSource()`; consumed by `web/src/hooks/use-sse-job-tracking.ts:46` — `setupSseForJob()` |
| **Body/Params** | None |
| **Success** | `onmessage`: parses JSON event data, updates fileJobs state with status/stage/progress/message/error. On terminal status: fetches full job status. Closes connection. |
| **Error** | `onerror`: closes connection, sets `pollError: "连接中断，正在重试..."`, exponential backoff reconnect (1s base, capped at 30s). JSON parse error: swallowed. |
| **Classification** | ✅ Working — robust SSE handling with reconnect, backoff, cleanup on unmount, and terminal state handling |

---

#### 30. `POST /api/v1/jobs/ocr/local/check`

| Field | Detail |
|---|---|
| **URL** | `/jobs/ocr/local/check` |
| **Method** | POST |
| **File:line** | `web/src/app/settings/page.tsx:1184` — `requestLocalOcrCheck()` |
| **Body/Params** | `{provider: string, language: string}` |
| **Success** | Returns `LocalOcrCheckResponse` |
| **Error** | Extracts message from body, throws Error |
| **Classification** | ✅ Working — called in parallel for both tesseract and paddle (runtime + models = 4 total checks) |

---

#### 31. `POST /api/v1/jobs/ocr/ai/check`

| Field | Detail |
|---|---|
| **URL** | `/jobs/ocr/ai/check` |
| **Method** | POST |
| **File:line** | `web/src/app/settings/page.tsx:1334` — `onCheckAiOcrModel()` |
| **Body/Params** | Complex payload: `provider`, `api_key`, `model`, `base_url`, `ocr_ai_chain_mode`, `ocr_ai_layout_model`, `ocr_ai_prompt_preset`, optional prompt overrides, concurrency settings, rate limit settings |
| **Success** | Sets `aiOcrCheck` state, toast "OCR 能力验证通过" or "未通过" |
| **Error** | Sets `aiOcrCheckError` via `normalizeFetchError()`, toast error |
| **Classification** | ✅ Working — pre-validates that required fields are filled before submitting |

---

#### 32. `GET /api/v1/admin/users?limit=N`

| Field | Detail |
|---|---|
| **URL** | `/admin/users?limit=<N>` |
| **Method** | GET |
| **File:line** | `web/src/app/admin/page.tsx:61` — `fetchAdminData()` |
| **Body/Params** | Query: `limit` (100) |
| **Success** | Normalizes users via `normalizeUser()`, filters to valid entries |
| **Error** | Sets error via `normalizeFetchError()` |
| **Classification** | ✅ Working |

---

#### 33. `GET /api/v1/admin/users/:id`

| Field | Detail |
|---|---|
| **URL** | `/admin/users/<id>` |
| **Method** | GET |
| **File:line** | `web/src/app/admin/users/[id]/page.tsx:57` — `fetchUser()` |
| **Body/Params** | None |
| **Success** | Normalizes user, populates form fields |
| **Error** | 404 → "用户不存在", other → `normalizeFetchError()` |
| **Classification** | ✅ Working — handles 404 specially |

---

#### 34. `PUT /api/v1/admin/users/:id`

| Field | Detail |
|---|---|
| **URL** | `/admin/users/<id>` |
| **Method** | PUT |
| **File:line** | `web/src/app/admin/users/[id]/page.tsx:114` — `handleSave()` |
| **Body/Params** | `{daily_task_limit?, max_file_size_mb?, concurrent_task_limit?, active?, role?}` |
| **Success** | Updates target user state, toast "用户信息已更新" |
| **Error** | Toast error |
| **Classification** | ✅ Working |

---

#### 35. `POST /api/v1/admin/users/:id/reset-password`

| Field | Detail |
|---|---|
| **URL** | `/admin/users/<id>/reset-password` |
| **Method** | POST |
| **File:line** | `web/src/app/admin/page.tsx:189` — `handleResetPassword()` |
| **Body/Params** | `{new_password: string}` |
| **Success** | Toast "用户 xxx 的密码已重置", closes dialog |
| **Error** | Toast error via `normalizeFetchError()` |
| **Classification** | ✅ Working |

---

#### 36. `POST /api/v1/admin/users/batch-delete`

| Field | Detail |
|---|---|
| **URL** | `/admin/users/batch-delete` |
| **Method** | POST |
| **File:line** | `web/src/app/admin/page.tsx:123` — `handleBatchDelete()` |
| **Body/Params** | `{user_ids: number[]}` |
| **Success** | Toast "已禁用 N 个用户（跳过 M 个）", refetches |
| **Error** | Toast error |
| **Classification** | ✅ Working |

---

#### 37. `POST /api/v1/admin/users`

| Field | Detail |
|---|---|
| **URL** | `/admin/users` |
| **Method** | POST |
| **File:line** | `web/src/app/admin/page.tsx:150` — `handleAddUser()` |
| **Body/Params** | `{username: string, password: string, role: "user"|"admin"}` |
| **Success** | Toast "用户 xxx 创建成功", resets form, refetches |
| **Error** | Toast error via `normalizeFetchError()` |
| **Classification** | ✅ Working |

---

#### 38. `GET /api/v1/admin/stats`

| Field | Detail |
|---|---|
| **URL** | `/admin/stats` |
| **Method** | GET |
| **File:line** | `web/src/app/admin/page.tsx:62` — `fetchAdminData()` (parallel with users fetch) |
| **Body/Params** | None |
| **Success** | Sets `stats` state |
| **Error** | Falls through to `normalizeFetchError()` (shared error with users fetch) |
| **Classification** | ⚠️ Shared error state — if either users or stats fails, both show the same error message. Only users fetch failure is caught specifically; stats failure silently sets error to users fetch message if it also failed. |

---

#### 39. `GET /api/v1/admin/invites?limit=N`

| Field | Detail |
|---|---|
| **URL** | `/admin/invites?limit=<N>` |
| **Method** | GET |
| **File:line** | `web/src/app/admin/invites/page.tsx:54` — `fetchInvites()` |
| **Body/Params** | Query: `limit` (100) |
| **Success** | Sets `invites` state from `data.invites` |
| **Error** | Sets error via `normalizeFetchError()` |
| **Classification** | ✅ Working |

---

#### 40. `POST /api/v1/admin/invites`

| Field | Detail |
|---|---|
| **URL** | `/admin/invites` |
| **Method** | POST |
| **File:line** | `web/src/app/admin/invites/page.tsx:85` — `handleGenerate()` |
| **Body/Params** | `{expires_in_days?: number}` |
| **Success** | Sets `lastGeneratedCode`, toasts "邀请码已生成", refetches |
| **Error** | Toast error via `normalizeFetchError()` |
| **Classification** | ✅ Working |

---

#### 41. `GET /api/v1/admin/env`

| Field | Detail |
|---|---|
| **URL** | `/admin/env` |
| **Method** | GET |
| **File:line** | `web/src/app/admin/env/page.tsx:59` — `fetchEnv()` |
| **Body/Params** | None |
| **Success** | Sets `envVars` and `rawContent` from `data.vars` and `data.raw` |
| **Error** | Sets error via `normalizeFetchError()` |
| **Classification** | ✅ Working |

---

#### 42. `PUT /api/v1/admin/env`

| Field | Detail |
|---|---|
| **URL** | `/admin/env` |
| **Method** | PUT |
| **File:line** | `web/src/app/admin/env/page.tsx:123` — `handleSave()` |
| **Body/Params** | `{vars: Record<string, string>}` (key-value pairs from table or parsed raw) |
| **Success** | Updates `envVars`/`rawContent` from response, resets edited state |
| **Error** | Toast error via `normalizeFetchError()` |
| **Classification** | ✅ Working |

---

#### 43. `GET /api/v1/admin/site-settings`

| Field | Detail |
|---|---|
| **URL** | `/admin/site-settings` |
| **Method** | GET |
| **File:line** | `web/src/app/admin/site-settings/page.tsx:57` |
| **Body/Params** | None |
| **Success** | Sets `settings` and `originalDeployMode` |
| **Error** | Sets error via `normalizeFetchError()` |
| **Classification** | ✅ Working |

---

#### 44. `PUT /api/v1/admin/site-settings`

| Field | Detail |
|---|---|
| **URL** | `/admin/site-settings` |
| **Method** | PUT |
| **File:line** | `web/src/app/admin/site-settings/page.tsx:79` — `handleSave()` |
| **Body/Params** | `{settings: Record<string, string | null>}` |
| **Success** | If deploy mode changed: logs out and redirects. Otherwise: toast "配置已保存" |
| **Error** | Toast error via `normalizeFetchError()` |
| **Classification** | ✅ Working — special handling for deploy mode change trigger |

---

### Summary Statistics

| Classification | Count |
|---|---|
| ✅ Working (clean error handling) | 40 |
| ⚠️ Missing/weak error handling | 3 |
| ❌ Suspicious | 0 |
| 🔗 Unknown (needs backend context) | 0 |
| **Total** | **44** |

---

### Issues Found

#### 1. ⚠️ Duplicated Download Logic (3 locations)
- `web/src/app/page.tsx:403` — `handleDownload()`
- `web/src/app/jobs/page.tsx:198` — `handleDownload()`
- `web/src/app/tracking/page.tsx:277` — `handleDownloadByJobId()`
Same pattern: fetch blob → createObjectURL → `<a>` click → revoke. Should be a shared utility.

#### 2. ⚠️ `save()` in use-settings silently ignores API errors
- `web/src/hooks/use-settings.ts:148-153` — manual `save()` catches errors silently
- User may think settings were saved to server when they weren't

#### 3. ⚠️ Admin stats error handling shares a single error state with users fetch
- `web/src/app/admin/page.tsx:60-62` — `Promise.all` with shared catch
- If stats fetch fails, the error message from users fetch (or generic) is shown

#### 4. Info: `apiFetch` always uses same-origin proxy, `probeApiOrigin` uses direct cross-origin
- `apiFetch()` → `/api/v1/...` (Next.js rewrite proxy)
- `probeApiOrigin()` → `${origin}/health` (direct fetch — used only for origin discovery)
- No issues — this is by design

#### 5. Info: All API calls go through `/api/v1/...` proxy
- Verified: no frontend code directly calls any external API
- The sync origin `apiFetch` approach is consistently used throughout

#### 6. Info: Middleware allows 3 paths without auth
- `/api/v1/auth/*`, `/api/v1/setup/*`, `/api/v1/config/*` — bypass auth cookie check
- `/health` — bypass auth for Next.js rewrite
- All other `/api/*` paths require auth cookie or `API_BEARER_TOKEN`

---

### Code Patterns

**Centralized error handling**:
```typescript
// api.ts — shared error formatters used across codebase:
readResponseErrorMessage(response, fallback) // → extracts server message
normalizeFetchError(error, fallback)           // → handles AbortError, TypeError, etc.
```

**Typical API call pattern**:
```typescript
try {
  const response = await apiFetch("/path")
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.message || "fallback message")
  }
  const data = await response.json()
  // use data
} catch (e) {
  // handle via normalizeFetchError() or set error state
}
```

**SSE pattern** (use-sse-job-tracking.ts):
- `createJobEventSource(jobId)` from api.ts → `new EventSource("/api/v1/jobs/${jobId}/events")`
- onmessage: parse JSON → update state
- onerror: close → exponential backoff reconnect
- Terminal state: close EventSource, clear timers
- Cleanup: close all EventSources on unmount

---

### Related Specs

- `.trellis/spec/frontend/index.md` — frontend guidelines
- `.trellis/spec/backend/index.md` — backend guidelines

### Caveats / Not Found

- All API calls are thoroughly documented above
- No hardcoded external URLs found (all go through `/api/v1/` proxy)
- Upload-session-provider.tsx and theme-provider.tsx do NOT make API calls (pure state management)
- Job-debug-panel.tsx does NOT make API calls (pure display component)
- Pdf-canvas-preview.tsx does NOT make API calls (renders object URLs)
