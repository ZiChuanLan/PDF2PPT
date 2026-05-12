# Research: Untouched Modules Audit (Comprehensive Refactor Round 2)

- **Query**: Audit directories untouched by previous refactor for large files, duplicate code patterns, unused code, dead imports, and simplification opportunities.
- **Scope**: internal
- **Date**: 2026-05-11

## Findings

---

## 1. `api/app/convert/ocr/` — OCR Package (14 files, ~13,499 lines)

### File Line Counts

| File Path | Lines | Risk |
|---|---|---|
| `api/app/convert/ocr/ai_client.py` | 5,581 | **CRITICAL** — largest file in project |
| `api/app/convert/ocr/local_providers.py` | 4,320 | **CRITICAL** — 5 classes + ~30 helpers |
| `api/app/convert/ocr/layout_models.py` | 571 | Moderate |
| `api/app/convert/ocr/deepseek_parser.py` | 489 | Moderate |
| `api/app/convert/ocr/result_parsing.py` | 460 | Moderate |
| `api/app/convert/ocr/runtime_probe.py` | 447 | Moderate |
| `api/app/convert/ocr/vendors.py` | 411 | Moderate |
| `api/app/convert/ocr/json_extraction.py` | 324 | Low |
| `api/app/convert/ocr/base.py` | 294 | Low |
| `api/app/convert/ocr/prompts.py` | 259 | Low |
| `api/app/convert/ocr/routing.py` | 193 | Low |
| `api/app/convert/ocr/utils.py` | 152 | Low |
| `api/app/convert/ocr/__init__.py` | 98 | Low |

### CRITICAL: `ai_client.py` (5,581 lines)

This is the single largest file in the entire project. Contains:

- **Class `AiOcrClient(OcrProvider)`** (lines 799-4527, ~3,700 lines) — an enormous class with ~100 methods covering:
  - PaddleDoc parser integration (~30 methods: `_get_paddle_doc_parser`, `_run_paddle_doc_predict_with_timeout`, `_ocr_image_with_paddle_doc_parser`, etc.)
  - Local layout block OCR (~20 methods: `_get_local_layout_model`, `_ocr_local_layout_block_crop`, etc.)
  - AI chat completions for OCR (`_chat_completion`, `ocr_image`)
  - Image region detection (`detect_image_regions`, `_detect_image_regions_with_prompt`)
  - Layout geometry, DeepSeek parsing, result normalization
  - Internal rate limiting classes: `_AiRequestRateLimiter` (lines 502-591), `_AiRequestReservation` (lines 489-500)
- **Class `AiOcrTextRefiner`** (lines 4586-5581, ~995 lines) — text refinement with AI chat completion
- **~10 module-level helper functions** (lines 193-734) — Paddle timeout, retry config, rate limiting, etc.

**Opportunities**: The PaddleDoc parser subsystem (~1,500 lines), local layout block OCR (~1,000 lines), and AI chat completion pipeline (~1,200 lines) could each be separate modules.

### CRITICAL: `local_providers.py` (4,320 lines)

Massive file cramming 5 classes and ~30 private helper functions:

- **Classes** (6 total):
  - `RemoteOcrClientSpec` (line 530) — small config dataclass
  - `BaiduOcrClient(OcrProvider)` (line 670, ~193 lines)
  - `TesseractOcrClient(OcrProvider)` (line 863, ~325 lines)
  - `PaddleOcrClient(OcrProvider)` (line 1188, ~357 lines)
  - `LazyPaddleOcrClient(OcrProvider)` (line 1545, ~20 lines — thin wrapper)
  - `OcrManager` (line 1565, ~912 lines) — orchestrator with provider selection, line merging, text deduplication, quality notes
- **Module-level functions** (lines 530-669, 2477-4320): remote OCR client factory, bbox/IoU helpers, line merging, deduplication, noise filtering, ink detection
- **Entry point**: `ocr_image_to_elements()` (line 3769) — the public API

**Opportunities**: Each OCR provider (Baidu, Tesseract, Paddle) could be its own file. The OcrManager's post-processing chain (line merging, dedup, noise filtering, ink detection — ~700 lines) is a candidate for extraction.

### Duplicate Code Patterns in OCR Package

#### DUPLICATE 1: `_contains_cjk()` — identical in 2 files
- `api/app/convert/ocr/local_providers.py` line 2675
- `api/app/convert/pptx/font_utils.py` line 25

Both contain the same Unicode-range checks (CJK Unified Ideographs, Extension A, Hiragana+Katakana, Hangul Syllables). The `font_utils.py` version has slightly different edge-case handling (`text or ""` vs `text`).

#### DUPLICATE 2: `_is_cjk_char()` — identical in 2 files
- `api/app/convert/ocr/local_providers.py` line 2689
- `api/app/convert/pptx/font_utils.py` line 38

Both use identical Unicode-range checks.

#### DUPLICATE 3: `_normalize_bbox_px()` — identical implementation in 2 files
- `api/app/convert/ocr/local_providers.py` line 2710
- `api/app/convert/ocr/result_parsing.py` line 96

Both follow the exact same logic: check list[4] → float cast → NaN guard → (min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1)). `ai_client.py` imports from `result_parsing.py`, but `local_providers.py` uses its own copy.

#### DUPLICATE 4: Bbox normalization scattered across files
Four different functions with overlapping purposes:
- `_coerce_bbox_xyxy` in `ocr/utils.py` line 41 (handles list, tuple, dict, numpy)
- `_normalize_bbox_px` in `ocr/local_providers.py` line 2710 (list only)
- `_normalize_bbox_px` in `ocr/result_parsing.py` line 96 (list only, identical copy)
- `_coerce_bbox_pt` in `pptx/bbox_utils.py` line 21 (delegates to `require_bbox_xyxy`)

### Dead / Backward-Compat Code

- `ocr/__init__.py` lines 51-54: Four backward-compat aliases that all resolve to `AiOcrVendorAdapter`:
  ```python
  SiliconFlowAiOcrAdapter = AiOcrVendorAdapter
  PpioAiOcrAdapter = AiOcrVendorAdapter
  NovitaAiOcrAdapter = AiOcrVendorAdapter
  DeepSeekAiOcrAdapter = AiOcrVendorAdapter
  ```

### `# type: ignore` Comments
- `ai_client.py`: 3 ignores (paddle doc, chat completion args, PIL)
- `local_providers.py`: 1 ignore (PIL getpixel)
- `layout_models.py`: 1 ignore (paddlex import)
- 5 ignores across remaining OCR files

---

## 2. `api/app/convert/pdf_parser.py` (340 lines)

### Structure

A well-sized module with a clear purpose: extract PDF text layer → IR.

- 1 public function: `parse_pdf_to_ir()`
- ~12 private helpers: `_bbox_to_list`, `_color_int_to_hex`, `_iter_text_line_elements`, `_extract_text_block_info`, etc.
- Uses `pymupdf` (no multi-vendor abstraction needed)

### Observations
- 3 `# type: ignore[attr-defined]` for PyMuPDF methods (`find_tables`, `get_text`)
- Dependency on `app.models.error.AppException` — tight coupling to error model
- `_EXT_TO_MIME` dictionary at module level — hardcoded MIME map

### Caveats
No major issues. File size is moderate. If PyMuPDF extraction logic grows, splitting into a dedicated module would be appropriate.

---

## 3. `api/app/worker.py` (1,178 lines) + `worker_helpers/` (10 files, ~2,921 lines)

### Worker Line Counts

| File Path | Lines | Risk |
|---|---|---|
| `api/app/worker.py` | 1,178 | **HIGH** — giant function |
| `api/app/worker_helpers/ocr_stage.py` | 1,249 | **HIGH** |
| `api/app/worker_helpers/ocr_runtime.py` | 646 | Moderate |
| `api/app/worker_helpers/debug.py` | 299 | Low |
| `api/app/worker_helpers/layout_assist_stage.py` | 192 | Low |
| `api/app/worker_helpers/layout.py` | 184 | Low |
| `api/app/worker_helpers/ppt_stage.py` | 174 | Low |
| `api/app/worker_helpers/geometry_utils.py` | 68 | Low |
| `api/app/worker_helpers/guarded.py` | 63 | Low |
| `api/app/worker_helpers/__init__.py` | 46 | Low |

### CRITICAL: `process_pdf_job()` has 58 parameters (lines 236-296)

```python
def process_pdf_job(
    job_id: str,
    *,
    enable_ocr: bool = False,
    retain_process_artifacts: bool = False,
    remove_footer_notebooklm: bool = False,
    text_erase_mode: str | None = None,
    enable_layout_assist: bool = False,
    layout_assist_apply_image_regions: bool = False,
    provider: str | None = None,
    api_key: str | None = None,
    # ... 46 more parameters
    ocr_strict_mode: bool | None = True,
    job_timeout: str | None = None,
) -> None:
```

- After the signature, lines 308-366 explicitly reference all parameters to suppress linter warnings (unused unused-variable assignment)
- This is a **parameter object** anti-pattern — all options from the API are passed as individual keyword arguments

### CRITICAL: Massive parameter normalization block (~300 lines)

Lines 436-~750 contain local `_normalize_float()` and `_normalize_int()` helper functions, which are then applied to every single numeric parameter individually. Example pattern repeated ~15 times:

```python
normalized_ocr_ai_page_concurrency = _normalize_int(
    ocr_ai_page_concurrency,
    default=ocr_concurrency["page_concurrency_default"],
    low=_OCR_AI_PAGE_CONCURRENCY_LOW,
    high=ocr_concurrency["page_concurrency_max"],
)
```

### Worker Helpers Structure

The `worker_helpers/` directory was created in the Round 1 refactor. It's well-modularized:

- `ocr_stage.py` (1,249 lines) — still large but focused: runs OCR stage orchestration, page processing loop, parallel AI OCR, progress tracking
- `ocr_runtime.py` (646 lines) — OCR runtime setup and route planning
- `layout_assist_stage.py`, `layout.py`, `ppt_stage.py`, `debug.py`, `geometry_utils.py`, `guarded.py` — all under 300 lines

### Observations
- `_normalize_int()` and `_normalize_float()` are locally defined inner functions in `process_pdf_job` — they exist ONLY inside that function's scope, meaning they cannot be reused or tested independently
- The job path helper `_job_dir()` (line 211) is 4 lines — trivial
- Job secrets are fetched from Redis at the start (lines 301-306) — mixes concerns early

---

## 4. `api/app/convert/pptx/` — PPTX Package (14 files, excluding generator/main.py)

### File Line Counts

| File Path | Lines | Risk |
|---|---|---|
| `api/app/convert/pptx/scanned_page.py` | 3,971 | **CRITICAL** |
| `api/app/convert/pptx/font_utils.py` | 1,038 | **HIGH** |
| `api/app/convert/pptx/preview.py` | 379 | Moderate |
| `api/app/convert/pptx/generator/footer.py` | 243 | Low |
| `api/app/convert/pptx/generator/probing.py` | 178 | Low |
| `api/app/convert/pptx/bbox_utils.py` | 166 | Low |
| `api/app/convert/pptx/generator/_parameter_parser.py` | 137 | Low |
| `api/app/convert/pptx/generator/text_erase.py` | 126 | Low |
| `api/app/convert/pptx/slide_builder.py` | 87 | Low |
| `api/app/convert/pptx/generator/markdown_utils.py` | 51 | Low |
| `api/app/convert/pptx/color_utils.py` | 35 | Low |
| `api/app/convert/pptx/constants.py` | 23 | Low |
| `api/app/convert/pptx/generator/__init__.py` | 20 | Low |
| `api/app/convert/pptx/__init__.py` | 5 | Low |

### CRITICAL: `scanned_page.py` (3,971 lines)

This is the second-largest file in the project. 39 private functions with no classes except one internal dataclass (`_ScannedImageRegionInfo` at line 1730):

- **PDF rendering**: `_render_pdf_page_png()` (line 116) — PyMuPDF page to PIL image
- **Image region detection**: `_detect_image_regions_from_render()` (line 166, ~388 lines)
- **Shape analysis**: `_analyze_shape_crop()` (line 554), `_is_shape_confirmed_crop()` (line 676)
- **Color sampling**: `_sample_pixmap_rgb()` (line 690), `_pix_to_rgb_array()` (line 719), `_sample_bbox_background_rgb()` (line 762), `_sample_bbox_text_rgb()` (line 821)
- **Ink detection**: `_estimate_bbox_ink_line_count()` (line 924)
- **Region erasure**: `_erase_regions_in_render_image()` (line 1133, ~597 lines — very large function)
- **Region tightening**: `_tighten_scanned_image_region_bbox_by_visual_bounds()` (line 1990, ~241 lines)
- **Region merging**: `_try_merge_fragmented_scanned_image_regions()` (line 3086, ~290 lines)
- **Region building**: `_build_scanned_image_region_infos()` (line 3376, ~435 lines)
- **Text cutouts**: `_apply_text_cutouts_to_scanned_image_region_crops()` (line 3899)
- **Baseline OCR height estimation**: `_estimate_baseline_ocr_line_height_pt()` (line 2311)

**11 separate `import numpy as np` calls** inside individual functions (lines 82, 723, 859, 939, 1385, 2003), each guarded. Numpy is imported on-demand per-function rather than at module level.

### CRITICAL: `font_utils.py` (1,038 lines)

20 private functions dealing with text measurement and fitting:

- `_measure_text_width_pt()` (line 105) — PIL ImageFont-based text measurement
- `_measure_text_lines()` (line 147) — Multi-line text measurement
- `_wrap_paragraph_to_lines()` (line 249, ~108 lines) — CJK-aware text wrapping
- `_fit_font_size_pt()` (line 372, ~69 lines) — Auto-size text to fit box
- `_fit_mineru_text_style()` (line 525, ~224 lines) — MinerU text style fitting
- `_fit_ocr_text_style()` (line 854, ~184 lines) — OCR text style fitting
- `_prefer_wrap_for_ocr_text()` (line 749), `_resolve_visual_wrap_override_for_ocr_text()` (line 817)

**Duplicate**: Contains `_contains_cjk()` (line 25) and `_is_cjk_char()` (line 38) — identical to the versions in `ocr/local_providers.py`.

**Duplicate**: `_contains_cjk()` and `_is_cjk_char()` share the same CJK Unicode range definitions — `_contains_cjk` could trivially call `_is_cjk_char` instead of duplicating the ranges.

---

## 5. Other `api/app/convert/` Files

### File Line Counts

| File Path | Lines | Risk |
|---|---|---|
| `api/app/convert/mineru_adapter.py` | 1,967 | **HIGH** |
| `api/app/convert/baidu_doc_adapter.py` | 1,178 | **HIGH** |
| `api/app/convert/llm_adapter.py` | 824 | Moderate |
| `api/app/convert/geometry.py` | 91 | Low |
| `api/app/convert/pptx_generator.py` | 12 | Low (shim) |
| `api/app/convert/__init__.py` | 12 | Low |

### `mineru_adapter.py` (1,967 lines) — 41 private functions

Flat file with many small extraction helpers:

- `_extract_text()` (line 628), `_extract_bbox()` (line 669), `_extract_item_kind()` (line 698), `_extract_image_rel_path()` (line 732), `_extract_page_idx()` (line 567)
- `_extract_content_items()` (line 323), `_extract_content_items_from_layout()` (line 535) — two-stage extraction
- `_build_ir_from_mineru_outputs()` (line 826, ~316 lines) — core IR builder
- `_crop_pdf_region_png()` (line 756) — region cropping
- `_recover_missing_notebooklm_footer_elements()` (line 1324) — notebooklm footer recovery
- `class MineruClient` (line 1411, ~286 lines) — API client
- `parse_pdf_to_ir_with_mineru()` (line 1697) — public entry point

### `baidu_doc_adapter.py` (1,178 lines) — 28 private functions

Structurally similar to mineru_adapter (same pattern: private extraction helpers → abstract parse/flatten → build IR):

- `_extract_text()` (line 408), `_extract_bbox_candidate()` (line 313), `_extract_position_bbox_candidate()` (line 282), `_extract_kind()` (line 432), `_extract_image_path()` (line 452), `_extract_page_idx()` (line 266)
- `_collect_page_payload()` (line 538), `_collect_content_items()` (line 713), `_build_content_item()` (line 659)
- `_normalize_bbox_to_pdf_pt()` (line 470) — bbox normalization
- `class BaiduDocParserClient` (line 898, ~98 lines) — API client
- `parse_pdf_to_ir_with_baidu_doc()` (line 1024) — public entry point

### Duplicate Patterns: mineru_adapter.py ↔ baidu_doc_adapter.py

| Function | mineru_adapter.py | baidu_doc_adapter.py | Notes |
|---|---|---|---|
| `_extract_page_idx()` | line 567 | line 266 | Different signatures (dict vs Any, different fallback defaults) but same purpose |
| `_extract_text()` | line 628 | line 408 | Same purpose, different implementation |
| `_extract_bbox()` / `_extract_bbox_candidate()` | line 669 | line 313 | Same purpose, different names |
| `_is_image_like_kind()` | line 725 | line 463 | **IDENTICAL** implementation (both check `lowered` against `_IMAGE_KIND_TOKENS`) |

Both adapters follow the same architectural pattern: Fetch JSON → extract pages → extract items → build IR elements. They could share a base class or shared extraction utilities.

### `llm_adapter.py` (824 lines)

- `class LlmProvider(ABC)` (line 50) — abstract base
- `class OpenAiProvider(LlmProvider)` (line 468, ~112 lines)
- `class AnthropicProvider(LlmProvider)` (line 580, ~76 lines)
- `class LlmLayoutService` (line 656, ~168 lines)
- ~12 module-level helpers for prompt building, validation, image processing

### `geometry.py` (91 lines) — Lightweight

Contains `coerce_bbox_xyxy()` used by `ocr/utils.py`. Clean, focused utility.

### `pptx_generator.py` (12 lines) — Backward-compat shim

Simply re-exports from the new `pptx/generator/` structure. Could be deleted if all callers migrated.

### `convert/__init__.py` (12 lines)

Tries to import `parse_pdf_to_ir` from `pdf_parser`; falls back to `None` if PyMuPDF unavailable. Only exposes `parse_pdf_to_ir`.

---

## Cross-Cutting Issues

### Issue 1: CJK Character Classification Duplication

`_contains_cjk()` and `_is_cjk_char()` are defined identically in two files:
- `api/app/convert/ocr/local_providers.py` (lines 2675-2698)
- `api/app/convert/pptx/font_utils.py` (lines 25-47)

Both use the same CJK Unicode ranges. `_is_cjk_char` is a single-character version of `_contains_cjk`. These should be merged into a shared utility.

### Issue 2: Bbox Normalization Fragmentation

At least four functions serve overlapping bbox normalization purposes across the codebase:
- `ocr/utils.py::_coerce_bbox_xyxy()` — most comprehensive (handles list, tuple, dict, numpy, polygon points)
- `ocr/result_parsing.py::_normalize_bbox_px()` — identical copy of `local_providers.py::_normalize_bbox_px()`
- `ocr/local_providers.py::_normalize_bbox_px()` — canonical (?) version
- `pptx/bbox_utils.py::_coerce_bbox_pt()` — thin wrapper around `require_bbox_xyxy`

### Issue 3: Conditional Numpy Imports

Numpy is conditionally imported in 11 places across 4 files:
- `ocr/ai_client.py` — 3 places (lines 2513, 5043, 5202)
- `ocr/local_providers.py` — 2 places (lines 1264, 3957)
- `pptx/scanned_page.py` — 6 places (lines 82, 723, 859, 939, 1385, 2003), each with `# type: ignore`

All use the pattern: `import numpy as np` inside a function scope with a try/except or with `# type: ignore`. This suggests numpy is optional but heavily used.

### Issue 4: Adapter Pattern Duplication

`mineru_adapter.py` and `baidu_doc_adapter.py` follow near-identical architectural patterns:
1. Private extraction helpers (text, bbox, kind, page_idx, image_path)
2. Collection functions (collect content items, collect page payloads)
3. A client class for API calls
4. A public `parse_pdf_to_ir_with_*` entry point
5. Footer/brand text normalization

They could share base extraction utilities but are currently completely independent.

### Issue 5: Worker Parameter Object Anti-Pattern

`process_pdf_job()` has 58 parameters that are all individually passed through the RQ job queue. A single `JobOptions` dataclass or TypedDict could encapsulate this configuration, dramatically reducing the function signature and the parameter normalization boilerplate.

### Issue 6: `# type: ignore` Count

- `api/app/convert/ocr/`: 6 ignores
- `api/app/convert/pptx/`: 11 ignores (mostly numpy + PIL)
- `api/app/convert/pdf_parser.py`: 3 ignores
- `api/app/convert/llm_adapter.py`: 3 ignores
- `api/app/convert/mineru_adapter.py`: 1 ignore
- `api/app/worker.py`: 1 ignore
- **Total**: ~25 type ignores across audited modules

---

## Summary Table

| Issue | Severity | Files Affected | Lines |
|---|---|---|---|
| `ai_client.py` monolithic class | CRITICAL | 1 | 5,581 |
| `local_providers.py` multi-class cramming | CRITICAL | 1 | 4,320 |
| `scanned_page.py` monolithic module | CRITICAL | 1 | 3,971 |
| `process_pdf_job` 58-param signature | HIGH | 1 | 1,178 |
| Worker normalization boilerplate | HIGH | 1 | ~300 |
| Adapter type duplication (mineru ↔ baidu) | HIGH | 2 | ~3,145 |
| `ocr_stage.py` large stage function | HIGH | 1 | 1,249 |
| `font_utils.py` text fitting complexity | HIGH | 1 | 1,038 |
| CJK helpers duplicated | MEDIUM | 2 | ~50 |
| `_normalize_bbox_px` duplicated | MEDIUM | 2 | ~30 |
| `_is_image_like_kind` duplicated | MEDIUM | 2 | ~14 |
| Backward-compat aliases (dead code) | LOW | 1 | 4 |
| Conditional numpy imports (11 sites) | LOW | 4 | ~20 |

---

## Caveats / Not Found

- Some files were intentionally left untouched in Round 1 because they are "leaf" modules that don't cause maintenance friction — e.g., `geometry.py` (91 lines), `constants.py` (23 lines), `slide_builder.py` (87 lines). These are fine as-is.
- The backward-compat aliases in `ocr/__init__.py` may have external callers in the frontend or test code — deletion requires verification of call sites.
- `pptx_generator.py` (12-line shim) may have external callers — deletion requires migration.
- No TODOs, FIXMEs, or HACKs were found in any audited files — the code is well-maintained but large.
