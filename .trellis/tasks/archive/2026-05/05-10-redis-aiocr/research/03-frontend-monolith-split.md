# Research: Frontend Monolith Component Split

- **Query**: Deep-dive `web/src/app/page.tsx` (1681 lines) and `web/src/app/settings/page.tsx` (2888 lines) for monolithic refactoring opportunities
- **Scope**: internal
- **Date**: 2026-05-10

## Findings

---

## 1. `web/src/app/page.tsx` (1681 lines)

### 1.1 Complete Hook/Callback/Effect Inventory

#### useState (14 local state variables)

| Variable | Line | Type | Purpose |
|---|---|---|---|
| `settingsSnapshot` | 126 | `Settings` | Local settings snapshot for quick config |
| `fileJobs` | 140 | `FileJobState[]` | Per-file job submission + status tracking |
| `queueSize` | 141 | `number` | Global queue size from job list |
| `isJobIdHydrated` | 142 | `boolean` | Hydration guard (init true, never changed) |
| `actionError` | 143 | `string \| null` | Validation/submit error message |
| `previewPageInput` | 144 | `string` | Current preview page number input |
| `previewPageCount` | 145 | `number` | Total page count of preview file |
| `previewFileIndex` | 146 | `number` | Index of currently previewed file |
| `usePageRange` | 157 | `boolean` | Whether page range is enabled |
| `retainProcessArtifacts` | 160 | `boolean` | Retain intermediate processing images |
| `showHomeLog` | 161 | `boolean` | Show/hide debug log panel |
| `preflightWarning` | 257 | `string \| null` | Model-not-ready warning message |
| `preflightAcknowledged` | 258 | `boolean` | User acknowledged preflight warning |
| `filePreviewUrl` | 637 | `string` | Object URL for PDF/image preview |

#### useRef

| Variable | Line | Type | Purpose |
|---|---|---|---|
| `lastTerminalToastRef` | 164 | `{ jobId, status }` | Prevent duplicate toasts on repeated terminal renders |

#### useCallback (12 callbacks)

| Callback | Lines | Dep Count | Purpose |
|---|---|---|---|
| `refreshSettingsSnapshot` | 172-174 | 0 | Reload settings from localStorage |
| `updateSettingsSnapshot` | 176-187 | 0 | Functional updater + persist to localStorage |
| `fetchJobs` | 189-205 | 0 | GET /jobs list + queue size |
| `fetchJobStatus` | 207-224 | 0 | GET /jobs/:id single status + normalization |
| `onDrop` | 226-243 | 1 | File drop handler: size check + addFiles + reset state |
| `handleConvertAll` | 269-398 | 10 | **GIANT (130 lines)**: validate, preflight, build FormData, parallel submit, toast |
| `handleCancelJob` | 400-408 | 1 | POST /jobs/:id/cancel |
| `handleDownload` | 410-425 | 0 | GET /jobs/:id/download → blob → download |
| `handleDownloadAll` | 427-438 | 2 | Promise.allSettled over all completed jobs |
| `handleResetAll` | 440-451 | 3 | Reset all state (clearUpload + 7 setState calls) |
| `handlePreviewPageCommit` | 651-658 | 1 | Clamp + commit preview page on blur/Enter |
| `handlePreviewPageCountChange` | 659-664 | 0 | Update from PdfCanvasPreview callback |

#### useEffect (5 effects)

| Effect | Lines | Deps | Purpose |
|---|---|---|---|
| Clamp previewFileIndex | 149-155 | `[fileCount, previewFileIndex]` | Clamp index when files added/removed |
| **SSE subscription** | **475-591** | `[activeJobIdsKey, fetchJobStatus]` | **116 lines**: per-job SSE with exponential backoff reconnect |
| Toast on terminal | 594-609 | `[fileJobs, completedCount]` | Toast when all jobs reach terminal state |
| Init + poll + focus | 611-629 | `[fetchJobs, refreshSettingsSnapshot]` | Initial load, focus refresh, interval poll |
| File preview URL | 638-648 | `[currentPreviewFile]` | CreateObjectURL / revokeObjectURL |

#### useMemo (3 memos)

| Memo | Lines | Deps | Purpose |
|---|---|---|---|
| `downloadedLayoutModels` | 260-268 | `[modelStatus]` | Set of layout model IDs with ready=true |
| `activeJobIdsKey` | 463-472 | `[fileJobs]` | Comma-joined active job IDs → stable string for SSE dep |
| `stageSteps` | 681-704 | `[fileJobs]` | Stepped progress: parsing/ocr/generating/done |

### 1.2 Logical Feature Groups

| Feature | Key States/Handlers | Logic Lines | UI Lines |
|---|---|---|---|
| **File Upload** | useUploadSession, onDrop, useDropzone | 226-254 | 731-771 |
| **File List & Preview** | previewFileIndex, previewPageInput, previewPageCount, filePreviewUrl, PdfCanvasPreview | 149-155, 638-664 | 856-1008 |
| **Quick Config** | settingsSnapshot, updateSettingsSnapshot, parse engine, OCR, PPT mode selects | 172-187 | 773-849, 1099-1329 |
| **Job Submission** | handleConvertAll, buildJobConfig, validateRunConfig, preflight | 269-398 | 1333-1396 |
| **SSE Tracking** | SSE useEffect, per-job reconnect, backoff | 475-591 | (no UI) |
| **Progress Display** | overallProgress, stageSteps, fileJobs rendering | 631-704 | 1409-1674 |
| **Download/Cancel** | handleCancelJob, handleDownload, handleDownloadAll | 400-438 | 1548-1620 |
| **Debug Panel** | showHomeLog, JobDebugPanel | — | 1644-1674 |
| **Model Status** | useModelStatus, useEffectiveModelStatus | 255-267 | 1147-1153 |

### 1.3 State Coupling Map

`fileJobs` is the **central coupling point** — 11 subsystems read/write it:

```
fileJobs
  ├─ handleConvertAll          (writes: initializes all jobs)
  ├─ SSE useEffect             (writes: patch status/progress from events)
  ├─ terminal toast useEffect  (reads: detect completion)
  ├─ activeJobIdsKey memo      (reads: derive SSE subscription key)
  ├─ overallProgress           (reads: aggregate progress)
  ├─ stageSteps memo           (reads: compute step indicators)
  ├─ hasActiveJobs             (reads: derived boolean)
  ├─ allCompleted              (reads: derived boolean)
  ├─ handleDownloadAll         (reads: find completed jobs)
  ├─ stage "converting"        (reads: determine stage)
  ├─ job list rendering        (reads: render per-job cards)
  └─ handleResetAll            (writes: clears to [])
```

```text
settingsSnapshot
  ├─ Quick config UI           (reads/writes via updateSettingsSnapshot)
  ├─ handleConvertAll          (reads for buildJobConfig + validateRunConfig)
  ├─ preflight check           (reads for required providers)
  ├─ useEffectiveModelStatus   (reads for remote readiness)
  └─ downloadedLayoutModels    (reads via modelStatus)
```

```text
uploadFiles / fileCount
  ├─ onDrop                    (writes via addFiles)
  ├─ handleConvertAll          (reads for File entries → FormData)
  ├─ file list UI              (reads)
  ├─ PDF preview               (reads currentPreviewFile)
  ├─ stage determination       (reads fileCount)
  └─ handleResetAll            (writes via clearUpload)
```

```text
modelStatus / preflightWarning
  ├─ preflight check in handleConvertAll
  ├─ ModelStatusBadge display
  ├─ OCR provider readiness radio buttons
  ├─ preflight warning UI (acknowledge/override buttons)
  └─ downloadedLayoutModels memo
```

### 1.4 SSE Event Handling Deep Dive (lines 475-591, 116 lines)

This is the most complex single block. Structure:

1. **Entry**: Derives `activeJobIds` by splitting `activeJobIdsKey` string
2. **Per-job setup**: `setupSseForJob(jid)` creates `EventSource` via `createJobEventSource(jid)`
3. **onmessage** (lines 491-541):
   - Parses SSE event.data JSON: `{ status, stage, progress, message, error }`
   - Patches `fileJobs` for matching jobId (functional update)
   - On terminal status: fetches full response via `fetchJobStatus(jid)` (to get debug_events), then closes EventSource
   - Resets backoff counter on successful delivery
4. **onerror** (lines 543-575):
   - Closes failed EventSource, deletes from sources Map
   - Sets `pollError: "连接中断，正在重试..."` on job
   - Exponential backoff: `SSE_RECONNECT_BASE_MS * 2^(attempts-1)`, capped at 30s
   - setTimeout to call `setupSseForJob(jid)` again
5. **Management state** (local to useEffect):
   - `sources: Map<string, EventSource>` — active connections
   - `timers: Map<string, ReturnType<typeof setTimeout>>` — pending reconnect timers
   - `reconnectAttempts: Map<string, number>` — per-job attempt counters
   - `mounted: boolean` — cleanup guard
6. **Cleanup**: Closes all EventSources, clears all timers

**Interaction with page**: SSE only touches `fileJobs` (via `setFileJobs`) and calls `fetchJobStatus`. It does NOT read/write settings, upload state, or preview state. **This is well-encapsulated and a prime candidate for extraction into `useSSEJobTracking`.**

### 1.5 Stage Logic

```typescript
const stage: "upload" | "preview" | "converting" = (() => {
  if (fileJobs.length > 0) return "converting"
  if (fileCount > 0) return "preview"
  return "upload"
})()
```

The entire render tree branches on `stage` with large conditional blocks — currently inline JSX, not sub-components.

---

## 2. `web/src/app/settings/page.tsx` (2888 lines)

### 2.1 Section Structure Map

| Section | Lines | Wrapper | Content Summary |
|---|---|---|---|
| Private sub-components | 60-633 | — | FieldLabel, AdvancedReveal, PromptTextarea, CollapsibleSection, SensitiveInput, RuntimeConfigSection, FieldBlock |
| SettingsPage header | 1310-1340 | — | Title "参数设置" / "处理设置", badges, description |
| Toolbar | 1342-1360 | — | Auto-save indicator, clear/save buttons |
| **Parse Engine Card** | 1362-1390 | Card | 4 engine mode buttons |
| Advanced Toggle | 1392-1407 | — | "高级参数与诊断" show/hide |
| **API Config** | 1410-1600 | CollapsibleSection | API origin editor + MinerU token/base-url/model/language/checkboxes |
| **Processing Strategy** | 1602-1883 | CollapsibleSection | Text erase mode, scanned page mode, OCR render DPI, remove footer, image bg clear tuning |
| **OCR Config** | 1885-2880 | CollapsibleSection | Provider selector, Baidu config, AIOCR config (API key/chain/layout/model/check/prompt/concurrency), Tesseract config, local OCR check |
| Runtime Config | 2881-2883 | RuntimeConfigSection | Server-side env vars (self mode only) |

### 2.2 Already-Extracted Sub-Components

| Component | Lines | Props | Reuse Count |
|---|---|---|---|
| `FieldLabel` | 60-77 | `htmlFor, children, hint?` | ~15 times |
| `AdvancedReveal` | 79-106 | `show, children` | ~10 times |
| `PromptTextarea` | 108-115 | `React.ComponentProps<"textarea">` | 3 times |
| `CollapsibleSection` | 117-166 | `title, description?, hint?, defaultOpen?, children` | 3 times |
| `SensitiveInput` | 168-212 | `id?, value, onChange, placeholder?, disabled?, autoComplete?` | 3 times |
| `RuntimeConfigSection` | 357-595 | (none) | **Fully independent** — own state, own API calls |
| `FieldBlock` | 597-633 | `id, label, hint?, value, onChange, step?` | ~12 times |

**Note**: `RuntimeConfigSection` is already a perfect example of what the rest of the file should look like — a standalone component with its own internal state and API calls, rendered as a child.

### 2.3 Conditional Visibility Logic (the `ocrState` machine)

The `ocrState` object (computed at line 716) drives all visibility:

| ocrState property | Controls |
|---|---|
| `isOcrEnabledForCurrentEngine` | Entire OCR Config section visibility |
| `shouldShowOcrProviderSelector` | OCR provider radio buttons |
| `shouldShowBaiduConfig` | Baidu API key/secret fields |
| `shouldShowTesseractConfig` | Tesseract min confidence + language fields |
| `shouldShowAiVendorAdapter` | AIOCR vendor select dropdown |
| `needsRequiredOcrAiConfig` | Dedicated OCR API params block (key, base URL, chain, model) |
| `shouldShowLocalOcrCheck` | Local OCR check suite section |
| `isBaiduDocParseMode` | Baidu parse type select (vs just API keys) |
| `isOcrAiChainLayoutBlock` | Layout model radio group |
| `isOcrAiChainDocParser` | PaddleOCR-VL long side input |
| `isOcrAiChainDirect` | Model filtering + hint text changes |
| `isPromptDrivenOcrChain` | Prompt experiment section |
| `isMineruProvider` | MinerU-specific config + hides non-Mineru options |
| `isOcrProviderPaddleLocal` | PaddleOCR-specific hints and PaddleOCR-VL model check |
| `isOcrProviderBaidu` | Baidu-specific mode hints |
| `isOcrProviderTesseract` | Tesseract-specific hints |
| `canUseAiOcr` | Whether AIOCR features are usable |
| `selectedOcrProvider` | Currently selected provider ID |
| `availableOcrProviders` | Which providers to show in radio group |

### 2.4 Form Control Catalog (~50+ controls grouped by co-occurrence)

| Group | Controls | Always Together? | Lines |
|---|---|---|---|
| Parse Engine | 4 buttons | Yes | 1371-1388 |
| API Origin | 1 text input + 2 buttons | Yes | 1437-1461 |
| MinerU Config | 4 inputs + 1 select + 3 checkboxes = 8 | Yes (when mineru_cloud) | 1469-1597 |
| Text Erase Mode | 1 select | Always visible | 1621-1658 |
| Scanned Page Mode | 1 select | Always visible | 1673-1686 |
| OCR Render DPI | 1 number input | Advanced only | 1702-1718 |
| Remove Footer | 1 checkbox | Always visible | 1721-1736 |
| Image Tuning | 6 number inputs + reset button = 7 | Under AdvancedReveal | 1756-1881 |
| OCR Provider | 2 radio buttons | Conditional | 1909-1982 |
| OCR Strict Mode | 1 checkbox | Advanced only | 1993-2009 |
| AIOCR Vendor | 1 select | Advanced, conditional | 2017-2035 |
| AIOCR API Key | 1 sensitive input | Conditional | 2046-2061 |
| AIOCR Base URL | 1 text input | Conditional | 2073-2086 |
| AIOCR Chain Mode | 1 select | Conditional | 2095-2112 |
| Layout Model | 5 radio buttons | When chain=layout_block | 2122-2194 |
| PaddleOCR-VL Side | 1 number input | When chain=doc_parser, advanced | 2206-2223 |
| OCR Model | 1 text input + suggestion dropdown | Conditional | 2242-2288 |
| Prompt Preset | 1 select | Under prompt experiment | 2367-2382 |
| Prompt Overrides | 2-3 textareas | Under prompt experiment | 2399-2458 |
| Page Concurrency | 1 number input | Under advanced | 2476-2504 |
| Block Concurrency | 1 number input | Under advanced | 2513-2536 |
| RPM Limit | 1 number input | Under advanced | 2547-2561 |
| TPM Limit | 1 number input | Under advanced | 2571-2585 |
| Max Retries | 1 number input | Under advanced | 2595-2611 |
| Baidu API Key | 1 sensitive input | When baidu provider | 2664-2675 |
| Baidu Secret Key | 1 sensitive input | When baidu provider | 2684-2695 |
| Baidu App ID | 1 text input | Advanced, when baidu | 2705-2719 |
| Baidu Parse Type | 1 select | When baidu_doc mode | 2642-2658 |
| Tesseract Min Conf | 1 number input | When tesseract provider | 2728-2741 |
| Tesseract Language | 1 text input | When tesseract provider | 2750-2763 |
| OCR Check Button | 1 button + result card | Conditional | 2292-2332 |
| Local OCR Check | 1 button + 2 result cards | Conditional | 2766-2878 |

### 2.5 Auto-Save (500ms debounce) from use-settings.ts

From `web/src/hooks/use-settings.ts` lines 109-136:

```
Every setSettings() call → new settings object reference
  → triggers useEffect with [settings] dep
  → starts 500ms setTimeout
  → each new change resets the timer
  → on timeout: saves to localStorage (self) or API (public)
  → sets lastSavedAt timestamp

settings/page.tsx useEffect (line 651-655):
  → lastSavedAt change → refetchModelStatus()
```

**Impact**: Any keystroke in any input triggers a new settings object → timer reset. The save only fires once after typing stops for 500ms. This is efficient and already well-encapsulated in the hook.

### 2.6 Complex Callbacks Requiring Extraction

| Callback | Lines | Complexity |
|---|---|---|
| `onCheckAiOcrModel` | 1193-1308 | **116 lines, 11 settings deps**: validation, payload construction, POST, response parsing, state update |
| `onRunLocalOcrSuite` | 1158-1191 | 34 lines: runs two parallel check suites |
| `runSingleLocalOcrSuite` | 1128-1156 | 29 lines: Promise.allSettled for runtime+model checks |
| `onSaveApiOrigin` | 1063-1088 | 26 lines: save/clear/resolve API origin |
| `onAutoDetectApiOrigin` | 1090-1107 | 18 lines: clear + resolve |
| `onResetScannedImageTuning` | 1041-1052 | 12 lines: reset 6 fields to defaults |

---

## 3. Existing Custom Hooks (already extracted)

Located at `web/src/hooks/`:

| Hook | File | Lines | Purpose |
|---|---|---|---|
| `useModelStatus` | `use-model-status.ts` | 28-67 | Fetch + cache model status from `/models/status` |
| `useEffectiveModelStatus` | `use-model-status.ts` | 76-134 | Merge backend status with localStorage-based remote readiness |
| `useSettings` | `use-settings.ts` | 46-174 | Full settings lifecycle: load, auto-save (500ms debounce), clear, save, deploy mode |
| `useModelDownload` | `use-model-download.ts` | 29-184 | Download lifecycle: start, cancel, poll status, progress tracking |

**Key observation**: These 4 hooks already demonstrate excellent separation of concerns. The same pattern should be applied to extract additional hooks from the monolithic page components.

---

## 4. Proposed Split Plan

### 4.1 New Custom Hooks for page.tsx

| Hook | State Returned | ~LOC | Replaces |
|---|---|---|---|
| `useSettingsSnapshot` | `{ settingsSnapshot, updateSettingsSnapshot, refreshSettingsSnapshot }` | 40 | Lines 126 + 172-187 |
| `useJobSubmit` | `{ fileJobs, submitJobs, isSubmitting }` | 130 | handleConvertAll + fileJobs initialization |
| `useSSEJobTracking` | (modifies fileJobs via setFileJobs parameter) | 140 | Lines 475-591 SSE useEffect |
| `useJobPolling` | `{ jobs, queueSize, fetchJobs }` | 60 | Lines 189-205 + 611-629 |
| `useFilePreview` | `{ previewFileIndex, setPreviewFileIndex, previewPageInput, setPreviewPageInput, previewPageCount, setPreviewPageCount, filePreviewUrl, handlePreviewPageCommit, handlePreviewPageCountChange }` | 70 | Lines 144-155, 637-664 |
| `usePreflightCheck` | `{ preflightWarning, preflightAcknowledged, checkPreflight, acknowledgePreflight }` | 50 | Lines 257-258, 285-311 |

### 4.2 New Sub-Components for page.tsx

| Component | Props | ~LOC | Replaces Lines |
|---|---|---|---|
| `UploadZone` | `getRootProps, getInputProps, isDragActive, isDragReject, user, isAuthLoading` | 40 | 747-771 |
| `QuickConfigBar` | `settingsSnapshot, updateSettingsSnapshot, modelStatus, isModelStatusLoading, refetchModelStatus, downloadedLayoutModels` | 160 | 773-849 |
| `FilePreviewPanel` | `uploadFiles, previewFileIndex, setPreviewFileIndex, previewPageInput, setPreviewPageInput, previewPageCount, previewPage, filePreviewUrl, handlePreviewPageCommit, handlePreviewPageCountChange, currentPreviewFile, removeFile, handleResetAll` | 90 | 856-1008 |
| `ConfigSidebar` | `settingsSnapshot, updateSettingsSnapshot, usePageRange, setUsePageRange, pageStartInput, setPageStartInput, pageEndInput, setPageEndInput, isImageInput, retainProcessArtifacts, setRetainProcessArtifacts, currentPreviewFile, previewPage, modelStatus, isModelStatusLoading, refetchModelStatus` | 210 | 1012-1406 |
| `FileJobProgress` | `fileJobs, stageSteps, overallProgress` | 50 | 1409-1492 |
| `FileJobItem` | `fj, index, onDownload, onCancel` | 60 | 1506-1581 |
| `FileJobList` | `fileJobs, handleDownload, handleCancelJob` | 30 | 1495-1584 |
| `JobActionsBar` | `hasActiveJobs, allCompleted, completedCount, fileJobs, handleDownloadAll, handleDownload, handleResetAll, handleCancelJob` | 60 | 1587-1642 |

### 4.3 New Custom Hooks for settings/page.tsx

| Hook | State Returned | ~LOC | Replaces |
|---|---|---|---|
| `useOcrModelSuggestions` | `{ ocrModelOptions, visibleOcrModelOptions, filteredOptions, ocrModelLoading, ocrModelError, showOcrModelSuggestions, setShowOcrModelSuggestions, ocrModelSuggestionLayer, ocrModelPickerRef }` | 100 | Model fetching effect (lines 969-1034), suggestion dropdown (lines 823-960), filtering memos (lines 796-821) |
| `useAiOcrCheck` | `{ aiOcrCheck, aiOcrChecking, aiOcrCheckError, runCheck }` | 90 | Lines 675-676, 1193-1308 |
| `useLocalOcrCheck` | `{ localOcrSuite, localOcrSuiteChecking, localOcrSuiteError, runSuite }` | 90 | Lines 668-674, 1109-1191 |
| `useApiOrigin` | `{ apiOrigin, apiOriginInput, setApiOriginInput, apiOriginResolving, apiOriginError, apiOriginOverrideEnabled, saveApiOrigin, autoDetectApiOrigin }` | 80 | Lines 660-714, 1063-1107 |

### 4.4 New Sub-Components for settings/page.tsx

| Component | Props | ~LOC | Replaces Lines |
|---|---|---|---|
| `ParseEngineSelector` | `parseEngineMode, onSelect` | 40 | 1371-1388 |
| `ApiOriginEditor` | `showAdvanced, apiOrigin, apiOriginInput, setApiOriginInput, ...` | 80 | 1423-1466 |
| `MineruConfigFields` | `settings, setSettings, isPublicMode` | 80 | 1469-1597 |
| `ProcessingStrategySection` | `showAdvanced, settings, setSettings, isMineruProvider, onResetImageTuning` | 130 | 1602-1883 |
| `OcrProviderSelector` | `selectedOcrProvider, availableProviders, modelStatus, onSelect, getDownloadState, onDownload, onCancel` | 60 | 1895-1982 |
| `OcrAiConfigPanel` | `settings, setSettings, ocrState, modelStatus, isPublicMode, ocrModelSuggestionLayer, showAdvanced, aiOcrCheck, aiOcrChecking, aiOcrCheckError, runAiOcrCheck` | 450 | 2037-2629 |
| `BaiduConfigFields` | `settings, setSettings, isBaiduDocParseMode, isPublicMode, showAdvanced` | 80 | 2632-2721 |
| `TesseractConfigFields` | `settings, setSettings` | 40 | 2723-2764 |
| `LocalOcrCheckPanel` | `suiteResult, isChecking, error, onRunCheck` | 110 | 2766-2878 |
| `OcrModelSuggestionDropdown` | `filteredOptions, selectedModel, onSelect, onClose, style, direction, pickerRef, panelRef` | 80 | 908-960, 2276-2288 |
| `OcrPromptExperiment` | `settings, setSettings, ocrState, showOcrPromptExperiment, setShowOcrPromptExperiment, hasCustomOcrPromptConfig, currentOcrPromptOverride, currentOcrPromptOverrideLabel, currentOcrPromptOverrideHint, currentOcrPromptOverridePlaceholder, currentOcrPromptVariableHint` | 130 | 2334-2460 |
| `OcrConcurrencyPanel` | `settings, setSettings, ocrState, autoOcrAiPageConcurrency, autoOcrAiBlockConcurrency` | 90 | 2462-2619 |

### 4.5 What Stays in the Page Component

#### page.tsx (~200-250 lines):
- Stage logic (`upload` / `preview` / `converting`)
- High-level orchestration: hook calls, state wiring
- Stage-conditional rendering calling sub-components
- `handleResetAll` (orchestrates multiple state resets across hooks)
- Overall progress aggregation (reads fileJobs)
- Derived booleans: `hasActiveJobs`, `allCompleted`, `completedCount`, `failedCount`, `canStart`

#### settings/page.tsx (~200-250 lines):
- Header + Toolbar markup
- `useSettings()` hook integration
- `showAdvanced` / `showOcrPromptExperiment` toggle state
- `ocrState` memo computation
- Conditional rendering of sections based on `ocrState`
- Section-level CollapsibleSection wrappers

### 4.6 Shared State that Needs Context or Props

**Must go through props** (caller owns state, passes down):
- `settings` / `setSettings` (from useSettings) → all settings sub-components
- `fileJobs` / `setFileJobs` → all job-related sub-components
- `modelStatus` / `refetchModelStatus` → model-dependent sub-components
- `showAdvanced` → all AdvancedReveal-wrapped sub-components

**Should go into React Context** (avoids deep prop drilling):
- `ocrState` (used by 10+ settings sub-components)
- `isPublicMode` (used by all API key fields)
- `modelStatus` (used by OCR provider selector, layout model selector, etc.)

**Candidate for a dedicated context**:
```typescript
// Proposed: OcrContext
interface OcrContextValue {
  ocrState: ReturnType<typeof resolveOcrSettingsState>
  modelStatus: ModelStatusResponse | null
  isPublicMode: boolean
  settings: Settings
  setSettings: (updater: Settings | ((prev: Settings) => Settings)) => void
}
```

### 4.7 Estimated File Count and LOC Summary

| Category | Files | Total LOC |
|---|---|---|
| New hooks (6 page + 4 settings) | 10 | ~800 |
| New sub-components (8 page + 12 settings) | 20 | ~1,600 |
| Refactored page.tsx | 1 | ~250 |
| Refactored settings/page.tsx | 1 | ~250 |
| **Total** | **32 files** | **~2,900** |

Before refactor: 2 files, ~4,569 lines
After refactor: 32 files, average ~90 lines each

---

## 5. Component Reuse / Duplication Between Pages

### 5.1 Clear Duplication Opportunities

| Pattern | page.tsx | settings/page.tsx | Shared Component Suggested |
|---|---|---|---|
| OCR provider radio (paddleocr/tesseract) with readiness badges | Lines 1162-1211 | Lines 1910-1981 | `OcrProviderSelector` — identical structure: radio buttons + CheckIcon "就绪" badges + readiness warnings |
| Layout model display with download status | Lines 1242-1271 (dropdown) | Lines 2114-2194 (radio group) | `LayoutModelSelector` — different UI but same data source (LAYOUT_MODELS + modelStatus) |
| Parse engine selection | Lines 777-796 (Select dropdown) | Lines 1371-1388 (Button grid) | `ParseEnginePicker` — could unify into one component with a `variant` prop |
| Model readiness warning | Lines 1213-1218 ("未就绪，请前往设置") | Lines 1957-1961 | `ModelReadinessWarning` — same warning pattern |
| PPT generation mode select | Lines 800-813 (upload stage) + Lines 1107-1119 (preview stage) | N/A | Already duplicated within page.tsx itself! Should be `PptGenerationModeSelect` |

### 5.2 Already Shared (via imports)

| Shared Resource | Used By |
|---|---|
| `useModelStatus()` hook | Both pages |
| `useAuth()` / `useUploadSession()` providers | page.tsx |
| `useSettings()` hook | settings/page.tsx |
| `ModelStatusBadge` component | page.tsx only (settings rolls its own) |
| `LAYOUT_MODELS` constant | Both pages |
| `@/lib/settings` exports (PARSE_ENGINE_MODE_LABELS, etc.) | Both pages |
| `@/lib/api` (apiFetch, normalizeFetchError) | Both pages |

### 5.3 page.tsx Self-Duplication

The PPT generation mode and parse engine selects appear **twice** within page.tsx:
1. Upload stage config bar (lines 777-821)
2. Preview stage config sidebar (lines 1099-1329)

Both render the same selects with the same onChange handlers. These should be a single `QuickConfigPanel` component used in both stages.

---

## 6. Caveats / Risks

1. **SSE connection management is critical** — the `useSSEJobTracking` hook must handle cleanup perfectly to avoid zombie EventSources. The current implementation is correct; extraction must preserve all edge cases (mounted flag, Map-based connection tracking, reconnect backoff).

2. **`handleConvertAll` is the largest single callback (130 lines)** and depends on 10 state variables. Extracting it into `useJobSubmit` requires careful dependency management — it reads settings, upload files, page range, model status, and preflight state.

3. **The settings page's conditional rendering is complex** — ~15 boolean flags from `ocrState` drive visibility. Extracting sub-components must preserve the exact conditional logic; a `renderIf` pattern or proper prop-gating is needed.

4. **Auto-save 500ms debounce lives in `use-settings.ts`** — sub-components that call `setSettings()` will trigger auto-save correctly as long as they use the same `setSettings` function from the hook.

5. **`RuntimeConfigSection` already sets the pattern** — it's a fully self-contained component with its own state, API calls, and error handling. The other sections should follow this model.

6. **No existing tests** for either page component were found — refactoring should ideally add basic render tests for each extracted component.

7. **The `ocrState` computation** in settings/page.tsx (line 716) is a single `useMemo` that produces ~15 boolean/computed values. This should remain in the page component and be passed as props or context to sub-components — moving it would require duplicating the computation.

---

## 7. File Paths Referenced

| File | Lines | Role |
|---|---|---|
| `web/src/app/page.tsx` | 1681 | Main conversion page |
| `web/src/app/settings/page.tsx` | 2888 | Settings page |
| `web/src/hooks/use-model-status.ts` | 134 | Model status hook (shared) |
| `web/src/hooks/use-settings.ts` | 174 | Settings lifecycle + auto-save (settings page only) |
| `web/src/hooks/use-model-download.ts` | 199 | Model download management (settings page only) |
| `web/src/components/upload-session-provider.tsx` | — | Upload file state provider (page.tsx only) |
| `web/src/components/model-status-badge.tsx` | — | Model status badge (page.tsx only) |
| `web/src/components/download-progress-button.tsx` | — | Download button with progress (settings page only) |
| `web/src/components/pdf-canvas-preview.tsx` | — | PDF canvas renderer (page.tsx only) |
| `web/src/components/job-debug-panel.tsx` | — | Job debug event viewer (page.tsx only) |
| `web/src/lib/settings.ts` | — | Settings types, labels, defaults (both pages) |
| `web/src/lib/run-config.ts` | — | buildJobConfig, validateRunConfig, ocrState resolution (both pages) |
| `web/src/lib/api.ts` | — | apiFetch, normalizeFetchError, SSE helpers (both pages) |
| `web/src/lib/constants.ts` | — | HOME_JOB_LIMIT, poll intervals, SSE reconnect base (page.tsx) |
| `web/src/lib/layout-models.ts` | — | LAYOUT_MODELS constant (both pages) |
| `web/src/lib/job-status.ts` | — | Job status types, labels, normalizers (page.tsx) |
