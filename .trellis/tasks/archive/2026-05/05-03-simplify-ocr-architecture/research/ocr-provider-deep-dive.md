# Research: OCR Provider Architecture Deep Dive

- **Query**: Deep-dive into the OCR provider architecture — execution flows, code path overlap, redundancy analysis, and optimal simplification path
- **Scope**: internal
- **Date**: 2026-05-03

## Findings

### 1. Provider Overview

**6 OCR Providers** defined in `OcrManager.__init__()` (local_providers.py:1153-1162):

| Provider ID | Legacy Aliases | Primary Class |
|---|---|---|
| `auto` | — | `OcrManager` (hybrid fallback) |
| `aiocr` | `remote`, `ai` | `AiOcrClient` |
| `paddle` | — | `AiOcrClient` (same class!) |
| `paddle_local` | `paddle-local`, `local_paddle` | `PaddleOcrClient` |
| `baidu` | — | `BaiduOcrClient` |
| `tesseract` / `local` | — | `TesseractOcrClient` |

**5 AI Vendors** (vendors.py:63-101): `openai`, `siliconflow`, `ppio`, `novita`, `deepseek`

**3 Chain Modes**: `direct` (prompt OCR), `doc_parser` (PaddleOCR-VL pipeline), `layout_block` (local layout detection + per-block AI OCR)

**5 Route Kinds** (routing.py:5-9): `machine_ocr`, `remote_doc_parser`, `remote_prompt_ocr`, `local_layout_block_ocr`, `hybrid_auto`

### 2. Execution Flow Diagrams

#### 2.1 `aiocr` + `direct` (prompt OCR)

```
OcrManager → AiOcrClient (route=remote_prompt_ocr)
  → ocr_image()
    → _chat_completion() with full-page image + JSON prompt
    → _normalize_items_to_pixels() (auto-detect bbox coordinate system)
    → returns [{text, bbox, confidence}]
```

#### 2.2 `aiocr` + `doc_parser` (PaddleOCR-VL pipeline)

```
OcrManager → AiOcrClient (route=remote_doc_parser)
  → ocr_image()
    → _ocr_image_with_paddle_doc_parser()
      → _get_paddle_doc_parser() → PaddleOCRVL(api_key, server_url, model)
      → parser.predict(image) → PaddleX pipeline
      → _extract_paddle_doc_parser_output() → {text_elements, image_regions, layout_blocks}
      → _scale_paddle_doc_parser_output()
    → returns [{text, bbox, confidence}]
```

#### 2.3 `aiocr` + `layout_block`

```
OcrManager → AiOcrClient (route=local_layout_block_ocr)
  → ocr_image()
    → _ocr_image_with_local_layout_blocks()
      → _run_local_layout_analysis() → paddlex.create_model("PP-DocLayoutV3").predict()
      → for each text block:
          → _crop_layout_block() + _tighten_layout_block_bbox_by_visual_bounds()
          → _ocr_local_layout_block_crop() → _chat_completion() per block
      → ThreadPoolExecutor for concurrency
    → returns [{text, bbox, confidence, ocr_layout_label}]
```

#### 2.4 `paddle`

```
OcrManager → AiOcrClient (route=remote_doc_parser, same code path as aiocr+doc_parser!)
  → identical to #2.2 above
```

#### 2.5 `paddle_local`

```
OcrManager → PaddleOcrClient
  → ocr_image()
    → engine = PaddleOCR(lang)
    → engine.predict(image) / engine.ocr(image)
    → parse PaddleOCR 3.x output (rec_texts, rec_polys) or legacy format
    → returns [{text, bbox, confidence}]
```

#### 2.6 `baidu`

```
OcrManager → BaiduOcrClient
  → ocr_image()
    → AipOcr.accurate(image_data, options) / .general()
    → parse words_result with location
    → returns [{text, bbox, confidence}]
```

#### 2.7 `tesseract` / `local`

```
OcrManager → TesseractOcrClient
  → ocr_image()
    → pytesseract.image_to_data(image, lang, psm)
    → _extract_elements_from_data()
    → auto-fallback: try multiple PSM modes + languages + lower confidence thresholds
    → returns [{text, bbox, confidence}]
```

#### 2.8 `auto` (non-strict)

```
OcrManager.__init__():
  → tries BaiduOcrClient (primary)
  → tries TesseractOcrClient (fallback)
  → tries AiOcrClient (supplementary)
  → tries PaddleOcrClient (last resort)

OcrManager.ocr_image_lines():
  → runs ALL available providers in parallel
  → merges results: Baidu → Tesseract → Paddle → AI
  → prunes AI supplement if machine OCR exists
  → _merge_line_items_prefer_primary()
```

#### 2.9 `auto` (strict)

```
OcrManager.__init__():
  → requires ai_api_key
  → creates AiOcrClient only (no fallbacks)
  → behaves like aiocr
```

### 3. Code Path Overlap Matrix

| | aiocr+direct | aiocr+doc_parser | aiocr+layout_block | paddle | paddle_local | baidu | tesseract |
|---|---|---|---|---|---|---|---|
| **aiocr+direct** | — | 0% | 15% | 0% | 0% | 0% | 0% |
| **aiocr+doc_parser** | 0% | — | 5% | **100%** | 0% | 0% | 0% |
| **aiocr+layout_block** | 15% | 5% | — | 5% | 0% | 0% | 0% |
| **paddle** | 0% | **100%** | 5% | — | 0% | 0% | 0% |
| **paddle_local** | 0% | 0% | 0% | 0% | — | 0% | 0% |
| **baidu** | 0% | 0% | 0% | 0% | 0% | — | 0% |
| **tesseract** | 0% | 0% | 0% | 0% | 0% | 0% | — |

**Critical finding**: `paddle` provider is **100% identical** to `aiocr` + `doc_parser`:

- `OcrManager.__init__()` for `paddle` (local_providers.py:1299-1338) calls the **exact same** `create_remote_ocr_client()` as `aiocr`
- Both create an `AiOcrClient` instance
- Both resolve to `route_kind = ROUTE_KIND_REMOTE_DOC_PARSER`
- Both use `_ocr_image_with_paddle_doc_parser()` for actual OCR

The only difference: `paddle` forces `_is_paddleocr_vl_model()` validation and defaults to PaddleOCR-VL model name.

### 4. Vendor Adapter Analysis

**5 adapter classes** (vendors.py:280-301):

| Adapter | Custom Behavior |
|---|---|
| `OpenAiAiOcrAdapter` | `supports_remote_paddle_doc_parser()` → True for local/private URLs |
| `SiliconFlowAiOcrAdapter` | Inherits default (pass) |
| `PpioAiOcrAdapter` | Inherits default (pass) |
| `NovitaAiOcrAdapter` | Inherits default (pass) |
| `DeepSeekAiOcrAdapter` | Inherits default (pass) |

**Only `OpenAiAiOcrAdapter` has custom logic.** The other 4 adapters are empty pass-through classes.

**Vendor-specific tuning** (vendors.py:48-60): Only `siliconflow` has a `VendorTuningConfig` entry. All others use defaults.

**Model name normalization** (vendors.py:104-134): Per-vendor casing:
- `novita`, `ppio` → lowercase (`paddlepaddle/paddleocr-vl-1.5`)
- Others → mixed case (`PaddlePaddle/PaddleOCR-VL-1.5`)

**Server URL normalization** (base.py:179-220): Per-vendor path forcing:
- `siliconflow` → `/v1`
- `novita`, `ppio` → `/openai`
- `deepseek` → `/v1`

### 5. DeepSeek Special Handling

DeepSeek requires special treatment in **three areas**:

#### 5.1 Grounding Tags (deepseek_parser.py)
- DeepSeek-OCR outputs `<|ref|>text<|/ref|><|det|>[[x0,y0,x1,y1]]<|/det|>` instead of JSON
- `_extract_deepseek_tagged_items()` parses these tags into standard `{text, bbox, confidence}` format
- This is a **result parser**, not a client code path — it's model-specific, not vendor-specific

#### 5.2 Image-First Ordering (vendors.py:137-144)
- `_should_send_image_first_for_ai_ocr()` returns True for DeepSeek-OCR models
- Reorders user content from `[text, image]` to `[image, text]`
- Affects: `build_user_content()` in all AI OCR paths

#### 5.3 Message Format (ai_client.py:2789-2790, 3233-3239, 3910-3916)
- DeepSeek-OCR models use single-message format: `[{role: "user", content}]`
- Other models use two-message format: `[{role: "system", ...}, {role: "user", ...}]`
- Affects: layout_block OCR, image region detection, direct page OCR

**Key insight**: DeepSeek's differences are all about **prompt/response format**, not **API protocol**. The OpenAI client library is used identically. The special handling is in:
1. Response parsing (grounding tags → this is model-specific, independent of vendor)
2. Content ordering (image-first → can be a config flag)
3. Message structure (single vs two messages → can be a config flag)

### 6. Auto Mode Analysis

**Strict auto** (local_providers.py:1341-1381): Behaves exactly like `aiocr` — creates only `AiOcrClient`, no fallbacks.

**Non-strict auto** (local_providers.py:1382-1446): 
1. Tries Baidu OCR as primary
2. Adds Tesseract as fallback
3. Adds PaddleOCR local as last resort
4. Adds AI OCR as supplementary
5. In `ocr_image_lines()`: runs all available providers, merges results

**Can auto be simplified?**
- Strict auto → already identical to `aiocr`, can be removed as a separate provider
- Non-strict auto → this is the only provider that does **multi-provider merging**. It's a distinct feature, not just a "pick the best" selector.

### 7. Route Kind Analysis

Route kinds are **derived from** (provider, chain_mode) combinations:

| Provider | Chain Mode | Route Kind |
|---|---|---|
| `baidu` | — | `machine_ocr` |
| `tesseract`/`local` | — | `machine_ocr` |
| `paddle_local` | — | `machine_ocr` |
| `paddle` | — | `remote_doc_parser` (forced) |
| `aiocr` | `direct` | `remote_prompt_ocr` |
| `aiocr` | `doc_parser` | `remote_doc_parser` |
| `aiocr` | `layout_block` | `local_layout_block_ocr` |
| `auto` | — | `hybrid_auto` |

**Route kinds are NOT independent** — they're fully derivable from (provider, chain_mode). The `normalize_ocr_route_kind()` function (routing.py:39-67) maps many aliases but ultimately produces one of 6 canonical values.

**OcrRoutePlan** (routing.py:22-33) adds derived flags like `allow_text_refiner`, `allow_linebreak_refiner`, `auto_enable_linebreak`, etc. These are also derivable from provider + chain_mode.

### 8. Redundancy Analysis

#### 8.1 Eliminable Providers

| Provider | Can Remove? | Replacement |
|---|---|---|
| `paddle` | **YES** | `aiocr` + `doc_parser` (100% code overlap) |
| `auto` (strict) | **YES** | `aiocr` (identical behavior) |
| `auto` (non-strict) | **NO** | Unique multi-provider merging feature |

#### 8.2 Eliminable Vendor Adapters

| Adapter | Can Remove? | Replacement |
|---|---|---|
| `SiliconFlowAiOcrAdapter` | **YES** | `AiOcrVendorAdapter` base class (empty) |
| `PpioAiOcrAdapter` | **YES** | `AiOcrVendorAdapter` base class (empty) |
| `NovitaAiOcrAdapter` | **YES** | `AiOcrVendorAdapter` base class (empty) |
| `DeepSeekAiOcrAdapter` | **YES** | `AiOcrVendorAdapter` base class (empty) |
| `OpenAiAiOcrAdapter` | **PARTIALLY** | Keep for `supports_remote_paddle_doc_parser()` local-URL check |

**After removal**: Just 1 adapter class with configurable `supports_remote_paddle_doc_parser` flag.

#### 8.3 Eliminable Vendor Profiles

| Profile | Can Remove? | Why Keep |
|---|---|---|
| `openai` | KEEP | Default fallback |
| `siliconflow` | KEEP | `supports_remote_paddle_doc_parser=True`, tuning config |
| `ppio` | KEEP | Different default_base_url, different model casing |
| `novita` | KEEP | Different default_base_url, different model casing |
| `deepseek` | KEEP | Different default_base_url |

**After simplification**: Keep 5 profiles but move differences to config:
- `default_base_url` → user sets via `base_url`
- `default_model` → user sets via `model`
- `max_tokens_ocr/refiner` → can be unified to a single default
- `supports_remote_paddle_doc_parser` → derived from base_url (local/private = True)

#### 8.4 Vendor-Specific Tuning (VendorTuningConfig)

Only `siliconflow` has custom tuning (vendors.py:49-58). All others use defaults.

**After simplification**: `VendorTuningConfig` can be a single default config with per-provider overrides only when genuinely needed (currently only SiliconFlow for PaddleOCR-VL-1.5 stability).

### 9. Code Size Breakdown

| File | Lines | Role |
|---|---|---|
| `ai_client.py` | 5243 | AiOcrClient + AiOcrTextRefiner + all OCR logic |
| `local_providers.py` | ~2600 | OcrManager + BaiduOcrClient + TesseractOcrClient + PaddleOcrClient + merge utils |
| `vendors.py` | 317 | Vendor profiles + adapters + model name normalization |
| `routing.py` | 193 | Route kind constants + OcrRoutePlan builder |
| `base.py` | 293 | Base class + constants + PaddleOCR-VL server URL normalization |
| `deepseek_parser.py` | 489 | DeepSeek grounding tag parser |
| `prompts.py` | — | OCR prompt templates |
| `result_parsing.py` | — | PaddleOCR-VL output parsing |
| `json_extraction.py` | — | JSON extraction from AI responses |
| `utils.py` | — | Bbox coercion, model detection |

### 10. Optimal Architecture Proposal

#### Minimal Provider Set (3 providers + 1 mode)

| Provider | Purpose | Notes |
|---|---|---|
| `aiocr` | All AI-based OCR (OpenAI-compatible) | Handles direct, doc_parser, layout_block via chain_mode |
| `machine` | Local OCR (Tesseract + PaddleOCR local) | Merged into one provider with auto-detection |
| `baidu` | Baidu API OCR | Independent API, keep separate |
| `auto` | Multi-provider hybrid | Non-strict only, merges machine + AI results |

#### Minimal Vendor Profile Set (1 profile + config)

```python
@dataclass
class AiOcrProfile:
    base_url: str | None = None
    api_key: str = ""
    model: str = "gpt-4o-mini"
    max_tokens_ocr: int = 8192
    supports_remote_paddle_doc: bool = False  # derived from base_url
    model_casing: str = "auto"  # "lowercase" for novita/ppio, "mixed" for others
```

#### DeepSeek Handling (3 config flags, no adapter)

```python
@dataclass
class DeepSeekConfig:
    image_first: bool = False  # True for deepseek-ocr
    single_message: bool = False  # True for deepseek-ocr
    response_parser: str = "json"  # "json" or "grounding_tags"
```

#### Route Kind Derivation

Route kinds become a **computed property** of (provider, chain_mode):

```python
def derive_route_kind(provider: str, chain_mode: str) -> str:
    if provider == "baidu": return "machine_ocr"
    if provider in ("tesseract", "machine"): return "machine_ocr"
    if provider == "paddle_local": return "machine_ocr"
    if provider == "aiocr":
        return {"direct": "remote_prompt_ocr", "doc_parser": "remote_doc_parser", "layout_block": "local_layout_block_ocr"}[chain_mode]
    if provider == "auto": return "hybrid_auto"
```

### 11. Key Files Summary

| File Path | Lines | Description |
|---|---|---|
| `api/app/convert/ocr/ai_client.py` | 5243 | Core AI OCR client (AiOcrClient, AiOcrTextRefiner) |
| `api/app/convert/ocr/local_providers.py` | ~2600 | OcrManager orchestrator + local OCR clients |
| `api/app/convert/ocr/vendors.py` | 317 | Vendor profiles, adapters, model name normalization |
| `api/app/convert/ocr/routing.py` | 193 | Route kind constants and OcrRoutePlan builder |
| `api/app/convert/ocr/base.py` | 293 | OcrProvider ABC, constants, server URL normalization |
| `api/app/convert/ocr/deepseek_parser.py` | 489 | DeepSeek grounding tag parser |
| `api/app/worker_helpers/ocr_runtime.py` | 646 | Worker-side OCR setup (OcrRuntimeSetup) |
| `api/app/job_options.py` | 525 | Job option normalization |

### 12. Code Patterns

#### Pattern: Provider Creates AiOcrClient Regardless of Name
- `paddle` provider → `create_remote_ocr_client()` → `AiOcrClient` (local_providers.py:1310)
- `aiocr` provider → `create_remote_ocr_client()` → `AiOcrClient` (local_providers.py:1247)
- Both use the same factory function, same class, same constructor

#### Pattern: Vendor Differences Are Configuration, Not Code
- `SiliconFlowAiOcrAdapter` (vendors.py:287-288) → empty class, inherits all behavior
- `PpioAiOcrAdapter` (vendors.py:291-292) → empty class
- `NovitaAiOcrAdapter` (vendors.py:295-296) → empty class
- `DeepSeekAiOcrAdapter` (vendors.py:299-300) → empty class

#### Pattern: DeepSeek Special Handling Is Model-Specific, Not Vendor-Specific
- `_is_deepseek_ocr_model()` checks model name, not vendor
- Grounding tag parsing works regardless of which vendor hosts the model
- Image-first ordering checks model name, not vendor

## Caveats / Not Found

- **`paddle` provider removal impact**: Frontend settings page likely exposes `paddle` as a separate option. Need to check frontend code for UI references.
- **`auto` mode in strict**: If removed, existing users with `ocr_provider=auto` + strict mode will need migration guidance.
- **SiliconFlow tuning**: The `VendorTuningConfig` for SiliconFlow includes specific PaddleOCR-VL-1.5 timeouts. These are genuinely needed for stability and cannot be removed without testing.
- **Model casing**: Novita/PPIO require lowercase model names. This is a real vendor difference that needs config-based handling.
- **Server URL paths**: Different vendors need different URL paths (`/v1` vs `/openai`). This is derived from base_url host, not from vendor ID.
