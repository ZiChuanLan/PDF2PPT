# PRD: 全流程架构优化 — AIOCR 链路、硬编码消除、转换效率

## 概述

全面优化 PDF2PPT 项目中 AIOCR 转换链路，消除硬编码，提升转换效率和代码可维护性。

## 需求背景

全代码库审查发现三大类问题：
1. **AIOCR 链路**：超时硬编码、并发控制分散、请求无超时保护、SSE 重连无退避
2. **硬编码值**：~150+ 个硬编码常量，部分需要外部可配置化
3. **转换效率**：前端轮询不一致、死代码存在、巨石函数影响可维护性

## 优化范围

### 1. AIOCR 链路优化（核心）

| 项 | 现状 | 目标 |
|---|---|---|
| 请求超时 | 无实际超时控制（fetch 无 timeout、AI API 部分有但混杂） | 所有外部 HTTP 调用统一超时 + 可配置 |
| 并发控制 | OCR AI 并发(1-8 页)、Block 并发(1-8) 有 bounds 但混合在 worker 中 | 提取到独立配置层 |
| 错误重试 | 硬编码 8s 基础退避 + 0.75s 上限 | 提取为可配置的重试策略 |
| Rate Limit | RPM/TPM 有 bounds 但计算逻辑散落 | 统一 RateLimiter 配置 |
| OCR 旁路阈值 | ~20 个置信度/覆盖率阈值硬编码在 ai_client.py | 按需暴露为配置项 |
| 模型下载超时 | 30s 硬编码 fallback | 统一使用 Settings 环境变量 |

### 2. 硬编码消除

| 项 | 位置 | 方案 |
|---|---|---|
| Job 超时 `"1h"` | worker.py RQ enqueue | 改为 env 可配置 |
| 字体路径 | jobs.py/preview.py/font_utils.py (3处) | 增加环境探测 + fallback 链 |
| 前端 API 超时 | constants.ts 声明未使用 | apiFetch 强制使用 AbortController |
| 前端轮询不一致 | tracking(3s) vs JOB_POLL_INTERVAL_MS(2s) | 统一使用 constants.ts |
| Auth cookie/JWT TTL | 前端 cookie maxAge vs 后端 JWT expiry 各自硬编码 | 后端通过 API 下发 TTL 或共享常量 |

### 3. 前端可观测性

| 项 | 方案 |
|---|---|
| SSE 重连 | 使用 `SSE_RECONNECT_BASE_MS`，实现指数退避 |
| 模型下载轮询 | 使用 `MODEL_DOWNLOAD_POLL_INTERVAL_MS` |
| API 请求 | 所有 fetch 强制 AbortController 超时 |

### 4. 死代码清理

| 项 | 文件 | 方案 |
|---|---|---|
| Layout Assist 整段不可达 | worker.py:347 + 4个关联模块 | 删除或添加环境开关 |
| MinerU `hybrid_ocr` 废弃参数 | 多处 | 清理引用 |

## 不做的事

- 不重构 OCR 算法调参常量 (~60 个 in ai_client.py) — 这些是经验性视觉调优参数，配置化收益低
- 不拆分巨石函数 — 超出本轮范围
- 不添加前端 SSR/测试/骨架屏 — 性能优化而非功能开发

## 验收标准

1. 所有外部 HTTP 请求（AI API、MinerU、Baidu）有统一可配置的超时机制
2. `JOB_TIMEOUT`、`OCR_PAGE_TIMEOUT_S` 等关键超时通过环境变量可配置
3. 前端 `apiFetch` 强制使用 AbortController 超时，不再有挂死等待
4. SSE 重连实现指数退避（1s → 2s → 4s → 8s → max 30s）
5. 前端所有轮询统一使用 `constants.ts` 中的常量
6. 字体路径支持环境探测 + 多级 fallback
7. Layout Assist 死代码清理完成
8. lint + typecheck 通过
