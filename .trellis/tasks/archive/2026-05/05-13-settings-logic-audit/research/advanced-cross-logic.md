# Research: Advanced & Cross-Tab Logic Audit

- **Query**: Audit general-advanced-section, admin-settings, cross-tab logic, and settings type field coverage
- **Scope**: internal
- **Date**: 2026-05-13

## Findings

---

## 1. general-advanced-section.tsx — Issues

### 1.1 Empty heading when `enableLayoutAssist` is OFF (UI Glitch)

**File**: `web/src/components/settings/general-advanced-section.tsx`, lines 28–98

The component renders its heading unconditionally at line 31:
```tsx
<h3 className="text-base font-semibold">通用高级设置</h3>
<p className="text-sm text-muted-foreground">专家选项和调优参数</p>
```

But ALL content below is gated behind `{settings.enableLayoutAssist && (...)}` at line 36. When `enableLayoutAssist` is `false` (the default!), the "高级" tab shows only the heading with zero content — an empty tab that looks broken.

**Severity**: Medium (visual defect; tab appears empty for most users since `enableLayoutAssist` defaults to `false`)

### 1.2 Visual assist modes not filtered by `parseEngineMode`

**File**: `web/src/components/settings/general-advanced-section.tsx`, lines 38–93

All four visual assist mode selectors are shown unconditionally (inside the `enableLayoutAssist` gate):
- `visualAssistModeLocal` (line 40-51) — relevant for `local_ocr` mode
- `visualAssistModeRemote` (line 53-65) — relevant for `remote_ocr` mode
- `visualAssistModeBaiduDoc` (line 67-79) — relevant for `baidu_doc` mode
- `visualAssistModeMineru` (line 81-93) — relevant for `mineru_cloud` mode

**Problem**: All four are shown regardless of which `parseEngineMode` is selected. When using `local_ocr`, the user still sees `visualAssistModeMineru` and `visualAssistModeBaiduDoc`. When using `mineru_cloud`, they see `visualAssistModeLocal` and `visualAssistModeRemote`. These irrelevant settings create confusion but are harmless (silently ignored by the backend for the non-active parse mode).

**Severity**: Low (cosmetic — irrelevant fields are sent to backend but ignored)

### 1.3 No conditional display for `parseEngineMode`

The component receives `settings: Settings` but does NOT read `settings.parseEngineMode`. It cannot conditionally show/hide mode-specific fields. The component header/description also doesn't mention that these settings are parse-mode-specific.

---

## 2. admin-settings.tsx — Issues

### 2.1 Public mode gating — OK

**File**: `web/src/app/settings/page.tsx`, line 189
```tsx
{!isPublicMode && <AdminSettings />}
```

`AdminSettings` is only rendered when not in public mode. Correct.

### 2.2 `ENABLE_LAYOUT_ASSIST` runtime flag vs user `enableLayoutAssist` — NOT a logic issue

**File**: `web/src/components/settings/admin-settings.tsx`, lines 197-211

The admin panel has a server-side `ENABLE_LAYOUT_ASSIST` checkbox (runtime config). This is a **server-level feature flag** separate from the user-level `enableLayoutAssist` setting in the Output tab. The admin toggle controls whether the server allows layout assist at all; the user setting controls whether the user wants it for their job. This is correct and intentional — two different layers of control.

### 2.3 No conditional display issues

All runtime config fields are relevant regardless of parse engine mode. No fields need to be hidden based on other settings.

---

## 3. Cross-Tab Logic Issues

### 3.1 OCR tab correctly hidden for MinerU

**File**: `web/src/app/settings/page.tsx`, lines 156-165
```tsx
{settings.parseEngineMode === "mineru_cloud" ? (
  <div>MinerU 已内置 OCR 处理，无需额外配置</div>
) : (
  <OcrStrategySection ... />
)}
```
Correct — OCR tab shows a placeholder for MinerU mode.

### 3.2 `enableLayoutAssist` checkbox in Output tab NOT hidden for MinerU / baidu_doc

**File**: `web/src/components/settings/output-quality-section.tsx`, lines 254-286

The `enableLayoutAssist` checkbox and `layoutAssistApplyImageRegions` sub-option are rendered unconditionally for all parse modes. However:
- The "Content Generation AI" section (lines 109-233) IS correctly hidden for MinerU (`!isMineruMode && settings.enableLayoutAssist`)
- `enableLayoutAssist` is a user-level hint; the backend may ignore it for MinerU. But the checkbox being shown may mislead users into thinking layout assist works with MinerU.

**Severity**: Low (potential user confusion but no functional breakage)

### 3.3 `enableOcr` only shown in `local_ocr` mode — Intentional, verified correct

**File**: `web/src/components/settings/ocr-strategy-section.tsx`, lines 211-223
**Verification**: `web/src/lib/run-config.ts` line 622:
```ts
enable_ocr: run.parseProvider === "local" ? Boolean(settings.enableOcr) : false,
```
`enableOcr` is only consumed when `parseProvider === "local"`. So restricting the UI to `local_ocr` mode only is correct.

### 3.4 `baiduDocParseType` in OCR tab — Placement question

**File**: `web/src/components/settings/ocr-strategy-section.tsx`, lines 560-577

The `baiduDocParseType` selector (general vs paddle_vl) lives in the OCR tab under `parseMode === "baidu_doc"`. Conceptually this is a parsing method choice (how to parse within baidu_doc), and could arguably belong in the Parse tab. However, since it only applies to baidu_doc mode and determines OCR behavior, its current placement in the OCR tab is reasonable.

### 3.5 OCR tab `doc_parser` mode `ocrPaddleVlDocparserMaxSidePx` has NO UI

**File**: `web/src/components/settings/ocr-strategy-section.tsx`

When `ocrAiChainMode === "doc_parser"` (remote_ocr), the paddle VL docparser max side pixel (`ocrPaddleVlDocparserMaxSidePx`) is referenced in `run-config.ts` line 693 but has NO corresponding UI control in the OCR tab. The default value is `"2200"`.

**Severity**: Medium (power user setting without any UI access)

---

## 4. Settings Type — Field UI Coverage Audit

### Complete field-to-UI mapping

| # | Settings Field | UI Location | Has UI? |
|---|---|---|---|
| 1 | `provider` | output-quality (conditional on `enableLayoutAssist` && `!isMineruMode`) | ✅ |
| 2 | `preferredMainProvider` | No direct UI (auto-set when `provider` changes, line 126-127 of output-quality-section) | ⚠️ derived |
| 3 | `parseEngineMode` | parsing-method tab | ✅ |
| 4 | `openaiApiKey` | output-quality (conditional) | ✅ |
| 5 | `openaiBaseUrl` | output-quality (conditional) | ✅ |
| 6 | `openaiModel` | output-quality (conditional) | ✅ |
| 7 | `claudeApiKey` | output-quality (conditional on `provider="claude"`) | ✅ |
| 8 | `mineruApiToken` | parsing-method (conditional on `mineru_cloud`) | ✅ |
| 9 | `mineruBaseUrl` | parsing-method (conditional) | ✅ |
| 10 | `mineruModelVersion` | parsing-method (conditional) | ✅ |
| 11 | `mineruEnableFormula` | parsing-method (conditional) | ✅ |
| 12 | `mineruEnableTable` | parsing-method (conditional) | ✅ |
| 13 | `mineruLanguage` | parsing-method (conditional) | ✅ |
| 14 | `mineruIsOcr` | parsing-method (conditional) | ✅ |
| 15 | `mineruHybridOcr` | parsing-method (conditional) | ✅ |
| 16 | `enableLayoutAssist` | output-quality | ✅ |
| 17 | `layoutAssistApplyImageRegions` | output-quality (conditional on `enableLayoutAssist`) | ✅ |
| 18 | `visualAssistModeLocal` | general-advanced (conditional on `enableLayoutAssist`) | ✅ |
| 19 | `visualAssistModeRemote` | general-advanced (conditional on `enableLayoutAssist`) | ✅ |
| 20 | `visualAssistModeBaiduDoc` | general-advanced (conditional on `enableLayoutAssist`) | ✅ |
| 21 | `visualAssistModeMineru` | general-advanced (conditional on `enableLayoutAssist`) | ✅ |
| 22 | `enableOcr` | ocr-strategy (`local_ocr` only) | ✅ |
| 23 | `removeFooterNotebooklm` | output-quality | ✅ |
| 24 | `textEraseMode` | output-quality | ✅ |
| 25 | `scannedPageMode` | output-quality | ✅ |
| 26 | `pptGenerationMode` | output-quality | ✅ |
| 27 | `imageBgClearExpandMinPt` | output-quality | ✅ |
| 28 | `imageBgClearExpandMaxPt` | output-quality | ✅ |
| 29 | `imageBgClearExpandRatio` | output-quality | ✅ |
| 30 | `scannedImageRegionMinAreaRatio` | output-quality | ✅ |
| 31 | `scannedImageRegionMaxAreaRatio` | output-quality | ✅ |
| 32 | `scannedImageRegionMaxAspectRatio` | output-quality | ✅ |
| 33 | `ocrRenderDpi` | ocr-strategy (`local_ocr`) | ✅ |
| 34 | `ocrStrictMode` | ocr-strategy (`local_ocr`) | ✅ |
| 35 | `ocrProvider` | ocr-strategy (`local_ocr`) | ✅ |
| 36 | `baiduDocParseType` | ocr-strategy (`baidu_doc`) | ✅ |
| 37 | `ocrBaiduAppId` | ocr-strategy (`baidu_doc`) | ✅ |
| 38 | `ocrBaiduApiKey` | ocr-strategy (`baidu_doc`) | ✅ |
| 39 | `ocrBaiduSecretKey` | ocr-strategy (`baidu_doc`) | ✅ |
| 40 | `ocrTesseractMinConfidence` | ocr-strategy (`local_ocr`, conditional on tesseract) | ✅ |
| 41 | `ocrTesseractLanguage` | ocr-strategy (`local_ocr`, conditional on tesseract) | ✅ |
| 42 | `ocrAiApiKey` | ocr-strategy (`remote_ocr`) | ✅ |
| 43 | `ocrAiProvider` | ocr-strategy (`remote_ocr`) | ✅ |
| 44 | `ocrAiBaseUrl` | ocr-strategy (`remote_ocr`) | ✅ |
| 45 | `ocrAiModel` | ocr-strategy (`remote_ocr`) | ✅ |
| 46 | `ocrAiChainMode` | ocr-strategy (`remote_ocr`) | ✅ |
| 47 | `ocrAiLayoutModel` | ocr-strategy (`remote_ocr`, conditional on `layout_block`) | ✅ |
| 48 | `ocrAiPromptPreset` | ocr-strategy (`remote_ocr`, conditional on `direct`) | ✅ |
| 49 | `ocrAiDirectPromptOverride` | ocr-strategy (`remote_ocr`) | ✅ |
| 50 | `ocrAiLayoutBlockPromptOverride` | ocr-strategy (`remote_ocr`) | ✅ |
| 51 | `ocrAiImageRegionPromptOverride` | ocr-strategy (`remote_ocr`) | ✅ |
| 52 | **`ocrPaddleVlDocparserMaxSidePx`** | **NOWHERE** | ❌ **MISSING** |
| 53 | **`ocrAiPageConcurrencyAuto`** | **NOWHERE** | ❌ **MISSING** |
| 54 | `ocrAiPageConcurrency` | ocr-strategy (`remote_ocr`, line 491-503) | ✅ |
| 55 | **`ocrAiBlockConcurrency`** | **NOWHERE** | ❌ **MISSING** |
| 56 | `ocrAiRequestsPerMinute` | ocr-strategy (`remote_ocr`, line 521-536) | ✅ |
| 57 | `ocrAiTokensPerMinute` | ocr-strategy (`remote_ocr`, line 538-553) | ✅ |
| 58 | `ocrAiMaxRetries` | ocr-strategy (`remote_ocr`, line 506-518) | ✅ |

### Summary: 3 fields with NO UI

| Field | Default | Used in `run-config.ts`? | Notes |
|---|---|---|---|
| `ocrPaddleVlDocparserMaxSidePx` | `"2200"` | Yes (line 693) | Max image side for PaddleOCR-VL doc_parser mode |
| `ocrAiPageConcurrencyAuto` | `true` | Yes (line 307) | Auto-detect concurrency vs manual; auto-set when `ocrAiPageConcurrency` empty or default |
| `ocrAiBlockConcurrency` | `""` (empty = auto) | Yes (line 316, 697) | Manual block concurrency override |

**Note**: `ocrAiPageConcurrencyAuto` is automatically managed — it's set to `true` by `loadStoredSettings()` when `ocrAiPageConcurrency` is empty or at default, and to `false` when the user sets a custom value. This auto-detection means the lack of a manual toggle is semi-intentional. However, there's no UI to toggle it back to auto after setting a manual value — the user would have to clear their stored settings.

**Note**: `preferredMainProvider` (field #2) has no dedicated UI but is derived from `provider` changes in `output-quality-section.tsx` lines 126-128. This is intentional and correct.

### Previously known "4 missing" vs current 3

Without access to the prior research that identified "4 missing", the most likely candidates:
- The prior 4 probably included `ocrAiBlockConcurrency` and `ocrPaddleVlDocparserMaxSidePx`
- One of the other 2 may have gained a UI during a previous refactor
- Or `ocrAiPageConcurrencyAuto` was not counted since it's auto-managed

---

## 5. Additional Observations

### 5.1 `provider` field is conditionally hidden — double guard

**File**: `web/src/components/settings/output-quality-section.tsx`, lines 108-109

```tsx
{!isMineruMode && settings.enableLayoutAssist && (
```

The `provider` selector (content generation AI) requires BOTH `!isMineruMode` AND `enableLayoutAssist`. This means if the user has `enableLayoutAssist` enabled but is in `mineru_cloud` mode, they can't see or change their `provider` setting. Since MinerU handles content generation internally, this is intentional.

### 5.2 OpenAI key shown when `parseEngineMode === "remote_ocr"` regardless of `provider`

**File**: `web/src/components/settings/output-quality-section.tsx`, lines 136-137

The OpenAI API key is shown when `(settings.provider === "openai" || settings.parseEngineMode === "remote_ocr")`. This means even when `provider === "claude"`, if `parseEngineMode === "remote_ocr"`, the OpenAI key field is still shown. This is intentional — AIOCR in remote_ocr mode may need an OpenAI-compatible key regardless of the content generation provider.

---

## Caveats / Not Found

- Could not locate the prior research that identified "4 missing UI fields" — no research files exist under `05-13-settings-logic-audit/` yet.
- Did NOT trace backend consumption of cross-mode visual assist settings to determine if they're truly ignored or if there's unexpected cross-contamination.
- The VLM prompt override fields (`ocrAiDirectPromptOverride`, `ocrAiLayoutBlockPromptOverride`, `ocrAiImageRegionPromptOverride`) are confirmed to be in the OCR tab under `remote_ocr` → 高级选项 — consistent with "VLM prompt move" refactor.
