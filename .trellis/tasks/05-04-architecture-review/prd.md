# 全面审查链路架构并优化

## Goal

对 pdf2ppt 的完整处理链路进行系统性审查，找出每一步的潜在问题、性能瓶颈和 bug，并提出优化方案。

## Architecture Overview

```
前端 (Next.js) → API (FastAPI) → Worker (RQ+Redis) → Redis
                      ↓
            5阶段处理流水线:
            解析 → OCR → 版式辅助 → PPTX生成 → 打包清理
```

## What I already know

- 项目是 PDF 转 PPT 的转换工具
- 架构包含：前端 (Next.js) → API (FastAPI) → Worker (RQ+Redis) → Redis
- 处理链路：上传 → 解析 → OCR → 版式辅助 → PPTX 生成 → 打包
- OCR 支持多种 provider：PaddleOCR、Tesseract、AIOCR、百度文档解析、MinerU
- 有本地和远程两种处理模式

## Research References

- [`research/frontend-upload-flow.md`](research/frontend-upload-flow.md) — 前端上传和任务跟踪流程分析
- [`research/api-endpoints.md`](research/api-endpoints.md) — API 层架构和安全分析
- [`research/worker-pipeline.md`](research/worker-pipeline.md) — Worker 处理流水线分析
- [`research/ocr-providers.md`](research/ocr-providers.md) — OCR Provider 集成分析
- [`research/file-storage-cleanup.md`](research/file-storage-cleanup.md) — 文件存储和清理机制分析

---

## Findings Summary

### 🔴 Bug / 高优先级问题

#### F1: Quota 字段未生效
- **位置**: `api/app/routers/jobs.py`
- **问题**: `daily_task_limit` 和 `concurrent_task_limit` 在 User 模型中存在，但 `create_job` 端点未检查
- **影响**: 用户配额限制形同虚设

#### F2: 配额字段未检查
- **位置**: `api/app/routers/jobs.py:create_job`
- **问题**: 用户的 `daily_task_limit` 和 `concurrent_task_limit` 字段存在但未被使用
- **影响**: 用户可以无限制创建任务

#### F3: API Key 泄露风险
- **位置**: `api/app/routers/jobs.py:create_job`
- **问题**: `api_key` 参数传递到 worker kwargs 中，虽然 RQ description 已清理但 kwargs 字典仍包含
- **影响**: Redis 中可能存储敏感信息

#### F4: Cleanup Daemon 竞态条件
- **位置**: `api/app/services/job_cleanup.py:96-100`
- **问题**: 如果 worker 挂起 24h 无心跳，cleanup daemon 可能基于 `st_mtime` 删除仍在处理的目录
- **影响**: 数据丢失风险（低概率但存在）

#### F5: 内存中读取整个文件
- **位置**: `api/app/routers/jobs.py:991` — `await file.read()`
- **问题**: 大文件（最大 100MB）完全加载到内存，并发上传时内存压力大
- **影响**: 高并发场景下可能导致 OOM

### 🟡 中优先级问题

#### M1: 轮询效率低下
- **位置**: `web/src/app/page.tsx:437-465`
- **问题**: 每个活跃任务每 2 秒轮询一次，N 个任务 = 每 2 秒 N 个请求
- **建议**: 使用后端已有的 SSE 端点 (`/jobs/{id}/events`)

#### M2: 无上传进度指示
- **位置**: 前端上传流程
- **问题**: 没有 chunked upload 或 XHR progress 事件
- **建议**: 添加上传进度条

#### M3: Poll 错误静默吞没
- **位置**: `web/src/app/page.tsx:455-457`
- **问题**: 轮询错误被空 catch 吞没，用户无反馈
- **建议**: 添加错误状态显示和重试机制

#### M4: 无 Rate Limiting
- **位置**: 所有 API 端点
- **问题**: 没有请求频率限制
- **建议**: 添加 rate limiter middleware

#### M5: 无磁盘空间监控
- **位置**: 全局
- **问题**: 没有磁盘空间检查，磁盘满时会直接 crash
- **建议**: 添加磁盘空间预检查

#### M6: Paddle 模型缓存无清理
- **位置**: Docker volumes (`paddlex-cache`, `paddle-cache`)
- **问题**: 模型缓存无限增长，无清理机制
- **建议**: 添加缓存大小限制或定期清理

#### M7: 前端未使用 SSE 端点
- **位置**: `web/src/app/page.tsx`
- **问题**: 后端有 `/jobs/{id}/events` SSE 端点，但前端仍用轮询
- **建议**: 迁移到 SSE 实时推送

#### M8: `.env` 文件直接写入
- **位置**: `api/app/routers/admin.py:PUT /admin/env`
- **问题**: 直接写入 `.env` 文件，无备份机制
- **建议**: 添加备份和回滚机制

### 🟢 低优先级 / 优化建议

#### L1: 下载全串行
- **位置**: `web/src/app/page.tsx:402-412`
- **问题**: `handleDownloadAll` 串行下载，不并行
- **建议**: 使用 `Promise.all` 并行下载

#### L2: `ir.parsed.json` 未清理
- **位置**: `api/app/worker.py:623`
- **问题**: 中间 IR 文件在 TTL 过期前一直占用磁盘
- **建议**: 在 cleanup 阶段删除

#### L3: Layout Assist 阶段已禁用
- **位置**: `api/app/worker_helpers/layout_assist_stage.py:242`
- **问题**: `enable_layout_assist = False` 强制禁用
- **影响**: 该阶段代码存在但不执行

#### L4: 无 metrics/observability
- **位置**: 全局
- **问题**: 没有 Prometheus metrics、distributed tracing
- **建议**: 添加基础 metrics（可选）

#### L5: Worker 无显式内存限制
- **位置**: `api/app/worker.py`
- **问题**: 没有内存使用限制，并行 OCR 可能消耗大量内存
- **建议**: 添加内存监控和限制

#### L6: OCR Provider 链路复杂度
- **位置**: `api/app/convert/ocr/`
- **问题**: 多 provider + fallback + strict/best-effort 模式 + AI disable 逻辑，状态管理复杂
- **建议**: 考虑简化配置，添加更好的文档

---

## Bug Fixes (要修复的)

### Fix 1: Quota 检查未生效
**文件**: `api/app/routers/jobs.py`
**修复**: 在 `create_job` 中添加 `daily_task_limit` 和 `concurrent_task_limit` 检查

### Fix 2: API Key 泄露
**文件**: `api/app/routers/jobs.py`
**修复**: 从 worker kwargs 中移除 `api_key`，通过安全渠道传递

### Fix 3: Poll 错误静默吞没
**文件**: `web/src/app/page.tsx`
**修复**: 添加错误状态显示，不是静默忽略

### Fix 4: 内存中读取大文件
**文件**: `api/app/routers/jobs.py`
**修复**: 使用流式写入替代 `await file.read()`

### Fix 5: `.env` 写入无备份
**文件**: `api/app/routers/admin.py`
**修复**: 写入前创建备份

---

## Requirements

- [ ] 审查并修复发现的 Bug
- [ ] 实现配额检查
- [ ] 修复 API Key 泄露问题
- [ ] 添加流式文件上传
- [ ] 优化前端轮询机制（迁移到 SSE）
- [ ] 添加 rate limiting
- [ ] 添加磁盘空间监控
- [ ] 添加 `.env` 写入备份

## Acceptance Criteria

- [ ] 所有 Bug 修复通过测试
- [ ] 配额检查生效
- [ ] API Key 不再泄露
- [ ] 大文件上传不导致 OOM
- [ ] 前端使用 SSE 实时更新
- [ ] Rate limiter 防止滥用
- [ ] 磁盘空间不足时有警告
- [ ] `.env` 写入前自动备份

## Definition of Done

- 所有 Bug 修复已提交
- 配额检查已实现
- 前端迁移到 SSE
- Rate limiter 已添加
- 代码通过 lint 和 typecheck
- 文档已更新

## Subtasks

| 子任务 | 描述 | 状态 |
|--------|------|------|
| [05-05-api-bugfixes](../05-05-api-bugfixes/prd.md) | API 层高优先级 Bug 修复 | pending |
| [05-05-frontend-sse-migration](../05-05-frontend-sse-migration/prd.md) | 前端 SSE 迁移和错误处理优化 | pending |
| [05-05-rate-limit-disk-monitor](../05-05-rate-limit-disk-monitor/prd.md) | Rate Limiting 和磁盘监控 | pending |
| [05-05-storage-cache-cleanup](../05-05-storage-cache-cleanup/prd.md) | 文件存储优化和缓存清理 | pending |

## Out of Scope

- 重大架构重构
- 新功能开发（如新的 OCR provider）
- 性能基准测试
- Prometheus/Grafana 集成

## Technical Notes

- 项目路径：/home/lan/workspace/pdf2ppt
- 前端：web/src/
- API：api/app/
- Worker：api/app/worker.py
- 任务目录：.trellis/tasks/05-04-architecture-review/
