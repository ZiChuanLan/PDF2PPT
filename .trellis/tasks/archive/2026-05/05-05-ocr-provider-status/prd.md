# feat: OCR 提供方状态检测和下载 UI

## Goal

让传统 OCR 提供方（PaddleOCR、Tesseract）在主页和设置页面像版面模型一样显示检测状态和下载提示，避免用户选择不可用的提供方。

## Requirements

### 1. 主页 OCR 提供方选择器
- PaddleOCR 未就绪时：显示下载按钮（复用 `DownloadProgressButton`）
- Tesseract 未就绪时：显示安装提示（需要系统包）
- 已就绪：正常显示，无额外提示

### 2. 设置页面集成
- PaddleOCR 下载按钮集成到模型状态系统（已有后端支持）
- 移除独立的"本地 OCR 综合检测"或与主状态合并

### 3. 后端（无需改动）
- 已有 `probe_local_paddleocr()` 和 `probe_local_tesseract()`
- 已有 PaddleOCR 下载端点 `POST /models/download?model=paddleocr`
- 已有状态端点 `/api/v1/models/status`

## Acceptance Criteria

- [ ] PaddleOCR 未就绪时主页显示下载按钮
- [ ] Tesseract 未就绪时显示安装提示
- [ ] 下载进度实时显示
- [ ] 设置页面 PaddleOCR 下载按钮正常工作

## Technical Notes

- 主页: `web/src/app/page.tsx:1081-1101`
- 设置: `web/src/app/settings/page.tsx`
- 状态 badge: `web/src/components/model-status-badge.tsx`
- 下载 hook: `web/src/hooks/use-model-download.ts`
- 后端下载: `api/app/routers/model_status.py`
