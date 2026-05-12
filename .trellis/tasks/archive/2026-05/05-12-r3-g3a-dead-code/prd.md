# R3-G3a: dead code + misc cleanup

## Goal

Remove dead code (F1), consolidate duplicate imports (F2), fix frontend test stub (F3).

## Requirements

### F1: Delete `pptx_generator.py` shim
`api/app/convert/pptx_generator.py` — a 12-line backward-compat shim. Verify no callers still import from it, then delete the file.

### F2: Conditional numpy imports → module top
11 locations in the codebase have `import numpy as np` inside functions instead of at module top. numpy is a hard dependency. Find and move them to top-level imports.

### F3: Fix `web/package.json` test:unit stub
Current stub claims "no repository tests". Replace with a real npm script that at minimum runs `tsc --noEmit` (type check) since there are no frontend tests yet. Update the test:unit script description.

## Acceptance Criteria

- [ ] pptx_generator.py deleted (after confirming no callers)
- [ ] All conditional `import numpy as np` moved to top-level
- [ ] web/package.json test:unit runs real type check
- [ ] py_compile pass, tsc --noEmit pass

## Out of Scope

- Adding Vitest or frontend tests
- Full numpy audit beyond import locations
