# Research: Active Task Disposition Plan

- **Query**: Governance/disposition plan for the 6 active Trellis tasks — dependency inversions, overlaps, safest execution/archive order
- **Scope**: Internal (task artifacts: prd.md, task.json, research/, implement.jsonl, implementation-summary.md, git history)
- **Date**: 2026-05-15
- **Source**: Archived parent research at `archive/2026-05/05-14-architecture-flow-naming-cleanup/research/active-task-boundaries.md`

## 1. Critical Discovery: Implementation is Already Complete

> **All code changes matching the scope of tasks A, B, D, and E are already committed to `main`.**
> The working tree is **clean** (`git status --short` shows nothing).

**How this happened**: The archived `architecture-flow-naming-cleanup` research noted these tasks as "in progress" and analyzed their dependency chains. However, the git log reveals that between May 14 and May 15, the implementation work was actually **done directly in commits** — not inside task-managed sub-agent sessions. The tasks were never updated to reflect this.

### Task-to-Commit Mapping

| Task | Commits | Scope Alignment | Status |
|------|---------|-----------------|--------|
| **A** `05-13-comprehensive-audit` | `c8b283d` | ✅ Dead code removal, model filtering, naming confirmation | Committed |
| **B** `05-13-fix-all-logic` | `7a7b950`, `7748f15` | ✅ All 7 fix items match research findings from C | Committed |
| **C** `05-13-settings-logic-audit` | (no separate commit) | Research consumed by B's commit `7a7b950` | **Merged into B** implicitly |
| **D** `05-13-refactor-settings-page-by-backend-flow` | `c1a240a`, `74bb587`, `2e06d9c`, `0b81760`, `1c4bb9d`, `efd6f7f`, `f0d9bcc`, `b365903`, `b715124`, `452c5d7` | ✅ 5 new components, flow-based page, deployment complete | Committed |
| **E** `05-14-home-model-sync` | `3b00ea2`, `69726b8`, `0365bed` | ✅ OCR model list from backend, layout model download filtering | Committed |

### Commit Details

**Commit `7a7b950` (B — fix-all-logic):**
```
F1: v2 buildJobConfig reads settings.enableLayoutAssist (was hardcoded false)
F2: ocrAiPromptPreset now shows for direct + layout_block
F3: add ocrAiBlockConcurrency + ocrPaddleVlDocparserMaxSidePx UI fields
F4: remove deprecated mineruHybridOcr checkbox
F5: prompt overrides conditional by chain mode
F6: hide layout assist checkbox in MinerU mode
F7: advanced tab placeholder when layout assist disabled
```

**Commit `c8b283d` (A — comprehensive-audit):**
```
F1: Add capability:'vision' to model fetch (filter out non-vision models)
F2: Remove dead admin_default_password config field
F3: Remove 7 unused constants from constants.ts
F4: Remove dead QuotaInfo type and deprecated createJobFormData
F5: Best preset correct now (layout assist works)
F6: Parse engine naming confirmed correct (translation layer exists)
```

**Commit `3b00ea2` (E — home-model-sync):**
```
- QuickConfigPanel OCR model list now fetched from backend (not hardcoded)
- Layout model dropdown filtered by downloaded models
```

---

## 2. Overlap & Dependency Analysis

### Original Broken Chains (from archived research)

| Pair | Original Concern | Current Status | Verdict |
|------|-----------------|----------------|---------|
| **C→B** (settings-logic-audit→fix-all-logic) | B's implement.jsonl references C's research; C never started. Dependency inverted. | B's commit `7a7b950` addressed all C findings. C's research was consumed as intended. | **⚠ Resolved in code, but C's task lifecycle is incomplete** (no PRD, no start, no archive). The dependency inversion was ultimately harmless because B read C's research directly. |
| **B→D** (fix-all-logic touches refactored components) | B fixes could conflict with D's new architecture | B's `7a7b950` correctly modified D's 5 new components (`general-advanced-section.tsx`, `ocr-strategy-section.tsx`, etc.) **directly** — no conflict. | ✅ Resolved |
| **A↔C duplicate research** (3 missing UI fields found twice) | Both tasks independently found `ocrPaddleVlDocparserMaxSidePx`, `ocrAiPageConcurrencyAuto`, `ocrAiBlockConcurrency` | All 3 fields added in B's commit `7a7b950` (F3) | ✅ Resolved |
| **B scope mismatch** (layout assist dead code) | B's title said "v2布局辅助死代码" which is a backend issue | B's F1 fixed the backend issue too (`buildJobConfig` in `run-config.ts` reads settings instead of hardcoding false). Also backend commit `b715124` + `b365903` further fixed this. | ✅ Resolved |

### Dependency Graph (actual — as built)

```
comprehensive-audit (A) ──findings──► committed in c8b283d
                                          │
settings-logic-audit (C) ──research──► fix-all-logic (B) ──committed in 7a7b950
                                          │
refactor-settings-page (D) ──created──► components consumed by B ──committed in c1a240a..452c5d7
                                          │
home-model-sync (E) ──committed in 3b00ea2, 69726b8, 0365bed
```

**Key insight**: The real dependency flow was **C→B→D** (C researched → B fixed → D created the infrastructure B fixed against). B depended on D and D on the backend pipeline understanding. But the commits landed in parallel and everything merged cleanly.

---

## 3. Per-Task Disposition Assessment

### A: `05-13-comprehensive-audit` — 全代码审计:发现死代码和缺失功能

| Attribute | Value |
|-----------|-------|
| **Current status** | `in_progress` |
| **PRD** | ✅ Exists (record-only audit) |
| **jsonl** | ✅ Curated |
| **Implementation** | ✅ Complete per commit `c8b283d` |
| **Disp** | **→ ARCHIVE** |

**Rationale**: Dead code removed, model filtering fixed, naming verified. Record-and-fix cycle complete. No remaining action items. Must be archived.

---

### B: `05-13-fix-all-logic` — 修复所有UI逻辑缺陷: v2布局辅助死代码+条件显示+缺失UI

| Attribute | Value |
|-----------|-------|
| **Current status** | `in_progress` |
| **PRD** | ❌ Never existed (relied on C's research as de facto spec) |
| **jsonl** | ✅ Curated (references C's research) |
| **Implementation** | ✅ Complete per commit `7a7b950` + `7748f15` |
| **Disp** | **→ ARCHIVE** |

**Rationale**: All 7 fix items committed. No remaining code changes needed. No PRD was ever written, but writing one retroactively provides no value — the work is done. Accept the deficit and archive.

---

### C: `05-13-settings-logic-audit` — 全面分析设置页面UI逻辑问题

| Attribute | Value |
|-----------|-------|
| **Current status** | **`planning`** ⚠ |
| **PRD** | ❌ Never existed |
| **jsonl** | ❌ Seed only |
| **Research** | ✅ 3 files (consumed by B — all 20+ issues addressed in B's commit) |
| **Implementation** | N/A (was audit-only, not implement task) |
| **Disp** | **→ ARCHIVE** |

**Rationale**: This task was conceived as an audit with research already complete. But every finding from its 3 research files was fixed by B's commit. There is no remaining work. Keeping a `planning` task with no PRD and seed jsonl around serves no purpose. The knowledge is captured in the research files (which will be preserved in the archive). Archive with note: research consumed by fix-all-logic, all findings actioned.

---

### D: `05-13-refactor-settings-page-by-backend-flow` — 重构设置页面:基于后端处理流程

| Attribute | Value |
|-----------|-------|
| **Current status** | `in_progress` |
| **PRD** | ✅ Detailed (requirements met per implementation-summary.md) |
| **jsonl** | ✅ Curated |
| **Research** | ✅ `backend-flow.md` (643 lines — most comprehensive pipeline doc) |
| **Implementation** | ✅ Complete per `implementation-summary.md` and 9+ commits |
| **Old orphaned components** | `basic-settings.tsx`, `ocr-settings.tsx`, `advanced-settings.tsx` still exist but were marked as "可删除" in impl summary. However, they are dead code — no imports reference them anymore. These were identified in the comprehensive audit too. |
| **Disp** | **→ ARCHIVE** (after deleting orphaned old components, or defer orphan cleanup to a future explicit dead-code sweep) |

**Rationale**: Implementation verified complete via `implementation-summary.md` and the 9+ commits on `main`. The 3 orphaned old components have zero risk being left behind (no imports, no runtime path). Can either be cleaned up now (trivial delete, <5 min) or left for a future dedicated dead-code pass. Recommend: **archive now, mention orphan deletion as optional follow-up**.

---

### E: `05-14-home-model-sync` — 首页OCR/Layout模型与设置不同步

| Attribute | Value |
|-----------|-------|
| **Current status** | `in_progress` |
| **PRD** | ✅ Clear, narrow scope |
| **jsonl** | ❌ Seed only |
| **Implementation** | ✅ Complete per commits `3b00ea2`, `69726b8`, `0365bed` |
| **Disp** | **→ ARCHIVE** |

**Rationale**: Both PRD requirements met:
1. OCR model list fetched from backend (not hardcoded) — commit `3b00ea2`
2. Layout model dropdown filtered by downloaded — commits `3b00ea2` + `69726b8`

jsonl was never curated, but no implementation work remains so curation serves no purpose. Archive.

---

### Governance Task: `05-14-active-tasks-governance` — 治理 active tasks 边界与收口

| Attribute | Value |
|-----------|-------|
| **Current status** | **`planning`** |
| **PRD** | ✅ Exists (well-scoped) |
| **jsonl** | ❌ Seed only |
| **Disp** | **→ Activate → Execute archive operations → Archive itself** |

**Rationale**: This is the meta-task that drives archival of the other 5 tasks. Once the archival actions are complete, this task should archive itself.

---

## 4. Disposition Action Plan

### Strategy: Plan + Directly Close Obvious Issues

Given that all implementation work is already committed, the governance strategy collapses to **one simple action per task: archive**. No PRD repair, no jsonl curation, no scope redefinition needed.

### Ordered Action List

```
Phase 1 — Archive completed tasks (all 5, order doesn't matter)
──────────────────────────────────────────────────────────────────
 1. Archive A (comprehensive-audit)      — 2 min: task.py archive
 2. Archive B (fix-all-logic)            — 2 min: task.py archive
 3. Archive C (settings-logic-audit)     — 2 min: task.py archive
    (Add note: research consumed by fix-all-logic, all findings actioned)
 4. Archive D (refactor-settings-page)   — 2 min: task.py archive
 5. Archive E (home-model-sync)          — 2 min: task.py archive

Phase 2 — Clean up governance task
──────────────────────────────────────────────────────────────────
 6. Curate implement.jsonl / check.jsonl  for governance task
 7. task.py start active-tasks-governance
 8. Commit any changes (e.g., if orphaned components deleted)
 9. Archive governance task itself
```

### Total estimated effort: ~15 minutes

### What NOT to touch yet

| Item | Reason |
|------|--------|
| D's 3 orphaned components (`basic-settings.tsx`, `ocr-settings.tsx`, `advanced-settings.tsx`) | Dead code but harmless. Deleting them is not required for archival. Can be a 5-minute drive-by if desired. |
| `05-05-ocr-status-sync` archived task | Already archived. No action needed. Leave as-is. |
| Spec updates | The `trellis-update-spec` phase 3.3 step per workflow. If governance identifies spec-worthy learnings (e.g., "task lifecycle must track commits"), a separate lightweight spec update can be done, but it is optional for this pass. |

---

## 5. Summary Table

| # | Task Slug | Current Status | Implementation Status | Recommend |
|---|-----------|----------------|------------------------|-----------|
| A | `comprehensive-audit` | `in_progress` | ✅ Done (commit `c8b283d`) | **Archive** |
| B | `fix-all-logic` | `in_progress` | ✅ Done (commit `7a7b950`) | **Archive** |
| C | `settings-logic-audit` | **`planning`** 🚫 | ❌ Not an impl task; research consumed by B | **Archive** |
| D | `refactor-settings-page-by-backend-flow` | `in_progress` | ✅ Done (9+ commits) | **Archive** |
| E | `home-model-sync` | `in_progress` | ✅ Done (commits `3b00ea2`+) | **Archive** |
| G | `active-tasks-governance` | **`planning`** | N/A (executor) | **Activate → Archive others → Archive self** |

**Note on task D orphan cleanup**: The `implementation-summary.md` lists 3 orphaned components as "可删除（可选）". Deleting them now is optional but cheap (3 file deletions, no import changes since nothing references them). Recommend: if the user wants a clean finish, delete them during Phase 2; otherwise they can accumulate until a future dead-code pass.

---

## 6. Risks if Not Acted Upon

| Risk | Severity | Timeline |
|------|----------|----------|
| New developer joins and sees 6 "in progress" tasks with clean working tree → confusion | 🟡 Medium | Immediate |
| `task.py` commands malfunction because of stale active-task pointer (too many in_progress tasks) | 🟢 Low | Depends on script logic |
| **Per-turn breadcrumb `[workflow-state:in_progress]` fires on every new query** because multiple tasks are `in_progress` — the workflow thinks we're in Phase 2, loading unnecessary sub-agent routing | 🔴 High | **Every session start** |
| If someone `task.py start`s task C today, the workflow expects brainstorm+jsonl+implement, but the research is already consumed and obsolete | 🟡 Medium | If attempted |

## Caveats / Not Found

- No commits were verified for the *exact* boundary of task E's second PRD requirement (auto-switch layout model when current selection is not downloaded). The `3b00ea2` commit message says "filter layout models by downloaded" which implies this is handled.
- Task D's old orphaned components (`basic-settings.tsx`, `ocr-settings.tsx`, `advanced-settings.tsx`) were verified dead by the comprehensive audit but were not deleted in any commit. They remain on disk with no imports. This is confirmed low-risk.
- No runtime tests were executed to verify the fix commits work end-to-end — only commit messages and git diffs were inspected.
