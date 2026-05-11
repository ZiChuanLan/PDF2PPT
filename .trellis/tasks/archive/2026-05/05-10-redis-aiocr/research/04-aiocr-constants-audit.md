# Research: AIOCR Pipeline Constants Audit

- **Query**: Catalog ALL unexternalized constants across `api/app/convert/ocr/` pipeline
- **Scope**: internal
- **Date**: 2026-05-10

---

## Executive Summary

The AIOCR pipeline contains **~200+ named constants** across 12 files. Approximately **30** of these are already externalized via `config.py` Settings or have env-var runtime helpers. The remaining **~170** are module-level named constants or inline hardcoded values, classified below by category and priority.

The largest concentration is in `ai_client.py` (~75 named constants) and `local_providers.py` (~105 named constants). About **15 duplicates** exist across files for the same semantic value (e.g., default confidence, max side pixels, overlapping thresholds).

**Overall externalization ratio**: ~15% (30 of 200+).

---

## 1. Constants Already Externalized (config.py Settings)

| Setting | Default | Env Var | Consumed In |
|---------|---------|---------|-------------|
| `ocr_paddle_vl_predict_timeout_s` | 180.0 | `OCR_PADDLE_VL_PREDICT_TIMEOUT_S` | `_get_paddle_predict_timeout()` ai_client.py:194 |
| `ocr_ai_retry_backoff_base_s` | 8.0 | `OCR_AI_RETRY_BACKOFF_BASE_S` | `_get_retry_backoff_base()` ai_client.py:203 |
| `ocr_ai_rate_limited_min_delay_s` | 2.0 | `OCR_AI_RATE_LIMITED_MIN_DELAY_S` | `_get_rate_limited_min_delay()` ai_client.py:211 |
| `ocr_ai_page_concurrency_default` | 1 | (settings field) | OCR manager layer |
| `ocr_ai_page_concurrency_max` | 8 | (settings field) | OCR manager layer |
| `ocr_ai_block_concurrency_default` | 1 | (settings field) | OCR manager layer |
| `ocr_ai_block_concurrency_max` | 8 | (settings field) | OCR manager layer |
| `ocr_ai_rpm_default` | 1 | (settings field) | OCR manager layer |
| `ocr_ai_rpm_max` | 2000 | (settings field) | OCR manager layer |
| `ocr_ai_tpm_default` | 1000 | (settings field) | OCR manager layer |
| `ocr_ai_tpm_max` | 2000000 | (settings field) | OCR manager layer |
| `ocr_ai_max_retries_default` | 0 | (settings field) | OCR manager layer |
| `ocr_ai_max_retries_max` | 8 | (settings field) | OCR manager layer |
| `ocr_render_dpi` | 200 | `OCR_RENDER_DPI` | PdfParser layer |
| `scanned_render_dpi` | 200 | `SCANNED_RENDER_DPI` | PdfParser layer |
| `ocr_page_timeout_s` | 300 | `OCR_PAGE_TIMEOUT_S` | OcrManager |
| `ocr_max_consecutive_timeouts` | 2 | `OCR_MAX_CONSECUTIVE_TIMEOUTS` | OcrManager |
| `ocr_total_timeout_s` | 3600 | `OCR_TOTAL_TIMEOUT_S` | OcrManager |
| `ocr_image_region_timeout_s` | 12 | `OCR_IMAGE_REGION_TIMEOUT_S` | OcrManager |
| `enable_layout_assist` | False | `ENABLE_LAYOUT_ASSIST` | Feature toggle |

**Total**: 20 Settings fields related to OCR. Only ~10% of all OCR constants.

---

## 2. Runtime Env-Var Helpers (NOT in config.py)

These read `os.getenv()` at call time but bypass the Settings pydantic model:

| Env Var | File:Line | Default | Type |
|---------|-----------|---------|------|
| `OCR_PADDLE_VL_DOCPARSER_INIT_TIMEOUT_S` | ai_client.py:1521 | 30.0 | float |
| `OCR_PADDLE_VL_DOCPARSER_PROGRESS_LOG_INTERVAL_S` | ai_client.py:1349 | 10.0 | float |
| `OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S` | ai_client.py:1589 | 120.0 | float |
| `OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S_V15` | ai_client.py:1598 | varies | float |
| `OCR_PADDLE_VL_DOCPARSER_RETRY_TIMEOUT_S` | ai_client.py:1615,1621 | varies | float |
| `OCR_PADDLE_VL_DOCPARSER_RETRY_ON_TIMEOUT` | ai_client.py:1632 | True(v1)/False(v15) | bool |
| `OCR_PADDLE_VL_DOCPARSER_SINGLEFLIGHT` | ai_client.py:1644 | True(v15)/False | bool |
| `OCR_PADDLE_VL_DOCPARSER_SINGLEFLIGHT_WAIT_S` | ai_client.py:1666 | varies | float |
| `OCR_PADDLE_VL_DOCPARSER_SINGLEFLIGHT_LOCK_DIR` | ai_client.py:1671 | /tmp | string |
| `OCR_PADDLE_VL_DOCPARSER_MAX_SIDE_PX` | ai_client.py:1718 | 2200 | int |
| `OCR_PADDLE_VL_DOCPARSER_MAX_PIXELS` | result_parsing.py:61 | None | int |
| `OCR_PADDLE_VL_DOCPARSER_MAX_CONCURRENCY` | ai_client.py:1562 | None | int |
| `OCR_PADDLE_VL_DOCPARSER_USE_QUEUES` | ai_client.py:1575 | True | bool |
| `OCR_PADDLE_VL_REC_SERVER_URL` | ai_client.py:1489 | None | string |
| `OCR_PADDLE_VL_REC_BACKEND` | ai_client.py:1500 | vllm-server | string |
| `OCR_PADDLE_ALLOW_MODEL_DOWNGRADE` | ai_client.py:886 | False | bool |
| `OCR_PADDLE_VL_ALLOW_PROMPT_FALLBACK` | ai_client.py:890 | False | bool |
| `OCR_PADDLE_PROMPT_FALLBACK_MODEL` | ai_client.py:4150 | None | string |
| `OCR_AI_REQUEST_TIMEOUT_S` | ai_client.py:3951 | 25.0 | float |
| `OCR_AI_REQUEST_TIMEOUT_S_QWEN` | ai_client.py:3960 | 25.0 | float |
| `OCR_AI_REQUEST_TIMEOUT_S_DEEPSEEK_OCR` | ai_client.py:3969 | 25.0 | float |
| `OCR_AI_REQUEST_TIMEOUT_S_PADDLE_VL` | ai_client.py:3979 | 25.0 | float |
| `OCR_AI_LAYOUT_MODEL_INIT_TIMEOUT_S` | ai_client.py:2101 | 30.0 | float |
| `OCR_AI_LAYOUT_MODEL_PREDICT_TIMEOUT_S` | ai_client.py:2298 | 45.0 | float |
| `OCR_AI_LAYOUT_BLOCK_REQUEST_TIMEOUT_S` | ai_client.py:2728 | 40.0 | float |
| `OCR_AI_LAYOUT_BLOCK_REQUEST_TIMEOUT_S_QWEN` | ai_client.py:2735 | 40.0 | float |
| `OCR_AI_LAYOUT_BLOCK_REQUEST_TIMEOUT_S_DEEPSEEK_OCR` | ai_client.py:2743 | 40.0 | float |
| `OCR_AI_LAYOUT_BLOCK_RETRY_TIMEOUT_S` | ai_client.py:2772 | varies | float |
| `OCR_AI_LAYOUT_BLOCK_RETRY_TIMEOUT_S_QWEN` | ai_client.py:2765 | varies | float |
| `OCR_AI_LAYOUT_BLOCK_RETRY_ON_TIMEOUT` | ai_client.py:2786 | True | bool |
| `OCR_AI_LAYOUT_BLOCK_RETRY_ON_TIMEOUT_QWEN` | ai_client.py:2783 | True | bool |
| `OCR_AI_LAYOUT_BLOCK_MIN_SIDE_PX` | ai_client.py:2683 | 0 | int |
| `OCR_AI_LAYOUT_BLOCK_MAX_CONCURRENCY` | ai_client.py:2702 | 4 | int |
| `OCR_AI_LAYOUT_BLOCK_PROGRESS_LOG_INTERVAL_S` | ai_client.py:2721 | 10.0 | float |
| `OCR_AI_IMAGE_REGION_TIMEOUT_S` | ai_client.py:3501 | 30.0 | float |
| `OCR_AI_LAYOUT_COVERAGE_BYPASS_THRESHOLD` | ai_client.py:2974 | 0.30 | float |
| `OCR_AI_MAX_ATTEMPTS` | ai_client.py:4173 | 3 | int |
| `OCR_AI_EMPTY_RESPONSE_BREAK_AFTER` | ai_client.py:4176 | 2 | int |

**Total**: ~38 env vars read at runtime but NOT in Settings pydantic. These bypass validation, documentation, and centralized management.

---

## 3. Complete ai_client.py Constants Catalog

### 3.1 Rate Limiter (ai_client.py:92-97)

| Constant | Value | Class | Notes |
|----------|-------|-------|-------|
| `_RATE_LIMITER_CUTOFF_WINDOW_S` | 60.0 | P2-algorithmic | Rate limiter pruning window |
| `_RATE_LIMITER_MAX_WAIT_S` | 60.0 | P2-algorithmic | Max wait in limiter |
| `_RATE_LIMITER_SLEEP_MIN_S` | 0.05 | P2-internal | Min sleep between checks |
| `_RATE_LIMITER_SLEEP_MAX_S` | 5.0 | P2-internal | Max sleep between checks |
| `_CHARS_PER_TOKEN` | 4.0 | P2-algorithmic | Estimation ratio |

### 3.2 Retry / Backoff (ai_client.py:99-104)

| Constant | Value | Class | Notes |
|----------|-------|-------|-------|
| `_RETRY_BACKOFF_BASE_S` | 8.0 | P0-env | Already linked to Settings |
| `_RETRY_BACKOFF_MAX_S` | 0.75 | P1-algorithmic | Cap per attempt |
| `_RETRY_BACKOFF_MULTIPLIER` | 2 | P1-algorithmic | Exponential factor |
| `_RATE_LIMITED_MIN_DELAY_S` | 2.0 | P0-env | Already linked to Settings |
| `_NON_RATE_LIMITED_MIN_DELAY_S` | 0.25 | P2-algorithmic | Min delay for non-429 |

### 3.3 Debug Text Limits (ai_client.py:106-110)

| Constant | Value | Class |
|----------|-------|-------|
| `_DEBUG_TEXT_COMPACT_LIMIT` | 160 | P3-internal |
| `_DEBUG_TEXT_CONTENT_LIMIT` | 400 | P3-internal |
| `_DEBUG_TEXTS_LIMIT` | 240 | P3-internal |
| `_DEBUG_LABEL_LIMIT` | 64 | P3-internal |

### 3.4 Paddle / Singleflight (ai_client.py:112-117)

| Constant | Value | Class | Notes |
|----------|-------|-------|-------|
| `_PADDLE_DOC_MAX_SIDE_PX` | 6000 | P1-env | Upper bound; env can lower |
| `_PADDLE_VL15_PREDICT_TIMEOUT_S` | 180.0 | P0-env | Linked to Settings |
| `_PADDLE_MIN_PREDICT_TIMEOUT_S` | 10.0 | P1-algorithmic | Floor for all predict timeouts |
| `_PADDLE_RETRY_TIMEOUT_CAP_S` | 90.0 | P1-algorithmic | Default retry cap |
| `_SINGLEFLIGHT_WAIT_S` | 3.0 | P1-env | Fallback when vendor has no tuning |

### 3.5 Concurrency Wait (ai_client.py:119-122)

| Constant | Value | Class |
|----------|-------|-------|
| `_CONCURRENCY_WAIT_MIN_S` | 0.01 | P2-internal |
| `_CONCURRENCY_WAIT_MAX_S` | 0.1 | P2-internal |
| `_DONE_WAIT_TIMEOUT_S` | 1.0 | P2-internal |

### 3.6 Layout Model (ai_client.py:124-127)

| Constant | Value | Class | Notes |
|----------|-------|-------|-------|
| `_LAYOUT_MODEL_INIT_TIMEOUT_MIN_S` | 5.0 | P1-env | Env overrides with higher |
| `_LAYOUT_BLOCK_DIMENSION_MIN_PX` | 3.0 | P2-algorithmic | Skip tiny blocks |
| `_LAYOUT_BLOCK_PREDICT_TIMEOUT_MIN_S` | 5.0 | P1-env | Env overrides with higher |

### 3.7 Image Processing: Block Crop Padding (ai_client.py:129-135)

| Constant | Value | Class |
|----------|-------|-------|
| `_BLOCK_CROP_PAD_MAX_PX` | 24 | P2-algorithmic |
| `_BLOCK_CROP_PAD_MIN_PX` | 2 | P2-algorithmic |
| `_BLOCK_CROP_PAD_RATIO` | 0.03 | P2-algorithmic |
| `_BLOCK_CROP_YPAD_MAX_PX` | 24 | P2-algorithmic |
| `_BLOCK_CROP_YPAD_MIN_PX` | 2 | P2-algorithmic |
| `_BLOCK_CROP_YPAD_RATIO` | 0.18 | P2-algorithmic |

### 3.8 Ring Margin - Visual Bounds Tightening (ai_client.py:137-143)

| Constant | Value | Class |
|----------|-------|-------|
| `_RING_YMARGIN_MAX_PX` | 18 | P2-algorithmic |
| `_RING_YMARGIN_MIN_PX` | 2 | P2-algorithmic |
| `_RING_YMARGIN_RATIO` | 0.10 | P2-algorithmic |
| `_RING_XMARGIN_MAX_PX` | 18 | P2-algorithmic |
| `_RING_XMARGIN_MIN_PX` | 2 | P2-algorithmic |
| `_RING_XMARGIN_RATIO` | 0.04 | P2-algorithmic |

### 3.9 Background Diff / Edge / Outer Margin (ai_client.py:146-158)

| Constant | Value | Class |
|----------|-------|-------|
| `_BG_DIFF_LIGHT_THRESHOLD` | 18.0 | P2-algorithmic |
| `_BG_DIFF_DARK_THRESHOLD` | 22.0 | P2-algorithmic |
| `_BG_DIFF_LIGHT_BG_LUMA` | 150.0 | P2-algorithmic |
| `_EDGE_THRESH_LOW` | 22 | P2-algorithmic |
| `_EDGE_THRESH_HIGH` | 26 | P2-algorithmic |
| `_EDGE_HEIGHT_CUTOFF` | 96 | P2-algorithmic |
| `_OUTER_MARGIN_MAX_PX` | 12 | P2-algorithmic |
| `_OUTER_MARGIN_MIN_PX` | 2 | P2-algorithmic |
| `_OUTER_MARGIN_RATIO` | 0.05 | P2-algorithmic |

### 3.10 Row/Col Thresholds (ai_client.py:160-164)

| Constant | Value | Class |
|----------|-------|-------|
| `_ROW_THRESHOLD_MIN_PX` | 2 | P2-algorithmic |
| `_ROW_THRESHOLD_RATIO` | 0.0035 | P2-algorithmic |
| `_COL_THRESHOLD_MIN_PX` | 1 | P2-algorithmic |
| `_COL_THRESHOLD_RATIO` | 0.020 | P2-algorithmic |

### 3.11 Keep/Tightened Ratios (ai_client.py:166-181)

Control when visual tightening is skipped (bbox already tight enough).

| Constant | Value | Class |
|----------|-------|-------|
| `_KEEP_AREA_RATIO` | 0.94 | P2-algorithmic |
| `_KEEP_WIDTH_RATIO` | 0.97 | P2-algorithmic |
| `_KEEP_HEIGHT_RATIO` | 0.90 | P2-algorithmic |
| `_PAD_X_MAX_PX` | 18 | P2-algorithmic |
| `_PAD_X_MIN_PX` | 2 | P2-algorithmic |
| `_PAD_X_RATIO` | 0.08 | P2-algorithmic |
| `_PAD_Y_MAX_PX` | 12 | P2-algorithmic |
| `_PAD_Y_MIN_PX` | 2 | P2-algorithmic |
| `_PAD_Y_RATIO` | 0.12 | P2-algorithmic |
| `_TIGHTENED_WIDTH_RATIO` | 0.985 | P2-algorithmic |
| `_TIGHTENED_HEIGHT_RATIO` | 0.94 | P2-algorithmic |
| `_DEFAULT_TOLERANCE_PX` | 1.5 | P2-algorithmic |

### 3.12 Request Timeout (ai_client.py:220-223)

| Constant | Value | Class | Notes |
|----------|-------|-------|-------|
| `_REQUEST_TIMEOUT_BUFFER_S` | 12.0 | P1-algorithmic | Buffer added to base timeout |
| `_REQUEST_TIMEOUT_MULTIPLIER` | 1.5 | P1-algorithmic | Multiplier for timeout calc |
| `_REQUEST_TIMEOUT_CAP_S` | 55.0 | P1-env | Max retry timeout cap |
| `_RETRY_TIMEOUT_BUFFER_S` | 8.0 | P1-algorithmic | Buffer for retry timeout |

### 3.13 OCR Bypass (Layout Block → Direct Page) (ai_client.py:225-246)

| Constant | Value | Class | Notes |
|----------|-------|-------|-------|
| `_LOW_CONFIDENCE_THRESHOLD` | 0.6 | P1-algorithmic | Below this = aggressive bypass |
| `_HIGH_CONFIDENCE_THRESHOLD` | 0.85 | P1-algorithmic | Above this = conservative bypass |
| `_LOW_CONFIDENCE_COVERAGE_MULTIPLIER` | 0.6 | P1-algorithmic | Lower threshold for low conf |
| `_HIGH_CONFIDENCE_COVERAGE_MULTIPLIER` | 1.3 | P1-algorithmic | Raise threshold for high conf |
| `_WIDE_FLAT_MIN_ASPECT_RATIO` | 7.0 | P1-algorithmic | Wide-flat block detection |
| `_WIDE_FLAT_MIN_WIDTH_RATIO` | 0.35 | P1-algorithmic | Min width for wide-flat |
| `_WIDE_FLAT_MAX_HEIGHT_RATIO` | 0.18 | P1-algorithmic | Max height for wide-flat |
| `_WIDE_FLAT_MAX_VERTICAL_SPAN` | 0.28 | P1-algorithmic | Max vertical spread |
| `_WIDE_FLAT_MIN_COVERAGE_RATIO` | 0.65 | P1-algorithmic | Min coverage for wide-flat |
| `_CONFIDENCE_BYPASS_LOW_THRESHOLD` | 0.5 | P1-algorithmic | Individual detection low |
| `_CONFIDENCE_BYPASS_AVG_THRESHOLD` | 0.4 | P1-algorithmic | Average for bypass trigger |
| `_CONFIDENCE_BYPASS_RATIO_THRESHOLD` | 0.5 | P1-algorithmic | Ratio for bypass trigger |

### 3.14 OCR Result Validation (ai_client.py:241-247)

| Constant | Value | Class | Notes |
|----------|-------|-------|-------|
| `_VALIDATION_DENSITY_THRESHOLD` | 0.3 | P1-algorithmic | Chars per 10Kpx threshold |
| `_VALIDATION_COHERENCE_THRESHOLD` | 0.4 | P1-algorithmic | Alphanumeric ratio |
| `_VALIDATION_MIN_CHARS_FOR_COHERENCE` | 10 | P1-algorithmic | Min chars for check |
| `_VALIDATION_LARGE_IMAGE_AREA` | 500000 | P1-algorithmic | Large image pixel area |
| `_VALIDATION_TOO_FEW_BLOCKS` | 2 | P1-algorithmic | Too-few-blocks threshold |
| `_PIXELS_PER_10K` | 10000.0 | P2-internal | Density calc divisor |

### 3.15 Instance-Level Runtime Constant (ai_client.py:2974)

| Constant | Value | Class | Notes |
|----------|-------|-------|-------|
| `_LOW_COVERAGE_THRESHOLD` (instance attr) | env var, default 0.30 | P1-env | Coverage bypass threshold |
| `_SCORE_BBOX_COVERAGE_WEIGHT` | 1.6 | P2-internal | Line 3794, inline | 
| `_SCORE_BBOX_VARIANCE_DIVISOR` | 32.0 | P2-internal | Line 3794, inline |
| `_SCORE_BBOX_OUT_RATE_WEIGHT` | 2.0 | P2-internal | Line 3794, inline |

---

## 4. Inline Hardcoded Constants in ai_client.py (NOT named module-level)

### 4.1 AiOcrClient.__init__() range bounds (ai_client.py:901-928)

| Value | Context | Line |
|-------|---------|------|
| `high=8` | `_coerce_int_in_range` for layout_block_max_concurrency | 906 |
| `low=1, high=2000` | RPM limit range | 912-913 |
| `low=1, high=2_000_000` | TPM limit range | 917-918 |
| `low=0, high=8` | Max retries range | 925-926 |

### 4.2 AiOcrTextRefiner.__init__() range bounds (ai_client.py:4627-4646)

| Value | Context | Line |
|-------|---------|------|
| `low=1, high=2000` | RPM limit range | 4629-4630 |
| `low=1, high=2_000_000` | TPM limit range | 4634-4635 |
| `low=0, high=8` | Max retries range | 4643-4644 |

### 4.3 Chat completion token estimation (ai_client.py:655)

| Value | Context | Line |
|-------|---------|------|
| `image_tokens = int(image_items) * 512` | Token estimate per image | 655 |

### 4.4 DeepSeek tagged items extraction (ai_client.py:2425)

| Value | Context | Line |
|-------|---------|------|
| `max_items=48` | Call to `_extract_deepseek_tagged_items` | 2425 |

### 4.5 Layout block OCR (ai_client.py)

| Value | Context | Line |
|-------|---------|------|
| `clamp_max_tokens(768, kind="ocr")` | Layout block crop token budget | 3098 |
| `temperature=0` | Chat completion temperature | 3097, 4258 |
| `timeout=1.0` | `wait()` timeout in ThreadPoolExecutor loop | 3415 |
| `confidence clamped 0.55-0.98` | Layout block OCR result confidence | 3432-3435 |
| `confidence default 0.82` | Layout block OCR fallback confidence | 3438 |
| `max_regions=12` | Image region validation | 3602 |
| `return 4` | Default max_workers for layout blocks | 2716 |

### 4.6 Direct Page OCR - Attempt Limits (ai_client.py:4198-4203)

| Value | Context | Line |
|-------|---------|------|
| `[60, 40, 24, 16, 10]` | Standard model attempt limits | 4198 |
| `[180, 120, 90, 60, 40]` | DeepSeek model attempt limits | 4203 |
| `requested_tokens = 8192` | Base OCR token budget | 4210 |
| `int(320 + int(item_limit) * 22)` | DeepSeek token calc | 4215 |
| `max(900, requested_tokens)` | DeepSeek min tokens | 4216 |
| `min(3500, requested_tokens)` | DeepSeek max tokens | 4217 |

### 4.7 Image Region Detection (ai_client.py:3499-3505)

| Value | Context | Line |
|-------|---------|------|
| `max(8.0, _env_float(...))` | Min request timeout | 1900 |
| `clamp_max_tokens(1024, kind="ocr")` | Image region token budget | 3504 |

### 4.8 Text Refiner (AiOcrTextRefiner) (ai_client.py:4668-4922)

| Value | Context | Line |
|-------|---------|------|
| `timeout_s=60.0` | Hardcoded refiner chat timeout | 4668 |
| `temperature=0` | Refiner chat completion | 4675 |
| `clamp_max_tokens(4096, kind="refiner")` | Text refine call | 4761 |
| `clamp_max_tokens(3072, kind="refiner")` | Linebreak refine call | 4922 |
| `max_items_per_call: int = 80` | Refine items default | 4683 |
| `max_items_per_call: int = 36` | Linebreak assist default | 4797 |
| `max_lines_per_item: int = 8` | Linebreak default | 4798 |

### 4.9 Line Split Constants (inline in AiOcrTextRefiner)

| Value | Context | Line |
|-------|---------|------|
| `min_ratio = 0.45` | Plausibility check base | 4998 |
| `min_ratio = 0.56` | Plausibility for <=64 chars | 5002 |
| `min_ratio = 0.62` | Plausibility for <=36 chars | 5004 |
| `compact_len <= 44 and diff >= 3` | Split plausibility check | 4992 |
| `w >= 0.25 * width and h/w <= 0.12` | Wide banner detection (line 5022-5023) | 5022 |
| `short_len <= 5 and imbalance < 0.30` | Imbalance guard | 5025 |
| `contrast < 8.0` | Ink projection contrast min | 5075, 5240 |
| `ink >= 0.16` | Ink mask threshold | 5080, 5244 |
| `max(0.02 * h_px, 1.0)` | Min row profile sum | 5082 |
| `0.015 * w_px` | Min col profile sum | 5246 |
| `h_px / 54.0` | Smoothing kernel divisor | 5085 |
| `0.22 * h_px` | Max merge gap | 5104 |
| `0.55 * avg_h` | Min line height ratio check | 5182 |
| `1.80 * avg_h` | Max line height ratio check | 5184 |
| `th = float(np.percentile(col_profile, 65.0))` | Column profile percentile | 5250 |
| `max(0.04, min(0.22, th))` | Column threshold clamp | 5251 |
| `margin_px = max(1, int(round(0.025 * float(base_w))))` | X-tighten margin | 5262 |
| `min_ratio = 0.28 if compact_len <= 8 else 0.22` | Min ratio for short/long | 5275 |

---

## 5. base.py Constants

| Constant | Value | Type | Line |
|----------|-------|------|------|
| `_ACRONYM_ALLOWLIST` | {AI, API, LLM, ...} | Set | 25-47 |
| `_VALID_AI_OCR_PROVIDERS` | {auto, openai, ...} | Set | 50-57 |
| `_AI_OCR_PROVIDER_ALIASES` | Map of aliases | Dict | 59-73 |
| `_PADDLE_OCR_VL_MODEL_V1` | "PaddlePaddle/PaddleOCR-VL" | String | 75 |
| `_PADDLE_OCR_VL_MODEL_V15` | "PaddlePaddle/PaddleOCR-VL-1.5" | String | 76 |
| `_DEFAULT_PADDLE_OCR_VL_MODEL` | = V1 | String | 77 |
| `_DEFAULT_PADDLE_DOC_BACKEND` | "vllm-server" | String | 78 |
| `_VALID_PADDLE_DOC_BACKENDS` | {vllm-server, sglang-server} | Set | 79 |
| `_LOC_TOKEN_PATTERN` | Regex | Compiled | 287 |

All are structural/semantic constants (provider IDs, model names, regex). Leave as-is.

---

## 6. result_parsing.py Constants

| Constant | Value | Line | Class |
|----------|-------|------|-------|
| `_IMAGE_REGION_LABEL_TOKENS` | {image, figure, chart, ...} | 15-28 | P3-structural |
| `_NON_IMAGE_REGION_LABEL_TOKENS` | {text, table, formula, ...} | 30-40 | P3-structural |
| `_PADDLE_DOC_VLM_PIXEL_FACTOR` | 28*28 = 784 | 42 | P2-algorithmic |
| `_PADDLE_DOC_VLM_MIN_PIXELS` | 784*130 = 101920 | 43 | P2-algorithmic |
| `_PADDLE_DOC_VLM_DEFAULT_MAX_PIXELS` | 784*1280 = 1003520 | 44 | P2-algorithmic |
| `_PADDLE_DOC_VLM_BASE_MAX_SIDE_PX` | 2200 | 45 | **DUPLICATE**: Same value as `_PADDLE_OCR_MAX_SIDE_PX` in local_providers.py:66 and env default in ai_client.py:1718 |
| **Inline**: `confidence = 0.9` | Default when no confidence | 371,374 | **DUPLICATE**: Different from 0.7 (ai_client.py:4470), 0.82 (ai_client.py:3438), 0.85 (local_providers.py:69) |

---

## 7. vendors.py Constants

| Constant | Value | Line | Class |
|----------|-------|------|-------|
| `VendorTuningConfig.vl_rec_max_concurrency` | 4 | 34 | P1-algorithmic |
| `VendorTuningConfig.use_queues` | True | 36 | P1-algorithmic |
| `VendorTuningConfig.predict_timeout_override` | None | 38 | P1-algorithmic |
| `VendorTuningConfig.retry_timeout_override` | None | 40 | P1-algorithmic |
| `VendorTuningConfig.retry_on_timeout` | False | 42 | P1-algorithmic |
| `VendorTuningConfig.singleflight` | False | 44 | P1-algorithmic |
| `VendorTuningConfig.singleflight_wait_s` | 3.0 | 46 | P1-algorithmic |
| `VendorTuningConfig.layout_block_max_concurrency` | None | 48 | P1-algorithmic |
| `VendorConfig.max_tokens_ocr` | 8192 | 69 | P0-env |
| `VendorConfig.max_tokens_refiner` | 4096 | 71 | P0-env |
| `clamp_max_tokens min` | 256 | 358-359 | P1-algorithmic |

### Vendor-Specific Tuning Overrides

**SiliconFlow** (vendors.py:90-107):
| Setting | Value |
|---------|-------|
| `vl_rec_max_concurrency` | 4 |
| `use_queues` | False |
| `predict_timeout_override` | 180.0 |
| `retry_timeout_override` | 20.0 |
| `retry_on_timeout` | False |
| `singleflight` | True |
| `singleflight_wait_s` | 10.0 |
| `layout_block_max_concurrency` | 2 |

---

## 8. local_providers.py Constants (~105 constants)

All are well-named module-level constants. Grouped by function:

### 8.1 Baidu OCR (8 constants, lines 15-37)

| Constant | Value |
|----------|-------|
| `_BAIDU_AREA_RATIO_PRUNE_THRESHOLD` | 0.16 |
| `_BAIDU_WIDTH_RATIO_PRUNE_THRESHOLD` | 0.85 |
| `_BAIDU_HEIGHT_RATIO_PRUNE_THRESHOLD` | 0.08 |
| `_BAIDU_COMPACT_TEXT_LENGTH_LIMIT` | 24 |
| `_BAIDU_AREA_RATIO_THRESHOLD_ALT` | 0.06 |
| `_BAIDU_COMPACT_TEXT_LENGTH_LIMIT_ALT` | 6 |
| `_BAIDU_HEIGHT_RATIO_THRESHOLD_ALT` | 0.06 |
| `_BAIDU_DEFAULT_CONFIDENCE` | 0.95 |

### 8.2 Tesseract OCR (8 constants, lines 42-61)

| Constant | Value | Notes |
|----------|-------|-------|
| `_TESSERACT_DEFAULT_MIN_CONFIDENCE` | 50.0 | 0-100 scale |
| `_TESSERACT_PSM_SPARSE_TEXT` | 11 | PSM mode |
| `_TESSERACT_LOW_RECALL_LINE_THRESHOLD` | 12 |
| `_TESSERACT_LOW_RECALL_WORD_THRESHOLD` | 80 |
| `_TESSERACT_LOW_CONFIDENCE_RETRY_THRESHOLD` | 25.0 |
| `_TESSERACT_LOOKS_EMPTY_LINE_THRESHOLD` | 8 |
| `_TESSERACT_LOOKS_EMPTY_WORD_THRESHOLD` | 40 |

### 8.3 PaddleOCR (4 constants, lines 66-74)

| Constant | Value |
|----------|-------|
| `_PADDLE_OCR_MAX_SIDE_PX` | 2200 |
| `_PADDLE_OCR_DEFAULT_CONFIDENCE` | 0.85 |
| `_PADDLE_OCR_MAX_NODES_FOR_TRAVERSAL` | 20000 |

### 8.4 Merge / Band / Noise / Dedupe / Quality (~80+ constants)

These are all algorithmic tuning knobs for OCR result post-processing. Full catalog in file lines 78-497. Key groups:
- Merge gap thresholds (4 constants, lines 78-88)
- Band clustering (4 constants, lines 92-104)
- Noise detection (6 constants, lines 108-124)
- Coarse AI paragraph pruning (2 constants, lines 129-133)
- Overlap merge (1 constant, line 138)
- Deduplication (16 constants, lines 144-182) - various thresholds for different dedupe strategies
- Text color sampling (22 constants, lines 186-250)
- Quality notes (14 constants, lines 254-296)
- Line break assist (20 constants, lines 300-348)
- Contextual noise filtering (18 constants, lines 350-422)
- Merge line items (8 constants, lines 424-444)
- Word-level merge (6 constants, lines 448-464)
- AI supplement pruning (10 constants, lines 466-494)

All are P2-algorithmic class — tuning knobs that are already named.

---

## 9. layout_models.py Inline Constants

| Value | Context | Line | Issue |
|-------|---------|------|-------|
| `imgsz=1024` | DocLayoutYoloProvider.predict() | 204 | Hardcoded inference size |
| `conf=0.2` | DocLayoutYoloProvider.predict() | 204 | Hardcoded confidence threshold |

---

## 10. Duplicate Constants Found

### 10.1 Max Side Pixel = 2200 (Defined in 3+ Places)

| Location | Constant Name | Value |
|----------|--------------|-------|
| `result_parsing.py:45` | `_PADDLE_DOC_VLM_BASE_MAX_SIDE_PX` | 2200 |
| `local_providers.py:66` | `_PADDLE_OCR_MAX_SIDE_PX` | 2200 |
| `ai_client.py:1718` | Env default for `OCR_PADDLE_VL_DOCPARSER_MAX_SIDE_PX` | 2200 |

**Recommendation**: Unify into one constant in `config.py` or a shared `constants.py`.

### 10.2 Default Confidence Values (4 Different Defaults)

| Location | Value | Context |
|----------|-------|---------|
| `ai_client.py:4470` | 0.7 | AI OCR JSON items (no confidence field) |
| `ai_client.py:3438` | 0.82 | Layout block OCR fallback |
| `local_providers.py:69` | 0.85 | PaddleOCR default |
| `local_providers.py:37` | 0.95 | Baidu OCR default |
| `result_parsing.py:371-374` | 0.9 | Paddle doc parser fallback |
| `deepseek_parser.py:205` | 0.72 | DeepSeek tagged items |
| `deepseek_parser.py:385` | 0.45 | DeepSeek det-only fallback |

**These are intentional per-provider but should be documented.**

### 10.3 Overlap / IoU Thresholds (Many Similar Values)

Multiple dedupe thresholds across `local_providers.py` with overlapping semantics:
- `_DEDUPE_STRONG_SAME_BBOX_OVERLAP` = 0.985
- `_DEDUPE_NEAR_SAME_BBOX_OVERLAP` = 0.965  
- `_DEDUPE_EXACT_LIKE_OVERLAP` = 0.93
- `_DEDUPE_MULTI_PROVIDER_OVERLAP` = 0.88
- `_DEDUPE_SINGLE_PROVIDER_OVERLAP` = 0.85
- `_OVERLAP_MERGE_THRESHOLD` = 0.90
- `_MERGE_LINE_ITEMS_OVERLAP_THRESHOLD` = 0.85

Not duplicates per se, but a named constant group that should be in one place.

---

## 11. Full AIOCR Call Chain Map

```
OcrManager (external layer)
  -> routing.build_ocr_route_plan()
    -> ROUTE_KIND_MACHINE_OCR:
      -> local_providers.BaiduOcrClient (Baidu API)
      -> local_providers.TesseractOcrClient (local Tesseract)
      -> local_providers.PaddleOcrClient (local PaddleOCR)
    -> ROUTE_KIND_REMOTE_PROMPT_OCR:
      -> ai_client.AiOcrClient.ocr_image()
        -> _ocr_image_with_ai_ocr_prompt() [direct page OCR]
          -> _chat_completion() -> _run_chat_completion_request()
            -> OpenAI client (via vendors adapter)
            -> _AiRequestRateLimiter (rate limiting)
          -> _normalize_items_to_pixels() (bbox coordinate normalization)
          -> _score_bbox_transform() (coordinate system scoring)
    -> ROUTE_KIND_REMOTE_DOC_PARSER:
      -> ai_client.AiOcrClient._ocr_image_with_paddle_doc_parser()
        -> _get_paddle_doc_parser() -> PaddleOCRVL client
        -> _run_paddle_doc_predict_with_timeout()
          -> singleflight lock (optional)
          -> _get_paddle_doc_parser().predict()
            -> PaddleOCR-VL remote API
          -> _extract_paddle_doc_parser_output() (result_parsing.py)
          -> _scale_paddle_doc_parser_output()
    -> ROUTE_KIND_LOCAL_LAYOUT_BLOCK_OCR:
      -> ai_client.AiOcrClient._ocr_image_with_local_layout_blocks()
        -> _run_local_layout_analysis() (PaddleX/PP-DocLayout + DocLayout-YOLO)
        -> _should_bypass_local_layout_block_ocr() (bypass logic)
        -> _tighten_layout_block_bbox_by_visual_bounds() (visual tightening)
        -> _crop_layout_block() (crop + polygon mask)
        -> _ocr_local_layout_block_crop() (per-block OCR)
          -> _chat_completion() for each block
        -> _validate_layout_block_ocr_results() (post-OCR quality check)

External supporting paths:
  -> ai_client.AiOcrTextRefiner.refine_items() (text refinement)
  -> ai_client.AiOcrTextRefiner.assist_line_breaks() (line break splitting)
  -> ai_client.AiOcrClient.detect_image_regions() (image region detection)
  -> deepseek_parser._extract_deepseek_tagged_items() (DeepSeek grounding)
  -> deepseek_parser._extract_deepseek_grounding_regions() (DeepSeek regions)
  -> json_extraction._extract_json_list() (JSON extraction)
  -> json_extraction._extract_partial_json_object_list() (truncated recovery)
  -> prompts.build_ai_ocr_direct_prompt() (prompt rendering)
  -> prompts.build_ai_ocr_layout_block_prompt()
  -> prompts.build_ai_ocr_image_region_prompt()
```

---

## 12. Externalization Plan

### Priority Classification

| Priority | Definition | Count |
|----------|-----------|-------|
| **P0-env** | Causes real ops problems; must be env-configurable | ~12 |
| **P1-env** | Useful for tuning per deployment; should be env-configurable | ~35 |
| **P1-algorithmic** | Tuning knob but rare to change; keep as named constant | ~50 |
| **P2-algorithmic** | Algorithm-internal tuning; leave as named constant | ~80 |
| **P2-internal** | Purely internal implementation detail | ~15 |
| **P3-structural** | Data structures, provider IDs, regex patterns | ~20 |

### P0: Should Go to config.py Settings (env-var-backed)

| Proposed Setting Name | Current Constant | Default | Rationale |
|----------------------|------------------|---------|-----------|
| `ocr_ai_request_timeout_s` | env var default | 25.0 | Core request timeout |
| `ocr_ai_request_timeout_s_qwen` | env var default | 25.0 | Qwen-specific timeout |
| `ocr_ai_request_timeout_s_deepseek` | env var default | 25.0 | DeepSeek-specific |
| `ocr_ai_request_timeout_s_paddle_vl` | env var default | 25.0 | Paddle-VL-specific |
| `ocr_paddle_vl_docparser_init_timeout_s` | env var default | 30.0 | Parser init timeout |
| `ocr_paddle_vl_docparser_predict_timeout_s` | env var default | 120.0 | Predict timeout |
| `ocr_paddle_vl_docparser_max_side_px` | env var default | 2200 | Max side px (unify duplicates) |
| `ocr_ai_layout_model_init_timeout_s` | env var default | 30.0 | Layout model init |
| `ocr_ai_layout_model_predict_timeout_s` | env var default | 45.0 | Layout model predict |
| `ocr_ai_layout_block_request_timeout_s` | env var default | 40.0 | Block OCR request |
| `ocr_ai_image_region_timeout_s` | env var default | 30.0 | Image region detection |
| `ocr_ai_layout_coverage_bypass_threshold` | env var default | 0.30 | Layout bypass |
| `ocr_ai_max_attempts` | env var default | 3 | Max OCR retry attempts |
| `ocr_ai_empty_response_break_after` | env var default | 2 | Empty response guard |
| `ocr_ai_refiner_timeout_s` | Hardcoded 60.0 | 60.0 | Currently inline! |
| `ocr_ai_refiner_max_tokens` | Hardcoded 4096 | 4096 | Via clamp_max_tokens |
| `ocr_ai_linebreak_max_tokens` | Hardcoded 3072 | 3072 | Via clamp_max_tokens |
| `ocr_ai_refine_max_items_per_call` | Default 80 | 80 | Currently method default |
| `ocr_ai_linebreak_max_items_per_call` | Default 36 | 36 | Currently method default |
| `ocr_ai_linebreak_max_lines_per_item` | Default 8 | 8 | Currently method default |

### P1: Should Remain as Named Module Constants (but documented)

All algorithmic tuning knobs in sections 3.7-3.14 above, plus the ~80+ constants in local_providers.py. These are rarely changed in production but are valuable during algorithm development.

### P2: Leave Inline or Keep as Named Constants

- Debug text limits (section 3.3)
- Concurrency wait internals (section 3.5)
- Token estimation constants (CHARS_PER_TOKEN, image_tokens * 512)
- Bbox scoring internals (section 3.15)
- Layout model dimension minimums

### P3: Structural Constants (Leave As-Is)

- Provider IDs, aliases, model names
- Label token sets (image/non-image region labels)
- Regex patterns
- Acronym allowlists

---

## 13. Caveats / Not Found

1. **Some inline numbers are truly structural**: e.g., array indexing bounds, image dimension minimums, `(x1 - x0) <= 0.0` checks. These are not "constants" in need of externalization.
2. **env vars with the same semantic but different names**: e.g., `OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S` and `OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S_V15` — these layer model-version-specific overrides on top of the base.
3. **Vendor tuning defaults** (vendors.py) are configuration data, not constants — they already serve the purpose of centralized tuning.

## Related Specs

- `.trellis/spec/backend/index.md` — backend coding conventions
- `.trellis/spec/frontend/index.md` — frontend conventions (not directly applicable)

## Related Files

All OCR pipeline files under `api/app/convert/ocr/`:
- `ai_client.py` (5579 lines) — main AI OCR client, largest constant concentration
- `local_providers.py` — Baidu/Tesseract/PaddleOCR providers + post-processing
- `base.py` — shared types, helpers, env utilities
- `vendors.py` — vendor profiles and tuning configs
- `routing.py` — OCR route kind constants
- `result_parsing.py` — Paddle doc parser output parsing
- `deepseek_parser.py` — DeepSeek grounding tag parsing
- `prompts.py` — prompt templates
- `layout_models.py` — layout model registry
- `json_extraction.py` — JSON extraction utilities
- `utils.py` — bbox coercion helpers
- `runtime_probe.py` — runtime availability probes

Reference: `api/app/config.py` (186 lines) — current Settings with 20 OCR-related fields.
