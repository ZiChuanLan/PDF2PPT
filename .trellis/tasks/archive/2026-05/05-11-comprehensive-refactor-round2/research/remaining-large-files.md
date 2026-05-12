# Research: Remaining Large Files Audit (Round 2 Targets)

- **Query**: Audit 5 files not fully addressed in the previous refactor for extraction targets
- **Scope**: internal
- **Date**: 2026-05-11

## Findings

---

## 1. `web/src/app/settings/page.tsx`

**Line count**: 2787 lines (was 2961, reduced by 184)

### Structure Breakdown

| Section | Lines | Description |
|---------|-------|-------------|
| Imports | 1–68 | 68 lines of imports |
| Config/constants/types | 69–224 | Options, RuntimeConfig interface, defaults (~156 lines) |
| `RuntimeConfigSection()` | 226–523 | Self-contained server-side env editor (~298 lines) |
| `SettingsPage()` main | 525–2787 | Main page component (~2263 lines) |

### Three Large CollapsibleSection Blocks

#### A. "接口配置" (API Config) — lines 1309–1498 (~190 lines)
- API origin override UI (~56 lines within AdvancedReveal)
- MinerU token, base URL, model version, language, checkboxes (~98 lines when active)

#### B. "处理策略" (Processing Strategy) — lines 1501–1782 (~282 lines)
- Text erase mode selector
- Scanned page mode selector
- OCR render DPI
- Remove footer NotebookLM checkbox
- Image background clear & region threshold params (6 numeric fields with reset button, ~102 lines within AdvancedReveal)

#### C. "OCR 配置" / "文档解析配置" — lines 1784–2778 (~995 lines) **← main target**
- OCR provider selector with radio cards + download buttons (~95 lines)
- OCR strict mode toggle
- AIOCR vendor adapter dropdown
- **"专用 OCR 接口参数"** block (lines 1936–2529, ~594 lines):
  - API Key + Base URL + chain mode selector (~75 lines)
  - Layout model selector with per-model radio cards + download buttons (~90 lines, lines 2013–2095)
  - PaddleOCR-VL docs parser max side px
  - Model picker with autocomplete portal (lines 2124–2187, ~64 lines, distinct JSX block)
  - AI OCR capability check button + result display (lines 2189–2231, ~43 lines)
  - **"提示词实验"** sub-section (lines 2233–2360, ~128 lines, inside AdvancedReveal):
    - Prompt preset selector
    - Direct/layout-block prompt override textarea
    - Image region prompt override textarea
  - **"并发与限流"** sub-section (lines 2362–2519, ~158 lines, inside AdvancedReveal):
    - Multi-page concurrency input
    - Per-page block concurrency input
    - RPM/TPM/retry count inputs (3-column grid, ~73 lines)
- Baidu config (API key, secret key, app ID, doc parse type) (lines 2531–2619, ~89 lines)
- Tesseract config (min confidence, language) (lines 2622–2663, ~42 lines)
- Local OCR check suite (Tesseract + PaddleOCR cards) (lines 2665–2777, ~113 lines)

### Extraction Targets (Priority Order)

| Priority | Target | Lines | Suggested File |
|----------|--------|-------|----------------|
| P0 | "OCR 配置" CollapsibleSection → `OcrConfigSection` | ~995 | `web/src/components/settings/ocr-config-section.tsx` |
| P1 | "专用 OCR 接口参数" block → `OcrAiParamsSection` | ~594 | `web/src/components/settings/ocr-ai-params-section.tsx` |
| P1 | `RuntimeConfigSection` → separate file | ~298 | `web/src/components/settings/runtime-config-section.tsx` |
| P2 | "提示词实验" block → `PromptExperimentSection` | ~128 | Nested in ocr-ai-params or standalone |
| P2 | "并发与限流" block → `ConcurrencyRateLimitSection` | ~158 | Nested in ocr-ai-params or standalone |
| P3 | Local OCR check suite → `LocalOcrCheckPanel` | ~113 | `web/src/components/settings/local-ocr-check-panel.tsx` |
| P3 | Baidu config block → `BaiduConfigFields` | ~89 | Inline extraction |

---

## 2. `api/app/convert/pptx/generator/main.py`

**Line count**: 1594 lines (was 1664, reduced by 70)

### Structure Breakdown

| Section | Lines | Description |
|---------|-------|-------------|
| Imports + `_is_layout_parse_source` | 1–81 | Imports + 1 small helper |
| `generate_pptx_from_ir()` signature + docstring | 83–135 | Function signature with 15+ params |
| lazy pptx imports | 138–157 | importlib lazy loading |
| IR validation + param normalization | 158–196 | Input validation |
| Slide setup | 198–260 | Presentation object, slide dimensions, page iteration prep |
| **Scanned-page branch** (`not has_text_layer`) | 257–1030 | ~774 lines: the largest contiguous block |
| **Text-page branch** (`has_text_layer`) | 1032–1591 | ~560 lines: second largest block |
| Save + return | 1593–1594 | Final lines |

### Scanned-Page Branch Details (lines 257–1030, ~774 lines)

| Sub-section | Lines | Description |
|-------------|-------|-------------|
| Nested `_text_coverage_ratio()` | 366–419 | ~54 lines — closure computing OCR coverage |
| Nested `_text_inside_counts()` | 421–456 | ~36 lines — closure counting text items inside region |
| Image region info building | 458–505 | ~48 lines |
| Text erase bbox collection | 507–607 | ~101 lines — building erase bbox lists from OCR text |
| Erase mode dispatch (fill vs smart) | 609–650 | ~42 lines |
| Background image erase + cleanup | 652–752 | ~101 lines — erase, clear regions, final text overlay |
| Image overlay placement | 754–771 | ~18 lines |
| **OCR text box creation loop** | 773–1012 | ~240 lines — per-text-item: heading detection, wrap probing, font fitting, color sampling, text box placement |

### Text-Page Branch Details (lines 1032–1591, ~560 lines)

| Sub-section | Lines | Description |
|-------------|-------|-------------|
| MinerU text-page background processing | 1032–1128 | ~97 lines — render, erase, clear, place background |
| OCR sampling render fallback | 1130–1152 | ~23 lines |
| NotebookLM footer fill overlays | 1154–1176 | ~23 lines |
| Image element loop | 1177–1203 | ~27 lines |
| Table element loop | 1205–1281 | ~77 lines |
| Footer fill overlay shapes | 1283–1304 | ~22 lines |
| **Text element rendering loop** | 1306–1580 | ~275 lines — per-element: style fitting, color sampling, font application |

### Extraction Targets (Priority Order)

| Priority | Target | Lines | Suggested Location |
|----------|--------|-------|-------------------|
| P0 | **Scanned-page slide builder** (lines 320–1029) → `_build_scanned_page_slide()` | ~710 | `generator/_scanned_page.py` |
| P0 | **Text-page slide builder** (lines 1032–1591) → `_build_text_page_slide()` | ~560 | `generator/_text_page.py` |
| P1 | Nested closures → module-level functions: `_compute_text_coverage_ratio()`, `_count_text_inside_bbox()` | ~91 | `generator/_scanned_page.py` |
| P1 | OCR text items build + text box creation (lines 507–1012) → `_build_scanned_ocr_text_items()` + `_place_scanned_text_boxes()` | ~506 | Sub-functions in `_scanned_page.py` |
| P2 | MinerU background processing (lines 1032–1128) → `_build_mineru_text_background()` | ~97 | `generator/_text_page.py` |
| P2 | Table rendering loop (lines 1205–1281) → `_place_tables_on_slide()` | ~77 | `generator/_text_page.py` |
| P2 | Text element rendering loop (lines 1306–1580) → `_place_text_elements_on_slide()` | ~275 | `generator/_text_page.py` |

---

## 3. `web/src/components/home/preview-stage.tsx`

**Line count**: 661 lines

### Structure Breakdown

| Section | Lines | Description |
|---------|-------|-------------|
| Imports + Props interface | 1–71 | 71 lines |
| Component signature | 72–108 | Destructured props |
| JSX return — Back button | 111–123 | 13 lines |
| JSX — **Left column**: File list + PDF preview | 128–263 | ~136 lines |
| JSX — **Right column**: Config + actions | 267–657 | ~391 lines |
| Action error display | 652–656 | 5 lines |

### Left Column Sub-Sections

| Sub-section | Lines | Description |
|-------------|-------|-------------|
| Multi-file list | 130–177 | ~48 lines — file cards with remove button |
| Single file info | 180–192 | ~13 lines |
| PDF preview controls + canvas | 194–263 | ~70 lines — page nav, canvas preview |

### Right Column Sub-Sections

| Sub-section | Lines | Description |
|-------------|-------|-------------|
| **Page range settings** | 268–352 | ~85 lines — checkbox, single-page trial, start/end inputs |
| **Quick config panel** | 354–583 | ~230 lines — the largest block |
| └ PPT generation mode | 357–375 | 19 lines |
| └ Parse engine selector | 376–408 | 33 lines |
| └ Local OCR provider radios | 409–473 | ~65 lines |
| └ AI OCR chain mode selector | 475–495 | 21 lines |
| └ Layout model selector | 496–525 | 30 lines |
| └ OCR model selector | 526–563 | 38 lines |
| └ Retain artifacts checkbox + settings link | 565–582 | 18 lines |
| **Action buttons** | 586–656 | ~71 lines — preflight warning, convert buttons, error display |

### Extraction Targets (Priority Order)

| Priority | Target | Lines | Suggested File |
|----------|--------|-------|----------------|
| P0 | **Quick config panel** → `QuickConfigPanel` | ~230 | `web/src/components/home/quick-config-panel.tsx` |
| P1 | Page range section → `PageRangeSection` | ~85 | `web/src/components/home/page-range-section.tsx` |
| P1 | Action buttons + preflight → `ActionButtons` | ~71 | `web/src/components/home/action-buttons.tsx` |
| P2 | File list (multi + single) → `FileList` | ~63 | `web/src/components/home/file-list.tsx` |
| P2 | Local OCR provider radios (within QuickConfigPanel) → inline sub-component | ~65 | Inside quick-config-panel.tsx |
| P2 | AI OCR chain + model config (within QuickConfigPanel) → inline sub-component | ~89 | Inside quick-config-panel.tsx |

---

## 4. `api/app/routers/jobs.py`

**Line count**: 1838 lines

### Endpoint Count: 12

| # | Endpoint | Method | Line | Description |
|---|----------|--------|------|-------------|
| 1 | `/api/v1/jobs/ocr/local/check` | POST | 276 | Local OCR probe |
| 2 | `/api/v1/jobs/ocr/ai/check` | POST | 510 | AI OCR capability check |
| 3 | `/api/v1/jobs` | GET | 602 | List recent jobs |
| 4 | `/api/v1/jobs` | POST | 685 | Create job (60+ Form params) |
| 5 | `/api/v1/jobs/v2` | POST | 1180 | Create job v2 (JSON config) |
| 6 | `/api/v1/jobs/{job_id}` | GET | 1437 | Get job status |
| 7 | `/api/v1/jobs/{job_id}/events` | GET | 1542 | SSE progress stream |
| 8 | `/api/v1/jobs/{job_id}/cancel` | POST | 1586 | Cancel job |
| 9 | `/api/v1/jobs/{job_id}` | DELETE | 1646 | Delete job + artifacts |
| 10 | `/api/v1/jobs/{job_id}/download` | GET | 1707 | Download PPTX result |
| 11 | `/api/v1/jobs/{job_id}/artifacts` | GET | 1746 | List artifact images |
| 12 | `/api/v1/jobs/{job_id}/artifacts/file` | GET | 1832 | Serve artifact file |

### Largest Functions

| Function | Lines | Description |
|----------|-------|-------------|
| `create_job` (POST /) | 685–1177 (493) | Massive endpoint: upload, validate, quota check, create + queue |
| `create_job_v2` (POST /v2) | 1180–1434 (255) | V2 endpoint with **heavy code duplication** from create_job |
| `_run_ai_ocr_capability_check` | 385–507 (123) | AI OCR probe: image generation, client creation, result validation |
| `list_jobs` (GET /) | 602–682 (81) | Job listing with RQ queue metadata |

### Duplication Between create_job and create_job_v2

Both endpoints duplicate:
- `_classify_upload_kind()` + validation (same check)
- Disk space check via `shutil.disk_usage()`
- `ensure_job_dir()` + streaming file write with size limit
- `_write_upload_as_input_pdf()`
- User quota checks (concurrent + daily)
- `redis_service.create_job()` + initial status write
- Secret storage (`store_job_secrets`)
- `_submit_job()` dispatch
- Error handling + cleanup (rmtree + delete_job rollback)

~150+ lines of duplicated logic.

### Extraction Targets (Priority Order)

| Priority | Target | Lines | Suggested File |
|----------|--------|-------|----------------|
| P0 | **Shared job-creation logic** → `_create_job_core()` helper | ~150 saved | Extract from both `create_job` and `create_job_v2` |
| P0 | Image upload helpers (lines 118–233) → separate module | ~116 | `api/app/routers/_upload_utils.py` or `api/app/services/upload_service.py` |
| P1 | AI OCR check helpers (lines 315–557) → separate module | ~243 | `api/app/routers/_ocr_check.py` or `api/app/services/ocr_check_service.py` |
| P2 | `_collect_page_images` + artifact endpoints (lines 574–600, 1746–1838) → module | ~120 | `api/app/routers/_job_artifacts.py` |
| P2 | SSE event generator (lines 1479–1583) → separate function | ~105 | Already a standalone function, but in same file |

---

## 5. `api/app/routers/models.py`

**Line count**: 1286 lines (merged from former `model_status.py`)

### Endpoint Count: 6

| # | Endpoint | Method | Line | Description |
|---|----------|--------|------|-------------|
| 1 | `/api/v1/models` | POST | 391 | List models from provider API |
| 2 | `/api/v1/models/status` | GET | 757 | Get model readiness (local + remote) |
| 3 | `/api/v1/models/download` | POST | 941 | Trigger background download (admin) |
| 4 | `/api/v1/models/download/status` | GET | 1035 | Poll download progress |
| 5 | `/api/v1/models/download/cancel` | POST | 1069 | Cancel active download (admin) |
| 6 | `/api/v1/models/delete` | POST | 1197 | Delete cached model (admin) |

### Structure Breakdown

| Section | Lines | Description |
|---------|-------|-------------|
| Imports + constants | 1–148 | Imports, provider maps, regex patterns (~148 lines config) |
| Model filtering utilities | 150–367 | ~218 lines of classification/pattern-matching helpers |
| Model list endpoint | 370–459 | Pydantic models + POST / endpoint (~90 lines) |
| **Download infrastructure** | 462–564 | DownloadTask, persistence, restore on startup (~103 lines) |
| Response models | 567–631 | Pydantic models for status/download/cancel/delete (~65 lines) |
| Provider status helpers | 633–749 | `_get_setting`, `_check_local_providers`, `_check_remote_providers` (~117 lines) |
| Model status endpoint | 757–786 | GET /status (~30 lines) |
| Background download fns | 789–913 | `_download_paddleocr_models`, layout model download, progress tracking (~125 lines) |
| Alias resolution | 915–938 | Layout model alias map (~24 lines) |
| Download endpoints | 941–1114 | POST /download, GET /download/status, POST /download/cancel (~174 lines) |
| Model deletion | 1121–1286 | POST /delete + helpers (`_delete_paddlex_model`, `_delete_doclayout_yolo_model`) (~166 lines) |

### Largest Functions

| Function | Lines | Description |
|----------|-------|-------------|
| `download_model` | 941–1032 (92) | POST /download — alias resolution, dedup check, thread launch |
| `delete_model` | 1197–1286 (90) | POST /delete — alias resolution, provider dispatch, cache deletion |
| `_check_local_providers` | 647–697 (51) | Probe tesseract, paddle, layout models |
| `cancel_download` | 1069–1114 (46) | POST /download/cancel — alias resolve, state check, flag set |

### Extraction Targets (Priority Order)

| Priority | Target | Lines | Suggested File |
|----------|--------|-------|----------------|
| P0 | **Model filtering utilities** (lines 150–367) → `_model_filtering.py` | ~218 | `api/app/routers/_model_filtering.py` |
| P1 | **Download infrastructure + endpoints** (lines 462–1114) → separate router | ~653 | `api/app/routers/_model_download.py` (or sub-router included in models.py) |
| P2 | **Model deletion** (lines 1121–1286) → `_model_deletion.py` | ~166 | Join download module or standalone |
| P2 | **Provider status helpers** (lines 633–749) → `_model_status_helpers.py` | ~117 | `api/app/routers/_model_status_helpers.py` |

---

## Summary Table

| File | Current Lines | Top Extraction Target | Estimated Savings |
|------|---------------|----------------------|-------------------|
| `settings/page.tsx` | 2787 | OcrConfigSection (~995 lines) → separate file | ~995 lines moved |
| `pptx/generator/main.py` | 1594 | Scanned-page branch (~710) + Text-page branch (~560) → separate modules | ~1270 lines moved |
| `home/preview-stage.tsx` | 661 | QuickConfigPanel (~230) + PageRangeSection (~85) + ActionButtons (~71) | ~386 lines moved |
| `routers/jobs.py` | 1838 | Shared job-creation logic + upload helpers + OCR check module | ~509 lines moved |
| `routers/models.py` | 1286 | Model filtering (~218) + Download module (~653) | ~871 lines moved |

### Caveats

1. **settings/page.tsx**: The OCR config section depends heavily on `useState` hooks declared at the top of `SettingsPage` (lines 547–571). Extracting it into a sub-component requires either prop-drilling ~20 state values or using a shared context. The AI OCR check callback `onCheckAiOcrModel` (line 1087) has a large dependency array (20 items), which makes prop-drilling verbose but feasible.

2. **pptx/generator/main.py**: The nested closures `_text_coverage_ratio` and `_text_inside_counts` capture local variables (`ocr_text_elements`, `baseline_ocr_h_pt`, `page_w_pt`, `page_h_pt`). Extracting them to module-level requires passing these as explicit parameters. The scanned-page and text-page branches share the `transform`, `slide`, `artifacts`, and many parameter variables — a shared context object or parameter bundle would reduce parameter count.

3. **routers/jobs.py**: The `create_job` and `create_job_v2` endpoints have significant code duplication (~150 lines). A shared `_create_job_core()` helper would reduce both. The v2 endpoint already generates kwargs then passes them, while v1 builds the dict inline — the v1 approach is the blocker to sharing.

4. **routers/models.py**: The download infrastructure uses module-level global state (`_download_tasks` dict + `_download_tasks_lock`). Extracting to a separate module requires careful import management to ensure the `_load_download_tasks()` call on module load (line 564) still happens at startup.

5. **preview-stage.tsx**: The QuickConfigPanel already receives props via the `PreviewStageProps` interface. Extracting it simply means passing a subset of those props to a new child component — the lowest-risk extraction of all five files.

