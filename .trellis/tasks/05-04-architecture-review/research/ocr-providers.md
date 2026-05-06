# Research: OCR Provider Integrations

- **Query**: Research all OCR provider integrations in the pdf2ppt project
- **Scope**: internal
- **Date**: 2026-05-04

## Findings

### Architecture Overview

The OCR system is organized under `api/app/convert/ocr/` with a layered architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    OcrManager (orchestrator)                  │
│  - Provider selection with fallback chain                    │
│  - Hybrid mode: combines multiple providers                  │
│  - Strict mode: no fallback, fail fast                       │
├─────────────────────────────────────────────────────────────┤
│                    OcrRoutePlan (routing)                     │
│  - Route kinds: machine_ocr, remote_doc_parser,              │
│    remote_prompt_ocr, local_layout_block_ocr, hybrid_auto    │
├─────────────────────────────────────────────────────────────┤
│                    Provider Implementations                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │Tesseract │ │PaddleOCR │ │ BaiduOcr │ │ AiOcrClient│      │
│  │(local)   │ │(local)   │ │ (remote) │ │ (remote)   │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### Files Found

| File Path | Description |
|---|---|
| `api/app/convert/ocr/__init__.py` | Package facade, re-exports all public APIs |
| `api/app/convert/ocr/base.py` | Abstract OcrProvider base class, constants, helpers |
| `api/app/convert/ocr/local_providers.py` | TesseractOcrClient, PaddleOcrClient, BaiduOcrClient, OcrManager |
| `api/app/convert/ocr/ai_client.py` | AiOcrClient - AI OCR using OpenAI-compatible vision models |
| `api/app/convert/ocr/routing.py` | OcrRoutePlan, route kind definitions, build_ocr_route_plan() |
| `api/app/convert/ocr/vendors.py` | VendorConfig, vendor profiles (OpenAI, SiliconFlow, PPIO, Novita, DeepSeek) |
| `api/app/convert/ocr/layout_models.py` | Layout model registry (PP-DocLayout, DocLayout-YOLO) |
| `api/app/convert/ocr/runtime_probe.py` | Runtime availability probes for local OCR engines |
| `api/app/convert/ocr/prompts.py` | AI OCR prompt templates |
| `api/app/convert/ocr/deepseek_parser.py` | DeepSeek-specific OCR parsing |
| `api/app/convert/ocr/result_parsing.py` | OCR result normalization and parsing |
| `api/app/convert/ocr/json_extraction.py` | JSON extraction from AI OCR responses |
| `api/app/convert/ocr/utils.py` | Bbox coercion, PaddleOCR-VL model detection |
| `api/app/convert/mineru_adapter.py` | MinerU API integration (separate from OCR package) |
| `api/app/worker_helpers/ocr_runtime.py` | OCR runtime setup for job workers |
| `api/app/worker_helpers/ocr_stage.py` | OCR stage execution in job pipeline |
| `api/app/routers/model_status.py` | Model status and download endpoints |
| `api/app/services/paddle_prewarm.py` | PaddleOCR model prewarm for container startup |
| `api/app/job_options.py` | OCR provider normalization and validation |

### Provider Details

#### 1. PaddleOCR (Local) — `PaddleOcrClient`

**File**: `api/app/convert/ocr/local_providers.py:706-1061`

- **Package**: `paddleocr` (PaddleOCR 3.x / PaddleX pipeline)
- **Language**: Supports `ch`, `en`, `latin`, `arabic`, `cyrillic`, `devanagari`
- **Engine**: Lazy initialization via `_ensure_engine()`, tries multiple constructor configs
- **Image preprocessing**: Downscales large images (max 2200px) before inference, scales bboxes back
- **Output parsing**: Handles both PaddleOCR 3.x (PaddleX pipeline) and legacy output formats
- **Constructor kwargs**: `use_textline_orientation=True`, `use_doc_orientation_classify=False`, `enable_mkldnn=False`, `device=cpu`
- **Error handling**: Falls back through multiple constructor configs, raises RuntimeError on complete failure

**Key behavior**:
```python
# PaddleOCR 3.x returns list of dicts with rec_texts/rec_polys
# Legacy returns [[quad], (text, score)]
# Code tries both formats
```

#### 2. Tesseract (Local) — `TesseractOcrClient`

**File**: `api/app/convert/ocr/local_providers.py:381-703`

- **Package**: `pytesseract` (requires system `tesseract-ocr` binary)
- **Default language**: `chi_sim+eng` (bilingual Chinese+English)
- **Page segmentation**: Tries PSM 11 (sparse text) first, falls back to PSM 6, 3
- **Language fallback**: Auto-switches from `eng` to `chi_sim+eng` if low recall
- **Confidence threshold**: Configurable `min_confidence` (default 50.0), auto-lowers to 25.0 on empty results
- **Output**: Returns per-word boxes with Tesseract structural hints (block_num, par_num, line_num, word_num)

**Key behavior**:
```python
# Multi-pass strategy: try primary lang + PSM 11, then fallback lang, then other PSMs
# Auto-lowers confidence threshold if result looks empty
# Preserves Tesseract structural hints for line merging
```

#### 3. Baidu Document Parsing (Remote) — `BaiduOcrClient`

**File**: `api/app/convert/ocr/local_providers.py:188-378`

- **Package**: `baidu-aip` (AipOcr SDK)
- **Credentials**: `api_key` + `secret_key` (stored in site_settings DB)
- **Endpoints**: Tries `accurate` → `general` → `basicAccurate` → `basicGeneral`
- **Options**: `detect_direction=true`, `probability=true`, `language_type=CHN_ENG`
- **Output**: Returns `{text, bbox: [x0, y0, x1, y1], confidence: 0.95}` per word
- **Defensive pruning**: Filters out coarse/paragraph-level boxes by area ratio and width ratio

**Key behavior**:
```python
# Baidu returns {left, top, width, height} in pixels
# Converted to [x0, y0, x0+w, y0+h] format
# Filters boxes with area_ratio >= 0.16 or width_ratio >= 0.85
```

#### 4. AIOCR (Remote) — `AiOcrClient`

**File**: `api/app/convert/ocr/ai_client.py:638-2500+`

- **Package**: `openai` (OpenAI-compatible API)
- **Providers**: OpenAI, SiliconFlow, PPIO, Novita, DeepSeek (via VendorConfig)
- **Models**: PaddleOCR-VL, PaddleOCR-VL-1.5, Qwen2.5-VL-72B, DeepSeek-OCR, etc.
- **Route kinds**:
  - `remote_prompt_ocr`: Direct vision model OCR via chat completion
  - `remote_doc_parser`: PaddleOCR-VL dedicated doc_parser protocol
  - `local_layout_block_ocr`: Local layout detection + remote AI per-block OCR
- **Concurrency**: Page-level and block-level concurrency control
- **Rate limiting**: RPM and TPM limits with shared rate limiter per API key
- **Retry**: Configurable max retries with exponential backoff for retryable errors

**Key behavior**:
```python
# PaddleOCR-VL uses dedicated doc_parser protocol (PaddleOCRVL class)
# Other models use OpenAI chat completion API
# Vendor-specific tuning: SiliconFlow has singleflight dedup, custom timeouts
# DeepSeek uses grounding tags and image-first content ordering
```

#### 5. MinerU (Remote) — `mineru_adapter.py`

**File**: `api/app/convert/mineru_adapter.py`

- **Separate from OCR package**: MinerU is a `parse_provider`, not an OCR provider
- **API**: REST API at `https://mineru.net` (configurable base_url)
- **Model versions**: `pipeline`, `vlm`, `MinerU-HTML`
- **Features**: Formula recognition, table recognition, language hints
- **Credentials**: `mineru_api_token` (stored in site_settings DB)
- **Output**: Returns IR (Intermediate Representation) with page elements

**Key behavior**:
```python
# MinerU is a parse_provider (local, mineru, baidu_doc)
# It bypasses the OCR stage entirely - does its own parsing
# Returns structured IR with text blocks, images, tables
```

### Provider Selection and Fallback Mechanisms

**File**: `api/app/convert/ocr/routing.py` + `api/app/convert/ocr/local_providers.py`

#### Provider IDs (normalized)

| ID | Description |
|---|---|
| `auto` | Hybrid mode: tries Baidu → Tesseract → PaddleOCR → AI OCR |
| `aiocr` | AI OCR only (requires api_key) |
| `baidu` | Baidu OCR only |
| `machine` | Local machine OCR: PaddleOCR first, Tesseract fallback |
| `tesseract` / `local` | Tesseract only |
| `paddleocr` / `paddle_local` | Local PaddleOCR only |
| `paddle` | Remote PaddleOCR-VL via doc_parser protocol |

#### Route Kinds

| Route Kind | Description |
|---|---|
| `machine_ocr` | Local OCR (Tesseract/PaddleOCR/Baidu) |
| `remote_doc_parser` | PaddleOCR-VL dedicated doc_parser protocol |
| `remote_prompt_ocr` | AI vision model via chat completion |
| `local_layout_block_ocr` | Local layout detection + remote AI per-block |
| `hybrid_auto` | Auto-selects based on available providers |

#### Fallback Chain (OcrManager)

```python
# In auto mode (non-strict):
1. Baidu OCR (if credentials available)
2. Tesseract (if installed)
3. PaddleOCR (if installed)
4. AI OCR (if api_key available)

# In strict mode (strict_no_fallback=True):
- No fallback allowed
- Fails fast on any provider error
- Returns AppException with ErrorCode.OCR_FAILED
```

#### AI Provider Reuse

```python
# When OCR doesn't have dedicated AI credentials:
# Falls back to main AI provider settings (OpenAI/Claude)
# Except for: aiocr, paddle, baidu, machine providers
def should_allow_main_ai_reuse(requested_ocr_provider: str) -> bool:
    return requested_ocr_provider not in {"aiocr", "paddle", "baidu", "machine"}
```

### Model Downloading and Management

**File**: `api/app/routers/model_status.py` + `api/app/convert/ocr/layout_models.py`

#### Layout Models Registry

| Model ID | Provider | Size | Speed | Accuracy |
|---|---|---|---|---|
| `pp_doclayout_s` | PaddleX | 1.2MB | 8ms GPU / 14ms CPU | 70.9% mAP |
| `pp_doclayout_m` | PaddleX | 23MB | 13ms GPU / 43ms CPU | 75.2% mAP |
| `pp_doclayout_l` | PaddleX | 124MB | 34ms GPU / 503ms CPU | 90.4% mAP |
| `pp_doclayout_v3` | PaddleX | 126MB | 24ms GPU | 25 classes + reading order |
| `doclayout_yolo` | YOLO | 10MB | Very fast | 93.4% AP50 (DocLayNet) |

#### Download Mechanism

```python
# PaddleX models: auto-download via paddlex.create_model()
# DocLayout-YOLO: download from HuggingFace via hf_hub_download()
# PaddleOCR: auto-download on first use via PaddleOcrClient._ensure_engine()
```

#### Download Endpoints

- `POST /api/v1/models/download` — Trigger download (admin only)
- `GET /api/v1/models/download/status` — Poll download progress
- `POST /api/v1/models/download/cancel` — Cancel active download

### Error Handling

#### Per-Provider Error Handling

| Provider | Error Type | Handling |
|---|---|---|
| Tesseract | ImportError | "pytesseract not installed" |
| Tesseract | RuntimeError | "Tesseract executable not available" |
| Tesseract | Empty result | Auto-lower confidence threshold, retry |
| PaddleOCR | ImportError | "paddleocr not installed" |
| PaddleOCR | RuntimeError | Try multiple constructor configs |
| Baidu | ValueError | "Credentials not found" |
| Baidu | RuntimeError | "Baidu OCR failed: {error_msg}" |
| AIOCR | ValueError | "AI OCR requires api_key" |
| AIOCR | TimeoutError | Retry with exponential backoff |
| AIOCR | Empty result | Mark as nonfatal, continue |
| MinerU | AppException | "mineru_api_token is required" |

#### Circuit Breaker Pattern

```python
# In ocr_stage.py:
# - Tracks consecutive timeouts
# - After N consecutive timeouts (ocr_max_consecutive_timeouts), stops OCR
# - Emits "ocr_timeout_circuit_open" warning

# In OcrManager:
# - Disables AI OCR provider after repeated failures
# - Sets ai_provider_disabled=True, ai_provider_disabled_reason
# - Skips AI OCR for remaining pages
```

#### Strict vs Non-Strict Mode

```python
# Strict mode (ocr_strict_mode=True):
# - Fails fast on any OCR error
# - Returns AppException with ErrorCode.OCR_FAILED
# - No fallback providers

# Non-strict mode (ocr_strict_mode=False):
# - Best-effort: keeps background image-only page
# - Continues conversion with warnings
# - Falls back to next provider in chain
```

### Performance Characteristics

#### Concurrency Controls

| Control | Description | Range |
|---|---|---|
| `ocr_ai_page_concurrency` | Parallel page processing | 1-8 |
| `ocr_ai_block_concurrency` | Parallel block processing (layout_block mode) | 1-8 |
| `ocr_ai_requests_per_minute` | API request rate limit | 1-2000 |
| `ocr_ai_tokens_per_minute` | API token rate limit | 1-2,000,000 |
| `ocr_ai_max_retries` | Max retry attempts per request | 0-8 |

#### Timeouts

| Timeout | Description | Default |
|---|---|---|
| `ocr_page_timeout_s` | Per-page OCR timeout | 300s |
| `ocr_total_timeout_s` | Total OCR stage timeout | 3600s |
| `ocr_image_region_timeout_s` | Image region detection timeout | 12s |
| `ocr_max_consecutive_timeouts` | Circuit breaker threshold | 2 |

#### Vendor-Specific Tuning

```python
# SiliconFlow:
#   vl_rec_max_concurrency=4
#   use_queues=False
#   predict_timeout_override=180s
#   singleflight=True (dedup concurrent requests)
#   layout_block_max_concurrency=2

# PPIO:
#   model_casing="lowercase"

# Novita:
#   supports_remote_paddle_doc=True
```

### Frontend Integration

**File**: `web/src/lib/settings.ts` + `web/src/lib/run-config.ts`

#### OCR Provider Settings

```typescript
// OCR providers in frontend:
type OcrProvider = "auto" | "aiocr" | "baidu" | "machine" | "tesseract" | "local" | "paddleocr"

// Parse providers (separate from OCR):
type ParseProvider = "local" | "mineru" | "baidu_doc"

// Parse engine modes:
type ParseEngineMode = "local_ocr" | "remote_ocr" | "baidu_doc" | "mineru_cloud"
```

#### Settings Keys

```typescript
// OCR settings stored in site_settings DB:
ocr_ai_api_key, ocr_ai_provider, ocr_ai_base_url, ocr_ai_model,
ocr_ai_chain_mode, ocr_ai_layout_model, ocr_ai_prompt_preset,
ocr_baidu_api_key, ocr_baidu_secret_key, ocr_baidu_app_id,
mineru_api_token, mineru_base_url, mineru_model_version
```

### Code Patterns

#### Provider Initialization Pattern

```python
# All providers follow this pattern:
class XxxOcrClient(OcrProvider):
    def __init__(self, ...):
        try:
            import required_package
        except ImportError:
            raise ImportError("package not installed")
        
        # Validate credentials/config
        if not credentials:
            raise ValueError("credentials not found")
        
        # Initialize client
        self.client = ...
    
    def ocr_image(self, image_path: str) -> List[Dict]:
        # Perform OCR
        # Return [{text, bbox: [x0,y0,x1,y1], confidence: float}]
```

#### Fallback Pattern

```python
# OcrManager.ocr_image() iterates providers:
for provider in self.providers:
    try:
        out = provider.ocr_image(image_path)
        self.last_provider_name = provider.__class__.__name__
        return out
    except Exception as e:
        logger.warning(f"OCR provider failed: {e}")
        continue
raise RuntimeError("All OCR providers failed")
```

### Related Specs

- `.trellis/spec/backend/index.md` — Backend coding guidelines
- `.trellis/spec/frontend/index.md` — Frontend coding guidelines

## Caveats / Not Found

1. **MinerU is NOT an OCR provider** — It's a `parse_provider` that bypasses the OCR stage entirely. It does its own document parsing and returns structured IR.

2. **PaddleOCR-VL has two modes**:
   - `remote_doc_parser`: Uses dedicated PaddleOCRVL class (requires `paddleocr` package)
   - `remote_prompt_ocr`: Uses standard OpenAI chat completion API

3. **Vendor-specific behavior is config-driven** — The old per-vendor adapter subclasses (SiliconFlow, PPIO, etc.) were removed. All behavior is now in `VendorConfig` dataclass.

4. **AI OCR provider reuse** — When OCR doesn't have dedicated credentials, it can reuse the main AI provider settings (OpenAI/Claude), except for explicit `aiocr`, `paddle`, `baidu`, `machine` providers.

5. **Strict mode** — The `strict_ocr_mode` flag controls whether OCR fails fast or degrades gracefully. Default is `True` (strict).

6. **Layout models are separate from OCR** — Layout models (PP-DocLayout, DocLayout-YOLO) are used for document layout analysis, not OCR. They can be used with the `local_layout_block_ocr` route kind.
