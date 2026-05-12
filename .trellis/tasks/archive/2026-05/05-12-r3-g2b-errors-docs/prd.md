# R3-G2b: error handling + docs

## Goal

Fix silent error catches in frontend hooks, unify logger usage in API routers, fix Makefile test description, and clarify config drift documentation.

## Requirements

### D1: `web/src/hooks/use-settings.ts` — 3 silent catches
Three catch blocks silently discard errors:
1. `fetchDeployMode()` — catch block
2. Settings load — catch block  
3. Auto-save — catch block
Fix: Add `console.error()` with descriptive message before re-throwing or handling.

### D2: `web/src/hooks/use-model-download.ts` — polling error silently swallowed
Fix: Add `console.error()` in the catch block.

### D3: `web/src/hooks/use-sse-job-tracking.ts` — 2 silent catches
Fix: Add `console.error()` with context in each catch block.

### D4: `web/src/app/page.tsx` — polling `silent` mode swallows errors
Find polling or SSE calls with silent error handling. Add `console.error()`.

### D5: `api/app/routers/models.py` — inconsistent logger usage
Line ~519 uses `logger.warning(msg, exc_info=True)` — should use `logger.exception(msg)` (which automatically includes traceback).

### D6: `api/app/routers/jobs.py` — cleanup path bare `except Exception` without logging
Fix: Add `logger.exception()` in the except block.

### E2: Makefile — "No repository tests" statement outdated
`Makefile` lines 120-121 claim "No repository tests" but there are ~20 test files in `api/tests/`. Fix the comment.

### E3: `.env.example` vs `config.py` — COOKIE_SECURE drift
`.env.example` has `COOKIE_SECURE=false` but `config.py` defaults to `True`. Add a comment in `.env.example` noting the default is `True` in code.

### E4: `.env.example` vs `config.py` — JOB_ROOT_DIR path inconsistency
`.env.example` has `JOB_ROOT_DIR=/app/data/jobs` (Docker) but `config.py` defaults to `data/jobs` (local). Add a comment in `.env.example` explaining the difference.

## Acceptance Criteria

- [ ] All silent catch blocks have console.error() or logger.exception()
- [ ] models.py uses logger.exception() not logger.warning(exc_info=True)
- [ ] Makefile comment updated to reflect actual test count
- [ ] .env.example comments clarify config.py defaults
- [ ] TypeScript compiles, Python py_compile passes

## Out of Scope

- Adding Sentry or error monitoring
- Retry logic for failed operations
- Full config documentation overhaul
