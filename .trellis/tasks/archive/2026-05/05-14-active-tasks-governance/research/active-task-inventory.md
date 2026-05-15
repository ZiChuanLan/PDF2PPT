# Research: Active Task Inventory & Governance Analysis

- **Query**: Systematic inventory of all 6 active Trellis tasks for governance planning — status, artifact completeness, overlap, and recommended disposition.
- **Scope**: internal (task.json, prd.md, implement.jsonl, check.jsonl, research/, git history)
- **Date**: 2026-05-15
- **Source**: Direct inspection of each task directory + `.trellis/tasks/archive/2026-05/05-14-architecture-flow-naming-cleanup/research/active-task-boundaries.md` (previous boundary analysis)

---

## Task A: `05-13-comprehensive-audit` — 全代码审计:发现死代码和缺失功能

| Attribute | Value |
|-----------|-------|
| **Status** | `in_progress` |
| **PRD** | ✅ Has PRD — scope: full-stack dead code audit, record-only, no fixes |
| **Research** | ✅ 3 files: `dead-backend.md`, `dead-frontend.md`, `missing-features.md` |
| **implement.jsonl** | ✅ Curated (frontend quality-guidelines.md + component-guidelines.md + 3 research files) |
| **check.jsonl** | ✅ Minimal (quality-guidelines.md only) |
| **Scope summary** | Front-to-back dead code census. Found ~23 unused exports, 7 dead constants, 3 missing UI fields, layout assist dead code, `capability` param gap. |
| **Completion signal** | Research is done; key findings match git commit `c8b283d fix: comprehensive audit — model filtering, dead code cleanup` which applied these findings. Further discoveries were passed to downstream tasks. |
| **Blockers** | None intrinsic — the audit itself is complete. Its "record-only" nature means it will never be "implemented", just referenced. |
| **Recommended disposition** | **Archive** — the research is complete and findings have already been consumed by downstream tasks. Keeping it `in_progress` adds noise to the active task list. If new dead code is discovered later, a fresh task is cleaner. |

---

## Task B: `05-13-fix-all-logic` — 修复所有UI逻辑缺陷: v2布局辅助死代码+条件显示+缺失UI

| Attribute | Value |
|-----------|-------|
| **Status** | `in_progress` |
| **PRD** | ❌ **No PRD** — scope only inferable from title + jsonl research refs |
| **Research** | ❌ None owned — depends on `05-13-settings-logic-audit/research/` (3 files) |
| **implement.jsonl** | ✅ Curated (quality + component guidelines + 3 external research files) |
| **check.jsonl** | ✅ Minimal (quality-guidelines.md only) |
| **Scope summary** | Fix UI logic defects: conditional visibility bugs, missing UI fields, layout assist dead code (though the latter is a **backend** issue — scope mismatch in title). |
| **Completion signal** | **Strong evidence of completion**: git commit `7a7b950` message reads exactly `fix: all UI logic issues — v2 layout assist, conditional display, missing fields`. This directly matches the task title. Additional commits `9481c8d` (layout assist flags in v2 job config) and `0365bed` etc. cover the remaining scope. |
| **Blockers** | None remaining — the implementation appears done per git history. |
| **Recommended disposition** | **Archive** — the fix has been committed. The missing PRD is a metadata gap but not a reason to keep it active when the code change is already landed. Rename would be pointless post-hoc. |

---

## Task C: `05-13-settings-logic-audit` — 全面分析设置页面UI逻辑问题

| Attribute | Value |
|-----------|-------|
| **Status** | `planning` |
| **PRD** | ❌ **No PRD** |
| **Research** | ✅ 3 files: `advanced-cross-logic.md`, `ocr-section-logic.md`, `output-parsing-logic.md` (detailed findings) |
| **implement.jsonl** | ❌ **Seed only** (only `_example` line) |
| **check.jsonl** | ❌ **Seed only** (only `_example` line) |
| **Scope summary** | Audit of refactored settings UI: OCR section logic errors (11 issues), output/parsing conditional display (6 issues), advanced/cross-tab issues (3 issues). |
| **Completion signal** | Research is complete. However, the research findings are **already referenced by task B's implement.jsonl** — meaning the research output has already been consumed as task B's implementation spec. Git commit `7a7b950` ("fix: all UI logic issues") appears to have addressed many of the findings. |
| **Blockers** | Status = `planning` but never started. Cannot transition to `in_progress` without PRD + curated jsonl. However, since the research has already been consumed and the fixes have been committed, starting this task now would only add a "formalize research" step. |
| **Broken chain** | This is the classic dependency inversion: task C (planning) owns research that task B (in_progress) depends on. C's research IS B's implementation spec. |
| **Recommended disposition** | **Archive** — the research was effectively the spec for task B, which is now implemented and committed. Starting C as a standalone audit after the fixes are already in would be circular. Option: if any findings were NOT covered by B, create a focused follow-up task instead. |

---

## Task D: `05-13-refactor-settings-page-by-backend-flow` — 重构设置页面:基于后端处理流程

| Attribute | Value |
|-----------|-------|
| **Status** | `in_progress` |
| **PRD** | ✅ Comprehensive PRD (192 lines — flow-based design, presets, terminology) |
| **Research** | ✅ 1 file: `backend-flow.md` (643-line pipeline analysis) |
| **implement.jsonl** | ✅ Curated (research + PRD) |
| **check.jsonl** | ✅ Curated (same) |
| **implementation-summary.md** | ✅ Exists — details 5 new components, refactored page.tsx, 3 orphaned old components, build/tc passed |
| **Scope summary** | Restructured settings from 4-tab to flow-based single page with presets, conditional display, user-friendly terminology. |
| **Completion signal** | **Strong**: implementation-summary.md explicitly confirms TypeScript compiles, Next.js builds, all components correctly imported, no runtime errors. Old components marked as "keep until confirmed". Git commits in the `refactor(web)` space support this. |
| **Blockers** | The 3 orphaned old components (`basic-settings.tsx`, `ocr-settings.tsx`, `advanced-settings.tsx`) are still on disk. This is not a blocker per se — the implementation works without deletion. However, they should not cause confusion if kept. |
| **Recommended disposition** | **Archive** — implementation is complete and verified per implementation-summary.md. Optionally do a clean-up pass to delete orphaned old components before archiving, but that's cosmetic. |

---

## Task E: `05-14-home-model-sync` — 首页OCR/Layout模型与设置不同步

| Attribute | Value |
|-----------|-------|
| **Status** | `in_progress` |
| **PRD** | ✅ Well-defined, narrow scope (2 specific fixes: OCR model fetching + Layout model download filter) |
| **Research** | ❌ None (scope is small and clear — no dedicated research needed) |
| **implement.jsonl** | ❌ **Seed only** (only `_example` line) |
| **check.jsonl** | ❌ **Seed only** (only `_example` line) |
| **Scope summary** | (1) QuickConfigPanel OCR dropdown uses `fetchModels()` instead of hardcoded list. (2) Layout model dropdown filters to `downloadedLayoutModels` only. |
| **Completion signal** | **Strong evidence of completion**: multiple git commits directly match:
  - `3b00ea2 fix(web): sync OCR model list from backend, filter layout models by downloaded`
  - `69726b8 fix(web): filter layout model dropdown by backend status in settings OCR tab`
  - `0365bed fix(web): show all layout models in settings with backend download status`
  - `6c52c1c fix(web): remove double /api/v1 prefix in model fetch call`
  - `1cfe5db fix(web): PaddleOCR model status retry, AbortError suppression, inline download`
  - `9fc2980 fix(web): show '已下载' state on download button when model completed` |
| **Blockers** | jsonl not curated, but the implementation is already in main. Curation would only matter if re-running trellis-check or spawning a new implement sub-agent. |
| **Recommended disposition** | **Archive** — implementation is done and committed to main. The missing jsonl curation is a workflow formality that no longer serves a purpose since the code is already merged. Consider whether the settings-side model sync (separate from QuickConfigPanel) was also included — git shows settings-side commits too. |

---

## Task 0: `05-14-active-tasks-governance` — 治理 active tasks 边界与收口 (Current Task)

| Attribute | Value |
|-----------|-------|
| **Status** | `planning` |
| **PRD** | ✅ Exists (86 lines — clear scope: governance only, not product code) |
| **Research** | ✅ Being produced now (this file) |
| **implement.jsonl** | ❌ **Seed only** — to be curated after research completes |
| **check.jsonl** | ❌ **Seed only** — same |
| **Scope summary** | Systematic review of all 5 sibling active tasks; produce disposition recommendations; fix broken task chains (C→B dependency inversion); archive/merge as needed. |
| **Blockers** | None yet — this task's research is the prerequisite for the governance actions. |
| **Recommended disposition** | N/A (current task) — the governance plan itself is the output. After execution, this task archives itself. |

---

## Git History Cross-Reference (Completion Validation)

Recent commits (all on `main`) show substantial completion across all active tasks:

| Commit | Matches Task | Notes |
|--------|-------------|-------|
| `a6c360d chore(task): archive architecture-flow-naming-cleanup` | (archived) | Previous cleanup already archived |
| `884ba48 docs(spec): add job config flattening and stage naming rules` | (spec update) | Architecture decisions captured |
| `0e09119 fix(web): align home stage naming with shared job stage contract` | E (home-model-sync) | Home stage naming alignment |
| `9481c8d fix(api): preserve layout assist flags in v2 job config` | B (fix-all-logic) | Layout assist backend fix |
| `7c85d6c fix(ocr): add missing adaptive coverage threshold constants` | B | OCR fix |
| `db14a15 fix(ocr): add missing _CONFIDENCE_BYPASS_* constants` | B | OCR fix |
| `e7909ed fix(api): undefined filename variable in _create_job_core` | B | API bug fix |
| `0365bed fix(web): show all layout models in settings...` | E | Model sync |
| `69726b8 fix(web): filter layout model dropdown...` | E | Model sync |
| `3b00ea2 fix(web): sync OCR model list from backend...` | E | Model sync |
| `1cfe5db fix(web): PaddleOCR model status retry...` | E | Model sync |
| `452c5d7 refactor(web): comprehensive frontend optimization` | D (settings refactor) | Component splitting |
| `9fc2980 fix(web): show '已下载' state...` | E | Model sync |
| `7a7b950 fix: all UI logic issues...` | B | **Exact match** to B's title |
| `7748f15 fix(web): improve settings UI logic...` | B | Conditional display |
| `c8b283d fix: comprehensive audit...` | A | Audit findings applied |
| `6c52c1c fix(web): remove double /api/v1 prefix...` | E | Model fetch fix |

**Key takeaway**: The vast majority (possibly all) of the implementation scope across tasks A, B, D, and E appears to have been committed to `main`. Only C (settings-logic-audit) has research but no implementation task — and that research was already consumed by B.

---

## Overlap & Cross-Reference Matrix (Updating Previous Analysis)

| Pair | Overlap | Severity | Status Change Since Previous Analysis |
|------|---------|----------|---------------------------------------|
| **C ↔ B** | C's research = B's impl spec; dependency inverted | 🔴 Still broken but moot | Research consumed; B is committed. C's research is now historical. |
| **A ↔ C** | 3 missing fields found twice | 🟡 Resolved | Both identified the same gaps; B's commit covers them. |
| **A ↔ E** | `capability` param | 🟢 Unclear | `capability` gap was noted by A. E's model sync commits may or may not have addressed it — need verification. |
| **B ↔ D** | B fixes D's refactored components | 🟡 Likely merged | Commits are on main — no conflict visible. |
| **C ↔ D** | C audits D's output | 🟡 Resolved | C's audit findings consumed by B; B's fix landed. |
| **B vs title** | Layout assist dead code = backend, not UI | 🔴 Scope mismatch | Commit `9481c8d fix(api): preserve layout assist flags` was a **backend** fix, proving the scope mismatch. The task title was inaccurate. |

---

## Disposition Summary

| Task | Status | PRD | jsonl Curated | Research | Scope Clear | Likely Done | Recommendation |
|------|--------|-----|---------------|----------|-------------|-------------|----------------|
| **A** comprehensive-audit | in_progress | ✅ | ✅ | ✅ 3 files | ✅ Record-only | ✅ Yes (audit complete, findings consumed) | **Archive** |
| **B** fix-all-logic | in_progress | ❌ Missing | ✅ (curated, ext refs) | ❌ (depends on C) | Partial (title has scope mismatch) | ✅ Yes (commit `7a7b950` matches title) | **Archive** |
| **C** settings-logic-audit | planning | ❌ Missing | ❌ Seed only | ✅ 3 files | ✅ Audit complete | ✅ Research consumed by B; B's fix landed | **Archive** |
| **D** refactor-settings-page | in_progress | ✅ | ✅ | ✅ 1 file | ✅ Clear | ✅ Yes (implementation-summary.md confirms) | **Archive** |
| **E** home-model-sync | in_progress | ✅ | ❌ Seed only | ❌ None needed | ✅ Clear, narrow | ✅ Yes (multiple matching commits) | **Archive** |
| **0** active-tasks-governance | planning | ✅ | ❌ Seed only | 🔄 In progress | ✅ Governance only | ❌ This IS the governance task | **Keep active → execute → archive** |

### Key Observations for Governance Action

1. **All 5 target tasks (A, B, C, D, E) appear to be effectively complete.** The implementation work across all scopes has matching git commits on `main`. None of these tasks have pending uncommitted code.

2. **The most critical broken chain (C→B) is no longer blocking** — task C's research was consumed by task B as implementation spec, and commit `7a7b950` ("fix: all UI logic issues") covers the combined scope. Task C never needed to transition past `planning`.

3. **There may be a small residual scope not covered:**
   - Whether the `capability` param gap (comprehensive-audit finding #6) was addressed by the home-model-sync commits needs verification.
   - The 3 orphaned old settings components (`basic-settings.tsx`, `ocr-settings.tsx`, `advanced-settings.tsx`) from task D are still on disk.

4. **The governance task (0) can now execute rapidly**: with all 5 targets ready for archive, the governance actions are straightforward. Focus on:
   - Verifying any residual gaps (capability param, orphaned components)
   - Archiving all 5 tasks
   - Capturing lessons in spec (task naming discipline, avoid C→B dependency inversion pattern)

---

## Caveats

- This inventory is based on task directory inspection + git log. It does not verify runtime behavior (e.g., whether `capability` param actually works now).
- The boundary analysis from the archived `architecture-flow-naming-cleanup` task was used as a cross-reference but independently verified.
- Task B's `implement.jsonl` references research files from task C. After archiving both, those paths will break in the historical record. Consider whether to copy the research files into task B's directory before archive, or leave the archived references as-is (they still resolve as the path won't change).
- Task E's settings-side model sync commits may overlap with task D's refactored settings components. No conflict was detected from git log but a runtime verification could be warranted.
- The `05-05-ocr-status-sync` archived task has 4 research files not reviewed here — may contain relevant background not considered.
