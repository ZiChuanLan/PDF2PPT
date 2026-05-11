# Research: PPTX Generator Monolith — Structure & Split Plan

- **Query**: Map the internal structure of `generator.py`, trace pipeline stages, identify module boundaries, propose split plan
- **Scope**: internal
- **Date**: 2026-05-10

## Findings

### 1. File-Level Overview

| File | LOC | Role |
|---|---|---|
| `generator.py` | 2221 | Main entrypoint: helpers + both page-type pipelines + presentation setup + IR validation |
| `scanned_page.py` | 3971 | Scanned-page rendering, image-region analysis, text erase, background sampling (already split) |
| `font_utils.py` | 1038 | Font mapping, CJK detection, text measurement, OCR/MinerU text fitting (already split) |
| `preview.py` | 379 | Final preview export, preview font loading (already split) |
| `bbox_utils.py` | 166 | BBox coercion, coordinate transforms, path helpers (already split) |
| `slide_builder.py` | 87 | Slide size type, transform, font-size inference, element iteration (already split) |
| `color_utils.py` | 35 | Hex→RGB, luma, color distance, contrast picking (already split) |
| `constants.py` | 23 | EMU/PT/Inch constants, SlideTransform dataclass (already split) |
| `__init__.py` | 5 | Public API: re-exports `generate_pptx_from_ir` |
| `pptx_generator.py` | 12 | Backward-compat shim to old import path `app.convert.pptx_generator` |

### 2. Top-Level Functions in `generator.py`

#### 2.1 Module-Level Regex Constants (lines 60–65)

Six compiled regex patterns for markdown stripping: headings, bullet lists, ordered lists, bold, inline code, links.

#### 2.2 Helper Functions (lines 68–637)

| # | Function | Lines | Responsibility | Callers (within file) |
|---|---|---|---|---|
| 1 | `_is_layout_parse_source` | 68–70 | Detect MinerU/Baidu text-parser sources | `generate_pptx_from_ir` (both branches), `_should_sample_local_text_colors` |
| 2 | `_maybe_export_final_preview_page_image` | 73–96 | Conditional wrapper for preview export | `generate_pptx_from_ir` (both branches) |
| 3 | `_should_probe_visual_wrap_for_ocr_text` | 99–137 | Heuristic: is a text box worth pixel-level line-count probing? | `generate_pptx_from_ir`, `_page_needs_ocr_sampling_render` |
| 4 | `_should_sample_local_text_colors` | 140–153 | Heuristic: is local bg/text color resampling needed? | `generate_pptx_from_ir`, `_page_needs_ocr_sampling_render` |
| 5 | `_page_needs_ocr_sampling_render` | 156–209 | Heuristic: does this page need an extra OCR sampling render? | `generate_pptx_from_ir` (text-page branch only) |
| 6 | `_should_center_scanned_heading` | 212–237 | Heuristic: does a scanned heading bbox look visually centered? | `generate_pptx_from_ir` (scanned-page branch only) |
| 7 | `_merge_text_erase_bboxes` | 240–361 | Merge nearby same-line erase boxes (iterative + sweep/union-find fast path) | `generate_pptx_from_ir` (scanned-page branch only) |
| 8 | `_sanitize_markdown_text` | 363–397 | Strip markdown markers from raw text | `generate_pptx_from_ir` (both branches), `_page_needs_ocr_sampling_render` |
| 9 | `_normalize_footer_brand_text` | 400–401 | Normalize text for footer brand matching | `_is_notebooklm_footer_text_element`, `_detect_notebooklm_footer_bbox_from_render` |
| 10 | `_is_notebooklm_footer_brand_normalized` | 404–411 | Check if normalized text contains "notebooklm" | `_is_notebooklm_footer_text_element` |
| 11 | `_is_notebooklm_footer_text_element` | 414–445 | Detect NotebookLM footer bbox from element metadata | `generate_pptx_from_ir` (both branches) |
| 12 | `_detect_notebooklm_footer_bbox_from_render` | 448–595 | Tesseract OCR on bottom-right crop to find NotebookLM footer (uses Pillow + pytesseract) | `generate_pptx_from_ir` (scanned-page branch only) |
| 13 | `_build_notebooklm_footer_fill_overlays` | 598–636 | Build fill overlays for NotebookLM footer area | `generate_pptx_from_ir` (text-page branch only) |

**Total helper function code: ~570 lines**

#### 2.3 Main Function `generate_pptx_from_ir` (lines 639–2221, ~1580 lines)

**A. Preliminaries (lines 693–865, ~170 lines)**
- Dynamic import of python-pptx modules (`Presentation`, `RGBColor`, `MSO_AUTO_SIZE`, `MSO_ANCHOR`, `PP_ALIGN`, `MSO_AUTO_SHAPE_TYPE`, `Emu`, `Pt`)
- IR validation (pages exist, first page dimensions valid)
- Mode/config normalization: `text_erase_mode`, `scanned_page_mode`, `ppt_generation_mode`
- Speed-mode adjustments: force fill mode, lower DPI
- Float parameter clamping via nested `_clamp_float` helper
- Page dimension capture from first page
- Output path validation + artifacts directory creation
- Presentation creation, slide dimensions, blank layout selection

**B. Per-Page Loop Preamble (lines 867–883, ~17 lines)**
- Progress callback closure via `_notify_page_done`
- Nonlocal `done_pages` tracker

**C. Branch: Scanned Page (no text layer) — lines 884–1656 (~770 lines)**

| Section | Lines | Description |
|---|---|---|
| Scanned-page strategy select | 947–953 | fullpage vs segmented mode |
| Render page image | 955–961 | `_render_pdf_page_png` |
| Background dimensions | 963–966 | EMU calculations from transform |
| Footer detection (fallback OCR) | 969–982 | `_detect_notebooklm_footer_bbox_from_render` |
| OCR text elements + baseline | 983–991 | `_estimate_baseline_ocr_line_height_pt` |
| `_text_coverage_ratio` nested function | 993–1046 | Overlap-based text coverage for image-region filtering |
| `_text_inside_counts` nested function | 1048–1083 | CJK-aware text count inside bbox |
| Full-page bg image check | 1085–1090 | `_is_near_full_page_bbox_pt` for each image element |
| Build scanned image region infos | 1092–1112 | `_build_scanned_image_region_infos` with coverage callbacks |
| Filter + dedupe OCR text | 1113–1125 | `_filter_scanned_ocr_text_elements`, `_dedupe_scanned_ocr_text_elements` |
| Apply text cutouts to image regions | 1126–1132 | `_apply_text_cutouts_to_scanned_image_region_crops` |
| Build text erase bboxes + text items | 1138–1234 | Footer erase + OCR erase + text_items list with bg_rgb |
| Erase bbox merge strategy | 1236–1277 | fill-mode (local) vs smart-mode (merged) |
| Protect bboxes for image regions | 1279–1302 | Don't erase inside confirmed image regions |
| Erase text from background image | 1304–1319 | `_erase_regions_in_render_image` |
| Clear image-crop background regions | 1321–1354 | `_clear_regions_for_transparent_crops` |
| Post-clear text wipe | 1356–1371 | Residual glyph cleanup after crop cutouts |
| Place background image | 1373–1379 | `slide.shapes.add_picture` |
| Place cropped image overlays | 1382–1398 | `slide.shapes.add_picture` per crop |
| Place editable text boxes | 1400–1638 | Font fitting, wrap probe, color sampling, textbox creation, nudge adjustments, font styling |
| Export preview + progress | 1640–1656 | `_maybe_export_final_preview_page_image` + `_notify_page_done` |

**D. Branch: Text Page (has text layer) — lines 1659–2218 (~560 lines)**

| Section | Lines | Description |
|---|---|---|
| MinerU background render | 1660–1755 | Render PDF, erase text, clear image regions, place as background |
| OCR sampling render (if needed) | 1757–1779 | Conditional extra render for OCR probes |
| Footer fill overlays | 1781–1802 | `_build_notebooklm_footer_fill_overlays` |
| Image placement | 1804–1830 | `slide.shapes.add_picture` for each image element |
| Table placement | 1832–1908 | `slide.shapes.add_table` with cell sizing from cell bboxes |
| Footer fill shape overlays | 1910–1931 | Clean rectangles over footer branding |
| Text element placement | 1933–2206 | Font fitting (MinerU/OCR/generic), color sampling, textbox creation, font styling, right-nudge for wrap tolerance |
| Export preview + progress | 2208–2218 | `_maybe_export_final_preview_page_image` + `_notify_page_done` |

**E. Save & Return (lines 2220–2221, ~2 lines)**
- `prs.save(str(out_path))` + `return out_path`

### 3. Generation Pipeline Stages (Ordered)

```
STAGE 0  — Library import (importlib python-pptx)
STAGE 1  — IR validation (pages exist, first page dimensions valid)
STAGE 2  — Config normalization (mode aliases -> canonical, param clamping)
STAGE 3  — Presentation setup (slide dimensions, blank layout, artifacts dir)

          +-- PER PAGE --------------------------------------------------+
          |                                                                |
          |  STAGE 4 -- Page-type detection (has_text_layer or not)        |
          |                                                                |
          |  +- BRANCH A: SCANNED PAGE (no text layer) -----------------+ |
          |  | STAGE 5a  -- Render PDF page to PNG                      | |
          |  | STAGE 6a  -- Build scanned image region infos            | |
          |  | STAGE 7a  -- Filter + dedupe OCR text elements           | |
          |  | STAGE 8a  -- Apply text cutouts to image region crops    | |
          |  | STAGE 9a  -- Compute text erase bboxes + build text items| |
          |  | STAGE 10a -- Erase text from background image            | |
          |  | STAGE 11a -- Clear image-crop background regions         | |
          |  | STAGE 12a -- Place background image on slide             | |
          |  | STAGE 13a -- Place cropped image overlays on slide       | |
          |  | STAGE 14a -- Place editable text boxes + font styling    | |
          |  | STAGE 15a -- Export final preview image                  | |
          |  +----------------------------------------------------------+ |
          |                                                                |
          |  +- BRANCH B: TEXT PAGE (has text layer) -------------------+ |
          |  | STAGE 5b  -- Render MinerU background + erase text       | |
          |  | STAGE 6b  -- OCR sampling render (conditional)           | |
          |  | STAGE 7b  -- Build NotebookLM footer fill overlays       | |
          |  | STAGE 8b  -- Place image elements on slide               | |
          |  | STAGE 9b  -- Place table elements on slide               | |
          |  | STAGE 10b -- Place footer fill shape overlays            | |
          |  | STAGE 11b -- Place text elements + font/color styling    | |
          |  | STAGE 12b -- Export final preview image                  | |
          |  +----------------------------------------------------------+ |
          |                                                                |
          +----------------------------------------------------------------+

STAGE 16 -- Save PPTX to disk (prs.save)
RETURN   -- Output path
```

### 4. Concerns Mixed in This Single File

| Concern | Approx Lines | Description |
|---|---|---|
| Library import + IR validation | 70 | python-pptx import, error handling |
| Config normalization + clamping | 130 | Mode aliases, param clamping, speed-mode overrides |
| Presentation setup | 20 | Slide dimensions, blank layout |
| Markdown sanitization | 50 | regex-based markdown stripping |
| NotebookLM footer detection | 240 | Element metadata heuristics + Tesseract OCR fallback |
| NotebookLM footer fill overlays | 40 | Background fill shape for branding removal |
| BBox erase merging | 120 | Iterative + union-find fast path |
| Visual wrap probing heuristics | 110 | Whether to do pixel-level line counting |
| OCR sampling render decision | 55 | Whether page needs extra render for probes |
| Centered heading detection | 25 | Visual centering heuristic for scanned headings |
| Scanned-page: image region analysis | 30 | `_text_coverage_ratio`, `_text_inside_counts` helpers |
| Scanned-page: text erase + background cleanup | 220 | Erase bbox building, merge strategy, image clear |
| Scanned-page: image placement | 20 | Background + crop overlay |
| Scanned-page: editable text placement | 240 | Font fitting, wrap probes, color sampling, textboxes |
| Text-page: MinerU background render | 95 | Layout-parse background rendering + cleaning |
| Text-page: image placement | 27 | Simple picture placement |
| Text-page: table placement | 77 | Table with cell sizing |
| Text-page: text placement | 275 | MinerU/OCR/generic font fitting, color sampling, wrap |
| Preview export | 35 (x2) | Final preview images (called per branch) |
| Progress callback | 15 | Page-done notification |

**Total distinct concerns: ~18**

### 5. External Imports of `generator.py`

| File | Import | Usage |
|---|---|---|
| `pptx/__init__.py:3` | `from .generator import generate_pptx_from_ir` | **Public API** -- sole re-export |
| `pptx_generator.py` (shim):3 | `from app.convert.pptx.generator import generate_pptx_from_ir` | **Backward compat** -- re-export with old path |
| `worker_helpers/ppt_stage.py:8` | `from ..convert.pptx_generator import generate_pptx_from_ir` | **Runtime caller** -- the worker that invokes generation |
| `tests/test_generator_perf_guards.py:15` | `from app.convert.pptx import generator` | **Tests** -- also accesses internal helpers: `_should_probe_visual_wrap_for_ocr_text`, `_should_sample_local_text_colors`, `_page_needs_ocr_sampling_render` |

**Verdict**: Only `generate_pptx_from_ir` is the true public API. The test file accesses internal helpers by importing the whole module -- this would need updating in any split. The shim `pptx_generator.py` also re-exports `_token_width_pt`, `_wrap_paragraph_to_lines` (from `font_utils`), and `_estimate_baseline_ocr_line_height_pt` (from `scanned_page`).

### 6. Proposed Split Plan

#### 6.1 New Module Structure

```
api/app/convert/pptx/
+-- __init__.py              (~7 lines)   Public API: re-export generate_pptx_from_ir
+-- constants.py             (23 lines)   [unchanged]
+-- color_utils.py           (35 lines)   [unchanged]
+-- bbox_utils.py            (166 lines)  [unchanged]
+-- slide_builder.py         (87 lines)   [unchanged]
+-- font_utils.py            (1038 lines) [unchanged]
+-- preview.py               (379 lines)  [unchanged -- merge _is_layout_parse_source]
+-- scanned_page.py          (3971 lines) [unchanged]
|
+-- generator/
    +-- __init__.py          (~15 lines)  Public API + relocated _is_layout_parse_source
    +-- main.py              (~180 lines) generate_pptx_from_ir: preliminaries (stages 0-3)
    +-- scanned_pipeline.py  (~780 lines) Scanned-page per-page loop (stages 5a-15a)
    +-- text_pipeline.py     (~570 lines) Text-page per-page loop (stages 5b-12b)
    +-- footer.py            (~280 lines) NotebookLM footer detection + fill overlays
    +-- text_erase.py        (~130 lines) _merge_text_erase_bboxes
    +-- markdown_utils.py    (~40 lines)  _sanitize_markdown_text + 6 regexes
    +-- probing.py           (~170 lines) Wrap probe, color-sample, OCR-sampling, centered heading
```

#### 6.2 Ownership Table

| New Module | Source Lines | Exports |
|---|---|---|
| `generator/main.py` | 639-865 (~170 lines) | `generate_pptx_from_ir` (refactored to delegate per-page work) |
| `generator/scanned_pipeline.py` | 884-1656 (~770 lines) | `_process_scanned_page(slide, page, ...)` |
| `generator/text_pipeline.py` | 1659-2218 (~570 lines) | `_process_text_page(slide, page, ...)` |
| `generator/footer.py` | 400-636 (~240 lines) | `_is_notebooklm_footer_text_element`, `_detect_notebooklm_footer_bbox_from_render`, `_build_notebooklm_footer_fill_overlays` + private helpers |
| `generator/text_erase.py` | 240-361 (~120 lines) | `_merge_text_erase_bboxes` |
| `generator/markdown_utils.py` | 60-65, 363-397 (~40 lines) | `_sanitize_markdown_text` + 6 regexes |
| `generator/probing.py` | 99-237 (~140 lines) | `_should_probe_visual_wrap_for_ocr_text`, `_should_sample_local_text_colors`, `_page_needs_ocr_sampling_render`, `_should_center_scanned_heading` |

#### 6.3 Estimated LOC After Split

| Module | New LOC |
|---|---|
| `generator/main.py` | ~170 |
| `generator/scanned_pipeline.py` | ~780 |
| `generator/text_pipeline.py` | ~570 |
| `generator/footer.py` | ~280 |
| `generator/text_erase.py` | ~130 |
| `generator/markdown_utils.py` | ~40 |
| `generator/probing.py` | ~170 |
| `generator/__init__.py` | ~15 |
| **Total (generator/)** | **~2155** |
| `pptx/__init__.py` (updated) | ~7 |
| `pptx_generator.py` (updated) | ~12 |
| **Original generator.py size** | **2221** |
| **Largest single file after split** | **~780 (scanned_pipeline.py)** |

#### 6.4 Dependency Graph (Proposed)

```
generator/main.py
  +-- imports from: scanned_pipeline.py, text_pipeline.py, constants.py, slide_builder.py
  |
generator/scanned_pipeline.py
  +-- imports from: generator/text_erase.py, generator/footer.py, generator/probing.py,
  |                  generator/markdown_utils.py, scanned_page.py, slide_builder.py,
  |                  bbox_utils.py, color_utils.py, constants.py, font_utils.py, preview.py
  |
generator/text_pipeline.py
  +-- imports from: generator/footer.py, generator/probing.py, generator/markdown_utils.py,
  |                  scanned_page.py, slide_builder.py, bbox_utils.py, color_utils.py,
  |                  constants.py, font_utils.py, preview.py
  |
generator/footer.py
  +-- imports from: bbox_utils.py, color_utils.py, scanned_page.py
  |
generator/text_erase.py
  +-- imports from: bbox_utils.py (only _coerce_bbox_pt)
  |
generator/markdown_utils.py
  +-- no internal imports (stdlib only)
  |
generator/probing.py
  +-- imports from: font_utils.py, color_utils.py, bbox_utils.py, scanned_page.py
```

**No circular dependencies** -- the graph is a DAG with `generator/main.py` at the top and leaf utility modules at the bottom.

#### 6.5 Shared Context / State

Both pipelines share:
- `transform: SlideTransform` -- passed from `main.py` into each pipeline function as a parameter
- `pix` (PIL Image / PixelAccess) -- rendered page image, created within each pipeline
- `artifacts: Path` -- directory for intermediate files
- `source_pdf: Path` -- path to source PDF
- `page_w_pt`, `page_h_pt`, `page_index` -- per-page dimensions and index
- `slide_w_emu`, `slide_h_emu` -- global slide dimensions (constant across pages)
- `scanned_render_dpi` -- integer DPI setting
- Various clamped float params: `image_bg_clear_expand_*`, `scanned_image_region_*`
- pptx module references: `Emu`, `Pt`, `RGBColor`, `MSO_ANCHOR`, `PP_ALIGN`, `MSO_AUTO_SIZE`, `MSO_AUTO_SHAPE_TYPE`

All of these are already passed as local variables/keyword arguments -- no global module state exists. The refactoring simply extracts the per-page loops into functions that receive these values as parameters.

### 7. Code Smells Found

| # | Smell | Location | Severity |
|---|---|---|---|
| 1 | **Duplicate function** | `_is_layout_parse_source` exists in both `generator.py:68` and `preview.py:26` -- identical implementations but not shared | Medium |
| 2 | **Monster function** | `generate_pptx_from_ir` is ~1580 lines (639-2221) -- the entire per-page loop is inlined | High |
| 3 | **Nested function definitions inside loop body** | `_text_coverage_ratio` (line 993) and `_text_inside_counts` (line 1048) are defined inside the per-page for-loop, re-created on every iteration | Medium |
| 4 | **Two huge branches** | Scanned-page branch (~770 lines) and text-page branch (~560 lines) are interleaved in one function with `if not has_text_layer:` / `continue` pattern -- they are effectively two separate functions sharing one function body | High |
| 5 | **Mixed abstraction levels** | High-level pipeline orchestration (slide creation, save) mixed with low-level pixel sampling, font metric math, and regex-based text cleaning in the same function | High |
| 6 | **Repeat patterns** | Textbox creation (add_textbox + set margins + font styling) is duplicated across scanned-page OCR text, text-page MinerU text, text-page OCR text, and text-page generic text -- each with minor variants | Medium |
| 7 | **Long functions among helpers** | `_detect_notebooklm_footer_bbox_from_render` is 147 lines (448-595), `_merge_text_erase_bboxes` is 121 lines (240-361) | Medium |
| 8 | **Implicit parameter dependencies** | `_clamp_float` is a nested function inside `generate_pptx_from_ir` (line 770) -- defined inside the function rather than at module level | Low |
| 9 | **Tight coupling to Pillow + pytesseract** inside generator.py | Footer detection imports PIL/pytesseract inline (lines 457-460) rather than through the abstraction layer used elsewhere | Low |
| 10 | **Regexes defined at module level but used only by one function** | 6 markdown regex constants (lines 60-65) are module-level but only used by `_sanitize_markdown_text` | Low |
| 11 | **Magic numbers** | Many heuristic thresholds (0.84, 0.72, 0.40, 1.14, 1.55, 1.35, etc.) are hardcoded rather than named constants | Low |

### 8. Test Coverage Impact

The file `tests/test_generator_perf_guards.py` (740 lines) imports the whole `generator` module and directly calls internal helper functions:
- `generator._should_probe_visual_wrap_for_ocr_text`
- `generator._should_sample_local_text_colors`
- `generator._page_needs_ocr_sampling_render`
- `generator.generate_pptx_from_ir`

After splitting, these tests must update their import paths. Since the tests depend on internal helpers, those helpers should remain importable from `pptx.generator.*` sub-modules.

### 9. Risks and Caveats

1. **Test breakage is guaranteed**: `test_generator_perf_guards.py` imports internals directly. Splitting requires test import updates.
2. **Shim compatibility**: `pptx_generator.py` currently imports from `app.convert.pptx.generator`. If the old `generator.py` file is renamed or removed, the shim must be updated to point to the new location.
3. **Two-page-type coupling**: The scanned-page and text-page pipelines share the NotebookLM footer logic (`_is_notebooklm_footer_text_element` is called by both branches), the markdown sanitizer, and progress/preview export wrappers. These dependencies are clean -- footer.py, markdown_utils.py, and preview.py are already separate modules that both branches can import.
4. **Nested functions `_text_coverage_ratio` and `_text_inside_counts`**: These are the trickiest part to extract, as they close over `ocr_text_elements` and `baseline_ocr_h_pt` from the enclosing loop. They should become module-level functions receiving those values as arguments, or class methods on a context object.
5. **No regression risk**: The split is purely structural -- no logic changes. All function signatures and behavior are preserved.

## Related Specs

- `.trellis/spec/backend/index.md` -- backend coding conventions
- `.trellis/spec/frontend/index.md` -- frontend conventions (not applicable to this backend split)
- `.trellis/workspace/lan/journal-1.md` -- developer journal referencing architecture review

## Not Found / Incomplete

- No AI OCR integration code exists yet; this research covers only the existing PPTX generator structure.
- Scanned_page.py (3971 lines) may itself warrant future splitting, but that is out of scope for this research.
