# Task Governance Thinking Guide

> **Purpose**: Decide whether a task is truly unfinished, or just stale-complete and ready to archive.

---

## The Problem

**Task metadata can drift behind delivered work.**

Common governance mistakes:
- Reopening a task just because its PRD or JSONL is incomplete
- Treating an old dependency inversion as still-live after the consuming fixes already landed
- Leaving many stale `in_progress` tasks active after the work is already on `main`
- Spending time backfilling historical task metadata instead of cleaning up the active-task list

---

## Before Repairing Task Metadata

### Step 1: Verify delivery state first

Before repairing PRDs, JSONL, or task chains, check whether the work is already delivered:

```bash
python3 ./.trellis/scripts/get_context.py --mode record
git status --porcelain
git log --oneline -20
```

Ask:
- Is the working tree clean?
- Do recent commits already match the task title/scope?
- Do sibling tasks or archived research show that the findings were already consumed?

### Step 2: Gather evidence from the task itself

Check the task directory and nearby research:

- `task.json`
- `prd.md`
- `implement.jsonl` / `check.jsonl`
- `research/*.md`
- `implementation-summary.md` or similar notes

**Important**: missing task artifacts do **not** automatically mean missing implementation.

### Step 3: Distinguish unfinished vs stale-complete

Use this split:

| State | Meaning | Normal action |
|------|---------|---------------|
| **Unfinished** | Work is still missing in code or validation | Continue / repair / re-scope |
| **Stale-complete** | Work already landed, but task lifecycle cleanup never happened | Archive based on evidence |

Evidence of **stale-complete** often includes:
- matching commits already on `main`
- clean working tree
- research findings already consumed by another task's implementation
- implementation summary or PRD showing intended scope is done

---

## Dependency Inversions: Live vs Historical

A dependency inversion is only actionable if it still blocks delivery.

Ask:
- Did the consuming task already land its fixes?
- Was the upstream research already consumed into committed code?
- Is there any remaining work that truly depends on repairing the old task chain?

If the answer is **no remaining blocker**, then the inversion is now **historical context**, not an active reason to reopen or prolong tasks.

---

## Archive-First Governance Rules

When many active tasks exist, prefer this order:

1. **Check whether the work is already shipped**
2. **Classify each task as unfinished or stale-complete**
3. **Archive stale-complete tasks with evidence**
4. **Only then repair truly active task chains or missing metadata**

This keeps the active-task list trustworthy and prevents governance work from turning into historical paperwork.

---

## When NOT to Archive Yet

Do **not** archive a task yet if any of these are true:

- The working tree still contains uncommitted implementation for that task
- Acceptance criteria are clearly unmet
- Research exists but no matching implementation ever landed
- Another active task still depends on unfinished outputs from it
- You cannot map the task scope to commits, artifacts, or current code behavior

---

## Minimal-Cleanup Principle

For already-shipped work:

- **Good**: archive the task with a short evidence-backed rationale
- **Good**: record that an earlier broken chain is now historical only
- **Bad**: retroactively rebuilding perfect PRDs / JSONL for old completed work
- **Bad**: expanding archive cleanup into unrelated feature work or repo-wide dead-code deletion

Only backfill historical task metadata if it is needed to safely continue new work.

---

## Batch Archive Checklist

Before batch-archiving stale tasks:

- [ ] Reviewed active tasks via `get_context.py --mode record`
- [ ] Confirmed matching commits or other strong completion evidence
- [ ] Confirmed the working tree is clean
- [ ] Distinguished live blockers from historical-only task-chain issues
- [ ] Verified no sibling task still needs unfinished outputs from the task being archived
- [ ] Kept cleanup scope smaller than feature-development scope

---

## Governance Heuristic

> **When task metadata and git history disagree, trust delivered evidence first, then clean up the task list to match reality.**
