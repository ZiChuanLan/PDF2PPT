# OCR PDF → PPT V3（隔离重写版）

这是一个**完全独立**于现有主项目流程的重写版本，目标是先把「渲染器 + 合成器 + OCR 提示词」单独打磨到稳定可用，再回集成。

## 设计目标

- 不切图，不做图片区域裁剪，保持整页背景。
- OCR 结果优先“少而准”，避免大面积误框污染整页。
- 可编辑优先：每页尽可能生成可编辑文本框。
- **纯 AI 路线：不使用 Tesseract。**
- 支持两种 AI OCR 后端：
  - `openai_chat`：直接多模态提示词抽取（适合 Qwen / DeepSeek OCR 等）
  - `paddle_doc_parser`：Paddle 官方 doc_parser 链路（适合 `PaddleOCR-VL` 系列，返回结构化块+bbox）
- 失败可诊断：输出详细 `v3_debug.json`。

## V3 核心改造

1. **双阶段 AI OCR（Primary + Retry）**
   - Primary 先做常规 OCR。
   - 质量门控判定不可靠时，触发 Retry prompt 做二次识别。

2. **AI 布局检测（图片区域）**
   - 额外检测 `image_regions`（图表/截图/图标区域）。
   - 合成时按区域裁切并回放成独立图片对象。

3. **新合成策略（Compositor）**
   - 背景层：擦除文字+图片区域后的页面底图。
   - 图片层：按 `image_regions` 放置图片。
   - 文字层：文本框二次清洗 + 字号自适应估算。

4. **完整调试输出**
   - 每页记录 primary/retry OCR 数量、layout 区域数量、最终来源与质量统计。

## 项目结构

```text
ocr_pdf2ppt_v3/
  src/ocr_pdf2ppt_v3/
    api.py
    cli.py
    pipeline.py
    siliconflow_ocr.py
    quality_gate.py
    page_cleaner.py
    ppt_builder.py
    pdf_renderer.py
    geometry.py
    config.py
    models.py
  tests/
```

## 安装

```bash
cd ocr_pdf2ppt_v3
pip install -e .
```

若要启用 Paddle doc_parser 后端：

```bash
pip install -e .[paddle]
```

## CLI 使用

```bash
ocr-pdf2ppt-v3 \
  --input ./demo.pdf \
  --output ./demo.v3.pptx \
  --api-key "$SILICONFLOW_API_KEY" \
  --base-url "https://api.siliconflow.cn/v1" \
  --model "Qwen/Qwen2.5-VL-72B-Instruct" \
  --ocr-backend auto \
  --work-dir ./tmp/v3-job
```

运行结束后重点看：

- `./tmp/v3-job/debug/v3_debug.json`
- `./tmp/v3-job/ocr/page-xxxx.json`
- `./tmp/v3-job/ocr/page-xxxx.layout.json`

### 关于 PaddleOCR-VL（重点）

如果你使用：

- `--model "PaddlePaddle/PaddleOCR-VL"`
- `--model "PaddlePaddle/PaddleOCR-VL-1.5"`

建议使用（或保持）`--ocr-backend auto`。V3 会自动切到 `paddle_doc_parser` 后端，走 Paddle 官方 doc_parser 调用路径，而不是简单的 `chat/completions` 纯文本输出。

这能拿到结构化字段（如 `parsing_res_list[].block_bbox`、`layout_det_res.boxes[].coordinate`），用于可编辑文本框与图片区域重建。

## API 使用

```bash
uvicorn ocr_pdf2ppt_v3.api:app --host 0.0.0.0 --port 8011
```

```bash
curl -X POST "http://127.0.0.1:8011/v1/convert" \
  -F "file=@./demo.pdf" \
  -F "api_key=$SILICONFLOW_API_KEY" \
  -F "model=Qwen/Qwen2.5-VL-72B-Instruct" \
  -F "ocr_backend=auto" \
  -o demo.v3.pptx
```

## 环境变量

可在 `.env` 中配置：

- `SILICONFLOW_API_KEY`
- `SILICONFLOW_BASE_URL`（默认 `https://api.siliconflow.cn/v1`）
- `SILICONFLOW_MODEL`（默认 `Qwen/Qwen2.5-VL-72B-Instruct`）
- `SILICONFLOW_OCR_BACKEND`（默认 `auto`）

## 测试

```bash
PYTHONPATH=src pytest -q
```
