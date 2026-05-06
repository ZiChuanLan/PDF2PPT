# 传统 OCR 选择器 UI 重构为卡片列表

## Goal

将传统 OCR 提供方（PaddleOCR / Tesseract）的选择器从简单 `<Select>` 下拉框重构为卡片列表，参照 AI OCR 版面切块模型的 UI 风格，每行显示一个提供方的详细信息、运行状态和下载按钮。

## What I already know

- 当前传统 OCR 选择器在 settings 页 (`settings/page.tsx:1595-1610`) 和主页 (`page.tsx:1117-1132`) 都是简单 `<Select>` 下拉框
- AI OCR 版面切块模型 (`settings/page.tsx:1742-1820`) 使用卡片列表：radio 选择 + 名称/大小/速度/描述 + 下载状态/按钮
- PaddleOCR 支持通过 `POST /api/models/download` 下载模型，Tesseract 不支持（需系统安装）
- 本地 OCR 检测面板 (`settings/page.tsx:2394-2470`) 已有运行环境 + 模型状态检测，但与选择器分离
- `model_status` API 返回 `local.paddleocr` 和 `local.tesseract` 的 ready/issues 状态
- `useModelDownload` hook 已支持 PaddleOCR 下载进度跟踪

## Requirements

1. Settings 页：将 OCR 提供方 `<Select>` 替换为卡片列表（参照版面切块模型样式）
2. 每张卡片显示：提供方名称、就绪状态、问题描述（如有）、下载按钮（仅 PaddleOCR）
3. 主页：将 OCR 提供方 `<Select>` 替换为类似的卡片式选择器（简化版，无需下载功能）
4. 未就绪的提供方可选但显示提示，或禁用选择

## Decision (ADR-lite)

**Context**: Tesseract 没有下载 API，需系统包管理器安装。
**Decision**: 方案 A — 仅显示就绪状态（✓/✗），未就绪时提示"需系统安装 tesseract-ocr"，不显示下载按钮。
**Consequences**: 与 PaddleOCR 卡片视觉一致但交互不同；用户需自行安装 Tesseract。

## Acceptance Criteria

- [ ] Settings 页 OCR 提供方选择器改为卡片列表（radio + 名称 + 状态）
- [ ] PaddleOCR 卡片显示下载状态/下载按钮（复用 DownloadProgressButton）
- [ ] Tesseract 卡片显示就绪状态（✓/✗），未就绪时提示"需系统安装 tesseract-ocr"
- [ ] 主页 OCR 提供方选择器也改为卡片式（简化版，无下载功能）
- [ ] 未就绪的提供方显示禁用状态或警告提示
- [ ] 样式与版面切块模型卡片一致（border、padding、颜色）

## Definition of Done

- Lint / typecheck 绿灯
- 两处 UI 都更新

## Out of Scope

- 新增 Tesseract 下载 API
- 其他 OCR 提供方（百度、MinerU 等）的 UI 改造

## Technical Notes

- Settings 页已有 `localOcrSuite` 检测逻辑，可复用
- 主页使用 `modelStatus` hook 获取 ready 状态
- `DownloadProgressButton` 组件可直接复用
- `LAYOUT_MODELS` 卡片样式作为参考模板
