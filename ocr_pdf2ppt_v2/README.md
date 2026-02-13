# OCR PDF → PPT V2（重构版）

这是一个**独立新项目**，目标是解决旧链路中“图片被裁切/切碎”的问题。

## 为什么旧方案容易切图

旧项目在扫描页会走“区域检测 + 裁图 + 回贴”的合成链路：

1. 检测图像区域；
2. 从整页渲染图中裁切多个图片块；
3. 擦除背景中的文本后，再把这些图片块叠加回去。

这条链路在复杂版式中很容易产生：

- 图片被拆成多块；
- 边缘错位；
- 透明背景处理后出现断裂感。

## V2 核心策略（避免切图）

V2 改成**整页背景优先**，不再做图片区域裁切：

1. PDF 每页渲染为整页图片；
2. OCR 只提取文本框（bbox）；
3. 用像素级 inpaint 仅擦除文本区域；
4. PPT 中每页先放整页背景图，再覆盖可编辑文本框。

> 关键点：每页只使用一张完整背景图，不切图片块，因此不会出现“图片被 API 切割”的问题。

## 目录结构

```text
ocr_pdf2ppt_v2/
  src/ocr_pdf2ppt_v2/
    api.py                # FastAPI 服务
    cli.py                # 命令行入口
    pipeline.py           # 端到端流程
    siliconflow_ocr.py    # 硅基流动 OCR 客户端
    page_cleaner.py       # 文本区域擦除
    ppt_builder.py        # PPT 构建
    pdf_renderer.py       # PDF 渲染
    geometry.py           # bbox/坐标变换
    config.py             # 配置
    models.py             # 数据模型
  tests/
```

## 依赖安装

在仓库根目录下执行（建议新建虚拟环境）：

```bash
pip install -e ./ocr_pdf2ppt_v2
```

## 环境变量

复制并配置：

```bash
cp ocr_pdf2ppt_v2/.env.example ocr_pdf2ppt_v2/.env
```

必须项：

- `SILICONFLOW_API_KEY`

可选项：

- `SILICONFLOW_BASE_URL`（默认 `https://api.siliconflow.cn/v1`）
- `SILICONFLOW_MODEL`（默认 `Qwen/Qwen2.5-VL-72B-Instruct`）

## CLI 使用

```bash
python -m ocr_pdf2ppt_v2.cli \
  --input ./demo.pdf \
  --output ./demo.pptx \
  --api-key "$SILICONFLOW_API_KEY"
```

常用参数：

- `--render-dpi 220`：PDF 渲染分辨率
- `--max-pages 10`：只处理前 N 页
- `--work-dir ./tmp/v2-job`：保留中间产物（渲染图/OCR JSON/clean 图）

## API 使用

启动服务：

```bash
uvicorn ocr_pdf2ppt_v2.api:app --host 0.0.0.0 --port 8010
```

请求示例：

```bash
curl -X POST "http://127.0.0.1:8010/v1/convert" \
  -F "file=@./demo.pdf" \
  -F "api_key=$SILICONFLOW_API_KEY" \
  -o demo.pptx
```

## 模型与接口说明

V2 使用硅基流动 OpenAI 兼容接口：

- Base URL: `https://api.siliconflow.cn/v1`
- 调用方式：`chat.completions`
- 默认模型：`Qwen/Qwen2.5-VL-72B-Instruct`

如需查看账号可用模型：

```bash
curl https://api.siliconflow.cn/v1/models \
  -H "Authorization: Bearer $SILICONFLOW_API_KEY"
```

## 测试

```bash
python -m pytest ocr_pdf2ppt_v2/tests -q
```

