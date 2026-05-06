# Simplify OCR/AI Pipeline Architecture

## Goal

消除厂商特定硬编码，统一为 OpenAI 兼容接口，简化参数传递，使架构清晰可维护。

## Current Problems

1. **5 个 AI 厂商适配器**，15+ SiliconFlow 专属路径，厂商改模型就坏
2. **60+ 表单字段**从前端传递到 worker，无结构化抽象
3. **5000+ 行代码**在 ai_client.py 和 local_providers.py
4. **30+ 环境变量**，很多是厂商专属超时/重试配置
5. **前后端重复归一化**相同的配置值

## Proposed Architecture (v2 — 基于深度调研)

### 核心思路

1. **6 个 OCR provider 实际只有 3 条代码路径** — `paddle` 与 `aiocr+doc_parser` 100% 相同，可合并
2. **5 个 vendor adapter 中 4 个是空壳** — 全部删除，改为配置字典
3. **DeepSeek 特殊处理基于模型名**，不是 vendor — 改为 3 个配置 flag
4. **Route kinds 完全可从 (provider, chain_mode) 推导** — 不需要独立概念

### 最优 Provider 方案：6 → 3+1

| 新 Provider | 覆盖原有                                              | 说明                                |
| ----------- | ----------------------------------------------------- | ----------------------------------- |
| `aiocr`       | `aiocr` + `paddle`                                        | 所有 AI OCR，通过 chain_mode 区分   |
| `machine`     | `tesseract` + `paddle_local`                              | 本地 OCR（tesseract + paddle 本地） |
| `baidu`       | `baidu`                                                   | 百度传统 OCR                        |
| `auto`        | `auto`                                                    | 自动选择：baidu → machine → aiocr   |

### Chain Mode（保留，但语义更清晰）

| Chain Mode     | 说明                       | 适用模型                             |
| -------------- | -------------------------- | ------------------------------------ |
| `direct`         | Vision prompt 直接返回文本 | 所有 VLM（GPT-4o-mini, Qwen, etc.） |
| `doc_parser`     | PaddleOCR-VL 专用协议      | PaddleOCR-VL 1/1.5                  |
| `layout_block`   | 本地布局模型 + AI OCR      | 任意 VLM + pp_doclayout             |

### Vendor 处理：删除适配器类，改为配置

```python
# vendors.py — 纯配置，无代码分支
VENDOR_DEFAULTS: dict[str, VendorConfig] = {
    "openai":     VendorConfig(base_url=None, paddle_doc_path=None),
    "siliconflow": VendorConfig(
        base_url="https://api.siliconflow.cn/v1",
        paddle_doc_path="/v1",
        model_casing="lowercase",
        supports_remote_paddle_doc=True,
        tuning=VendorTuningConfig(vl_rec_max_concurrency=4, ...),
    ),
    "ppio": VendorConfig(
        base_url="https://api.ppio.com/openai",
        paddle_doc_path="/openai",
        model_casing="lowercase",
    ),
    "novita": VendorConfig(
        base_url="https://api.novita.ai/openai",
        paddle_doc_path="/openai",
        model_casing="lowercase",
        supports_remote_paddle_doc=True,
    ),
    "deepseek": VendorConfig(
        base_url="https://api.deepseek.com/v1",
        paddle_doc_path="/v1",
        use_grounding=True,
        send_image_first=True,
        single_message_format=True,
    ),
}
```

### DeepSeek 特殊处理：3 个配置 flag

| Flag                   | 说明                              | 当前实现                  |
| ---------------------- | --------------------------------- | ------------------------- |
| `use_grounding`          | 输出 `<\|ref\|>` `<\|det\|>` grounding tags | `deepseek_parser.py` 解析 |
| `send_image_first`       | 请求中图片放文本前面              | `_should_send_image_first`  |
| `single_message_format`  | 只用 user message，不用 system    | 特殊 prompt 构建          |

这些 flag 在 `VendorConfig` 中设置，`AiOcrClient` 读取配置而非检查 vendor 名。

### 不做的事情（零功能损失）

- **不改变 OCR 链路逻辑**（layout_block、direct、doc_parser 三种模式保留）
- **不改变百度 OCR**（独立 API，保留）
- **不改变 MinerU**（独立服务，保留）
- **不改变本地 OCR**（Tesseract、PaddleOCR 本地版保留）
- **不改变 DeepSeek grounding tag 解析**（保留 deepseek_parser.py）
- **不改变 PaddleOCR-VL 支持**（性能远超通用模型，保留 doc_parser 链路）
- **不改变 auto 模式的 fallback 逻辑**（baidu → machine → aiocr）

## Acceptance Criteria

- [ ] `paddle` provider 合并进 `aiocr`（向后兼容：旧的 `paddle` 自动映射为 `aiocr+doc_parser`）
- [ ] `tesseract` + `paddle_local` 合并为 `machine` provider
- [ ] 删除 5 个 vendor adapter 类，改为 `VENDOR_DEFAULTS` 配置字典
- [ ] DeepSeek 特殊处理改为配置 flag（use_grounding, send_image_first, single_message_format）
- [ ] Route kinds 从 (provider, chain_mode) 自动推导，不再独立配置
- [ ] 删除厂商专属环境变量
- [ ] Job 创建使用结构化 JSON（v2 endpoint）
- [ ] 前端设置页面简化
- [ ] 所有 OCR 链路仍然正常工作（aiocr/baidu/machine/auto × direct/doc_parser/layout_block）
- [ ] 旧的 provider 名（paddle, tesseract, paddle_local）向后兼容

## Out of Scope

- 不重构 PPT 生成逻辑
- 不改变百度 OCR API 格式
- 不改变 MinerU 集成
- 不添加新的 OCR provider

## Technical Notes

### Research References

- [`research/ocr-pipeline-architecture.md`](research/ocr-pipeline-architecture.md) — 6 OCR providers, 5 AI vendors, 15+ SiliconFlow hard-coded paths
- [`research/settings-data-flow.md`](research/settings-data-flow.md) — 60+ form fields, 50+ worker kwargs
- [`research/ocr-provider-deep-dive.md`](research/ocr-provider-deep-dive.md) — **关键**：6 provider 实际 3 条代码路径，4/5 vendor adapter 为空壳
- [`research/paddleocr-vl-status.md`](research/paddleocr-vl-status.md) — PaddleOCR-VL 活跃维护，94.5% 准确率远超 GPT-4o-mini
- [`research/deepseek-ocr-status.md`](research/deepseek-ocr-status.md) — DeepSeek-OCR 活跃维护，需要特殊 prompt 格式

### Key Files to Modify

| File                                    | Lines | Change                                         |
| --------------------------------------- | ----- | ---------------------------------------------- |
| `api/app/convert/ocr/vendors.py`          | 276   | 删除 5 个 adapter 类，改为 VendorConfig + VENDOR_DEFAULTS |
| `api/app/convert/ocr/ai_client.py`        | 5271  | 删除 vendor 分支，改用配置驱动                   |
| `api/app/convert/ocr/local_providers.py`  | 2600  | 简化 OcrManager，合并 paddle→aiocr，tesseract+paddle_local→machine |
| `api/app/convert/ocr/routing.py`          | 193   | 简化 route kind 推导                            |
| `api/app/convert/ocr/base.py`             | 293   | 清理厂商特定归一化函数                          |
| `api/app/job_options.py`                  | 525   | 合并 paddle→aiocr，tesseract+paddle_local→machine |
| `web/src/lib/settings.ts`                 | 582   | 简化 ocrProvider 选项                           |
| `web/src/app/settings/page.tsx`           | 1382  | 简化 OCR provider 下拉                         |

### Risk Assessment

- **高风险**: local_providers.py 重写（OcrManager 是核心）
- **中风险**: provider 名变更（需向后兼容映射）
- **低风险**: vendor adapter 删除（它们是空壳）
