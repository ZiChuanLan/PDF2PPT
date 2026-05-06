# Research: Adaptive OCR Pipeline — Dynamic Layout Model Failure Detection

- **Query**: How to build a truly adaptive OCR pipeline that dynamically detects when a layout model is failing without hardcoded thresholds
- **Scope**: mixed (internal code + external research)
- **Date**: 2026-05-05

## Current State Analysis

### Current Bypass Logic

**File**: `api/app/convert/ocr/ai_client.py:2665-2752`

The current system uses `_should_bypass_local_layout_block_ocr()` which:

1. Runs layout analysis via `_run_local_layout_analysis(image_path)` (PP-DocLayout-V3 or DocLayout-YOLO)
2. Filters out image-like labels and OCR-skippable labels
3. Calculates `coverage = text_area / page_area`
4. If `coverage < 0.30` (hardcoded `_LOW_COVERAGE_THRESHOLD`), bypasses block OCR → sends full image to AI OCR
5. Also has a secondary check for "wide flat layout blocks" (few blocks, high aspect ratio, spanning >28% vertical)

**Problems with current approach**:
- The 30% threshold is a magic number — works for some screenshots but fails for others
- No consideration of layout model confidence scores
- No consideration of image characteristics (resolution, color depth, content type)
- Binary decision: either use all layout blocks or bypass entirely
- No post-OCR validation to check if the chosen strategy worked

### Layout Model Confidence Scores

**Key finding**: Both PP-DocLayout-V3 and DocLayout-YOLO **already expose per-detection confidence scores**.

From `layout_models.py:111-119` (LayoutModelProvider protocol):
```python
def predict(self, image_path: str) -> list[dict[str, Any]]:
    """Returns list of dicts with keys:
    - label: str — element label (e.g. "text", "figure")
    - score: float — confidence score
    - bbox: list[float] — [x0, y0, x1, y1]
    - order: int | None — reading order (optional)
    """
```

From PaddleX documentation, each detection returns:
- `cls_id`: Class ID (integer)
- `label`: Class label (string)
- `score`: Confidence score (float, 0-1)
- `coordinate`: Bounding box [xmin, ymin, xmax, ymax]

From DocLayout-YOLO (`layout_models.py:203-218`):
```python
results = self._model.predict(image_path, imgsz=1024, conf=0.2)
# ...
items.append({
    "label": result.names[int(boxes.cls[i])],
    "score": float(boxes.conf[i]),
    "bbox": xyxy,
    "order": None,
})
```

**Critical insight**: The confidence scores are currently extracted but **not used in the bypass decision**. They're passed through to the layout blocks but the bypass logic only looks at coverage area.

---

## Approach 1: Text Density Analysis

**Concept**: After layout block OCR, calculate characters per pixel area. Compare against expected density for the image type.

### Implementation
```python
def calculate_text_density(ocr_results: list[dict], image_area: float) -> float:
    total_chars = sum(len(r.get("text", "")) for r in ocr_results)
    return total_chars / (image_area / 10000)  # chars per 10K pixels

def expected_density_for_type(image_type: str) -> tuple[float, float]:
    """Returns (min, max) expected density range."""
    ranges = {
        "document": (50, 500),    # Dense text
        "screenshot": (10, 100),   # Moderate text
        "photo": (0, 5),          # Minimal text
        "mixed": (5, 200),        # Variable
    }
    return ranges.get(image_type, (10, 200))
```

### Trade-offs
| Factor | Assessment |
|--------|-----------|
| **Complexity** | Low — simple math after OCR |
| **Reliability** | Medium — requires knowing image type first |
| **Cost** | Zero extra — uses existing OCR results |
| **Latency** | Negligible |

**Problem**: This is a chicken-and-egg problem — you need to know the image type to set expected density, but you need density to classify the image type.

---

## Approach 2: Layout Model Confidence Scoring

**Concept**: Use the average confidence score from layout model detections to decide if the model is "working well".

### Implementation
```python
def assess_layout_quality(layout_blocks: list[dict]) -> dict:
    if not layout_blocks:
        return {"avg_confidence": 0.0, "low_confidence_ratio": 1.0, "quality": "poor"}
    
    scores = [b.get("score", 0.0) for b in layout_blocks]
    avg_score = sum(scores) / len(scores)
    low_conf = sum(1 for s in scores if s < 0.5) / len(scores)
    
    return {
        "avg_confidence": avg_score,
        "low_confidence_ratio": low_conf,
        "quality": "good" if avg_score > 0.7 and low_conf < 0.2 else "poor"
    }
```

### Trade-offs
| Factor | Assessment |
|--------|-----------|
| **Complexity** | Low — just averaging existing scores |
| **Reliability** | **High** — directly measures model certainty |
| **Cost** | Zero extra — scores already available |
| **Latency** | Negligible |

**Key insight**: When a layout model encounters an image type it wasn't trained on (e.g., screenshots), it typically produces **low-confidence detections** or **no detections at all**. This is a strong signal.

**From PaddleOCR docs**: PP-DocLayout-V3 is "trained on a self-built dataset containing Chinese and English academic papers, multi-column magazines, newspapers, PPTs, contracts, books, exam papers, research reports, ancient books, Japanese documents, and vertical text documents." — Notice: **no screenshots, no photos, no UI elements**.

---

## Approach 3: Image Type Classification

**Concept**: Classify images as "document", "screenshot", "photo", "mixed" before choosing an OCR strategy.

### Existing Solutions Found

1. **ScreenshotScanner** (PyPI: `screenshot-scanner`)
   - 13 heuristic checks: alpha channel, aspect ratio, ELA (Error Level Analysis), EXIF data, sharpness
   - No ML required, runs in milliseconds
   - Returns `is_screenshot` boolean with confidence score
   - GitHub: https://github.com/AzwadFawadHasan/ScreenshotScanner

2. **is_image_document_ai** (GitHub: Logophoman/is_image_document_ai)
   - MobileNetV2 or TinyCNN classifiers
   - 99%+ accuracy on document vs. image classification
   - Lightweight (MobileNetV2: ~14MB)
   - Trained on diverse dataset

3. **DocumentFigureClassifier-v2.5** (HuggingFace: docling-project)
   - EfficientNet-B0 based
   - 26 categories including "screenshot_from_computer", "screenshot_from_manual"
   - Can detect screenshots specifically

4. **Document-Type-Detection** (HuggingFace: prithivMLmods)
   - SigLIP2-based classification
   - Categories: Advertisement, Hand-Written, Invoice, Letter, News-Article, Resume

### Trade-offs
| Factor | Assessment |
|--------|-----------|
| **Complexity** | Medium — requires integrating external model or library |
| **Reliability** | **High** — dedicated classifiers achieve 99%+ accuracy |
| **Cost** | Small — one extra lightweight inference per image |
| **Latency** | ~5-20ms for MobileNetV2, ~1ms for heuristics |

**Recommendation**: ScreenshotScanner is the best fit — zero ML overhead, pure heuristics, designed exactly for this use case.

---

## Approach 4: Post-OCR Quality Validation

**Concept**: After OCR, check if results "make sense" — e.g., total text length vs image area, text coherence, language detection.

### Metrics to Check

1. **Text-to-area ratio**: `total_chars / (image_width * image_height)`
   - Documents: typically 0.001-0.01 chars/pixel
   - Screenshots: typically 0.0001-0.001 chars/pixel
   - Photos with text: typically <0.0001 chars/pixel

2. **Text coherence**: Check if OCR output forms recognizable words/sentences
   - Use language model perplexity (low = coherent)
   - Or simple heuristic: ratio of alphanumeric characters to total

3. **Block count sanity**: If layout model finds 0-2 text blocks on a full page, something is wrong

4. **Coverage vs. content mismatch**: If coverage is high but text is short, blocks may be misdetected

### Implementation
```python
def validate_ocr_quality(
    ocr_results: list[dict],
    image_size: tuple[int, int],
    layout_blocks: list[dict]
) -> dict:
    w, h = image_size
    page_area = w * h
    
    total_chars = sum(len(r.get("text", "")) for r in ocr_results)
    text_density = total_chars / (page_area / 10000)
    
    # Check for coherent text
    alphanumeric = sum(c.isalnum() for r in ocr_results for c in r.get("text", ""))
    coherence = alphanumeric / max(1, total_chars)
    
    # Check block count
    block_count = len(layout_blocks)
    
    return {
        "text_density": text_density,
        "coherence": coherence,
        "block_count": block_count,
        "suspicious": text_density < 5 or coherence < 0.5 or block_count < 2
    }
```

### Trade-offs
| Factor | Assessment |
|--------|-----------|
| **Complexity** | Low-Medium — simple metrics + optional language model |
| **Reliability** | Medium — works well for extreme cases, less for borderline |
| **Cost** | Zero extra if using existing results; small if using language model |
| **Latency** | Negligible for heuristics; ~10ms for language model |

---

## Approach 5: Ensemble Approach

**Concept**: Run layout model + full-page OCR in parallel, compare results, pick the better one.

### Academic Research Found

**CE-OCR (Consensus Entropy)** — arxiv.org/abs/2504.11101:
- Uses "Consensus Entropy" to measure agreement among multiple VLMs
- When CE is low (models agree), use ensemble output
- When CE is high (models disagree), route to stronger model
- Achieves 42.1% F1 improvement over VLM-as-Judge
- Only 7.3% of inputs require stronger model rephrasing

**LAION-AI/OCR-ensemble** (GitHub):
- 2-pass pipeline: classify image type → select expert model
- Uses CLIP for text detection and language detection
- Routes to specialized models based on content type

### Implementation for Our Case
```python
async def ensemble_ocr_decision(
    image_path: str,
    layout_model,
    ai_ocr_func
) -> tuple[str, str]:  # (strategy, reason)
    # Run both in parallel
    layout_task = asyncio.create_task(run_layout_ocr(image_path, layout_model))
    fullpage_task = asyncio.create_task(run_fullpage_ocr(image_path, ai_ocr_func))
    
    layout_results, fullpage_results = await asyncio.gather(layout_task, fullpage_task)
    
    # Compare results
    layout_chars = sum(len(r.get("text", "")) for r in layout_results)
    fullpage_chars = sum(len(r.get("text", "")) for r in fullpage_results)
    
    # If layout model found significantly less text, it's probably failing
    if layout_chars < fullpage_chars * 0.3:
        return "fullpage", "layout_model_underperforming"
    
    # If layout model found more text, it's probably working
    if layout_chars > fullpage_chars * 0.7:
        return "layout", "layout_model_working"
    
    # Borderline case — use confidence scores
    avg_conf = calculate_avg_confidence(layout_results)
    if avg_conf < 0.5:
        return "fullpage", "low_layout_confidence"
    
    return "layout", "default"
```

### Trade-offs
| Factor | Assessment |
|--------|-----------|
| **Complexity** | High — requires parallel execution, result comparison logic |
| **Reliability** | **Very High** — directly compares actual outputs |
| **Cost** | **2x API calls** — runs both strategies |
| **Latency** | Parallel, so ~1x latency, but 2x cost |

**Cost concern**: This doubles API calls to the AI vision model, which is expensive.

---

## Approach 6: Adaptive Threshold from Data

**Concept**: Instead of fixed 30%, compute a dynamic threshold based on the image's own characteristics.

### Image Characteristics to Consider

1. **Resolution**: Higher resolution → expect more text blocks
2. **Aspect ratio**: Extreme ratios (e.g., 21:9) suggest screenshots
3. **Color depth**: Grayscale suggests documents, color suggests mixed
4. **Entropy**: High entropy suggests complex content (screenshots), low suggests simple (documents)

### Implementation
```python
def compute_adaptive_threshold(
    image: Image.Image,
    layout_blocks: list[dict]
) -> float:
    w, h = image.size
    aspect_ratio = max(w, h) / min(w, h)
    
    # Base threshold
    base_threshold = 0.30
    
    # Adjust for aspect ratio (screenshots often have extreme ratios)
    if aspect_ratio > 2.0:
        base_threshold *= 0.7  # Lower threshold for wide images
    
    # Adjust for resolution (higher res → expect more coverage)
    megapixels = (w * h) / 1_000_000
    if megapixels > 5:
        base_threshold *= 1.2  # Higher threshold for high-res
    
    # Adjust for block count (few blocks → likely failing)
    if len(layout_blocks) < 3:
        base_threshold *= 0.5  # Much lower threshold
    
    return min(0.5, max(0.1, base_threshold))
```

### Trade-offs
| Factor | Assessment |
|--------|-----------|
| **Complexity** | Medium — need to tune adjustment factors |
| **Reliability** | Medium — still heuristic-based, just more flexible |
| **Cost** | Zero extra |
| **Latency** | Negligible |

**Problem**: This still uses magic numbers (0.7, 1.2, 0.5), just more of them. Not truly "adaptive".

---

## Recommended Approach: Multi-Signal Fusion

**Combine approaches 2, 3, and 4** for a robust, zero-extra-cost solution.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Input Image                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Quick Heuristics (< 1ms)                           │
│  - Aspect ratio check                                       │
│  - Resolution check                                         │
│  - ScreenshotScanner (optional, if installed)               │
│  → If clearly screenshot → bypass immediately               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Layout Model Analysis (~20-50ms)                   │
│  - Run PP-DocLayout-V3 / DocLayout-YOLO                     │
│  - Extract: block count, avg confidence, coverage           │
│  → If 0 blocks OR avg_confidence < 0.3 → bypass            │
│  → If coverage < adaptive_threshold → bypass                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Post-OCR Validation (after first OCR)              │
│  - Calculate text density (chars/pixel)                     │
│  - Check text coherence (alphanumeric ratio)                │
│  - Compare with expected range for image type               │
│  → If results suspicious → retry with full-page OCR         │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Plan

#### Phase 1: Use Existing Confidence Scores (Zero Cost)

**File to modify**: `api/app/convert/ocr/ai_client.py`

```python
def _should_bypass_local_layout_block_ocr(
    self,
    *,
    image_path: str,
    image: Image.Image,
) -> str | None:
    """Return a bypass reason when direct page OCR is safer/faster."""
    
    try:
        layout_blocks, image_regions = self._run_local_layout_analysis(image_path)
    except Exception:
        return None
    
    # ... existing caching code ...
    
    page_w, page_h = image.size
    if page_w <= 0 or page_h <= 0:
        return None
    
    page_area = max(1.0, float(page_w * page_h))
    text_blocks: list[list[float]] = []
    text_area = 0.0
    confidence_scores: list[float] = []  # NEW: collect confidence scores
    
    for block in layout_blocks:
        label = str(block.get("label") or "")
        if _is_image_like_layout_label(label):
            continue
        if self._should_skip_layout_block_for_ocr(label=label):
            continue
        bbox = block.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            continue
        bbox_n = _normalize_bbox_px(bbox)
        if bbox_n is None:
            continue
        x0, y0, x1, y1 = [float(v) for v in bbox_n]
        text_blocks.append([x0, y0, x1, y1])
        text_area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
        
        # NEW: collect confidence score
        score = block.get("score")
        if isinstance(score, (int, float)):
            confidence_scores.append(float(score))
    
    # NEW: Check confidence scores first (highest signal)
    if confidence_scores:
        avg_confidence = sum(confidence_scores) / len(confidence_scores)
        low_confidence_ratio = sum(1 for s in confidence_scores if s < 0.5) / len(confidence_scores)
        
        # If model is not confident, bypass
        if avg_confidence < 0.4:
            logger.info(
                "Layout model avg confidence %.2f below 0.4 — bypassing block OCR",
                avg_confidence,
            )
            return "low_layout_confidence"
        
        # If many detections are low confidence, bypass
        if low_confidence_ratio > 0.5:
            logger.info(
                "Layout model %.0f%% detections below 0.5 confidence — bypassing block OCR",
                low_confidence_ratio * 100,
            )
            return "high_low_confidence_ratio"
    
    # EXISTING: Coverage check (now with adaptive threshold)
    coverage = text_area / page_area
    
    # NEW: Adaptive threshold based on block count and confidence
    base_threshold = float(self._LOW_COVERAGE_THRESHOLD)
    if len(text_blocks) < 3:
        base_threshold *= 0.5  # Lower threshold when few blocks found
    if confidence_scores and sum(confidence_scores) / len(confidence_scores) < 0.6:
        base_threshold *= 0.7  # Lower threshold when confidence is mediocre
    
    if text_blocks and coverage < base_threshold:
        logger.info(
            "Layout text coverage %.1f%% below adaptive threshold %.0f%% — bypassing block OCR"
            " (text_blocks=%s, avg_conf=%.2f, layout_model=%s, image=%s)",
            coverage * 100,
            base_threshold * 100,
            len(text_blocks),
            sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0,
            self.layout_model,
            Path(image_path).name,
        )
        return "low_text_coverage"
    
    # ... rest of existing logic ...
```

#### Phase 2: Add Post-OCR Validation (Low Cost)

After the first OCR attempt (whether layout-based or full-page), validate the results:

```python
def _validate_ocr_results(
    self,
    ocr_results: list[dict],
    image: Image.Image,
    strategy_used: str,
) -> bool:  # True if results look valid, False if should retry
    """Validate OCR results and suggest retry if suspicious."""
    
    if not ocr_results:
        return False
    
    page_w, page_h = image.size
    page_area = page_w * page_h
    
    total_chars = sum(len(r.get("text", "")) for r in ocr_results)
    text_density = total_chars / (page_area / 10000)  # chars per 10K pixels
    
    # Check text coherence
    alphanumeric = sum(c.isalnum() for r in ocr_results for c in r.get("text", ""))
    coherence = alphanumeric / max(1, total_chars)
    
    # Suspicious if:
    # - Very little text found (density < 5 chars/10K pixels)
    # - Text is mostly garbage (coherence < 0.5)
    # - Only 1-2 blocks found on a full page
    suspicious = (
        text_density < 5
        or coherence < 0.5
        or (strategy_used == "layout" and len(ocr_results) < 2)
    )
    
    if suspicious:
        logger.warning(
            "OCR results suspicious: density=%.1f, coherence=%.2f, blocks=%d, strategy=%s",
            text_density,
            coherence,
            len(ocr_results),
            strategy_used,
        )
    
    return not suspicious
```

#### Phase 3: Optional ScreenshotScanner Integration (Zero ML Cost)

```python
# Optional dependency
try:
    from screenshot_scanner import ScreenshotScanner
    _screenshot_scanner = ScreenshotScanner()
except ImportError:
    _screenshot_scanner = None

def _quick_screenshot_check(image_path: str) -> bool:
    """Quick check if image is likely a screenshot."""
    if _screenshot_scanner is None:
        return False
    
    try:
        result = _screenshot_scanner.process(image_path)
        return result.get("is_screenshot", False)
    except Exception:
        return False
```

### Decision Matrix

| Signal | Weight | Threshold | Action |
|--------|--------|-----------|--------|
| ScreenshotScanner says screenshot | High | `is_screenshot=True` | Bypass immediately |
| 0 layout blocks detected | High | `len(blocks) == 0` | Bypass immediately |
| Avg confidence < 0.4 | High | `avg(score) < 0.4` | Bypass immediately |
| Coverage < adaptive threshold | Medium | `coverage < threshold` | Bypass |
| Post-OCR density < 5 chars/10Kpx | Medium | `density < 5` | Retry with different strategy |
| Post-OCR coherence < 0.5 | Medium | `coherence < 0.5` | Retry with different strategy |

### Expected Outcomes

| Image Type | Current Behavior | Proposed Behavior |
|------------|------------------|-------------------|
| **Document PDF** | ✅ Works (coverage > 30%) | ✅ Works (high confidence + coverage) |
| **Screenshot with text** | ❌ Often fails (coverage < 30%) | ✅ Bypasses (low confidence OR low coverage) |
| **Screenshot with dense text** | ❌ May fail (coverage > 30%) | ✅ Bypasses (low confidence) |
| **Photo of document** | ❌ May fail | ✅ Bypasses (low confidence) |
| **Mixed content** | ⚠️ Inconsistent | ✅ Adaptive threshold |

---

## References

### External Libraries

1. **ScreenshotScanner** — https://pypi.org/project/ScreenshotScanner/
   - Heuristic-based screenshot detection
   - 13 checks, no ML, milliseconds
   - MIT license

2. **is_image_document_ai** — https://github.com/Logophoman/is_image_document_ai
   - MobileNetV2 / TinyCNN classifiers
   - 99%+ accuracy on document vs. image
   - ~14MB model size

3. **DocumentFigureClassifier-v2.5** — https://huggingface.co/docling-project/DocumentFigureClassifier-v2.5
   - EfficientNet-B0 based
   - 26 categories including screenshots
   - Can run via ONNX

### Academic Research

1. **CE-OCR: Consensus Entropy for OCR Quality Assessment** — arxiv.org/abs/2504.11101
   - Training-free uncertainty metric
   - Measures agreement among multiple VLMs
   - 42.1% F1 improvement over VLM-as-Judge

2. **Confidence-Aware Document OCR Error Detection** — link.springer.com/chapter/10.1007/978-3-031-70442-0_13
   - ConfBERT: BERT + OCR confidence scores
   - Demonstrates confidence scores improve error detection

3. **Completeness Confidence Index (CCI)** — engrxiv.org/preprint/download/6568/10764
   - Residual signal analysis
   - Structural coherence validation
   - Cross-modal redundancy

4. **GLM-OCR** — arxiv.org/abs/2603.10910
   - Uses PP-DocLayout-V3 for layout analysis
   - Acknowledges error propagation in two-stage pipelines

### PaddleOCR / PaddleX Documentation

1. **Layout Detection** — paddlepaddle.github.io/PaddleX/latest/en/module_usage/tutorials/ocr_modules/layout_detection.html
   - Per-box confidence scores available
   - Score range: 0-1

2. **Layout Analysis** — paddlepaddle.github.io/PaddleOCR/main/en/version3.x/module_usage/layout_analysis.html
   - PP-DocLayout-V3 supports 25 element categories
   - Reading order support

---

## Caveats / Not Found

1. **No direct benchmark for "layout model failure detection"** — this is a novel problem specific to our use case (PDF-to-PPT with mixed document types)

2. **ScreenshotScanner reliability unknown** — it's a heuristic tool, not extensively benchmarked. May have false positives/negatives on edge cases.

3. **Confidence score calibration** — different models may have different confidence score distributions. PP-DocLayout-V3's 0.8 may mean something different from DocLayout-YOLO's 0.8.

4. **Cost of post-OCR validation** — if we need to retry OCR, that's an extra API call. Need to balance validation cost vs. retry cost.

5. **No information on PP-DocLayout-V3's training data for screenshots** — PaddleOCR docs mention training on "papers, magazines, PPTs, contracts, books" but not screenshots. This explains why it fails on screenshots.
