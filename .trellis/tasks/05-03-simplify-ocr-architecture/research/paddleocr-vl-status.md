# Research: PaddleOCR-VL Status (2025-2026)

- **Query**: Current status of PaddleOCR-VL (PaddleOCR Vision Language model) in 2025-2026
- **Scope**: external
- **Date**: 2026-05-03

## Findings

### 1. Maintenance Status

**Actively maintained by PaddlePaddle/Baidu.** The project is under continuous development with no official sunset announced.

| Milestone | Date | Version |
|---|---|---|
| PaddleOCR-VL initial release | Oct 16, 2025 | v3.3.0 |
| PaddleOCR-VL-1.5 release | Jan 29, 2026 | v3.4.0 |
| Latest PaddleOCR release | Apr 21, 2026 | v3.5.0 (ecosystem integration, no new VL model) |

GitHub repo: [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) — frequent commits, active issues/PRs.

### 2. Latest Version

**PaddleOCR-VL-1.5** (0.9B parameters) is the latest VL model, released Jan 29, 2026.

Key specs:
- 0.9B ultra-compact Vision-Language Model
- NaViT-style dynamic resolution visual encoder + ERNIE-4.5-0.3B language model
- End-to-end document parsing: text, tables, formulas, charts, layouts
- Structured Markdown/JSON output
- 109 languages supported
- 94.5% on OmniDocBench v1.5 (SOTA for lightweight models)
- Strong robustness to distortions (warping, scanning, skew, screen photos, illumination)

HuggingFace: `PaddlePaddle/PaddleOCR-VL-1.5`

### 3. Cloud Platform Availability

| Platform | Status | Notes |
|---|---|---|
| **SiliconFlow** (硅基流动) | ✅ Available | Supports VL and VL-1.5. Use via PaddleOCR client (vLLM backend) or OpenAI `/chat/completions` with image URLs. API base: `https://api.siliconflow.cn/v1` |
| **PPIO** | ✅ Available | One-click deployment templates for VL-1.5 on GPU servers. HTTP POST with base64/images, returns structured results |
| **Novita** | ✅ Available | `novitalabs/paddleocr-vl-1.5`. Dedicated instances, ~$0.63/hr GPU templates. OpenAI-compatible |
| **Official PaddleOCR Cloud** | ✅ Available | www.paddleocr.com with Experience Center and direct APIs |

**Usage pattern**: Send image/PDF URL or base64 + task prompt → structured data (Markdown/JSON) ready for LLMs/RAG.

**PaddleOCR CLI integration** (e.g., SiliconFlow):
```
--vl_rec_backend vllm-server
--vl_rec_server_url https://api.siliconflow.cn/v1
--vl_model_name PaddlePaddle/PaddleOCR-VL-1.5
```

### 4. Comparison with General Vision Models (Document OCR)

| Dimension | PaddleOCR-VL-1.5 (0.9B) | GPT-4o-mini | Qwen2.5-VL (72B) |
|---|---|---|---|
| **OmniDocBench accuracy** | ~94.5% (SOTA) | ~75% or below | ~87% range |
| **Text (edit distance)** | ~0.035 | Higher | Moderate |
| **Tables (TEDS)** | ~92-95% | Weaker | Strong |
| **Formulas (CDM)** | ~94+ | Weaker | Good |
| **Real-world distortions** | Excellent | Good | Good |
| **Model size** | 0.9B (ultra-compact) | Closed API | 7B/32B/72B |
| **Deployment** | Open-source, self-host | API-only | Open weights |
| **Cost** | ~$0.09/1K pages self-host | Token-based | Self-host |
| **Strengths** | Pure OCR accuracy, structure fidelity, high-volume | Quick integration, reasoning | Document understanding + reasoning |

**Bottom line**: PaddleOCR-VL-1.5 outperforms both GPT-4o-mini and Qwen2.5-VL on pure document OCR/parsing benchmarks while being far smaller (0.9B vs 72B). It is the best choice for accuracy-critical, high-volume document parsing.

### 5. Deprecation / Discontinuation Risk

**Risk level: LOW for 2025-2026.**

- No official deprecation announced by PaddlePaddle/Baidu
- Positioned as a flagship model in the PaddleOCR ecosystem
- PaddleOCR-VL-1.5 released Jan 2026, actively integrated with HuggingFace, AMD GPUs, production pipelines
- Strong community and enterprise adoption

**Minor caveats**:
- Some third-party serverless platforms deprecated hosted versions of `paddlepaddle/paddleocr-vl` around late 2025/early 2026, recommending alternatives like Qwen VL models. This is common for hosted endpoints and does **not** affect the open-source model.
- Novita changelog (Dec 25, 2025) noted deprecation of some hosted variants, but re-added VL-1.5 later.
- Self-hosting eliminates third-party dependency risks entirely.

### External References

- [PaddleOCR GitHub Releases](https://github.com/PaddlePaddle/PaddleOCR/releases) — official release notes
- [PaddleOCR-VL-1.5 on HuggingFace](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5) — model weights + docs
- [PaddleOCR-VL paper (arXiv:2601.21957)](https://arxiv.org/html/2601.21957v1) — technical details + benchmarks
- [SiliconFlow PaddleOCR-VL docs](https://docs.siliconflow.cn/cn/userguide/capabilities/multimodal-vision#6-paddleocr-客户端使用方法) — cloud API usage
- [PPIO PaddleOCR-VL blog](https://ppio.com/blogs/post/260130) — deployment templates
- [Novita PaddleOCR-VL](https://novita.ai/models/model-detail/paddlepaddle-paddleocr-vl) — cloud deployment
- [Codesota OCR comparison](https://www.codesota.com/ocr) — benchmark comparisons
- [Novita changelog](https://novita.ai/docs/changelog/25-12-25) — third-party deprecation notes

### Caveats / Not Found

- No exact pricing for SiliconFlow/PPIO serverless token-based pricing found (likely varies by plan)
- PaddleOCR v3.5.0 (Apr 2026) did not introduce a new VL model iteration — only ecosystem integration improvements
- Performance on Chinese-only documents vs multilingual was not specifically benchmarked in the sources found
