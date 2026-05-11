# Research: DeepSeek OCR Status (2025-2026)

- **Query**: Does DeepSeek have a dedicated OCR model? What are grounding tags? Is it still available? Deprecation risks?
- **Scope**: external (web research) + internal (codebase usage)
- **Date**: 2026-05-03

## Findings

### 1. DeepSeek Has a Dedicated OCR Model

**Yes, DeepSeek has a dedicated OCR model** — it is NOT just their general vision model (DeepSeek-VL/VL2).

| Model | Release | Architecture | Parameters |
|---|---|---|---|
| **DeepSeek-OCR** (v1) | 2025-10-20 | Windowed SAM + CLIP-Large + 16× compressor → DeepSeek-3B-MoE decoder (~570M active) | 3B total |
| **DeepSeek-OCR 2** | 2026-01-27 | Visual Causal Flow (DeepEncoder-V2, Qwen2-0.5B-based) → same decoder | 3B total |

Key distinction: DeepSeek-VL2 is a general-purpose vision-language model (VQA, reasoning, OCR). **DeepSeek-OCR is a specialized end-to-end OCR model** optimized for high-throughput document parsing with "Contexts Optical Compression" — compressing document images into very few vision tokens (64–1,120 per page) while maintaining ~97% accuracy at 10× compression.

### 2. Grounding Tags: `<|ref|>`, `<|det|>`, `<|grounding|>`

DeepSeek-OCR uses three special tags for layout-aware OCR:

#### `<|grounding|>` (Prompt Tag)
- **Included in the prompt** to activate layout-aware mode
- Without it, the model does "Free OCR" (plain text extraction, no bounding boxes)
- Example prompts:
  - `<image>\n<|grounding|>OCR this image.` → OCR with bounding boxes
  - `<image>\n<|grounding|>Convert the document to markdown.` → structured Markdown with layout
  - `<image>\nFree OCR.` → plain text, no grounding

#### `<|ref|>` and `<|det|>` (Output Tags)
These appear in the model's output when grounding mode is active:

```
<|ref|>title<|/ref|><|det|>[[x1,y1,x2,y2]]<|/det|>
# Document Title
<|ref|>paragraph<|/ref|><|det|>[[50,100,950,300]]<|/det|>
This is paragraph text...
```

- `<|ref|>LABEL<|/ref|>` — the element type (title, paragraph, image, table, etc.)
- `<|det|>[[x1,y1,x2,y2]]<|/det|>` — bounding box coordinates, **normalized to 0–999 scale**
- Can contain single box `[x1,y1,x2,y2]` or multiple boxes `[[x1,y1,x2,y2], ...]`

#### Two Grounding Modes (in practice)
| Mode | `<|ref\|>` behavior | Use case |
|---|---|---|
| `markdown` | Suppress ref content (redundant metadata) | Document-to-Markdown conversion |
| `ocr` | Emit ref content (the actual recognized text) | Standard OCR with spatial data |

### 3. Cloud Platform Availability (as of May 2026)

**Widely available** across multiple platforms:

| Platform | Status | Notes |
|---|---|---|
| **Hugging Face** | ✅ Fully available | Official weights: `deepseek-ai/DeepSeek-OCR` and `DeepSeek-OCR-2`. MIT license. |
| **PPIO (派欧云)** | ✅ Fully available | First to host OCR-2 (Jan 2026). One-click deployment, OpenAI-compatible API. |
| **SiliconFlow** | ✅ Available | Listed in model catalog; serverless inference for vision/OCR DeepSeek models. |
| **Google Vertex AI** | ✅ Available | Managed API (MaaS): `deepseek-ocr-maas` |
| **AWS SageMaker JumpStart** | ✅ Available | Since early 2026 |
| **vLLM** | ✅ Officially supported | Since 2025-10-23. Custom logits processor required. |
| **Ollama** | ✅ Available | Community support for local runs |
| **DeepSeek Cloud API** | ✅ Available | OpenAI-compatible endpoint. ~$0.15/1M tokens. |
| **DeepInfra, Atlas Cloud** | ✅ Available | Third-party API aggregators |

### 4. Comparison: DeepSeek-OCR vs General Vision Models for Document OCR

| Aspect | DeepSeek-OCR | General VLMs (DeepSeek-VL2, Qwen-VL, etc.) |
|---|---|---|
| **Design purpose** | End-to-end OCR + document parsing | General vision understanding + reasoning |
| **OCR accuracy** | ~97% at 10× compression (Fox benchmark) | Good but not optimized for compression |
| **Token efficiency** | 64–1,120 vision tokens/page | Typically thousands of tokens |
| **Throughput** | ~200k pages/day on single A100-40G | Lower (heavier models) |
| **Grounding support** | Native `<\|ref\|>` / `<\|det\|>` tags | Not native (some models have alternatives) |
| **Layout preservation** | Purpose-built (reading order, tables, formulas) | General-purpose, less precise |
| **OmniDocBench** | 91.09% (OCR-2) vs MinerU 2.0 ~similar with 6000+ tokens | Lower on pure document tasks |
| **Model size** | 3B (570M active) — lightweight | 7B+ typical |

**Key insight for this project**: DeepSeek-OCR's grounding tags (`<|ref|>` / `<|det|>`) are **model-specific output format**, not a generic API feature. General vision models won't produce these tags. The project's `deepseek_parser.py` is specifically designed to parse this output format.

### 5. Deprecation / Discontinuation Risk Assessment

**Overall risk: LOW for the model, MODERATE for cloud APIs**

| Risk Factor | Level | Details |
|---|---|---|
| **Model availability** | 🟢 Low | MIT-licensed, open weights on HuggingFace. Can self-host indefinitely. |
| **Cloud API stability** | 🟡 Moderate | No OCR-specific deprecation notices. General DeepSeek API retiring legacy models (deepseek-chat/reasoner → V4 migration, July 2026) but this doesn't affect OCR. |
| **Vendor lock-in** | 🟡 Moderate | If relying solely on DeepSeek Cloud API, moderate lock-in. Mitigated by OpenAI-compatible format. |
| **Geopolitical risk** | 🟡 Moderate | China-based hosting, data subject to local laws. |
| **Model evolution** | 🟢 Low | OCR-2 already released (Jan 2026). Active development continues. |
| **Community support** | 🟢 Low | vLLM official support, Unsloth fine-tuning support, active GitHub. |

**No deprecation signals for DeepSeek-OCR as of May 2026.** The model is actively maintained with OCR-2 improvements (reading order ED: 0.085 → 0.057, repetition rate: 6.25% → 4.17%).

### 6. Codebase Usage (Internal)

The project already uses DeepSeek-OCR extensively:

| File | Usage |
|---|---|
| `api/app/convert/ocr/deepseek_parser.py` | Dedicated grounding-tag parser (`<\|ref\|>`, `<\|det\|>`) |
| `api/app/convert/ocr/prompts.py` | `deepseek_ocr` prompt preset with `<\|grounding\|>` tag |
| `api/app/convert/ocr/vendors.py` | Vendor config with `default_model="deepseek-ai/DeepSeek-OCR"` |
| `api/app/convert/ocr/ai_client.py` | 83 lines referencing DeepSeek OCR (detection, routing, parsing) |
| `api/app/convert/ocr/local_providers.py` | Imports from deepseek_parser |
| `api/app/routers/models.py` | Regex pattern `deepseek[-_]?ocr` for model detection |
| Multiple test files | Extensive test coverage for DeepSeek OCR routing, grounding parsing |

Key model name variants detected in code:
- `deepseek-ai/DeepSeek-OCR` (canonical)
- `Pro/deepseek-ai/deepseek-ocr` (SiliconFlow prefix)
- `deepseek-ocr` / `deepseekocr` (lowercase matching)

## Caveats / Not Found

- **DeepSeek-OCR-2 differences**: OCR-2 uses a different encoder architecture (DeepEncoder-V2 based on Qwen2-0.5B vs SAM+CLIP). The grounding tag format is the same, but output quality/reliability may differ.
- **Prompt format evolution**: The official repo warns that trailing spaces after prompts can cause missing location/grounding data. Test thoroughly if upgrading prompt handling.
- **Not an OpenAI-compatible model**: DeepSeek-OCR does NOT use the standard `/v1/chat/completions` format with tool calls. It uses a specialized prompt format with `<image>` and `<|grounding|>` tags. This is different from the project's Phase 2 goal of "统一 OpenAI 兼容接口" — the OCR client needs special handling regardless.
- **Cloud API pricing**: PPIO quotes ~¥0.216/Mt for OCR-2; DeepSeek Cloud ~$0.15/1M tokens. Verify current pricing for production use.
