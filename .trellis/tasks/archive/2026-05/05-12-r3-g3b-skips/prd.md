# R3-G3b: Round 2 skipped items

## Goal

Handle 3 items voluntarily skipped in Round 2: settings/page.tsx OCR area extraction, jobs.py shared core function, models.py download module isolation.

## Requirements

### G1: `settings/page.tsx` OCR area extraction
`web/src/app/settings/page.tsx` — ~20 useState tightly coupled. Try to extract the OCR settings section into a sub-component. If the coupling is too tight, document why and skip.

### G2: `jobs.py` shared `_create_job_core()`
`api/app/routers/jobs.py` — v1 and v2 job creation share significant logic. Try to extract a shared helper. If parameter patterns diverge too much, document and skip.

### G3: `models.py` download module independent
`api/app/routers/models.py` — `_download_tasks` is a module-level global. Try to isolate download logic into a separate module. If global state makes this impossible without refactoring, document and skip.

## Acceptance Criteria

- [ ] G1: OCR section extracted into sub-component OR documented why impossible
- [ ] G2: Shared `_create_job_core()` helper OR documented why v1/v2 diverge too much
- [ ] G3: Download logic in separate module OR documented why global state prevents it
- [ ] py_compile pass, tsc --noEmit pass

## Out of Scope

- Full settings page rewrite
- jobs.py architecture changes
- models.py state management overhaul

## Technical Notes

- These items were voluntarily skipped in Round 2 due to tight coupling
- G1: ~20 useStates in settings/page.tsx make extraction risky
- G2: v1 and v2 job creation have diverging parameter patterns
- G3: `_download_tasks` module-level dict makes extraction complex
