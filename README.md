# PDF2PPT

`PDF2PPT` 用来把 PDF，尤其是扫描版、图片版和课件截图类文档，转换成**尽量高保真、尽量可编辑**的 PPTX。

项目重点：
- 尽量保留原稿的文字位置、字号、换行和图片区块
- OCR 可切换远程或本地引擎，但统一走同一条合成管线
- 部署配置尽量收敛，默认值尽量放在代码里而不是堆在 compose 里

## 快速启动（本地开发）

```bash
make dev-local
```

会自动启动：
- API: `http://127.0.0.1:8000`（若端口占用会自动换 8001）
- Web: `http://localhost:3000`

也可以直接运行：

```bash
bash scripts/dev/local_dev.sh
```

## VPS / Docker 最小配置

常规部署只需要关心下面几项：

```env
SILICONFLOW_API_KEY=你的key
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=PaddlePaddle/PaddleOCR-VL-1.5
OCR_PADDLE_VL_PREWARM=1
OCR_PADDLE_VL_PREWARM_TARGET=worker
OCR_PADDLE_VL_DOCPARSER_MAX_SIDE_PX=2200
```

说明：
- `OCR_PADDLE_VL_PREWARM=1` 用于容器启动时预热 PaddleOCR-VL，避免第一个请求承担冷启动
- `OCR_PADDLE_VL_DOCPARSER_MAX_SIDE_PX` 是目前仍建议保留的公开调节项
- 其他 PaddleOCR-VL 超时、重试、并发等细粒度参数默认走代码内置值，除非你在排障，否则不需要管

## Windows 可下载版（EXE + Release 包）

如果你希望用户在 GitHub 上下载后直接运行，可以使用 Windows 打包流程：

- 文档：`packaging/windows/README.md`
- 构建脚本：`packaging/windows/build_exe.ps1` / `packaging/windows/build_exe.bat`
- 自动化工作流：`.github/workflows/windows-release.yml`

当前打包链路输出的文件名仍沿用历史名字：

- `release/windows/PPT-OpenCode-Launcher.exe`
- `release/windows/ppt-opencode-win-x64.zip`

说明：
- `PPT-OpenCode-Launcher.exe` 是启动器
- 对最终用户分发，优先使用 `ppt-opencode-win-x64.zip`（包含 EXE + 运行所需目录）
- Markdown 文档品牌已经统一为 `PDF2PPT`，但打包产物文件名暂未跟着改动，避免影响现有发布链路

## 远程 OCR（推荐）

远程 OCR 走 OpenAI-Compatible 接口（例如 SiliconFlow / PPIO / Novita / OpenAI / DeepSeek 网关）。

建议通过以下方式之一配置：
- 在前端“设置页”填写 OCR 的 `API Key / Base URL / Model`
- 或在后端环境变量 / `.env` 中设置（示例见 `.env.example`）

注意：不要把真实 Key 提交到仓库或发到公开渠道。

### 常用模型示例

- DeepSeek 专用 OCR：`Pro/deepseek-ai/deepseek-ocr`
- PaddleOCR-VL：`PaddlePaddle/PaddleOCR-VL-1.5`
- 通用 VL 也可尝试 OCR：`Qwen/Qwen2.5-VL-72B-Instruct`（效果取决于模型与 prompt）

## 扫描页合成模式（关键）

设置项：`scanned_page_mode`

- `segmented`（分块）：尽量把截图/图表等区域裁为可编辑图片块，文字仍可编辑
- `fullpage`（全页）：整页作为背景图，仅覆盖可编辑文字，通常最接近原图（图片不可单独编辑）

## 项目结构

- `api/`：FastAPI 接口、任务队列、PDF 解析、OCR 和 PPTX 生成
- `web/`：Next.js 前端，负责上传、运行配置、结果跟踪和设置页
- `scripts/dev/`：本地开发辅助脚本
- `packaging/windows/`：Windows 启动器与发布打包脚本

说明：
- 公开仓库默认不保留测试样本、截图对比产物和临时基准脚本
- OCR 的真实密钥、样本 PDF、运行缓存也不应提交
