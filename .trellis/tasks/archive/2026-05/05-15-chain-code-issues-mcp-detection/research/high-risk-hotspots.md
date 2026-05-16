# Research: High-Risk Chain-Code Hotspots

- **Query**: Inspect high-risk areas in the codebase for potential chain-code issues (missing imports, kwargs propagation, stage naming, model capability filtering, task lifecycle)
- **Scope**: internal code search
- **Date**: 2026-05-15

## Findings

### 1. OCR/AIOCR Modules — Missing Imports / Runtime NameError

#### Risk Level: HIGH — confirmed by recent fix history

| File Path | Description | Risk | Status |
|---|---|---|---|
| `api/app/convert/ocr/_ocr_manager.py` | Central OCR orchestration — imports 20+ internal symbols | Missing import → NameError at runtime during worker execution | **Still live** |
| `api/app/convert/ocr/_ai_layout_block.py` | AI layout block OCR — had missing `_CONFIDENCE_BYPASS_*` constants | NameError during `doc_parser` or `layout_block` chain | **Fixed** in `db14a15` |
| `api/app/convert/ocr/_ocr_postprocess.py` | Post-process with conditional imports at function level (line 596: `from .result_parsing import _normalize_bbox_px`) | Conditional import inside function body can fail silently | **Still live** |
| `api/app/convert/ocr/_ocr_postprocess.py` | Adaptive coverage threshold constants — line 596 area | Missing constants broke OCR merging | **Fixed** in `7c85d6c` |
| `api/app/convert/ocr/runtime_probe.py` | Local model probing with `try: except ImportError:` guards | Lazy imports mask missing packages until runtime | **Still live** |
| `api/app/convert/ocr/layout_models.py` | Layout model detection with multiple `except ImportError` blocks | Import errors caught and silently handled; may cause degraded UX | **Still live** |
| `api/app/convert/ocr/_paddle_ocr.py` | PaddleOCR — wraps optional dependency | Missing install → `ImportError` caught and re-raised | **Still live** |
| `api/app/convert/ocr/_baidu_ocr.py` | Baidu OCR — wraps optional dependency | Same pattern | **Still live** |

**Why risky**: The OCR module has the highest density of optional/lazy imports in the project. Missing symbols in `_ocr_manager.py:6-12` (which imports from `ai_client`, `base`, `deepseek_parser`, `routing`, `runtime_probe`, `utils`, `vendors`, `_ocr_remote`, `_baidu_ocr`, `_tesseract_ocr`, `_paddle_ocr`, `_ocr_constants`, `_ocr_postprocess`) could cause a NameError that crashes the entire worker job for that file path. Since the `create_ocr_manager` is wrapped in a `try/except Exception` in `ocr_runtime.py:477`, some failures are caught, but the try block is so broad that it can silently degrade to image-only output.

**Code pattern** (`_ocr_manager.py` line 6-12):
```python
from .ai_client import AiOcrClient, AiOcrTextRefiner, _clone_image_region_payload, ...
from .routing import ROUTE_KIND_HYBRID_AUTO, ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR, ...
from .utils import _coerce_bbox_xyxy, _is_paddleocr_vl_model
from .vendors import _normalize_ai_ocr_provider
```

An MCP check should verify that every symbol referenced in `_ocr_manager.py` actually exists in the target module (static analysis / AST cross-reference).

---

### 2. Job Config Flattening / Worker Kwargs Propagation

#### Risk Level: HIGH — fragile manual assembly

| File Path | Description | Risk | Status |
|---|---|---|---|
| `api/app/schemas/job_config.py` | `to_worker_kwargs()` (lines 394-462) | Manually assembled flat dict — easy to miss fields | **Still live** |
| `api/app/routers/jobs.py` | `_create_job_core` and `_job_create_from_config` (lines 761-915) | Also manually reads kwargs keys | **Still live** |
| `api/app/worker_helpers/_param_normalizer.py` | `normalize_job_options()` — reads `JobOptions` fields | Duplicate normalization after manual flattening | **Still live** |
| `api/tests/test_job_config_to_worker_kwargs.py` | Tests for kwargs propagation | Only tests layout_assist flags — **many fields untested** | **Still live** |

**Why risky**: The `JobConfig.to_worker_kwargs()` method at `job_config.py:380-463` manually builds a dict with ~50 keys. If a field is added to a sub-config (e.g., `OcrAiConfig`, `MineruConfig`) but forgotten in `to_worker_kwargs()`, it silently drops the field. The only test file (`test_job_config_to_worker_kwargs.py`) barely covers 3-4 fields out of 50+.

Recent commit `9481c8d fix(api): preserve layout assist flags in v2 job config` confirms this was a real production issue: flags were missing in the flat kwargs path.

**Code pattern** showing the manual assembly:
```python
# job_config.py:394-462
return {
    "enable_ocr": self.enable_ocr,
    "provider": self.llm.provider,
    "mineru_enable_formula": mineru.enable_formula,
    # ... ~45 more keys, one by one
}
```

An MCP check should verify that every field in `JobConfig` sub-config classes has a corresponding key in `to_worker_kwargs()`.

---

### 3. Job Stage Naming / Frontend–Backend Status Mapping

#### Risk Level: MODERATE — mostly aligned, but some hardcoded assumptions

| File Path | Description | Risk | Status |
|---|---|---|---|
| `api/app/models/job.py:22-33` | Backend `JobStage` enum | Canonical source of truth | **Still live** |
| `web/src/lib/job-status.ts:97-106` | Frontend `JOB_STAGE_FLOW` | Defines stage ordering for progress bar | **Still live** |
| `web/src/lib/job-status.ts:108-110` | `STAGE_FLOW_ALIASES` — maps `upload_received` → `queued` | Alias layer fixes one divergence | **Still live** |
| `web/src/lib/job-status.ts:67-77` | `JOB_STAGE_LABELS` — Chinese translations | Needs manual update when backend adds stages | **Still live** |
| `api/app/worker.py:720-730` | PPT stage kwargs — hardcoded progress range (84→85→97→98) | Magic numbers coupled to stage order | **Still live** |
| `api/app/worker_helpers/ppt_stage.py:91-173` | PPT stage progress reporting | Same hardcoded range assumptions | **Still live** |

**Stages inventory**:

| Backend JobStage | Frontend JOB_STAGE_FLOW | JOB_STAGE_LABELS | Mapped? |
|---|---|---|---|
| `upload_received` | Not in flow | `"上传接收"` | Aliased to `queued` |
| `queued` | ✅ index 0 | `"队列等待"` | ✅ |
| `parsing` | ✅ index 1 | `"解析 PDF"` | ✅ |
| `ocr` | ✅ index 2 | `"OCR 识别"` | ✅ |
| `layout_assist` | ✅ index 3 | `"版式辅助"` | ✅ |
| `pptx_generating` | ✅ index 4 | `"生成 PPTX"` | ✅ |
| `packaging` | ✅ index 5 | `"打包"` | ✅ |
| `cleanup` | ✅ index 6 | `"清理"` | ✅ |
| `done` | ✅ index 7 | `"已完成"` | ✅ |

**Why risky**: The frontend `JOB_STAGE_LABELS` is a plain `Record<string, string>`. If a new stage is added to the backend enum but not to the frontend labels dict, the UI shows the raw English stage key to users (line 35: `JOB_STAGE_LABELS[detail.stage] || detail.stage`).

The progress range magic numbers (84→85→97→98→100) are scattered across `worker.py` and `ppt_stage.py` and depend on stage ordering — if a new stage is inserted, these numbers are wrong.

Recent commit `0e09119 fix(web): align home stage naming with shared job stage contract` shows the mapping was recently repaired.

**MCP check**: List all `JobStage` enum values; for each, verify a key exists in `JOB_STAGE_LABELS`. Verify that the stage flow ordering matches the expected pipeline sequence.

---

### 4. Model Capability Filtering Propagation

#### Risk Level: MODERATE — heuristic-based, may misclassify

| File Path | Description | Risk | Status |
|---|---|---|---|
| `api/app/routers/_model_filtering.py` | Capability detection — regex + structured signal | Heuristic may misclassify new model families | **Still live** |
| `api/app/routers/models.py` | Uses `_model_matches_capability` | Capability filter affects user-facing model lists | **Still live** |

**Key symbols and patterns**:

- `_model_filtering.py:13` — `_SUPPORTED_CAPABILITIES = {"all", "vision", "ocr"}`
- `_model_filtering.py:41-45` — `_OCR_NAME_PATTERNS = (r"\bocr\b", r"paddleocr", r"mineru")` — very narrow OCR detection
- `_model_filtering.py:103-109` — `_OCR_ONLY_VISION_NAME_PATTERNS` — has known OCR-specific model prefixes
- `_model_filtering.py:110-120` — `_OTHER_VISION_FAMILY_PATTERNS` — known VL model families
- `is_vision_model()` (line 303) — uses structural signal first, then falls back to heuristics
- `is_ocr_model()` (line 320) — only checks explicit name patterns

**Why risky**: `is_ocr_model()` at line 320-321 simply delegates to `is_explicit_ocr_model()`, which only checks `\bocr\b`, `paddleocr`, `mineru`. A new OCR-specific model whose name doesn't contain "ocr" (e.g., a hypothetical "doc-vision" model) would be classified as `vision` instead of `ocr`. This means the `?capability=ocr` filter could miss valid OCR models.

Conversely, `is_vision_model()` has comprehensive coverage of known families (OpenAI GPT-4o, Claude 3/4, Gemini, Qwen VL, GLM-V, InternVL, Pixtral, LLaVA, etc.) — but any new vision model family not matching these patterns would be classified as non-vision and excluded from `?capability=vision`.

The `_PROVIDER_ALIASES` dict (lines 23-40) has good coverage but needs maintenance for new providers.

**MCP check**: Verify that the OCR name patterns match known production OCR models. Check that vision name patterns cover all major VL model families.

---

### 5. Task/Archive Lifecycle and Finish-Work Bookkeeping Pitfalls

#### Risk Level: HIGH — multiple stale-complete tasks in git history

| File Path | Description | Risk | Status |
|---|---|---|---|
| `.trellis/scripts/task.py` | Task CLI — `archive`, `finish`, `start` commands | Lifecycle requires precise sequence | **Still live** |
| `.trellis/scripts/common/active_task.py` | Active task resolution | Session identity issues block `task.py start` | **Still live** |
| `.trellis/spec/guides/task-governance-thinking-guide.md` | Governance guide — addresses stale-complete tasks | Exists as documentation; not enforced | **Still live** |
| `.trellis/workflow.md` | Phase 3.4 commit + Phase 3.5 finish-work | Multi-step wrap-up easy to skip | **Still live** |

**Known lifecycle chain** (Phase 3.4 → 3.5):
1. Implement + Check → **code committed** (Phase 3.4 by main agent)
2. Spec update (Phase 3.3)
3. Commit changes (Phase 3.4 — main agent drives git)
4. **Critical: dirty tree check** — agent should run `git status` before suggesting `/finish-work`
5. `/finish-work` → archives task + records session

**Evidence of past failures**:
- `53a46e5 chore(task): archive active-tasks-governance` — tasks archived retroactively
- `7ed542a chore(task): archive stale active tasks governance cleanup` — governance cleanup
- `a6c360d chore(task): archive architecture-flow-naming-cleanup` — another retroactive archive
- These 3 governance commits in the recent log suggest the lifecycle was not followed during those tasks themselves, requiring a separate governance task to clean up.

**Current task state**: The task must pass through `planning` → (brainstorm → PRD → research → jsonl curation → `task.py start`) → `in_progress` → (implement → check → spec update → commit → `/finish-work`).

**MCP check**: Before calling `/finish-work`, the check SHOULD verify that:
1. Working tree is clean (no dirty files outside `.trellis/`)
2. All code changes are committed
3. PRD exit criteria are met
4. `implement.jsonl` / `check.jsonl` were curated for this task if sub-agents were used

---

## Cross-Cutting Risks

### A. Silent Exception Swallowing

**File**: `api/app/worker_helpers/ocr_runtime.py:477-527`
When `create_ocr_manager()` raises, the entire OCR runtime setup is caught, logged as a warning, and the manager is set to `None`. The job continues as image-only. **Any** NameError/ImportError inside the complex import chain is silently swallowed.

### B. Duplicate Normalization Paths

The `JobConfig.to_worker_kwargs()` → `validate_and_normalize_job_options()` → `normalize_job_options()` chain normalizes the same values at multiple layers. If the structured config validates types at the Pydantic level but the worker kwargs path doesn't re-validate, type mismatches can slip through.

### C. Progress Range Magic Numbers

Progress ranges are hardcoded and coupled to stage ordering:
- `worker.py:335-337` parsing: 5
- `worker.py:463` parsing done: 22
- `worker.py:523-525` OCR prep: 35
- `ppt_stage.py:92` ppt starting: 84
- `ppt_stage.py:105` ppt generating: 85-97
- `ppt_stage.py:166` packaging: 98
- `worker.py:783` done: 100

Inserting or reordering stages breaks these ranges.

---

## Caveats / Not Found

- No direct evidence of cyclic imports in the OCR module — all imports are acyclic, but the fan-in to `_ocr_manager.py` is high
- No `NameError` classes are defined in the OCR module — the risk is Python runtime `NameError` raised by the interpreter when a globally-imported symbol doesn't exist
- The `oauth_passport` variable issue in `e7909ed fix(api): undefined filename variable in _create_job_core streaming path` is already fixed on main
