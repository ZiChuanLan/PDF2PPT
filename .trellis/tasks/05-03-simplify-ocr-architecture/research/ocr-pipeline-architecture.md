# Research: OCR/AI Pipeline Architecture

- **Query**: How does the OCR/AI pipeline work in pdf2ppt?
- **Scope**: internal
- **Date**: 2026-05-03

## Findings

### Architecture Overview

The OCR pipeline has two main paths:

```
PDF Upload
    │
    ├─ parse_provider=local ──→ parse_pdf_to_ir() ──→ IR (pages)
    │                                                      │
    │                                               scanned_pages_exist?
    │                                                      │
    │                                              ┌───────┴───────┐
    │                                              │               │
    │                                         No scanned      Has scanned
    │                                         pages → skip    pages → OCR stage
    │                                                            │
    │                                              ┌─────────────┼─────────────┐
    │                                              │             │             │
    │                                         ocr_provider   ocr_provider   ocr_provider
    │                                           =aiocr        =baidu        =tesseract
    │                                              │             │             │
    │                                              ▼             ▼             ▼
    │                                         AiOcrClient   BaiduOcrClient  TesseractOcrClient
    │                                              │
    │                                    ┌─────────┼─────────┐
    │                                    │         │         │
    │                                route_kind:  route_kind: route_kind:
    │                               remote_prompt remote_doc  local_layout
    │                                    │         │         │
    │                                    ▼         ▼         ▼
    │                              Vision API  PaddleOCR  Local layout
    │                              (any LLM)   VL client  model + AI OCR
    │
    ├─ parse_provider=mineru ──→ parse_pdf_to_ir_with_mineru() ──→ IR
    │
    └─ parse_provider=baidu_doc ──→ parse_pdf_to_ir_with_baidu_doc() ──→ IR
```

### OCR Providers (6 total)

| Provider | ID | Type | Config Source |
|----------|-----|------|---------------|
| Auto (hybrid) | `auto` | Mixed | Multiple fallback chain |
| AI OCR | `aiocr` | Remote AI | ocr_ai_api_key, ocr_ai_provider, ocr_ai_base_url, ocr_ai_model |
| Baidu OCR | `baidu` | Remote API | ocr_baidu_api_key, ocr_baidu_secret_key |
| Tesseract | `tesseract` | Local | ocr_tesseract_language, ocr_tesseract_min_confidence |
| PaddleOCR VL | `paddle` | Remote AI | Same as aiocr (requires PaddleOCR-VL model) |
| Local PaddleOCR | `paddle_local` | Local | Language only |

### AI OCR Providers (5 vendors + auto)

| Vendor | ID | Default Base URL | Default Model | Special Features |
|--------|-----|------------------|---------------|------------------|
| OpenAI | `openai` | None (user-provided) | gpt-4o-mini | Generic OpenAI-compatible |
| SiliconFlow | `siliconflow` | https://api.siliconflow.cn/v1 | Qwen/Qwen2.5-VL-72B-Instruct | supports_remote_paddle_doc_parser=True |
| PPIO | `ppio` | https://api.ppio.com/openai | qwen/qwen2.5-vl-72b-instruct | Default URL path /openai |
| Novita | `novita` | https://api.novita.ai/openai | qwen/qwen2.5-vl-72b-instruct | supports_remote_paddle_doc_parser=True |
| DeepSeek | `deepseek` | https://api.deepseek.com/v1 | deepseek-ai/DeepSeek-OCR | Special grounding tags |

### OCR Chain Modes (3 modes)

| Mode | ID | Description |
|------|-----|-------------|
| Local Layout Block | `layout_block` | Local layout model + AI OCR per block |
| Direct (Prompt) | `direct` | Vision model returns JSON with text+bbox |
| Doc Parser | `doc_parser` | PaddleOCR-VL dedicated protocol |

### Route Kinds (5 kinds)

| Kind | ID | Description |
|------|-----|-------------|
| Machine OCR | `machine_ocr` | Local Tesseract/PaddleOCR |
| Remote Doc Parser | `remote_doc_parser` | PaddleOCR-VL dedicated channel |
| Remote Prompt OCR | `remote_prompt_ocr` | Vision model prompt-based |
| Local Layout Block | `local_layout_block_ocr` | Local layout model + AI per block |
| Hybrid Auto | `hybrid_auto` | Multi-provider combination |

### Vendor-Specific Hard-Coding Locations

#### SiliconFlow Special Cases

1. **`vendors.py:36`** — `supports_remote_paddle_doc_parser=True` in vendor profile
2. **`vendors.py:124`** — URL inference: host contains "siliconflow" → provider="siliconflow"
3. **`vendors.py:1412-1418`** — `vl_rec_max_concurrency=4` override for SiliconFlow PaddleOCR-VL-1.5
4. **`vendors.py:1428-1433`** — `use_queues=False` for SiliconFlow PaddleOCR-VL-1.5
5. **`vendors.py:1444-1455`** — Separate timeout env var for SiliconFlow V1.5: `OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S_V15_SILICONFLOW`
6. **`vendors.py:1470-1480`** — Separate retry timeout for SiliconFlow V1.5
7. **`vendors.py:1489-1492`** — `_is_siliconflow_paddle_doc_v15()` helper
8. **`vendors.py:1496-1511`** — Separate retry-on-timeout env var for SiliconFlow V1.5
9. **`vendors.py:1514-1528`** — Separate singleflight env var for SiliconFlow V1.5
10. **`vendors.py:1530-1534`** — Different singleflight wait time for SiliconFlow V1.5 (10s vs 3s)
11. **`vendors.py:2581-2587`** — Qwen3-VL on SiliconFlow: `layout_block_max_concurrency=2`
12. **`base.py:200-201`** — `_normalize_paddle_doc_server_url`: host contains "siliconflow" → force path `/v1`
13. **`base.py:236-243`** — `_resolve_paddle_doc_model_and_pipeline`: provider="siliconflow" forces lowercase model names
14. **`config.py:48-50`** — Default env vars: `SILICONFLOW_API_KEY`, `SILICONFLOW_BASE_URL`, `SILICONFLOW_MODEL`
15. **`worker.py:544-580`** — Legacy v2 mode: falls back to SiliconFlow credentials if no explicit OCR config

#### PPIO Special Cases

1. **`vendors.py:84-86`** — Model name normalization: `paddlepaddle/paddleocr-vl-1.5` (lowercase)
2. **`vendors.py:89-91`** — Model name normalization: `paddlepaddle/paddleocr-vl` (lowercase)
3. **`vendors.py:126-127`** — URL inference: host contains "ppio.com" or "ppinfra.com" → provider="ppio"
4. **`base.py:205-209`** — `_normalize_paddle_doc_server_url`: provider="ppio" → force path `/openai`

#### Novita Special Cases

1. **`vendors.py:36`** — `supports_remote_paddle_doc_parser=True` in vendor profile
2. **`vendors.py:84-86`** — Model name normalization: `paddlepaddle/paddleocr-vl-1.5` (lowercase)
3. **`vendors.py:89-91`** — Model name normalization: `paddlepaddle/paddleocr-vl` (lowercase)
4. **`vendors.py:128-129`** — URL inference: host contains "novita.ai" → provider="novita"
5. **`base.py:202-203`** — `_normalize_paddle_doc_server_url`: provider="novita" → force path `/openai`
6. **`base.py:236-243`** — `_resolve_paddle_doc_model_and_pipeline`: provider="novita" forces lowercase model names and downgrade V1.5 to V1

#### DeepSeek Special Cases

1. **`vendors.py:77-81`** — Model name normalization: `Pro/deepseek-ai/deepseek-ocr` → `deepseek-ai/DeepSeek-OCR`
2. **`vendors.py:96-103`** — `_should_send_image_first_for_ai_ocr`: DeepSeek-OCR requires image-first content
3. **`vendors.py:130-131`** — URL inference: host contains "deepseek.com" → provider="deepseek"
4. **`base.py:210-211`** — `_normalize_paddle_doc_server_url`: provider="deepseek" → force path `/v1`
5. **`deepseek_parser.py`** — Entire module for parsing DeepSeek grounding tags (`<|ref|>`, `<|det|>`)

### Data Flow: Settings → API → Worker

#### Frontend Settings (web/src/lib/settings.ts)

The frontend `Settings` type has 90+ fields. Key OCR-related fields:

```typescript
ocrProvider: OcrProvider          // "auto" | "aiocr" | "baidu" | "tesseract" | "paddle_local"
ocrAiProvider: OcrAiProvider      // "auto" | "openai" | "siliconflow" | "deepseek" | "ppio" | "novita"
ocrAiBaseUrl: string
ocrAiModel: string
ocrAiChainMode: OcrAiChainMode   // "direct" | "doc_parser" | "layout_block"
ocrAiApiKey: string
ocrBaiduApiKey: string
ocrBaiduSecretKey: string
ocrTesseractLanguage: string
ocrRenderDpi: string
ocrStrictMode: boolean
```

Settings are stored in `localStorage` (self mode) or `user_preferences` API (public mode).

#### API Request Flow

1. Frontend calls `POST /jobs` with all settings as form fields
2. `job_options.py` validates and normalizes all options via `validate_and_normalize_job_options()`
3. Worker receives all options as keyword arguments to `process_pdf_job()`

#### Worker to OCR Runtime

```python
worker.py: process_pdf_job()
    │
    ├── setup_ocr_runtime()  # Creates OcrManager + optional text refiner
    │       │
    │       └── create_ocr_manager()  # Factory in local_providers.py
    │               │
    │               └── OcrManager.__init__()
    │                       │
    │                       ├── provider="aiocr" → create_remote_ocr_client()
    │                       │       │
    │                       │       └── AiOcrClient.__init__()
    │                       │               │
    │                       │               ├── _create_ai_ocr_vendor_adapter()
    │                       │               │       └── OpenAiAiOcrAdapter / SiliconFlowAiOcrAdapter / ...
    │                       │               │
    │                       │               └── openai.OpenAI(base_url=..., api_key=...)
    │                       │
    │                       ├── provider="baidu" → BaiduOcrClient()
    │                       ├── provider="tesseract" → TesseractOcrClient()
    │                       └── provider="auto" → BaiduOcrClient + TesseractOcrClient + AiOcrClient
    │
    ├── run_ocr_stage()  # Iterates pages, calls ocr_manager.ocr_image_lines()
    │
    └── run_ppt_stage()  # Generates PPTX from IR
```

### OcrManager Initialization (30+ parameters)

The `OcrManager.__init__()` accepts these parameters:

```python
def __init__(
    self,
    provider: str | None = None,
    *,
    route_kind: str | None = None,
    ai_provider: str | None = None,
    ai_api_key: str | None = None,
    ai_base_url: str | None = None,
    ai_model: str | None = None,
    ai_layout_model: str | None = None,
    paddle_doc_max_side_px: int | None = None,
    layout_block_max_concurrency: int | None = None,
    request_rpm_limit: int | None = None,
    request_tpm_limit: int | None = None,
    request_max_retries: int | None = None,
    prompt_preset: str | None = None,
    direct_prompt_override: str | None = None,
    layout_block_prompt_override: str | None = None,
    image_region_prompt_override: str | None = None,
    baidu_app_id: str | None = None,
    baidu_api_key: str | None = None,
    baidu_secret_key: str | None = None,
    tesseract_min_confidence: float | None = None,
    tesseract_language: str | None = None,
    strict_no_fallback: bool = False,
    allow_paddle_model_downgrade: bool = False,
)
```

### AiOcrClient Initialization (15+ parameters)

```python
def __init__(
    self,
    *,
    api_key: str,
    base_url: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    layout_model: str | None = None,
    paddle_doc_max_side_px: int | None = None,
    layout_block_max_concurrency: int | None = None,
    request_rpm_limit: int | None = None,
    request_tpm_limit: int | None = None,
    request_max_retries: int | None = None,
    route_kind: str | None = None,
    prompt_preset: str | None = None,
    direct_prompt_override: str | None = None,
    layout_block_prompt_override: str | None = None,
    image_region_prompt_override: str | None = None,
)
```

### Vendor Adapter Pattern

```
AiOcrVendorAdapter (ABC)
    │
    ├── OpenAiAiOcrAdapter      # Generic OpenAI-compatible
    ├── SiliconFlowAiOcrAdapter  # SiliconFlow-specific
    ├── PpioAiOcrAdapter         # PPIO-specific
    ├── NovitaAiOcrAdapter       # Novita-specific
    └── DeepSeekAiOcrAdapter     # DeepSeek-specific
```

All adapters inherit from `AiOcrVendorAdapter` but most methods are inherited without override. The main differences are in:
- `supports_remote_paddle_doc_parser()` — only SiliconFlow, Novita, and self-hosted OpenAI endpoints
- `_normalize_paddle_doc_server_url()` — forces different URL paths per provider

### Pain Points and Complexity

1. **Excessive provider-specific branching**: The code has 15+ SiliconFlow-specific code paths, 6+ for Novita/PPIO, and 5+ for DeepSeek. Many are in `ai_client.py` which is 2600+ lines.

2. **Redundant abstraction layers**: 
   - `vendors.py` defines `AiOcrVendorProfile` + `AiOcrVendorAdapter` + 5 adapter classes
   - `base.py` defines `_normalize_paddle_doc_server_url()` with per-provider branching
   - `local_providers.py` has `OcrManager` which re-implements provider selection logic
   - `job_options.py` has normalization functions that duplicate vendor logic

3. **Inconsistent model name handling**: 
   - `vendors.py:63-93` — `_normalize_ai_ocr_model_name()` with provider-specific normalization
   - `base.py:223-269` — `_resolve_paddle_doc_model_and_pipeline()` with provider-specific downgrade logic
   - Different providers require different casing (SiliconFlow wants lowercase, DeepSeek wants mixed case)

4. **Environment variable explosion**: 30+ OCR-related env vars, many provider-specific:
   - `OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S_V15_SILICONFLOW`
   - `OCR_PADDLE_VL_DOCPARSER_RETRY_TIMEOUT_S_V15_SILICONFLOW`
   - `OCR_PADDLE_VL_DOCPARSER_RETRY_ON_TIMEOUT_V15_SILICONFLOW`
   - `OCR_PADDLE_VL_DOCPARSER_SINGLEFLIGHT_V15_SILICONFLOW`
   - etc.

5. **Frontend settings duplication**: 
   - `web/src/lib/settings.ts` has 90+ fields
   - `web/src/lib/run-config.ts` has additional normalization
   - `api/app/job_options.py` has 525 lines of validation/normalization
   - Many fields are strings that should be numbers (e.g., `ocrRenderDpi: string`)

6. **Auto mode complexity**: The `auto` provider in `OcrManager.__init__()` (lines 1340-1447) tries Baidu → Tesseract → PaddleOCR → AI OCR with multiple fallback paths and conditional logic.

7. **Legacy compatibility burden**: 
   - `worker.py:531-580` — Legacy `v2` mode with hardcoded SiliconFlow fallback
   - `settings.ts:238-273` — Legacy provider migration logic
   - `job_options.py:334-335` — Redundant Baidu provider normalization

### File Locations Summary

| File | Lines | Purpose |
|------|-------|---------|
| `api/app/convert/ocr/vendors.py` | 276 | Vendor profiles, adapters, model normalization |
| `api/app/convert/ocr/ai_client.py` | 2686+ | AiOcrClient, PaddleOCR-VL integration, layout analysis |
| `api/app/convert/ocr/base.py` | 293 | Base types, constants, env helpers |
| `api/app/convert/ocr/local_providers.py` | 2600+ | OcrManager, local providers, hybrid mode |
| `api/app/convert/ocr/routing.py` | 193 | Route kind definitions and normalization |
| `api/app/convert/ocr/deepseek_parser.py` | 489 | DeepSeek grounding tag parser |
| `api/app/convert/ocr/prompts.py` | — | OCR prompt templates |
| `api/app/convert/ocr/result_parsing.py` | — | Result parsing utilities |
| `api/app/convert/ocr/json_extraction.py` | — | JSON extraction from AI responses |
| `api/app/convert/ocr/utils.py` | — | Utility functions |
| `api/app/convert/ocr/runtime_probe.py` | — | Local OCR runtime detection |
| `api/app/worker.py` | 1024 | Main worker orchestrator |
| `api/app/worker_helpers/ocr_runtime.py` | — | OCR runtime setup helper |
| `api/app/worker_helpers/ocr_stage.py` | — | OCR stage runner |
| `api/app/job_options.py` | 525 | Job option validation/normalization |
| `api/app/config.py` | 125 | Global config (Settings class) |
| `web/src/lib/settings.ts` | 582 | Frontend settings types and defaults |
| `web/src/lib/run-config.ts` | — | Run config normalization |
| `web/src/hooks/use-settings.ts` | 178 | Settings hook with localStorage/API sync |
| `web/src/app/settings/page.tsx` | 1382+ | Settings UI page |

### Related Specs

- `.trellis/spec/backend/index.md` — Backend spec index
- `.trellis/spec/frontend/index.md` — Frontend spec index

## Caveats / Not Found

- The `ai_client.py` file is very large (2686+ lines) and contains the bulk of the complexity
- The `local_providers.py` file is also very large (2600+ lines) with extensive line-merging logic
- The `worker_helpers/ocr_runtime.py` and `worker_helpers/ocr_stage.py` files were not fully examined but contain the setup and stage execution logic
- The `prompts.py` file contains OCR prompt templates but was not examined in detail
- The `result_parsing.py` file contains result parsing utilities but was not examined in detail
