# 首页 OCR/Layout 模型选择与设置/状态同步

## Goal

修复首页（QuickConfigPanel）两个模型选择问题：OCR 模型列表使用硬编码占位符而非真实的后端可用模型，Layout 模型下拉列表包含未下载的模型。

## Requirements

### 1. OCR 模型下拉动态获取

- QuickConfigPanel 的 OCR 模型选择现在硬编码了5个固定选项（Qwen2.5-VL-7B/32B, PaddleOCR-VL, DeepSeek-OCR, GPT-4o-mini）
- 改为：像 Settings 页面一样，通过 `fetchModels()` 从 `POST /api/v1/models` 获取真实可用模型列表
- 在 `parseEngineMode === "remote_ocr"` 且有 API Key 时自动 fetch
- 保底：fetch 失败或返回空时显示一条提示信息

### 2. Layout 模型下拉过滤已下载

- 现在显示所有 `LAYOUT_MODELS` 中的模型（含未下载的）
- 改为：只显示 `downloadedLayoutModels` 中已就绪的模型
- 如果当前选中的模型不在已下载列表中，自动切换到第一个已下载模型或置空

## Acceptance Criteria

- [ ] OCR 模型下拉列表来源于 `fetchModels()` 而非硬编码
- [ ] Layout 模型下拉只显示已下载模型
- [ ] 用户不能选择未下载的 layout 模型
- [ ] `npm run lint` 通过
- [ ] `npx tsc --noEmit` 通过
- [ ] `npm run build` 通过

## Out of Scope

- 不影响 Settings 页面行为
- 不修改后端逻辑
- 不修改模型下载流程
