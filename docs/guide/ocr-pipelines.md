# OCR 与解析链路

## Parse Engine

| 模式 | 含义 | 适合场景 |
| --- | --- | --- |
| `local_ocr` | 本地解析 PDF，再按需执行 OCR | 通用默认模式 |
| `remote_ocr` | 以远程 OCR 为主的链路 | OCR 质量优先 |
| `baidu_doc` | 百度文档解析链路 | 结构化解析需求 |
| `mineru_cloud` | MinerU 云解析链路 | 表格、公式、复杂结构文档 |

## OCR Provider

| Provider | 含义 | 备注 |
| --- | --- | --- |
| `aiocr` | 远程 OpenAI-Compatible OCR | 适合高质量 OCR |
| `tesseract` | 本地 Tesseract | 依赖更少 |
| `paddle_local` | 本地 PaddleOCR | 纯本地方案 |
| `baidu` | 百度 OCR | 独立 provider |

## AIOCR Chain

| 模式 | 含义 | 特点 |
| --- | --- | --- |
| `direct` | 整页直接送视觉模型 | 最简单，配置最少 |
| `layout_block` | 先切块，再逐块识别 | 适合小字密集、图文混排 |
| `doc_parser` | 结构化文档识别通道 | 更强调结构信息 |

## Scanned Page Mode

| 模式 | 含义 | 结果特点 |
| --- | --- | --- |
| `fullpage` | 整页保留为背景图，再叠可编辑文字 | 最稳，最接近原图 |
| `segmented` | 尽量把图表、截图裁成独立图片对象 | 后续编辑更灵活 |

## 推荐起步配置

如果首次运行想优先提高成功率，建议从下面这组开始：

- `remote_ocr`
- `aiocr`
- `fullpage`

然后再根据结果逐步提高可编辑性：

- 想拆出更多图片区域时，再尝试 `segmented`
- 更看重结构化解析时，再尝试 `baidu_doc` 或 `mineru_cloud`

## 使用边界

这个项目更适合“扫描件、截图件、图片型文档的高保真重建”，不应理解为：

- 任意 PDF 都能 100% 还原成完全结构化、完全可编辑的原生 PPT
- 不配置 OCR 或解析能力也能在所有复杂文档上得到稳定结果
- 所有页面都一定比原稿更适合编辑
