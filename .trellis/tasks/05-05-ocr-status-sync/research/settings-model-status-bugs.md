# Research: Settings Page & Model Status Sync Bug Analysis

- **Query**: Thoroughly review of settings page, model status sync, settings validation, cross-page state, model download, status badge, and preflight checks for subtle bugs
- **Scope**: internal
- **Date**: 2026-05-05

## Findings

### Files Reviewed

| File Path | Description |
|---|---|
| `web/src/app/settings/page.tsx` | Settings page UI (2506 lines) |
| `web/src/lib/settings.ts` | Settings types, defaults, validation, localStorage I/O (587 lines) |
| `web/src/hooks/use-settings.ts` | Settings hook with auto-save, deploy mode (177 lines) |
| `web/src/hooks/use-model-status.ts` | Model status fetch + effective status merge (134 lines) |
| `web/src/hooks/use-model-download.ts` | Model download with polling (198 lines) |
| `web/src/components/model-status-badge.tsx` | Status badge with details panel (479 lines) |
| `web/src/components/download-progress-button.tsx` | Download progress UI (92 lines) |
| `web/src/lib/run-config.ts` | Run config resolution, validation, job config builder (1030 lines) |
| `web/src/lib/layout-models.ts` | Layout model registry (100 lines) |
| `web/src/app/page.tsx` | Main page with preflight checks (1573 lines) |

---

## Bug 1: Settings Load Path Bypasses Validation in Self-Hosted Mode

**File**: `web/src/hooks/use-settings.ts`, lines 74-85

**What the bug is**: In self-hosted mode (`deployMode === "self"`), settings are loaded by directly merging the raw localStorage JSON with `defaultSettings`:
```ts
const parsed = JSON.parse(raw) as Partial<Settings>
if (mounted) setSettings({ ...defaultSettings, ...parsed })
```

This does **NOT** call `loadStoredSettings()` from `lib/settings.ts`, which performs:
- Legacy value migration (e.g., `"v2"` → proper engine mode, `"paddle_local"` → `"paddleocr"`)
- Enum validation for all union types (OcrProvider, OcrAiProvider, OcrAiChainMode, etc.)
- Numeric field normalization (ocrRenderDpi, concurrency, retries)
- Prompt override normalization (line ending fixes, length caps)

**What should happen**: All settings loads should go through `loadStoredSettings()` to ensure validation and migration.

**What actually happens**: Stale or invalid localStorage values (from older versions or manual edits) are loaded without validation. If a user has legacy values like `ocrProvider: "paddle"` or `ocrAiProvider: "invalid"`, they'll be used as-is, potentially causing runtime errors.

**Impact**: Medium. Only affects users who upgraded from older versions without clearing localStorage. The main page (`page.tsx:162`) calls `loadStoredSettings()` correctly, but the settings hook does not.

**Suggested fix**: Replace the self-hosted load in `use-settings.ts` with:
```ts
import { loadStoredSettings } from "@/lib/settings"
// ...
const loaded = loadStoredSettings()
if (mounted) setSettings(loaded)
```

---

## Bug 2: `clear()` Does Not Clear Server-Side Preferences in Public Mode

**File**: `web/src/hooks/use-settings.ts`, lines 159-163

**What the bug is**: The `clear` function always operates on localStorage regardless of deploy mode:
```ts
const clear = React.useCallback(() => {
  localStorage.removeItem(SETTINGS_STORAGE_KEY)
  setSettings(defaultSettings)
  setLastSavedAt(null)
}, [])
```

**What should happen**: In public mode, `clear()` should also send a `DELETE` or `PUT` to `/user/preferences` to clear server-side stored preferences.

**What actually happens**: In public mode, clicking "清空本地配置" resets the UI to defaults, but the server still has the old preferences. On next page load, the old preferences are re-fetched from the API, making the "clear" action effectively a no-op.

**Impact**: Medium. Users in public mode cannot actually reset their preferences.

---

## Bug 3: Auto-Save Silently Fails in Public Mode

**File**: `web/src/hooks/use-settings.ts`, lines 116-139

**What the bug is**: The auto-save effect for public mode has:
```ts
void apiFetch("/user/preferences", {
  method: "PUT",
  body: JSON.stringify({ preferences: prefs }),
}).catch(() => {
  // Silently fail - will retry on next change
})
```

**What should happen**: Failed saves should notify the user or at least set a flag so the UI can show "unsaved" state.

**What actually happens**: If the API call fails (network error, 500, etc.), the user sees `lastSavedAt` updated (line 136 runs regardless of API success), giving the false impression that settings were saved. The `setLastSavedAt(Date.now())` on line 136 runs in the `setTimeout` callback after the API call is *initiated* (not after it completes), so it always fires.

**Impact**: Low-Medium. The 500ms debounce timer's `setLastSavedAt` fires before the API response arrives, so the UI incorrectly shows "自动保存已开启" even when the save failed.

**Suggested fix**: Move `setLastSavedAt` into the `.then()` handler, and add error notification.

---

## Bug 4: No Cross-Tab/Cross-Page Settings Synchronization

**File**: `web/src/hooks/use-settings.ts` (no `storage` event listener found anywhere)

**What the bug is**: Neither the settings page nor the main page listens for `storage` events. Both pages load settings from localStorage on mount but never re-sync.

**What should happen**: When settings change on one page (e.g., settings page), other open pages (e.g., main page) should detect the change via `window.addEventListener("storage", ...)` and update their state.

**What actually happens**: If a user has both the main page and settings page open (common in multi-tab workflows), changes on the settings page are invisible to the main page until a full reload. The main page's `settingsSnapshot` remains stale.

**Impact**: Low. Users typically navigate between pages rather than having them open simultaneously. But for power users with multiple tabs, this can cause jobs to be submitted with old settings.

---

## Bug 5: `useEffectiveModelStatus` Missing `ocrBaiduAppId` Dependency

**File**: `web/src/hooks/use-model-status.ts`, line 133

**What the bug is**: The `useMemo` dependency array is:
```ts
[backend, settings.ocrAiApiKey, settings.ocrAiBaseUrl, settings.ocrBaiduApiKey, settings.ocrBaiduSecretKey, settings.mineruApiToken]
```

The Baidu Doc check at lines 107-119 only checks `ocrBaiduApiKey` and `ocrBaiduSecretKey`, not `ocrBaiduAppId`. While `ocrBaiduAppId` is marked as optional in the code, if the backend requires it in some configurations, the effective status won't update when only the App ID changes.

**Impact**: Very low. The App ID is documented as optional and the backend likely doesn't require it.

---

## Bug 6: `useEffectiveModelStatus` AIOCR Ready Check Requires Non-Empty Base URL

**File**: `web/src/hooks/use-model-status.ts`, lines 92-103

**What the bug is**: The AIOCR readiness check requires both `ocrAiApiKey` AND `ocrAiBaseUrl` to be non-empty:
```ts
const hasKey = settings.ocrAiApiKey.trim().length > 0
const hasUrl = settings.ocrAiBaseUrl.trim().length > 0
ready: hasKey && hasUrl,
```

However, the default `ocrAiBaseUrl` is `"https://api.siliconflow.cn/v1"` (set in `settings.ts:186`), and `loadStoredSettings()` ensures it's populated for siliconflow providers. But if a user selects a different provider (e.g., `"deepseek"`) and clears the base URL field, the effective status will show AIOCR as not ready even though the backend might use a default URL.

**What should happen**: The frontend should either: (a) not require `ocrAiBaseUrl` for readiness (let the backend handle defaults), or (b) apply the same default URL logic as the backend.

**What actually happens**: Users who clear the OCR base URL (expecting the backend to use a default) see AIOCR as "not ready" in the status badge, even though the backend would successfully process requests.

**Impact**: Low. Most users either use siliconflow (which has a default URL) or explicitly set their own URL.

---

## Bug 7: Preflight Check Silently Passes When Provider Not in Status Response

**File**: `web/src/app/page.tsx`, lines 279-282

**What the bug is**: The preflight filter is:
```ts
const notReady = requiredProviders.filter((p) => {
  const bucket = p.kind === "local" ? modelStatus.local : modelStatus.remote
  return bucket[p.key] && !bucket[p.key].ready
})
```

The condition `bucket[p.key] && !bucket[p.key].ready` returns `false` when `bucket[p.key]` is `undefined` (provider not in response). This means if the backend doesn't include a required provider in its status response, the preflight check silently passes.

**What should happen**: If a required provider is missing from the status response entirely, it should be treated as "unknown/not ready" and warn the user.

**What actually happens**: A missing provider is treated as "ready" (or rather, "not not-ready"), potentially allowing jobs to be submitted when the backend hasn't confirmed the provider is available.

**Impact**: Low-Medium. This depends on whether the backend always includes all providers in its response. If the backend omits providers it doesn't know about, jobs could fail at runtime.

**Suggested fix**:
```ts
const notReady = requiredProviders.filter((p) => {
  const bucket = p.kind === "local" ? modelStatus.local : modelStatus.remote
  const status = bucket[p.key]
  return !status || !status.ready
})
```

---

## Bug 8: Download Hook Polling Creates Unnecessary Re-Renders

**File**: `web/src/hooks/use-model-download.ts`, lines 78-103

**What the bug is**: The polling effect depends on `downloads` (the state object):
```ts
React.useEffect(() => {
  const hasActiveDownloads = Object.values(downloads).some(d => d.status === "downloading")
  if (hasActiveDownloads && !pollTimerRef.current) { ... }
  else if (!hasActiveDownloads && pollTimerRef.current) { ... }
}, [downloads, fetchStatus])
```

Every time `fetchStatus` updates `downloads` via `setDownloads`, this effect re-runs. While the `if` conditions prevent duplicate interval creation, the effect itself runs on every poll cycle (every 1 second), performing `Object.values(downloads).some(...)` unnecessarily.

Additionally, `fetchStatus` is a `useCallback` with `[]` deps, so it's stable — but the `downloads` dependency causes the effect to re-run on every poll update.

**Impact**: Very low. Performance overhead is minimal, but the pattern is fragile.

---

## Bug 9: No Validation of String-to-Number Settings Before Job Submission

**File**: `web/src/lib/run-config.ts`, lines 657-806 (buildJobConfig)

**What the bug is**: Several settings are stored as strings (e.g., `ocrRenderDpi: "200"`, `ocrTesseractMinConfidence: "35"`) and converted to numbers at job submission time. While `loadStoredSettings()` validates these on load, the settings page allows free-form text input in `<Input type="number">` fields.

If a user types an invalid value (e.g., empty string after clearing, or a non-numeric value via paste), the `toFinitePositiveIntOrNull` helper returns `null`, and the field is silently omitted from the job config. This is generally safe (backend uses defaults), but the user has no indication that their input was ignored.

**What should happen**: The settings page should validate numeric inputs and show inline error messages for invalid values.

**What actually happens**: Invalid numeric inputs are silently ignored at job submission time. The user thinks they set a value, but it was discarded.

**Impact**: Low. The backend applies sensible defaults, and the settings page uses `type="number"` inputs which prevent most invalid input.

---

## Bug 10: `getOverallStatus` Returns "partial" When Some Providers Ready

**File**: `web/src/components/model-status-badge.tsx`, lines 80-93

**What the bug is**:
```ts
function getOverallStatus(...): "ready" | "partial" | "unknown" {
  // ...
  const readyCount = all.filter((s) => s.ready).length
  if (readyCount === all.length) return "ready"
  if (readyCount === 0) return "partial"  // ← should be "none" or similar
  return "partial"
}
```

When `readyCount === 0`, the function returns `"partial"` instead of something like `"none"`. This means the badge shows "部分就绪" (partial ready) with an amber dot when *nothing* is ready, which is misleading. "部分就绪" implies some things are ready, but actually nothing is.

**What should happen**: When zero providers are ready, the label should be something like "未就绪" (not ready) rather than "部分就绪" (partially ready).

**What actually happens**: The badge shows "部分就绪" with amber color even when no providers are ready at all.

**Impact**: Very low. Cosmetic issue only.

---

## Bug 11: Model Status Not Refetched After Settings Change

**File**: `web/src/app/settings/page.tsx`, line 331; `web/src/app/page.tsx`, line 234

**What the bug is**: Both pages call `useModelStatus()` which fetches status once on mount. Neither page refetches model status when settings change (e.g., after the user configures an API key).

The settings page does call `refetchModelStatus()` after a download completes (line 333), but not after settings are saved.

**What should happen**: After settings are saved (especially API keys), the model status should be refetched to reflect the new configuration.

**What actually happens**: After configuring API keys, the status badge continues showing the old status until the user manually navigates away and back, or triggers a download.

**Impact**: Low. The `useEffectiveModelStatus` hook on the main page compensates for this by overriding backend status based on local settings. But the settings page doesn't use `useEffectiveModelStatus`, so it shows stale backend status.

---

## Summary of Findings

| # | Bug | Severity | File | Lines |
|---|---|---|---|---|
| 1 | Settings load bypasses validation in self-hosted mode | Medium | use-settings.ts | 74-85 |
| 2 | `clear()` doesn't clear server-side prefs in public mode | Medium | use-settings.ts | 159-163 |
| 3 | Auto-save shows success even when API call fails | Low-Medium | use-settings.ts | 116-139 |
| 4 | No cross-tab settings synchronization | Low | use-settings.ts | (missing) |
| 5 | Missing `ocrBaiduAppId` in effective status deps | Very low | use-model-status.ts | 133 |
| 6 | AIOCR ready check requires non-empty base URL | Low | use-model-status.ts | 92-103 |
| 7 | Preflight passes when provider missing from response | Low-Medium | page.tsx | 279-282 |
| 8 | Download polling effect re-runs on every update | Very low | use-model-download.ts | 78-103 |
| 9 | No validation of numeric settings before submission | Low | run-config.ts | 657-806 |
| 10 | "部分就绪" shown when zero providers ready | Very low | model-status-badge.tsx | 80-93 |
| 11 | Model status not refetched after settings change | Low | settings/page.tsx | 331 |

## Caveats / Not Found

- No race conditions found in the download hook's start/cancel flow (the polling interval is correctly managed with refs).
- The `safeParseSettings` function correctly handles malformed JSON.
- The settings migration logic in `loadStoredSettings` is comprehensive for known legacy values.
- No XSS vulnerabilities found in settings rendering (all values are properly escaped by React).
- The `useModelDownload` hook correctly handles the mount/unmount lifecycle with `mountedRef`.
