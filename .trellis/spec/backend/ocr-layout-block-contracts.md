# OCR Layout Block Contracts

> Executable contract for local `layout_block` OCR when image-like layout labels must preserve both visual overlays and meaningful text.

---

## Scenario: OCR-eligible image-like layout blocks and under-segmentation fallback

### 1. Scope / Trigger

- Trigger: any change to local layout-block OCR routing, image-like label classification, scanned-page image-region filtering, or scanned image crop generation for AI-hint regions.
- This is mandatory code-spec depth because it is a cross-layer OCR contract:
  layout model output → OCR block scheduling → OCR element metadata → scanned-page text/image filtering → PPTX overlay output.

### 2. Signatures

- Layout label helpers:
  - `api/app/convert/ocr/result_parsing.py::_is_image_like_layout_label(value: Any) -> bool`
  - `api/app/convert/ocr/result_parsing.py::_is_ocr_eligible_image_like_label(value: Any) -> bool`
- Layout bypass gate:
  - `api/app/convert/ocr/_ai_layout_block.py::_should_bypass_local_layout_block_ocr(image_path: str, *, image: Image.Image) -> str | None`
- Local layout OCR entry:
  - `api/app/convert/ocr/_ai_layout_block.py::_ocr_image_with_local_layout_blocks(image_path: str, *, image: Image.Image) -> list[dict]`
- Route orchestrator fallback boundary:
  - `api/app/convert/ocr/_ai_chat.py::ocr_image(image_path: str) -> list[dict]`
- OCR-to-elements boundary:
  - `api/app/convert/ocr/_ocr_postprocess.py::ocr_image_to_elements(...) -> list[dict]`
- Scanned-page filter/crop boundary:
  - `api/app/convert/pptx/_scanned_region_build.py::_filter_scanned_ocr_text_elements(...) -> list[dict]`
  - `api/app/convert/pptx/_scanned_region_build.py::_save_scanned_image_region_crop(...)`
  - `api/app/convert/pptx/_scanned_region_build.py::_build_scanned_image_region_infos(...) -> list[_ScannedImageRegionInfo]`

### 3. Contracts

#### Layout-label contract

- Image-like classification and OCR-eligibility are separate decisions.
- `chart` may remain image-like for overlay purposes while also being OCR-eligible.
- Scope-A default contract:
  - `chart` → image-like **and** OCR-eligible
  - `image`, `seal` → image-like and **not** OCR-eligible
- Do **not** broaden OCR eligibility to other image-like labels unless the PRD explicitly expands scope and tests are updated.

#### OCR scheduling contract

- `_ocr_image_with_local_layout_blocks()` must not pure-skip OCR-eligible image-like labels.
- OCR-eligible image-like blocks must still continue to populate `image_regions` so scanned-page overlay behavior remains available.
- Raw OCR items produced from such blocks must carry a lightweight provenance flag:
  - `ocr_image_like: true`

#### Scanned-page filtering contract

- `_filter_scanned_ocr_text_elements()` normally suppresses text overlapping image regions.
- Exception: text elements with `ocr_image_like: true` must be preserved even when overlapping their paired image region.
- This exception exists specifically so dual-path blocks can yield both:
  - editable/extractable text
  - visual image overlays

#### Crop repair contract

- Crop expansion in this flow is limited to low-risk AI-hint / polygon-backed regions.
- Expansion must enlarge the saved crop content only; it must **not** move or enlarge the overlay placement bbox used in PPTX placement.
- Global bbox expansion for all scanned image regions is out of scope unless separately designed and tested.

#### Under-segmentation fallback contract

- `_should_bypass_local_layout_block_ocr()` is the pre-OCR gate for deciding whether the local `layout_block` route is trustworthy enough to use.
- When the layout model under-segments or yields unusable routing input, the function must return a stable bypass reason string and the caller must fall back to direct page OCR.
- Current required bypass reasons in this contract:
  - `low_layout_confidence`
  - `high_low_confidence_ratio`
  - `low_text_coverage`
  - `no_text_blocks`
  - `too_few_text_blocks`
  - `wide_flat_layout_blocks`
- `no_text_blocks` means local layout analysis produced zero text-like blocks after image-like / low-value filtering. This must bypass block OCR because there are no viable OCR tasks to schedule.
- `too_few_text_blocks` means a large image (`page_area > 3_000_000 px²`) produced at most 3 text-like blocks. Treat this as likely screenshot/UI under-segmentation and bypass block OCR.
- `ocr_image()` must preserve the chosen bypass reason in `last_layout_analysis_debug["layout_block_bypass_reason"]` before falling through to direct page OCR.
- For non-DeepSeek models, if `_ocr_image_with_local_layout_blocks()` runs but returns an empty usable result, `ocr_image()` must record `empty_block_ocr_result` and fall back to direct page OCR instead of returning `[]`.
- Do **not** treat `empty_block_ocr_result` as a layout-label-routing reason inside `_should_bypass_local_layout_block_ocr()`; it is a post-block-OCR fallback reason recorded by `ocr_image()` after scheduling was attempted.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Label is `chart` | Keep it in `image_regions` and allow it into OCR scheduling |
| Label is `image` or `seal` | Keep picture-only behavior unless PRD explicitly broadens scope |
| OCR text comes from an OCR-eligible image-like block | Preserve it through scanned-page text filtering using `ocr_image_like` metadata |
| Crop expansion applies to non-polygon / non-AI-hint region | Treat as scope violation for this contract |
| Overlay placement bbox changes because of crop padding | Treat as regression |
| Layout analysis yields zero text-like blocks | Return `no_text_blocks` and bypass to direct page OCR |
| Large image yields <=3 text-like blocks | Return `too_few_text_blocks` and bypass to direct page OCR |
| Non-DeepSeek block OCR returns empty usable result | Record `empty_block_ocr_result` and bypass to direct page OCR |
| New image-like OCR rule is introduced | Add focused tests for label eligibility, text preservation, and overlay stability |

### 5. Good / Base / Bad Cases

- Good: `chart` block is added to `image_regions`, sent to OCR, and its resulting text survives scanned-page filtering.
- Good: screenshot-like page yields only a few coarse text blocks, so block OCR is bypassed and direct page OCR is used instead.
- Base: `image` and `seal` still behave exactly as picture-only blocks.
- Bad: `chart` is OCR'd, but its text is later removed because overlap filtering ignores the image-like provenance flag.
- Bad: layout analysis yields zero or extremely few text blocks, but block OCR still runs and returns an empty/partial result instead of falling back.
- Bad: polygon padding expands the overlay bbox and causes visual placement drift in the PPTX.

### 6. Tests Required

- Add focused tests when changing this flow:
  - label eligibility tests for `_is_ocr_eligible_image_like_label()`
  - dual-path OCR tests proving `chart` is OCR'd and still contributes image regions
  - scanned-page filtering tests proving `ocr_image_like` text is preserved
  - crop tests proving polygon-backed expansion adds margin without breaking polygon masking
  - bypass tests proving `no_text_blocks` and `too_few_text_blocks` fall back to direct page OCR
  - fallback tests proving non-DeepSeek empty block OCR results are converted into `empty_block_ocr_result`
- Assertion points should explicitly cover:
  - `chart=True`, `image=False`, `seal=False` for OCR eligibility
  - overlap filtering keeps `ocr_image_like` text
  - non-image-like text behavior remains unchanged
  - crop output grows for polygon-backed regions while placement bbox remains unchanged
  - zero text-like blocks produce `layout_block_bypass_reason == "no_text_blocks"`
  - large sparse screenshots produce `layout_block_bypass_reason == "too_few_text_blocks"`
  - non-DeepSeek empty block OCR produces `layout_block_bypass_reason == "empty_block_ocr_result"`

Minimum regression pattern:

```python
assert _is_image_like_layout_label("chart") is True
assert _is_ocr_eligible_image_like_label("chart") is True
assert _is_ocr_eligible_image_like_label("image") is False
```

### 7. Wrong vs Correct

#### Wrong

```python
if _is_image_like_layout_label(label):
    continue
```

```python
if not text_blocks:
    return None
```

```python
if overlaps_image_region(element_bbox):
    continue
```

#### Correct

```python
is_image_like = _is_image_like_layout_label(label)
if is_image_like and not _is_ocr_eligible_image_like_label(label):
    continue
```

```python
if not text_blocks:
    return "no_text_blocks"
if len(text_blocks) <= 3 and page_area > 3_000_000:
    return "too_few_text_blocks"
```

```python
if element.get("ocr_image_like"):
    kept.append(element)
    continue
```

---

## Review Checklist

Before merging layout-block OCR changes, verify:

- [ ] `chart` dual-path behavior is explicit and tested
- [ ] `image_regions` collection remains intact for OCR-eligible image-like blocks
- [ ] under-segmentation bypass reasons are explicit and tested (`no_text_blocks`, `too_few_text_blocks`, `empty_block_ocr_result`)
- [ ] `ocr_image_like` provenance survives OCR post-processing into scanned-page filtering
- [ ] Crop padding is restricted to AI-hint / polygon-backed regions only
- [ ] Overlay placement bbox is unchanged by crop padding
- [ ] No broader image-like label expansion slipped in without PRD + tests
