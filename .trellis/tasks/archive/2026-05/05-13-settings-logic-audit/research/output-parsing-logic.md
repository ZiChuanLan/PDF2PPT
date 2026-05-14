# Research: Output & Parsing Section Logic Audit

- **Query**: Audit UI logic issues in output-quality-section.tsx and parsing-method-section.tsx
- **Scope**: internal (frontend + backend cross-reference)
- **Date**: 2026-05-13

## Findings

### Files Audited

| File Path | Description |
|---|---|
| `web/src/components/settings/output-quality-section.tsx` | Output quality settings (PPT mode, layout assist, content gen AI, image params) |
| `web/src/components/settings/parsing-method-section.tsx` | Parse engine radio buttons + MinerU-specific fields |
| `web/src/lib/run-config.ts` | Frontend run config builder (`buildJobConfig`, `resolveRunConfig`) |
| `web/src/lib/settings.ts` | Settings type definitions |
| `web/src/app/settings/page.tsx` | Settings page composition (tabs, OCR section gating) |
| `api/app/schemas/job_config.py` | Backend JobConfig model + `to_worker_kwargs()` |
| `api/app/worker.py` | Backend worker (layout assist providers, MinerU/baidu_doc handling) |

---

## Issue 1 [CRITICAL]: Layout Assist & Content Generation AI are dead code (v2 endpoint)

### Root cause: v2 API path hardcodes `enable_layout_assist` to `False`

**Backend** — `api/app/schemas/job_config.py:389-391`:
```python
# Deprecated (always False)
"enable_layout_assist": False,
"layout_assist_apply_image_regions": False,
```

**Frontend** — `web/src/lib/run-config.ts` in `buildJobConfig()` (lines 612+):
The function never includes `enable_layout_assist` or `layout_assist_apply_image_regions` in the JobConfig at all.

Additionally, `resolveRunConfig()` at line 332-333 hardcodes:
```typescript
const layoutAssistMode: LayoutAssistMode = "off"
const layoutAssistEnabled = false
```

### Affected UI elements (all non-functional):

| Element | File:Line | Appears | Actually Works |
|---|---|---|---|
| "启用布局辅助" checkbox | `output-quality-section.tsx:256-266` | ✅ | ❌ Never applied to jobs |
| "内容生成AI（用于布局辅助）" section | `output-quality-section.tsx:109-232` | ✅ | ❌ Provider/key never used |
| Provider selector (OpenAI/Claude) | `output-quality-section.tsx:120-133` | ✅ | ❌ |
| OpenAI API Key, Base URL, Model | `output-quality-section.tsx:136-212` | ✅ | ❌ |
| Claude API Key | `output-quality-section.tsx:215-231` | ✅ | ❌ |
| "应用图片区域识别" checkbox | `output-quality-section.tsx:272-283` | ✅ | ❌ |

**How to fix**: Either (a) remove these UI elements entirely if layout assist is permanently deprecated, or (b) thread `enableLayoutAssist` and `layoutAssistApplyImageRegions` through `buildJobConfig()` → `JobConfig.to_worker_kwargs()` and remove the hardcoded `False`.

---

## Issue 2: `mineruHybridOcr` checkbox shown but deprecated and ignored

### Location
`web/src/components/settings/parsing-method-section.tsx:184-195`

### Backend confirmation
- `api/app/worker.py:397-404` — `mineru_hybrid_ocr is deprecated and ignored`
- `api/app/schemas/job_config.py:408` — `"mineru_hybrid_ocr": False,  # deprecated`
- `api/app/routers/jobs.py:784` — `mineru_hybrid_ocr=False` (hardcoded in v1 form endpoint)

### Impact
User can toggle "MinerU 混合 OCR" checkbox on/off in settings, but the value never reaches the worker (always `False`).

**Recommendation**: Remove the checkbox from the UI.

---

## Issue 3: Layout Assist checkbox visible in MinerU mode but AI config section hidden

### Gating logic in `output-quality-section.tsx`

**Layout Assist checkbox** (lines 253-286):
```
Unconditionally rendered — no `isMineruMode` check
```

**Content Generation AI section** (line 109):
```jsx
{!isMineruMode && settings.enableLayoutAssist && (
  // provider, keys, models...
)}
```

**Provider check inside AI section** (line 61):
```typescript
const isMineruMode = settings.parseEngineMode === "mineru_cloud"
```

### Inconsistency

When `parseEngineMode === "mineru_cloud"`:
1. Layout Assist checkbox is **visible** and can be toggled
2. Content Generation AI section is **hidden** (blocked by `!isMineruMode`)
3. The user can check "启用布局辅助" but cannot configure **which AI provider** to use

Furthermore, MinerU mode forces `provider: "mineru"` (see `applyParseEngineMode` at `run-config.ts:781`), so there is no Content Generation AI provider to use anyway.

**Additional note**: The backend does NOT explicitly force-disable `enable_layout_assist` for MinerU (unlike `baidu_doc` which sets `enable_layout_assist = False` at `worker.py:432`). MinerU only disables the local OCR pass (lines 469-471), not layout assist. However, since Issue 1 already makes the entire feature dead, this inconsistency is academic until Issue 1 is resolved.

**Recommendation**: Either hide the Layout Assist checkbox in MinerU mode, or allow the Content Generation AI section to appear in MinerU mode if the user wants layout assist with a separate AI provider.

---

## Issue 4: OpenAI key always visible in remote_ocr mode even when provider is Claude

### Location
`output-quality-section.tsx:136-137`:
```jsx
{(settings.provider === "openai" ||
  settings.parseEngineMode === "remote_ocr") && (
```

### Problem

When `parseEngineMode === "remote_ocr"` AND `provider === "claude"`:
- OpenAI Key, Base URL, Model are shown (triggered by `remote_ocr` check)
- Claude Key is also shown (triggered by `provider === "claude"` at line 215)
- Both provider keys appear simultaneously

The backend's `_select_layout_assist_provider()` in `worker.py:88-128` picks **one** provider — it uses the main AI credentials first, not both. Showing both key fields is confusing to the user.

**Also**: The OpenAI key shows in `remote_ocr` mode because the original intent might have been that `remote_ocr` needs OpenAI for AI OCR. But the AI OCR now has its own dedicated key (`ocrAiApiKey`) configured in the OCR tab. The `settings.parseEngineMode === "remote_ocr"` condition likely predates the dedicated AI OCR key split.

---

## Issue 5: "内容生成AI" section header misleading for remote_ocr mode

### Location
`output-quality-section.tsx:111-113`:
```jsx
<div className="text-sm text-muted-foreground mb-2">
  内容生成AI（用于布局辅助）
</div>
```

### Problem

The section is shown when `parseEngineMode === "remote_ocr"` (line 137), but the label says "用于布局辅助" (for layout assist). In `remote_ocr` mode:
- The OpenAI key is NOT used for layout assist — it's used for AI OCR
- AI OCR has its own separate configuration in the OCR tab
- The label is misleading about the purpose

---

## Issue 6: MinerU-specific fields visibility — minor issues

### `mineruBaseUrl` placeholder
`parsing-method-section.tsx:117`:
```
placeholder="https://api.mineru.com"
```
The actual MinerU API URL is typically different. Should be the real default (or left empty).

### `mineruLanguage` — no dropdown/validation
`parsing-method-section.tsx:161-168`:
Free-text Input with placeholder "留空自动检测". No language code validation or dropdown. Could accept arbitrary invalid values.

---

## Verified Correct Behavior

| Element | Condition | Status |
|---|---|---|
| Content Generation AI hidden for MinerU | `isMineruMode` gate at line 109 | ✅ Correct |
| MinerU Token field | Only shown `parseEngineMode === "mineru_cloud"` (line 92) | ✅ Correct |
| MinerU Base URL, Model, Formula, Table, Language, OCR | All inside mineru_cloud gate | ✅ Correct |
| OCR tab replaced for MinerU | `settings page.tsx:156` and `ocr-strategy-section.tsx:120` | ✅ Correct |
| PPT Generation Mode | Always shown (applies to all modes) | ✅ Correct |
| Text Erase Mode, Scanned Page Mode | Always shown (advanced output, applies to all) | ✅ Correct |
| Remove NotebookLM Footer | Always shown | ✅ Correct |
| Image params | Always shown | ✅ Correct |
| Claude key | Only for `provider === "claude"` (line 215) | ✅ Correct |
| Baidu fields | Located in `ocr-strategy-section.tsx`, not `parsing-method-section.tsx` | ✅ Correct (design choice) |

---

## Summary of Issues to Fix

| # | Severity | Component | Issue |
|---|---|---|---|
| 1 | 🔴 CRITICAL | `output-quality-section.tsx` + backend | Layout Assist + Content Gen AI are dead code — hardcoded `False` in v2 endpoint |
| 2 | 🟡 Medium | `parsing-method-section.tsx` | `mineruHybridOcr` checkbox shown but backend says deprecated + ignored |
| 3 | 🟡 Medium | `output-quality-section.tsx` | Layout Assist checkbox visible in MinerU mode, but AI config section hidden |
| 4 | 🟡 Medium | `output-quality-section.tsx:136-137` | `remote_ocr` forces OpenAI key visibility even with Claude provider |
| 5 | 🟢 Low | `output-quality-section.tsx:111-113` | "内容生成AI（用于布局辅助）" label misleading in remote_ocr mode |
| 6 | 🟢 Low | `parsing-method-section.tsx:117,161` | MinerU placeholder URL inaccurate; language field open text |

## Caveats / Not Found

- Did NOT check whether the v1 Form-based endpoint (`POST /api/v1/jobs`) is still used by any code path — the frontend exclusively uses `/jobs/v2`.
- The `mineruIsOcr` field seems to be functional (passed to `parse_pdf_to_ir_with_mineru` in worker.py line 419) — NOT deprecated like `mineruHybridOcr`.
- Did NOT trace the full backend execution path for `enable_layout_assist` through the v1 endpoint to confirm it works there (v1 is unused by frontend anyway).
