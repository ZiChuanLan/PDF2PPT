# R3-G1a: worker.py refactor

## Goal

Refactor `api/app/worker.py` (1178 lines): introduce `JobOptions` dataclass to replace 58 keyword parameters, extract 300-line normalization boilerplate into a separate module.

## Requirements

1. Create `api/app/worker_helpers/_job_options.py` with `JobOptions` dataclass containing all 58 parameters
2. Update `process_pdf_job()` to accept `JobOptions` instead of 58 individual kwargs
3. Extract `_normalize_int()` / `_normalize_float()` + all normalization calls (~300 lines) → `api/app/worker_helpers/_param_normalizer.py`
4. Update callers in `api/app/routers/jobs.py` to construct `JobOptions` before enqueueing
5. Keep backward compatibility — public API `process_pdf_job()` signature must remain callable

## Acceptance Criteria

- [ ] py_compile pass for all modified files
- [ ] worker.py < 600 lines
- [ ] `JobOptions` dataclass validates all 58 parameters
- [ ] RQ job enqueue still works (same kwargs passed through)

## Out of Scope

- Functional changes to job processing
- Changing parameter names or defaults

## Technical Notes

- Lines 236-296: 58 keyword parameters
- Lines 308-366: unused-variable assignment to suppress linter (can remove after refactor)
- Lines 436-750: normalization boilerplate with `_normalize_int()` / `_normalize_float()` inner functions
- Caller in `jobs.py` creates kwargs dict then passes them to `process_pdf_job()`
