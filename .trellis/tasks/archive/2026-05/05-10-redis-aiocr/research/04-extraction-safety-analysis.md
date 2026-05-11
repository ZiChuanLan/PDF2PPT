# Research: Extraction Safety Analysis

- **Query**: Analyze extraction safety for `useSSEJobTracking` hook and `OcrConfigSection` component
- **Scope**: internal
- **Date**: 2026-05-10

## Findings

---

## Candidate 1: `useSSEJobTracking` hook from `page.tsx`

### 1.1 Exact Line Range

| Block | Lines | Description |
|---|---|---|
| `activeJobIdsKey` memo | 463-472 | Derives comma-joined active job IDs string from `fileJobs` |
| SSE `useEffect` | 474-591 | Full EventSource subscription + reconnect logic |

**Total**: 129 lines (lines 463-591, plus internal `activeJobIdsKey` memo at 462-472)

**Note**: The `activeJobIdsKey` memo (lines 463-472) is a dependency of the SSE effect. It MUST be included in the hook because it logically belongs together — the hook needs active job IDs to determine which jobs to track.

### 1.2 Dependencies (params to pass IN)

| Dependency | Type | Source | How to pass |
|---|---|---|---|
| `fileJobs` | `FileJobState[]` | Page state (line 140) | **Derived out**: pass as param OR derive `activeJobIds` inside hook and compute internally |
| `setFileJobs` | `React.Dispatch<React.SetStateAction<FileJobState[]>>` | Page state (line 140) | **Prop**: must be passed in; hook patches status into `fileJobs` |
| `fetchJobStatus` | `(targetJobId: string) => Promise<JobStatusResponse>` | Page callback (line 207) | **Prop**: must be passed in; called on terminal status |
| `createJobEventSource` | `(jobId: string) => EventSource` | `@/lib/api` (line 293) | **Import**: internal to hook |
| `SSE_RECONNECT_BASE_MS` | `number` | `@/lib/constants` | **Import**: internal to hook |
| `TERMINAL_JOB_STATUSES` | `Set<JobStatusValue>` | `@/lib/job-status` | **Import**: internal to hook |
| `FileJobState` type | type alias | local to `page.tsx` (line 74) | **Extract**: move to a shared types file (`web/src/lib/job-types.ts`) or `web/src/hooks/use-sse-types.ts` |
| `JobStatusValue` type | import | `@/lib/job-status` | **Import**: internal to hook |
| `JobStatusResponse` type | import | `@/lib/job-status` | **Import**: internal to hook |

### 1.3 Internal State (managed inside the hook)

| Variable | Type | Lines | Purpose |
|---|---|---|---|
| `sources` | `Map<string, EventSource>` | 480 | Active SSE connections |
| `timers` | `Map<string, ReturnType<typeof setTimeout>>` | 481 | Pending reconnect timers |
| `reconnectAttempts` | `Map<string, number>` | 483 | Per-job backoff counters |
| `mounted` | `boolean` | 479 | Cleanup guard |
| `MAX_BACKOFF_MS` | `30_000` (const) | 485 | Backoff cap |

### 1.4 Outputs / Side Effects

| Output | Target | Description |
|---|---|---|
| `setFileJobs(updater)` | Parent state | Patches `pollError`, `status`, on SSE events |
| `fetchJobStatus(jid)` call | Network | Fetches full status (incl. `debug_events`) on terminal |
| `es.close()` | Browser | Closes EventSources on terminal or cleanup |
| `clearTimeout(timer)` | Browser | Clears reconnect timers on cleanup |

**No explicit return value**. The hook is purely a side-effect hook. Could optionally return diagnostic info:
```typescript
{
  activeConnections: number  // sources.size
  reconnectCounts: Map<string, number>  // for debugging
}
```

### 1.5 Risk Assessment: **LOW** ✅

| Factor | Assessment | Reason |
|---|---|---|
| **Encapsulation** | Excellent | All state (maps, mounted flag) is local to the `useEffect` closure |
| **External coupling** | Minimal | Only touches `fileJobs` via `setFileJobs` + calls `fetchJobStatus` |
| **Settings dependency** | None | Does not read `settingsSnapshot` or any config |
| **Upload dependency** | None | Does not read `uploadFiles` or `fileCount` |
| **Preview dependency** | None | Does not read preview state |
| **Cleanup safety** | Thorough | `mounted` guard, cleanup closes ALL EventSources + clears ALL timers |
| **Edge cases** | Well-handled | JSON parse errors caught silently; `fetchJobStatus` failure is best-effort; reconnect backoff prevents thundering herd |

### 1.6 Existing Patterns to Reference

| Pattern | File | Lines |
|---|---|---|
| `useModelStatus` — fetch + cache hook | `web/src/hooks/use-model-status.ts` | 28-67 |
| `useModelDownload` — subscription lifecycle hook | `web/src/hooks/use-model-download.ts` | 29-184 |
| `createJobEventSource` — simple factory | `web/src/lib/api.ts` | 293-295 |

**Recommended hook signature**:
```typescript
function useSSEJobTracking(
  fileJobs: FileJobState[],
  setFileJobs: React.Dispatch<React.SetStateAction<FileJobState[]>>,
  fetchJobStatus: (jobId: string) => Promise<JobStatusResponse>
): void
```

Or even simpler — compute active job IDs inside the hook:
```typescript
function useSSEJobTracking(
  fileJobs: FileJobState[],
  setFileJobs: React.Dispatch<React.SetStateAction<FileJobState[]>>
): void
```
…and have the hook import `fetchJobStatus` from the caller or accept it as a third param. Best practice: pass it as a param to keep the hook testable.

### 1.7 `activeJobIdsKey` — Include or Exclude?

The `activeJobIdsKey` memo at lines 463-472:
```typescript
const activeJobIdsKey = React.useMemo(
  () => fileJobs
    .filter(j => j.jobId && j.isSubmitting === false && (!j.status || !TERMINAL_JOB_STATUSES.has(j.status.status)))
    .map(j => j.jobId!)
    .join(","),
  [fileJobs]
)
```
This derives which jobs need SSE tracking. It should move INTO the hook — it is logically the hook's input-derivation step. Without it, the caller would have to compute it and pass it down; including it makes the hook self-contained.

### 1.8 File to Extract Into

Suggested path: `web/src/hooks/use-sse-job-tracking.ts`

---

## Candidate 2: `OcrConfigSection` component from `settings/page.tsx`

### 2.1 Exact Line Range

**Lines 1958–2953** (996 lines). This is the entire block:

```
{isOcrEnabledForCurrentEngine ? (         // line 1958
  <CollapsibleSection                      // line 1959
    title={isBaiduDocParseMode ? ...}      // lines 1959-1966
    description=...
    hint=...
  >                                         // line 1967
    {/* Provider selector: 1968-2062 */}
    {/* OCR strict mode: 2064-2082 */}
    {/* AIOCR vendor adapter: 2084-2108 */}
    {/* AIOCR config block: 2110-2703 */}
    {/* Baidu config: 2705-2764 */}
    {/* Tesseract config: 2768-2836 */}
    {/* Local OCR check: 2839-2950 */}
  </CollapsibleSection>                     // line 2952
) : null}                                   // line 2953
```

### 2.2 All Variables/Functions It Depends On

#### A. Global/constant dependencies (can be imported)

| Variable | Defined at | Line |
|---|---|---|
| `ocrProviderLabels` | Module-level const | 252 |
| `ocrAiProviderOptions` | Module-level const | 214 |
| `ocrAiChainModeOptions` | Module-level const | 223 |
| `ocrAiLayoutModelOptions` | Module-level const | 229 |
| `ocrAiPromptPresetOptions` | Module-level const | 238 |
| `baiduDocParseTypeOptions` | Module-level const | 247 |
| `defaultSettings` | `@/lib/settings` | import |
| `LAYOUT_MODELS` | `@/lib/layout-models` | import |
| `PARSE_ENGINE_MODE_LABELS` | `@/lib/run-config` | import |
| `BAIDU_DOC_PARSE_TYPE_LABELS` | `@/lib/settings` | import |
| `getOcrConfigSourceLabel` | `@/lib/run-config` | import |
| `isPaddleOcrVlModelName` | `@/lib/settings` | import |
| `HoverHint` | `@/components/ui/hover-hint` | import |
| `Badge` | `@/components/ui/badge` | import |
| `Button` | `@/components/ui/button` | import |
| `CheckIcon` | `lucide-react` | import |
| `DownloadProgressButton` | `@/components/download-progress-button` | import |
| `createPortal` | `react-dom` | import |

#### B. UI sub-components defined in same file (would need moving/exporting or co-locating)

| Component | Lines | Used where |
|---|---|---|
| `FieldLabel` | 60-77 | ~15 times throughout OCR section |
| `AdvancedReveal` | 79-106 | 3 times in OCR section |
| `SensitiveInput` | 168-212 | 1 time (OCR API Key) |
| `PromptTextarea` | 108-115 | 2 times (prompt overrides) |
| `CollapsibleSection` | 117-166 | 1 time (outer wrapper) |

**Implication**: These helpers are used across the ENTIRE settings page, not just the OCR section. Moving them into the OcrConfigSection means either:
1. Duplicating them (bad)
2. Moving them to a shared `components/` subdirectory and importing from both places
3. Passing them as `children` or render props (unwieldy)

**Recommendation**: Move `FieldLabel`, `AdvancedReveal`, `SensitiveInput`, `PromptTextarea`, `CollapsibleSection` into files under `web/src/components/settings/`. They are generic UI primitives used throughout settings.

#### C. Props from parent page (state + callbacks that the parent owns)

| Prop | Type | Current source (line) | Used in OCR section? | Risk |
|---|---|---|---|---|
| `settings` | `Settings` | useSettings (710) | ✅ Everywhere | LOW — just data |
| `setSettings` | `(updater) => void` | useSettings (711) | ✅ Every onChange | LOW — stable identity from hook |
| `isPublicMode` | `boolean` | useSettings (713) | ✅ API key disabled state | LOW |
| `showAdvanced` | `boolean` | useState (730) | ✅ All AdvancedReveal wrappers | LOW |
| `modelStatusData` | `ModelStatusResponse \| null \| undefined` | useModelStatus (718) | ✅ Radio readiness badges | LOW |
| `ocrState` | Return type of `resolveOcrSettingsState` | useMemo (789) | ✅ ALL conditional rendering | **HIGH** — see below |
| `showOcrModelSuggestions` | `boolean` | useState (732) | ✅ Model input dropdown | MEDIUM |
| `setShowOcrModelSuggestions` | `(value) => void` | useState (733) | ✅ Toggle callback | MEDIUM |
| `ocrModelPickerRef` | `RefObject<HTMLDivElement>` | useRef (749) | ✅ Anchor for dropdown positioning | MEDIUM |
| `ocrModelLoading` | `boolean` | useState (739) | ✅ Loading indicator | LOW |
| `ocrModelError` | `string \| null` | useState (740) | ✅ Error display | LOW |
| `visibleOcrModelOptions` | `string[]` | useMemo (869) | ✅ Dropdown items | LOW |
| `filteredOcrModelOptions` | `string[]` | useMemo (878) | ✅ Filtered dropdown items | LOW |
| `ocrModelSuggestionLayer` | `React.ReactNode \| false \| null` | computed (981) | ✅ Portal render | **HIGH** — uses `createPortal(document.body, ...)` |
| `ocrModelSuggestionDirection` | `"up" \| "down"` | useState (754) | ✅ Dropdown direction | MEDIUM |
| `ocrModelSuggestionStyle` | `React.CSSProperties \| null` | useState (751) | ✅ Dropdown positioning | MEDIUM |
| `ocrModelSuggestionPanelRef` | `RefObject<HTMLDivElement>` | useRef (750) | ✅ Portal ref | MEDIUM |
| `aiOcrCheck` | `AiOcrCheckResponse \| null` | useState (747) | ✅ Result card | LOW |
| `aiOcrChecking` | `boolean` | useState (746) | ✅ Check button loading | LOW |
| `aiOcrCheckError` | `string \| null` | useState (748) | ✅ Error display | LOW |
| `onCheckAiOcrModel` | `() => Promise<void>` | useCallback (1266) | ✅ Button onClick | LOW |
| `showOcrPromptExperiment` | `boolean` | useState (731) | ✅ Prompt experiment expand | LOW |
| `setShowOcrPromptExperiment` | `(value) => void` | useState (731) | ✅ Toggle callback | LOW |
| `getDownloadState` | `(modelId) => DownloadState` | useModelDownload (719) | ✅ Layout model download buttons | LOW |
| `startDownload` | `(modelId) => Promise<void>` | useModelDownload (719) | ✅ Layout model download | LOW |
| `cancelDownload` | `(modelId) => void` | useModelDownload (719) | ✅ Layout model cancel | LOW |
| `localOcrSuiteChecking` | `boolean` | useState (741) | ✅ Check button loading | LOW |
| `localOcrSuite` | `LocalOcrCheckSuiteResult \| null` | useState (742) | ✅ Result cards | LOW |
| `localOcrSuiteError` | `string \| null` | useState (745) | ✅ Error display | LOW |
| `onRunLocalOcrSuite` | `() => Promise<void>` | useCallback (1231) | ✅ Button onClick | LOW |

That's **~30 individual props** if passed one-by-one. Completely unwieldy.

#### D. Computed values used in the section (derived at parent page level)

| Variable | Lines | Value |
|---|---|---|
| `isBaiduDocParseMode` | 791 | `ocrState.isBaiduDocParseMode` |
| `isMineruProvider` | 790 | `ocrState.isMineruProvider` |
| `isOcrEnabledForCurrentEngine` | 792 | `ocrState.isOcrEnabledForCurrentEngine` |
| `canUseAiOcr` | 793 | `ocrState.canUseAiOcr` |
| `selectedOcrProvider` | 794 | `ocrState.selectedOcrProvider` |
| `parseEngineMode` | 795 | `ocrState.parseEngineMode` |
| `isOcrProviderPaddleLocal` | 806 | `ocrState.isOcrProviderPaddleLocal` |
| `isOcrProviderBaidu` | 807 | `ocrState.isOcrProviderBaidu` |
| `isOcrProviderTesseract` | 808 | `ocrState.isOcrProviderTesseract` |
| `isOcrAiChainDirect` | 809 | `ocrState.isOcrAiChainDirect` |
| `isOcrAiChainDocParser` | 810 | `ocrState.isOcrAiChainDocParser` |
| `isOcrAiChainLayoutBlock` | 811 | `ocrState.isOcrAiChainLayoutBlock` |
| `isPromptDrivenOcrChain` | 812 | `isOcrAiChainDirect \|\| isOcrAiChainLayoutBlock` |
| `needsRequiredOcrAiConfig` | 813 | `ocrState.needsRequiredOcrAiConfig` |
| `shouldShowLocalOcrCheck` | 814 | `ocrState.shouldShowLocalOcrCheck` |
| `shouldShowOcrProviderSelector` | 831 | `ocrState.shouldShowOcrProviderSelector` |
| `shouldShowBaiduConfig` | 832 | `ocrState.shouldShowBaiduConfig` |
| `shouldShowTesseractConfig` | 833 | `ocrState.shouldShowTesseractConfig` |
| `shouldShowAiVendorAdapter` | 834 | `ocrState.shouldShowAiVendorAdapter` |
| `mainModelsApiKeyRaw` | 836 | `getMainProviderConfig(settings).apiKey` |
| `ocrModelsApiKey` | 837 | `ocrState.ocrModelsApiKey` |
| `ocrModelsBaseUrl` | 838 | `ocrState.ocrModelsBaseUrl` |
| `autoOcrAiPageConcurrency` | 798 | `resolveAutoOcrAiPageConcurrency(settings)` |
| `autoOcrAiBlockConcurrency` | 799 | `resolveAutoOcrAiBlockConcurrency(...)` |
| `tesseractSuite` | 815 | `localOcrSuite?.tesseract ?? null` |
| `paddleSuite` | 816 | `localOcrSuite?.paddle ?? null` |
| `hasTesseractSuite` | 817 | boolean |
| `hasPaddleSuite` | 823 | boolean |
| `tesseractSuiteReady` | 829 | boolean |
| `paddleSuiteReady` | 830 | boolean |
| `currentOcrPromptOverride` | 839 | string |
| `currentOcrPromptOverrideLabel` | 842 | string |
| `currentOcrPromptOverrideHint` | 845 | string |
| `currentOcrPromptOverridePlaceholder` | 848 | string (multiline) |
| `currentOcrPromptVariableHint` | 859 | string |
| `hasCustomOcrPromptConfig` | 862 | boolean |

**~35 derived values**. Many come from `ocrState`, some are local derivations.

### 2.3 Outputs

The section primarily **mutates `settings` via `setSettings`** and triggers side effects (downloads, check API calls). It renders JSX that is conditionally shown/hidden. No explicit return values.

### 2.4 Risk Assessment: **HIGH** ❌ — but mitigable through incremental extraction

| Factor | Assessment | Reason |
|---|---|---|
| **Size** | Critical | 996 lines — too large for a single extraction review |
| **Prop count** | Critical | ~65 individual values if passed one-by-one |
| **State coupling** | Critical | Tightly coupled to parent's `useSettings`, `useModelStatus`, `useModelDownload`, and ~15 local state variables |
| **Portal dependency** | High | `ocrModelSuggestionLayer` uses `createPortal(document.body, ...)` — parent page renders it at top of return (line 1385) |
| **Shared sub-components** | Medium | `FieldLabel`, `SensitiveInput`, etc. are used across the ENTIRE settings page; moving them into one section duplicates them |
| **Conditional complexity** | Medium | ~20 boolean flags from `ocrState` drive show/hide; extraction would move these conditionals into the parent |
| **Callbacks in deps** | Medium | `onCheckAiOcrModel` has 17 `useCallback` dependencies |
| **Constant arrays** | Low | Module-level const arrays can be imported from a shared location |
| **Type definitions** | Low | `LocalOcrCheckResult`, `AiOcrCheckResponse`, etc. are local types; can be moved to shared file |

### 2.5 Safer Alternative: Layered Incremental Extraction

Rather than extracting the entire 996-line block as one `OcrConfigSection`, extract smaller sub-components first:

#### Layer 1: LOW risk — can be extracted immediately

| Component | Lines | Dependencies | Props needed |
|---|---|---|---|
| `OcrProviderSelector` | 1968-2056 (~90 lines) | `ocrState`, `selectedOcrProvider`, `availableOcrProviders`, `modelStatusData`, `getDownloadState`, `startDownload`, `cancelDownload`, `ocrProviderLabels`, `setSettings` | ~10 props |
| `BaiduConfigFields` | 2705-2764 (~60 lines) | `settings`, `setSettings`, `isBaiduDocParseMode`, `isPublicMode`, `showAdvanced`, `baiduDocParseTypeOptions`, `defaultSettings` | ~7 props |
| `TesseractConfigFields` | 2768-2836 (~70 lines) | `settings`, `setSettings`, `defaultSettings` | ~3 props |
| `LocalOcrCheckPanel` | 2839-2950 (~110 lines) | `localOcrSuiteChecking`, `localOcrSuite`, `localOcrSuiteError`, `onRunLocalOcrSuite`, `tesseractSuite`, `paddleSuite`, `hasTesseractSuite`, `hasPaddleSuite`, `tesseractSuiteReady`, `paddleSuiteReady` | ~10 props |

#### Layer 2: MEDIUM risk — extract after Layer 1 is done

| Component | Lines | Dependencies | Props needed |
|---|---|---|---|
| `OcrConcurrencyPanel` | 2536-2693 (~160 lines) | `settings`, `setSettings`, `isOcrAiChainDirect`, `isOcrAiChainLayoutBlock`, `isOcrAiChainDocParser`, `autoOcrAiPageConcurrency`, `autoOcrAiBlockConcurrency`, `defaultSettings` | ~8 props |
| `OcrPromptExperiment` | 2407-2533 (~130 lines) | `settings`, `setSettings`, `isPromptDrivenOcrChain`, `isOcrAiChainLayoutBlock`, `showOcrPromptExperiment`, `setShowOcrPromptExperiment`, `currentOcrPromptOverride`, `currentOcrPromptOverrideLabel`, `currentOcrPromptOverrideHint`, `currentOcrPromptOverridePlaceholder`, `currentOcrPromptVariableHint`, `hasCustomOcrPromptConfig`, `ocrAiPromptPresetOptions` | ~13 props |

#### Layer 3: HIGH risk — extract last, after shared deps are settled

| Component | Lines | Dependencies | Notes |
|---|---|---|---|
| `OcrAiConfigPanel` | 2110-2703 (~590 lines) | Everything above combined | Would compose Layer 1+2 components internally |

### 2.6 What the Parent Page Would Keep

After extracting Layer 1 components, the parent page would retain:

```tsx
{isOcrEnabledForCurrentEngine ? (
  <CollapsibleSection title={...}>
    <OcrProviderSelector ... />
    <AdvancedReveal show={showAdvanced && !isBaiduDocParseMode}>
      {/* OCR strict mode checkbox */}
    </AdvancedReveal>
    <AdvancedReveal show={showAdvanced && shouldShowAiVendorAdapter}>
      {/* AIOCR vendor select */}
    </AdvancedReveal>
    {needsRequiredOcrAiConfig ? (
      <OcrAiConfigPanel ... />    {/* after Layer 3 */}
    ) : null}
    {shouldShowBaiduConfig && <BaiduConfigFields ... />}
    {shouldShowTesseractConfig && <TesseractConfigFields ... />}
    {shouldShowLocalOcrCheck && <LocalOcrCheckPanel ... />}
  </CollapsibleSection>
) : null}
```

This keeps the `CollapsibleSection` wrapper and conditional gates at the page level where they belong (they depend on `ocrState`).

### 2.7 React Context Consideration

To avoid 30+ props, a React Context could provide shared values:

```typescript
// Proposed: OcrSettingsContext
interface OcrSettingsContextValue {
  settings: Settings
  setSettings: (updater: Settings | ((prev: Settings) => Settings)) => void
  isPublicMode: boolean
  showAdvanced: boolean
  ocrState: ReturnType<typeof resolveOcrSettingsState>
  modelStatusData: ModelStatusResponse | null | undefined
  getDownloadState: (modelId: string) => DownloadState
  startDownload: (modelId: string) => Promise<void>
  cancelDownload: (modelId: string) => void
}
```

**Risk**: React Context causes re-renders of ALL consumers when any value changes. Since `settings` changes on every keystroke (auto-save debounce in `use-settings.ts`), this could degrade performance. **Recommendation**: stick with props for now; context only if prop drilling becomes a proven pain point.

### 2.8 Type Extraction

These types are currently local to `settings/page.tsx` and must be moved to a shared file for sub-components to reference:

| Type | Lines | Suggested location |
|---|---|---|
| `LocalOcrCheckResult` | 261-278 | `web/src/lib/ocr-check-types.ts` |
| `LocalOcrCheckResponse` | 280-283 | `web/src/lib/ocr-check-types.ts` |
| `LocalOcrCheckSuiteEntry` | 285-290 | `web/src/lib/ocr-check-types.ts` |
| `LocalOcrCheckSuiteResult` | 292-295 | `web/src/lib/ocr-check-types.ts` |
| `AiOcrCheckSampleItem` | 297-301 | `web/src/lib/ocr-check-types.ts` |
| `AiOcrCheckResult` | 303-314 | `web/src/lib/ocr-check-types.ts` |
| `AiOcrCheckResponse` | 316-319 | `web/src/lib/ocr-check-types.ts` |
| `RuntimeConfig` interface | 325-337 | `web/src/lib/runtime-config-types.ts` |

### 2.9 Helper Component Extraction

These UI primitives are used across the entire settings page. Extract them first (zero risk):

| Component | Lines | File |
|---|---|---|
| `FieldLabel` | 60-77 | `web/src/components/settings/field-label.tsx` |
| `AdvancedReveal` | 79-106 | `web/src/components/settings/advanced-reveal.tsx` |
| `PromptTextarea` | 108-115 | `web/src/components/settings/prompt-textarea.tsx` |
| `CollapsibleSection` | 117-166 | `web/src/components/settings/collapsible-section.tsx` |
| `SensitiveInput` | 168-212 | `web/src/components/settings/sensitive-input.tsx` |
| `FieldBlock` | 670-705 | `web/src/components/settings/field-block.tsx` |

These are already parameterized and stateless — pure extraction, no logic changes needed.

---

## Summary

| Candidate | Risk | Lines | Safe extraction? | Recommended first step |
|---|---|---|---|---|
| `useSSEJobTracking` | **LOW** | ~130 | ✅ Yes — self-contained, minimal deps | Extract to `web/src/hooks/use-sse-job-tracking.ts` with 3 params |
| `OcrConfigSection` (996-line monster) | **HIGH** | ~996 | ❌ No — 65+ deps, deeply coupled | Extract helpers first, then Layer 1 sub-components (OcrProviderSelector, BaiduConfigFields, TesseractConfigFields, LocalOcrCheckPanel) |

---

## Caveats / Not Found

1. **`FileJobState` type** is local to `page.tsx` (line 74). `useSSEJobTracking` needs it. Must be moved to a shared types file (e.g., `web/src/lib/job-types.ts`).
2. **`fileJobs` is the central coupling point** in `page.tsx` — 11 subsystems read/write it. Extracting `useSSEJobTracking` reduces coupling by 1, but doesn't eliminate it.
3. **The `ocrModelSuggestionLayer` uses `createPortal(document.body, ...)`** and is rendered at the TOP of the settings page return (line 1385), outside the section. This means the model suggestion dropdown rendering must stay in the parent — only the trigger (input + button at lines 2315-2361) lives inside the OCR section.
4. **No existing tests** for either page component. Extracted hooks/components should have basic tests added.
5. **The `ocrState` computation** (line 789) produces ~20 boolean/computed values in a single `useMemo`. This should remain in the parent page. Moving it into a sub-component would require re-computing it.

---

## File Paths Referenced

| File | Lines | Role |
|---|---|---|
| `web/src/app/page.tsx` | 463-591 | SSE effect to extract |
| `web/src/app/settings/page.tsx` | 1958-2953 | OCR config section to decompose |
| `web/src/app/settings/page.tsx` | 60-212 | Shared UI helpers (FieldLabel, SensitiveInput, etc.) |
| `web/src/app/settings/page.tsx` | 214-319 | Module constants + types |
| `web/src/hooks/use-model-status.ts` | 28-67 | Reference hook pattern |
| `web/src/hooks/use-model-download.ts` | 29-184 | Reference hook pattern |
| `web/src/lib/api.ts` | 293-295 | `createJobEventSource` factory |
| `web/src/lib/constants.ts` | — | `SSE_RECONNECT_BASE_MS` |
| `web/src/lib/job-status.ts` | — | `TERMINAL_JOB_STATUSES`, `JobStatusValue`, `JobStatusResponse` types |
