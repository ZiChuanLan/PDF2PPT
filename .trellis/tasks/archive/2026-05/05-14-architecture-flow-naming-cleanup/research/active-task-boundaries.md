# Research: Active Task Boundaries & Overlap Analysis

- **Query**: Analyze overlap/boundaries among active Trellis tasks related to settings, model sync, audits, and logic fixes. Determine what this parent task should own vs avoid duplicating.
- **Scope**: internal (task artifacts: prd.md, research/, implement.jsonl, check.jsonl, implementation-summary.md)
- **Date**: 2026-05-14

## 1. Active Task Inventory

### Task A: `05-13-comprehensive-audit` — 全代码审计:发现死代码和缺失功能

| Attribute | Value |
|-----------|-------|
| **Status** | `in_progress` |
| **PRD** | ✅ Has PRD (audit dead code + missing features) |
| **Research** | ✅ 3 files: `dead-backend.md`, `dead-frontend.md`, `missing-features.md` |
| **implement.jsonl** | ✅ Curated (spec + 3 research files) |
| **check.jsonl** | ✅ Minimum (just quality spec) |
| **Scope** | Full-stack dead code audit: backend orphans, frontend orphans, settings-without-UI, model filtering gap |
| **Out of Scope** | Fixing anything — record only |
| **Owner** | @lan |

**Key findings produced**:
- Backend: `admin_default_password` field is dead; `models/__init__.py` and `schemas/__init__.py` unused;
- Frontend: ~23 unused exports in lib files; 7 dead constants in `constants.ts`; 3 settings fields with no UI
- Cross-layer: `capability` param not sent to `/api/v1/models`; `parseEngineMode` → `parse_provider` mapping needs verification; "best" preset may not work without ENABLE_LAYOUT_ASSIST

---

### Task B: `05-13-fix-all-logic` — 修复所有UI逻辑缺陷: v2布局辅助死代码+条件显示+缺失UI

| Attribute | Value |
|-----------|-------|
| **Status** | `in_progress` |
| **PRD** | ❌ **No PRD** |
| **Research** | ❌ None owned; **depends on** `05-13-settings-logic-audit/research/` |
| **implement.jsonl** | ✅ Curated (references research from settings-logic-audit) |
| **check.jsonl** | ✅ Minimum (just quality spec) |
| **Scope** | Fix UI logic defects: layout assist dead code in v2 endpoint, conditional display bugs, missing UI fields |
| **Out of Scope** | Not explicitly stated (no PRD) |
| **Owner** | @lan |

**Title scope (unclear)**:
- "v2布局辅助死代码" — layout assist dead code (Issue 1 in output-parsing-logic)
- "条件显示" — conditional visibility (Issues 2-4 in ocr-section-logic, Issue 4 in output-parsing-logic)
- "缺失UI" — missing UI fields (Issues 5-7 in ocr-section-logic)

**Critical dependency**: This task's implementation spec IS the 3 research files from `settings-logic-audit`. But `settings-logic-audit` is still in `planning` and has no PRD.

---

### Task C: `05-13-settings-logic-audit` — 全面分析设置页面UI逻辑问题

| Attribute | Value |
|-----------|-------|
| **Status** | `planning` |
| **PRD** | ❌ **No PRD** |
| **Research** | ✅ 3 files: `advanced-cross-logic.md`, `ocr-section-logic.md`, `output-parsing-logic.md` |
| **implement.jsonl** | ❌ Still has only the `_example` seed row |
| **check.jsonl** | ❌ Still has only the `_example` seed row |
| **Scope** | Audit settings page UI logic: OCR section, output/parsing section, advanced & cross-tab logic |
| **Out of Scope** | Not specified |
| **Owner** | @lan |

**Key findings produced** (shared with fix-all-logic via jsonl):
- **OCR Section** (ocr-section-logic.md): 11 issues found (2 HIGH: prompt_preset hidden for layout_block, missing fields)
- **Output/Parsing** (output-parsing-logic.md): 6 issues found (1 CRITICAL: layout assist dead code in v2 endpoint)
- **Advanced/Cross** (advanced-cross-logic.md): 3 issues found (empty heading glitch, unconditional visual assist modes, 3 missing UI fields)

**Key status**: Research is complete but the task has never been `start`ed. No PRD exists. jsonl not curated.

---

### Task D: `05-13-refactor-settings-page-by-backend-flow` — 重构设置页面:基于后端处理流程

| Attribute | Value |
|-----------|-------|
| **Status** | `in_progress` |
| **PRD** | ✅ Detailed PRD (flow-based settings redesign with presets) |
| **Research** | ✅ 1 file: `backend-flow.md` (comprehensive 643-line pipeline analysis) |
| **implement.jsonl** | ✅ Curated (backend-flow research + PRD) |
| **check.jsonl** | ✅ Curated (same) |
| **Implementation** | ✅ Complete per `implementation-summary.md` |
| **Scope** | Restructure settings page UI: 4-tab → flow-based single page with presets, conditional display, user-friendly terminology |
| **Out of Scope** | Backend API changes, adding/removing config items, mobile |
| **Owner** | @lan |

**Key output**: Implemented 5 new components (`quick-presets`, `parsing-method-section`, `ocr-strategy-section`, `output-quality-section`, `general-advanced-section`) + refactored `settings/page.tsx`. Old 3 components (`basic-settings`, `ocr-settings`, `advanced-settings`) still exist but are orphaned.

---

### Task E: `05-14-home-model-sync` — 首页OCR/Layout模型与设置不同步

| Attribute | Value |
|-----------|-------|
| **Status** | `in_progress` |
| **PRD** | ✅ Well-defined, narrow scope (2 specific fixes) |
| **Research** | ❌ None (scope is small and clear) |
| **implement.jsonl** | ❌ Still has only `_example` seed row |
| **check.jsonl** | ❌ Still has only `_example` seed row |
| **Scope** | Fix QuickConfigPanel: (1) OCR model dropdown uses real models not hardcoded; (2) Layout model dropdown filters to downloaded only |
| **Out of Scope** | Settings page, backend logic, model download flow |
| **Owner** | @lan |

---

### Archived: `05-05-ocr-status-sync`

| Attribute | Value |
|-----------|-------|
| **Status** | Archived (not in active tasks list) |
| **Research** | 4 files (adaptive-ocr-fallback, backend-bug-review, pdf-upload-job-submission-bugs, settings-model-status-bugs) |
| **Relevance** | Historical research only; may contain useful background but not part of current workflow |

---

## 2. Overlap Matrix

### 2.1 Direct Overlaps

| Pair | Overlap Description | Severity |
|------|---------------------|----------|
| **C ↔ B** (settings-logic-audit ↔ fix-all-logic) | C's research is B's implementation spec. C has no PRD and is still in planning. B is in_progress but depends on an un-started task. **Dependency chain is inverted.** | 🔴 |
| **A ↔ C** (comprehensive-audit ↔ settings-logic-audit) | Both independently found the same 3 missing UI fields (`ocrPaddleVlDocparserMaxSidePx`, `ocrAiPageConcurrencyAuto`, `ocrAiBlockConcurrency`). Duplicate research effort. | 🟡 |
| **A ↔ E** (comprehensive-audit ↔ home-model-sync) | A found `capability` param not sent to POST /api/v1/models. E touches model fetching in QuickConfigPanel. If E adds model-filtering fixes, it should use `capability` correctly. | 🟢 |
| **B → D** (fix-all-logic touches refactored components) | B's fixes target the OCR/Output/Advanced sections that D just created. If B's changes conflict with D's component architecture, merge issues arise. | 🟡 |
| **C ↔ D** (settings-logic-audit audits D's output) | C's issues cover components D created. This is proper QA, but C hasn't been started — the issues are documented but not actioned through a formal fix cycle. | 🟡 |
| **B ⚠ Dead Code** (layout assist) | B's title includes "v2布局辅助死代码" — this is a **backend** issue in `job_config.py:389-391` where `enable_layout_assist` is hardcoded `False`. Fixing it requires backend changes, but B's scope is described as "UI logic defects". This is a scope mismatch. | 🔴 |

### 2.2 Dependency Graph

```
comprehensive-audit (A) [in_progress]
  ├── findings → fix-all-logic (B) [in_progress]  (informal)
  └── findings → home-model-sync (E) [in_progress] (informal)

settings-logic-audit (C) [planning]
  ├── research → fix-all-logic (B) [in_progress]  (formal: jsonl reference!)
  └── (should PRD → task start, but blocked)

refactor-settings-page (D) [in_progress - done]
  └── created components that B & C analyze

home-model-sync (E) [in_progress]
  └── no formal dependencies
```

**Broken chain**: C → B is the strongest dependency (formal jsonl reference), but C is the least complete task (no PRD, no start, no jsonl curation).

---

## 3. Per-Task Boundary Summary (One-Liner)

| Task Slug | One-Line Boundary |
|-----------|-------------------|
| `comprehensive-audit` | Front-to-back dead code census: finds orphans, unused exports, and missing features — record-only, no fixes. |
| `fix-all-logic` | Fixes UI logic bugs (conditional display, missing inputs, dead toggles) in refactored settings components — but title includes layout-assist dead code which is a backend fix. |
| `settings-logic-audit` | Audit of refactored settings UI: OCR section logic errors, output/parsing conditional display bugs, advanced cross-tab issues — research done, task not started. |
| `refactor-settings-page-by-backend-flow` | Restructured settings from 4-tab to flow-based single page with presets — implementation complete. |
| `home-model-sync` | Narrow: fix QuickConfigPanel OCR model fetching + layout model download filtering — no settings page changes. |

---

## 4. Recommendations for This Parent Task

### 4.1 Phase Priority

1. **Document architecture & naming first** — the value of this task is in clarifying concepts, not in pushing more code
2. **Diagnose the task chain** — the C→B dependency is broken and needs fixing before those two tasks proceed
3. **Identify truly cross-cutting issues** — layout assist dead code, naming inconsistencies, parse provider mapping

### 4.2 What This Task Should Own

| Scope | Why |
|-------|-----|
| **Architecture flow diagram** | End-to-end pipeline: Web → API → Job → Queue → Worker → OCR → PPT. Not done comprehensively by any task. |
| **Domain naming vocabulary** | Map `parse_engine_mode` ↔ frontend `ParseEngineMode` ↔ UI labels. Map `ocr_provider` ↔ `OcrProvider` ↔ UI labels. Identify value drift (e.g., backend accepts `"paddle"` + `"paddle_local"` as legacy aliases but frontend type doesn't include them). |
| **Parse provider mapping verification** | `missing-features.md` Finding #6 flagged that frontend `"local_ocr"` / `"remote_ocr"` may not map cleanly to backend `"local"` / `"v2"`. This must be verified. |
| **Task boundary reconciliation** | This document. Drive decisions: merge C into B? Close A? |
| **Naming cleanup plan** | List of renames, deprecations, and term alignments across frontend↔backend↔UI. |

### 4.3 What This Task Should NOT Duplicate

| Scope | Reason | Delegate To |
|-------|--------|-------------|
| Fixing UI conditional display bugs | Already in scope for B (fix-all-logic) | `fix-all-logic` |
| Adding missing UI fields | Already in scope for B | `fix-all-logic` |
| Model syncing on QuickConfigPanel | Already scoped in E | `home-model-sync` |
| Dead code removal | A found them but is record-only; B or this task can decide to clean up | Decision after this task |
| Re-refactoring settings page | D already completed this | Already done; avoid rework |

### 4.4 Critical Issues Requiring Cross-Task Coordination

| Issue | Affects Tasks | Recommendation |
|-------|---------------|----------------|
| Layout assist dead code (v2 endpoint hardcodes `False`) | B (title mentions it), A (found it), this task | **This is a backend fix**, not pure UI logic. B's title is misleading. Decide: should this parent task own the backend fix, or scope it separately? |
| settings-logic-audit (C) never started | C (blocked), B (depends on C) | Either (a) merge C's research into B as implement spec and archive C, OR (b) start C properly (PRD + jsonl + start) before B continues. Option (a) is faster. |
| 3 missing UI fields identified twice | A, C | Already tracked by both. Ensure B covers them without duplicate effort. |
| `parse_provider` mapping from frontend to backend | A (flagged), this task | This is a core architecture question. This task should own the investigation and resolution plan. |

### 4.5 Proposed Next Steps

1. **Write architecture flow doc** — `research/architecture-flow.md`
2. **Write naming vocabulary doc** — `research/naming-vocabulary.md`
3. **Write parse-provider mapping verification** — `research/parse-provider-mapping.md`
4. **Resolve task chain C→B**:
   - Option A: Merge `settings-logic-audit` into `fix-all-logic`, archive C
   - Option B: Start C properly, let B wait
   - Recommend: **Option A** — C's research IS already the spec for B; no need for a separate audit task
5. **Decide layout assist dead code handling**:
   - If backend fix: this parent task owns it (it's architecture-level)
   - If frontend-only: B owns it
   - Recommend: **this parent task** — the root cause is at the API schema layer (`job_config.py`)

---

## 5. Key Observations

### 5.1 Task Naming Problems (This Task's Namesake)

| Current Name | Problem |
|-------------|---------|
| `fix-all-logic` | "all logic" is too vague; includes backend dead code that shouldn't be there; doesn't reflect actual scope |
| `settings-logic-audit` vs `refactor-settings-page-by-backend-flow` | Both touch settings; one audits new UI while other built it; naming doesn't convey the dependency |
| `comprehensive-audit` | "Comprehensive" sets wrong expectations — doesn't cover backend logic bugs (those are in C/B) |
| `home-model-sync` | Clear, good. No issues. |

### 5.2 jsonl Curation Gaps

| Task | implement.jsonl | check.jsonl | Status |
|------|-----------------|-------------|--------|
| comprehensive-audit | ✅ Curated | ✅ Minimum | OK |
| fix-all-logic | ✅ Curated | ✅ Minimum | OK (uses external research) |
| **settings-logic-audit** | ❌ Seed only | ❌ Seed only | **Blocked** |
| refactor-settings-page | ✅ Curated | ✅ Curated | OK |
| **home-model-sync** | ❌ Seed only | ❌ Seed only | **Blocked** |

### 5.3 Research Quality & Duplication

- `comprehensive-audit/research/missing-features.md` Finding #6: **Parse provider mismatch** — frontend uses `"local_ocr"` / `"remote_ocr"` but backend accepts `"local"` / `"v2"`. This is a critical architecture-level finding that no current task owns fixing.
- `comprehensive-audit/research/dead-frontend.md` and `settings-logic-audit/research/advanced-cross-logic.md` both independently found the same 3 missing UI fields.
- `refactor-settings-page-by-backend-flow/research/backend-flow.md` is the most comprehensive pipeline document (643 lines) — this parent task should build on it, not redo it.

---

## Caveats / Not Found

- `fix-all-logic` has NO PRD — its scope can only be inferred from its task title and jsonl references. The title mentions "v2布局辅助死代码" but the research files focus on frontend UI logic. Likely a title scoping error.
- `settings-logic-audit` cannot be started (`task.py start`) until its jsonl is curated. No progress is possible on this task until that's done.
- The `05-05-ocr-status-sync` task has 4 research files not referenced anywhere — may contain useful context for architecture understanding.
- Not checked: whether the `capability` param gap (comprehensive-audit finding) affects home-model-sync's OCR model fetching fix.
- Not checked: actual runtime behavior of `parseEngineMode` → `parse_provider` conversion — this is flagged for verification.
