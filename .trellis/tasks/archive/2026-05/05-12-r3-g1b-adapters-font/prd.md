# R3-G1b: split adapters + font_utils

## Goal

Split 4 large adapter/utility files: `mineru_adapter.py` (1967), `baidu_doc_adapter.py` (1178), `ocr_stage.py` (1249), `font_utils.py` (1038). Eliminate 3 duplicate code patterns found in Round 2 audit.

## Requirements

### A3: mineru_adapter.py (1967→target <600)
- Extract private extraction helpers (text, bbox, kind, page_idx, image_path) → `_mineru_extract.py`
- Extract IR builder `_build_ir_from_mineru_outputs()` → `_mineru_build_ir.py`
- Keep `MineruClient` class + `parse_pdf_to_ir_with_mineru()` entry point in main file
- Re-export all public functions from `mineru_adapter.py`

### A4: baidu_doc_adapter.py (1178→target <400)
- Same pattern as mineru: extraction helpers → `_baidu_extract.py`
- IR builder → `_baidu_build_ir.py`
- Keep `BaiduDocParserClient` + `parse_pdf_to_ir_with_baidu_doc()` in main file

### A2: ocr_stage.py (1249→target <600)
- Extract page processing loop → `_ocr_page_loop.py`
- Extract parallel AI OCR dispatch → `_ocr_parallel.py`
- Extract progress tracking → `_ocr_progress.py`

### A5: font_utils.py (1038→target <400)
- Extract text measurement → `_font_measure.py`
- Extract text wrapping → `_font_wrap.py`
- Extract MinerU text style fitting → `_font_fit_mineru.py`
- Extract OCR text style fitting → `_font_fit_ocr.py`

### B1-B3: Duplicate code elimination
- B1: Extract shared `_is_image_like_kind()` → `api/app/convert/_adapter_utils.py`
- B2: Remove duplicate `_normalize_bbox_px()` from `ocr/local_providers.py`, use `ocr/result_parsing.py` version (or unify in `ocr/utils.py`)
- B3: Make `_contains_cjk()` call `_is_cjk_char()` instead of duplicating CJK ranges

## Acceptance Criteria

- [ ] py_compile pass for all modified files
- [ ] All public import paths unchanged (backward compatible re-exports)
- [ ] mineru_adapter.py < 600 lines
- [ ] baidu_doc_adapter.py < 400 lines
- [ ] ocr_stage.py < 600 lines
- [ ] font_utils.py < 400 lines
- [ ] B1: single canonical `_is_image_like_kind()` used by both adapters
- [ ] B2: single canonical `_normalize_bbox_px()` used everywhere

## Out of Scope

- Extracting shared base class for mineru/baidu adapters (too risky, leave structure as-is)
- Functional changes

## Technical Notes

- `_is_image_like_kind()` is IDENTICAL in mineru_adapter.py:725 and baidu_doc_adapter.py:463 — both check `lowered` against `_IMAGE_KIND_TOKENS`
- `_normalize_bbox_px()` identical in ocr/local_providers.py:2710 and ocr/result_parsing.py:96
- `_contains_cjk()` and `_is_cjk_char()` share identical CJK Unicode ranges — trivial to deduplicate internally
- `font_utils.py` already has CJK duplication fixed in Round 2, but B3 is about internal dedup within font_utils itself
