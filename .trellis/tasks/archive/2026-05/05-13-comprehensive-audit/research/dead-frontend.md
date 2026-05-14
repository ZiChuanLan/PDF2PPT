# Research: Frontend Dead Code Audit

- **Query**: Find dead/never-referenced TypeScript/TSX files, components, functions, settings fields, and unlinked pages
- **Scope**: internal (frontend)
- **Date**: 2026-05-13

## Findings

### 1. Components — All Used ✓

Every component under `web/src/components/` is imported by at least one page or other component:

| Component | File | Imported By |
|---|---|---|
| AuthProvider, useAuth | components/auth-provider.tsx | layout.tsx, page.tsx, workbench-nav, user-menu, login, register, setup, manage, admin |
| ThemeProvider | components/theme-provider.tsx | layout.tsx |
| UploadSessionProvider, useUploadSession | components/upload-session-provider.tsx | layout.tsx, page.tsx |
| WorkbenchNav | components/workbench-nav.tsx | layout.tsx |
| UserMenu | components/user-menu.tsx | workbench-nav.tsx |
| PresetPicker | components/preset-picker.tsx | home/upload-stage.tsx |
| PresetManager | components/preset-manager.tsx | presets/page.tsx |
| DeployModeComparison | components/deploy-mode-comparison.tsx | setup/page.tsx |
| PasswordStrengthMeter | components/password-strength-meter.tsx | setup/page.tsx |
| DownloadProgressButton | components/download-progress-button.tsx | ocr-strategy-section, model-status-badge, setup/page.tsx |
| ModelStatusBadge | components/model-status-badge.tsx | home/quick-config-panel.tsx |
| PdfCanvasPreview | components/pdf-canvas-preview.tsx | home/preview-stage.tsx |
| JobDebugPanel | components/job-debug-panel.tsx | home/converting-stage, tracking/page.tsx |
| All settings/ components | components/settings/*.tsx | settings/page.tsx |
| All home/ components | components/home/*.tsx | page.tsx, preview-stage.tsx |
| All ui/ components | components/ui/*.tsx | Used throughout |

**Result: No dead components found.**

---

### 2. Hooks — All Used ✓

| Hook | File | Imported By |
|---|---|---|
| useSettings | hooks/use-settings.ts | settings/page.tsx |
| useModelDownload | hooks/use-model-download.ts | ocr-strategy-section, model-status-badge, setup/page.tsx, download-progress-button (type) |
| useModelStatus, useEffectiveModelStatus | hooks/use-model-status.ts | page.tsx, quick-config-panel, preview-stage, model-status-badge |
| useSSEJobTracking | hooks/use-sse-job-tracking.ts | page.tsx |

**Result: No dead hooks found.**

---

### 3. Lib Files — Some Unused Exports Found

#### 3a. `lib/run-config.ts` — Several unused exported symbols

These exports are **defined but never imported** by any other file:

| Export | Kind | Notes |
|---|---|---|
| `OCR_PROVIDER_LABELS` | `const Record` | Only used internally in run-config.ts (via `resolveOcrSettingsState`) |
| `PARSE_ENGINE_OPTIONS` | `const array` | Not imported anywhere outside run-config.ts. Has a local `PARSE_ENGINE_OPTIONS` shadow in `parsing-method-section.tsx:17` |
| `getOcrConfigSourceLabel` | `function` | Not imported anywhere |
| `deriveSettingsUiState` | `const alias` | Alias for `resolveOcrSettingsState`; not imported anywhere |
| `getRunParseEngineLabel` | `function` | Not imported anywhere |
| `getRunModelLabel` | `function` | Not imported anywhere |
| `createJobFormData` | `function` (deprecated) | Marked `@deprecated` at line 816. Not imported anywhere; replaced by `buildJobConfig` |
| `applyParseEngineMode` | `function` | Not imported outside run-config.ts |
| `resolveAutoOcrAiBlockConcurrency` | `function` | Only used internally within run-config.ts |
| `normalizeVisibleOcrProvider` | `function` | Only used internally within run-config.ts |
| `getMainProviderConfig` | `function` | Only used internally within run-config.ts |

**Dead-code (can be made private or removed):** `OCR_PROVIDER_LABELS`, `PARSE_ENGINE_OPTIONS`, `getOcrConfigSourceLabel`, `deriveSettingsUiState`, `getRunParseEngineLabel`, `getRunModelLabel`, `createJobFormData`, `applyParseEngineMode`.

#### 3b. `lib/settings.ts` — Internal-only exports  

These are exported but **only consumed internally** by other functions in the same file:

| Export | Notes |
|---|---|
| `safeParseSettings` | Only called by `loadStoredSettings` (same file) |
| `loadPresetStorage` | Only called by `getAllPresets`, `getDefaultPreset`, etc. (same file) |
| `savePresetStorage` | Only called by preset mutation functions (same file) |
| `getPresetById` | Only called by `getDefaultPreset` (same file) |

These do not need to be exported. Making them non-exported would clarify the public API.

#### 3c. `lib/job-status.ts` — Unused export

| Export | Notes |
|---|---|
| `JOB_STAGE_COMPACT_LABELS` (line 79) | Defined as `Record<string, string>` but never imported anywhere. Not even used internally. |

#### 3d. `lib/layout-models.ts` — Unused exports

| Export | Notes |
|---|---|
| `DEFAULT_LAYOUT_MODEL` (line 71) | Only used internally within same file |
| `LAYOUT_MODEL_IDS` (line 73) | Never imported anywhere, not even internally |
| `normalizeLayoutModelId` (line 78) | Never imported anywhere, not used internally either |

#### 3e. `lib/auth.ts` — Unused type

| Export | Notes |
|---|---|
| `QuotaInfo` type (line 26) | Defined but never imported in any file. Not used. |

#### 3f. `hooks/use-settings.ts` — Internal-only exports

| Export | Notes |
|---|---|
| `SENSITIVE_KEYS` set (line 15) | Only used internally by `useSettings` |
| `DeployMode` type (line 12) | Only used internally (single source-of-truth for the type) |

#### 3g. `lib/constants.ts` — Unused constants

These constants are exported but **never imported** by any other file:

| Export | Value | Notes |
|---|---|---|
| `MODEL_STATUS_POLL_INTERVAL_MS` | 4000 | Not imported anywhere |
| `SETTINGS_AUTO_SAVE_DEBOUNCE_MS` | 3000 | Not imported anywhere (useSettings uses its own 500ms debounce) |
| `MAX_FILE_SIZE_BYTES` | 100MB | Not imported anywhere (page.tsx hardcodes 100MB inline) |
| `MAX_FILE_SIZE_LABEL` | "100MB" | Not imported anywhere |
| `JOBS_PAGE_LIMIT` | 100 | Not imported anywhere (jobs/page.tsx hardcodes `limit=50`) |
| `TOAST_DURATION_MS` | 4000 | Not imported anywhere |
| `AUTH_REFRESH_CHECK_MS` | 5 min | Not imported anywhere |

**Used constants (OK):** `HOME_JOB_LIMIT`, `TRACKING_JOB_LIMIT`, `JOB_LIST_POLL_INTERVAL_MS`, `JOB_POLL_INTERVAL_MS`, `MODEL_DOWNLOAD_POLL_INTERVAL_MS`, `SSE_RECONNECT_BASE_MS`, `ADMIN_USERS_LIMIT`, `ADMIN_INVITES_LIMIT`, `API_REQUEST_TIMEOUT_MS`.

---

### 4. UI Components (shadcn copies) — All Used ✓

All 10 UI components in `web/src/components/ui/` are imported by the project's own code:

- badge.tsx, button.tsx, card.tsx, checkbox.tsx, hover-hint.tsx, input.tsx, progress.tsx, select.tsx, sonner.tsx, tabs.tsx

**No unused shadcn copies.**

---

### 5. Settings Fields with No UI Rendering

The `Settings` type in `lib/settings.ts` has 58 fields. The settings page renders all but these 4:

| Setting Field | Type | UI Status | Used By |
|---|---|---|---|
| `preferredMainProvider` | `MainProvider` | No direct UI toggle | Set indirectly when `provider` changes in `OutputQualitySection`; consumed by `run-config.ts` |
| `ocrPaddleVlDocparserMaxSidePx` | `string` | No UI input | Only consumed by `run-config.ts` → `buildJobConfig` for PaddleOCR-VL doc parser |
| `ocrAiPageConcurrencyAuto` | `boolean` | No UI toggle | Controls auto/manual page concurrency; only set internally in settings migration code; consumed by `run-config.ts` |
| `ocrAiBlockConcurrency` | `string` | No UI input | Only consumed by `run-config.ts` → `buildJobConfig` |

These 4 fields are **functional gaps** rather than dead code — they are consumed by the backend job config builder but have no corresponding input in the settings page UI. They can only be set via localStorage editing or preset application.

---

### 6. Pages / Routes — All Linked ✓

All page routes are reachable from navigation or through application flow:

| Route | Entry Point |
|---|---|
| `/` (home) | Default route, workbench-nav |
| `/settings` | workbench-nav, home page links |
| `/jobs` | workbench-nav |
| `/tracking` | workbench-nav, jobs page links |
| `/presets` | preset-picker card "管理预设" link on home page upload stage |
| `/setup` | Auto-redirect from login when setup needed |
| `/login` | middleware redirect, user-menu |
| `/register` | login page link (public mode only) |
| `/manage` | user-menu + workbench-nav (public mode non-admin users) |
| `/admin` | user-menu + workbench-nav (admin users) |
| `/admin/site-settings` | admin page links |
| `/admin/env` | admin page links |
| `/admin/invites` | admin page links |
| `/admin/users/[id]` | admin user list detail links |
| `/auth/callback/route` | OAuth callback (next.js route handler, not a page) |

**Result: No orphaned pages found.**

---

## Summary

### No Dead Files
All 65 `.ts`/`.tsx` files are imported by at least one other file.

### Dead / Unused Lib Exports (7 lib files)
1. **`lib/run-config.ts`** — 8 unused exports: `OCR_PROVIDER_LABELS`, `PARSE_ENGINE_OPTIONS`, `getOcrConfigSourceLabel`, `deriveSettingsUiState`, `getRunParseEngineLabel`, `getRunModelLabel`, `createJobFormData` (deprecated), `applyParseEngineMode`
2. **`lib/constants.ts`** — 7 unused constants: `MODEL_STATUS_POLL_INTERVAL_MS`, `SETTINGS_AUTO_SAVE_DEBOUNCE_MS`, `MAX_FILE_SIZE_BYTES`, `MAX_FILE_SIZE_LABEL`, `JOBS_PAGE_LIMIT`, `TOAST_DURATION_MS`, `AUTH_REFRESH_CHECK_MS`
3. **`lib/job-status.ts`** — 1 unused export: `JOB_STAGE_COMPACT_LABELS`
4. **`lib/layout-models.ts`** — 2 unused exports: `LAYOUT_MODEL_IDS`, `normalizeLayoutModelId` (plus `DEFAULT_LAYOUT_MODEL` is internal-only)
5. **`lib/auth.ts`** — 1 unused type: `QuotaInfo`
6. **`lib/settings.ts`** — 4 exports can be demoted to private: `safeParseSettings`, `loadPresetStorage`, `savePresetStorage`, `getPresetById`
7. **`hooks/use-settings.ts`** — `SENSITIVE_KEYS` and `DeployMode` are internal-only

### Missing UI for Settings Fields (4 fields)
- `preferredMainProvider`, `ocrPaddleVlDocparserMaxSidePx`, `ocrAiPageConcurrencyAuto`, `ocrAiBlockConcurrency`

## Caveats / Not Found
- `ocrAiPageConcurrencyAuto` and `ocrAiBlockConcurrency` may have been intentionally excluded from the UI (server-side tuning only). This report identifies them as missing UI, not necessarily dead.
- `SENSITIVE_KEYS` in `use-settings.ts` is file-private in practice but exported; demoting it to non-exported would be safe.
- `createJobFormData` is explicitly marked `@deprecated` — can be removed if v1 API is no longer needed.
