# Research: OCR Strategy Section Logic Audit

- **Query**: Read `web/src/components/settings/ocr-strategy-section.tsx` completely and find ALL UI logic issues — conditional visibility, missing fields, dependency mismatches
- **Scope**: mixed (internal frontend + backend cross-reference)
- **Date**: 2026-05-13

## Files Examined

| File Path | Description |
|---|---|
| `web/src/components/settings/ocr-strategy-section.tsx` | Main component under audit (626 lines) |
| `web/src/hooks/use-model-download.ts` | `useModelDownload` hook (200 lines) |
| `web/src/lib/settings.ts` | Settings type definitions, defaults, migration (768 lines) |
| `web/src/lib/run-config.ts` | Run-time config resolution (827 lines) |
| `api/app/convert/ocr/prompts.py` | Backend prompt preset resolution & template rendering (259 lines) |
| `api/app/convert/ocr/routing.py` | OCR route plan — chain mode → route_kind mapping |
| `api/app/convert/ocr/_ai_chat.py` | AI chat OCR — direct prompt, image region prompt usage |
| `api/app/convert/ocr/_ai_layout_block.py` | Layout block OCR — layout_block prompt usage |
| `api/app/convert/ocr/ai_client.py` | AiOcrClient — stores all prompt overrides as instance fields |

## Findings

### 1. 提示词预设 (ocrAiPromptPreset) — Incorrect Visibility

**Current**: Only visible when `ocrAiChainMode === "direct"` (line 386).

**Backend reality**: `prompt_preset` is used in ALL THREE chain routes:
- `direct` mode: `_ai_chat.py` → `_make_prompt()` → `resolve_ai_ocr_prompt_preset()` + `build_ai_ocr_direct_prompt()`
- `layout_block` mode: `_ai_layout_block.py` → `_ocr_local_layout_block_crop()` → `resolve_ai_ocr_prompt_preset()` + `build_ai_ocr_layout_block_prompt()`
- `image_region` detection (used by `layout_block`): `_ai_chat.py` → `detect_image_regions()` → `resolve_ai_ocr_prompt_preset()` + `build_ai_ocr_image_region_prompt()`

`doc_parser` mode does NOT use prompt_preset (it uses PaddleOCR-VL structured output API, not chat prompts).

**Issue**: `prompt_preset` should be visible for both `direct` **and** `layout_block` modes. Currently hidden for `layout_block` and `doc_parser`.

### 2. 直出模式提示词覆盖 (ocrAiDirectPromptOverride) — Shows for Wrong Modes

**Current**: Always visible inside the CollapsibleSection (line 412-420), regardless of chain mode.

**Backend reality**: Only used in `direct` mode — `_ai_chat.py` → `_make_prompt()` → `build_ai_ocr_direct_prompt(override=self.direct_prompt_override)`.

**Issue**: This field shows for `layout_block` and `doc_parser` modes too, where the backend ignores it. Should be conditionally shown only for `direct` mode. Not harmful (backend ignores unused overrides) but confusing for users.

### 3. 版面切块模式提示词覆盖 (ocrAiLayoutBlockPromptOverride) — Shows for Wrong Modes

**Current**: Always visible inside the CollapsibleSection (line 422-434), regardless of chain mode.

**Backend reality**: Only used in `layout_block` mode — `_ai_layout_block.py` → `_ocr_local_layout_block_crop()` → `build_ai_ocr_layout_block_prompt(override=self.layout_block_prompt_override)`.

**Issue**: This field shows for `direct` and `doc_parser` modes too. Should be conditionally shown only for `layout_block` mode.

### 4. 图片区域提示词覆盖 (ocrAiImageRegionPromptOverride) — Shows for Wrong Modes

**Current**: Always visible inside the CollapsibleSection (line 436-448), regardless of chain mode.

**Backend reality**: Used for image region detection, which is part of the `layout_block` chain (via `_ai_chat.py` → `detect_image_regions()` → `build_ai_ocr_image_region_prompt()`). Not used in `direct` or `doc_parser` modes.

**Issue**: Should be conditionally shown only for `layout_block` mode (or at least hidden for `direct`). Note: `direct` mode does NOT run image region detection.

### 5. Missing Field: ocrAiBlockConcurrency

The Settings type (`settings.ts:89`) includes `ocrAiBlockConcurrency: string` and the backend (`run-config.ts:697-699`) sends it as `ai.block_concurrency`, but **no UI field exists** anywhere in the OCR strategy section for this setting.

The backend's `resolveAutoOcrAiBlockConcurrency()` only returns non-null for `layout_block` chain mode (returns null otherwise). So this field should be shown conditionally for `layout_block` mode.

### 6. Missing Field: ocrAiPageConcurrencyAuto Toggle

The Settings type (`settings.ts:87`) includes `ocrAiPageConcurrencyAuto: boolean`, controlling whether page concurrency is auto-calculated (`resolveAutoOcrAiPageConcurrency`) or user-specified. **No toggle exists in the UI** for this. The user can set `ocrAiPageConcurrency` manually but can't control whether auto mode is on/off.

### 7. Missing Field: ocrPaddleVlDocparserMaxSidePx

The Settings type (`settings.ts:86`) includes `ocrPaddleVlDocparserMaxSidePx: string` (default "2200") and the backend:
- `run-config.ts:693-696` sends it as `ai.paddle_vl_docparser_max_side_px`
- `api/app/convert/ocr/_ai_paddle_doc.py:810` uses it for PaddleOCR-VL doc_parser image resize

**No UI field exists**. This is most relevant for `doc_parser` chain mode and for PaddleOCR-VL model usage. Should show at least for `doc_parser` mode, and possibly also for `layout_block` when using PaddleOCR-VL.

### 8. OCR Render DPI & Strict Mode — Only in local_ocr Section

**Current**: `ocrRenderDpi` and `ocrStrictMode` are shown inside the local_ocr parse mode block (lines 178-209). They do NOT appear under `remote_ocr`, `baidu_doc`, or `mineru_cloud`.

**Backend reality**: The backend (`run-config.ts:665-669`) always sends `config.ocr.render_dpi` and `config.ocr.strict_mode` for ALL parse providers:
```typescript
config.ocr = {
  provider: run.effectiveOcrProvider,
  render_dpi: toFinitePositiveIntOrNull(settings.ocrRenderDpi) ?? undefined,
  strict_mode: Boolean(settings.ocrStrictMode),
}
```

**Issue**: Users in `remote_ocr` or `baidu_doc` modes cannot configure OCR render DPI or strict mode through the UI, even though the backend sends these values.

### 9. enableOcr Checkbox — Only in local_ocr Section

**Current**: The `enableOcr` checkbox (line 211-223) is inside the local_ocr section. It is NOT shown for `remote_ocr`, `baidu_doc`, or `mineru_cloud`.

**Backend reality**: `enableOcr` is a top-level job option (`api/app/worker_helpers/_job_options.py:16`), and the worker (`api/app/worker.py:479`) checks it to decide whether to run OCR:
```python
parse_provider_id == "local" and scanned_pages_exist and bool(options.enable_ocr)
```
However, the condition shows it's only used for `local` parse provider. For `remote_ocr` and `baidu_doc`, OCR is implicitly always on.

**Assessment**: This might be intentional — remote/baidu modes are OCR-centric by definition. Nevertheless, the field exists in settings and defaults to `true`, and users in non-local modes cannot change it. Consider if this is the desired UX or if the field should be moved to a shared section.

### 10. doc_parser Chain Mode — No Conditional UI

The `doc_parser` chain mode has **zero** conditional rendering inside the CollapsibleSection. The only chain-mode-specific conditions are:
- `direct` → shows prompt_preset (line 386) — **PARTIALLY CORRECT** (should also include `layout_block`)
- `layout_block` → shows layout_model + download (lines 451-488) — **CORRECT**

For `doc_parser`:
- No `prompt_preset` shown — **CORRECT** (doc_parser doesn't use prompts)
- All prompt overrides shown — **MISLEADING** (they're ignored by backend)
- No `ocrPaddleVlDocparserMaxSidePx` shown — **MISSING** (relevant for this mode)
- Concurrency/rate fields shown — **CORRECT** (they apply to all modes)

### 11. useModelDownload Hook — Download State Check

**File**: `web/src/hooks/use-model-download.ts`

**Assessment**: The hook is generally correct:
- `getDownloadState(modelId)` is memoized with `useCallback(fn, [downloads])` — stable reference
- On mount, `fetchStatus()` is called via useEffect to pick up existing downloads
- Polling starts when any download is in "downloading" status

**Minor issue — initial render flicker**: On first render, `downloads` state is `{}`, so `getDownloadState(opt.id)` returns `null` for all models. The dropdown options show "未下载" momentarily. After `fetchStatus()` resolves (first API call), state updates and labels correct themselves. This is a brief UX flicker, not a logic bug.

### 12. CollapsibleSection Condition for Advanced Options

**Line 383**: `<CollapsibleSection title="高级选项" defaultOpen={false}>`

**Assessment**: This is inside the `parseMode === "remote_ocr"` block (line 266), so it always shows for remote_ocr. There is no additional condition needed — all advanced options that should be conditionally shown have their own `{settings.ocrAiChainMode === "xxx" && ...}` guards (though, per findings above, those guards have issues). The CollapsibleSection itself is fine.

### 13. Baidu OCR Keys Section

**Lines 560-622**: Baidu section under `parseMode === "baidu_doc"`.

**Assessment**: 
- Three credential fields are always shown — **CORRECT**
- All three fields support hiding/showing passwords via `SensitiveInput` — **CORRECT**
- No OCR render DPI or strict mode shown (see Finding #8) — **ISSUE**

### 14. PaddleOCR Download in Local OCR Section

**Lines 165-175**: PaddleOCR model download shown when `ocrProvider === "paddleocr" || ocrProvider === "auto"`.

**Assessment**: Uses `getDownloadState("paddleocr")` which matches the model ID used in `getModelLabel()`. Start/cancel callbacks use the same ID. **CORRECT**, subject to the same initial-render flicker noted in Finding #11.

## Summary of All Issues

| # | Severity | Issue |
|---|----------|-------|
| 1 | **HIGH** | `ocrAiPromptPreset` hidden for `layout_block` mode, but backend uses it |
| 2 | MEDIUM | `ocrAiDirectPromptOverride` shows for all modes, only used by `direct` |
| 3 | MEDIUM | `ocrAiLayoutBlockPromptOverride` shows for all modes, only used by `layout_block` |
| 4 | MEDIUM | `ocrAiImageRegionPromptOverride` shows for all modes, only used by `layout_block` |
| 5 | **HIGH** | `ocrAiBlockConcurrency` missing from UI entirely |
| 6 | MEDIUM | `ocrAiPageConcurrencyAuto` toggle missing from UI |
| 7 | **HIGH** | `ocrPaddleVlDocparserMaxSidePx` missing from UI entirely |
| 8 | MEDIUM | OCR render DPI & strict mode only visible in local_ocr, sent for all modes |
| 9 | LOW | `enableOcr` checkbox only in local_ocr (possibly intentional) |
| 10 | MEDIUM | `doc_parser` mode has no mode-specific conditional UI |
| 11 | LOW | Download state label flickers "未下载" on initial render |

## Caveats / Not Found

- The `ocrAiChainMode === "doc_parser"` backend route uses `ROUTE_KIND_REMOTE_DOC_PARSER` which is the PaddleOCR-VL structured output pathway. No chat prompts are used. However, if the PaddleOCR-VL endpoint is unavailable, there's a `OCR_PADDLE_PROMPT_FALLBACK_MODEL` env var that allows fallback to prompt mode — in that edge case, `prompt_preset` COULD be relevant for `doc_parser` too.
- Image region detection (`detect_image_regions`) is used in `layout_block` mode and possibly in `auto` mode with AI OCR. For `direct` mode, image regions are generally not detected, so `ocrAiImageRegionPromptOverride` truly doesn't apply.
- The `enableOcr` field appears to only affect `local` parse provider behavior in the backend (worker.py line 479). For remote/baidu, OCR is always enabled implicitly. Whether this should be a visible toggle is a UX question.
