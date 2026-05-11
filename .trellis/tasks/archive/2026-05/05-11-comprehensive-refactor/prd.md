# 全面解析与优化：减少冗余、修复前后端链接、完善交互逻辑

## Goal

对 pdf2ppt 项目进行**全面解析和深度优化**。经过系统性审计（3 份研究报告），确认前后端 API 路径对齐无断裂，但存在代码冗余、静默错误吞没、巨型文件、路由冲突等问题。按优先级逐一修复。

## Research References

* [research/backend-api-audit.md](research/backend-api-audit.md) — 49 个端点全量目录，含路由冲突、废弃参数、SSE 无鉴权等
* [research/frontend-api-audit.md](research/frontend-api-audit.md) — 44 个 API 调用点审计，3 处静默吞错，3 处重复下载逻辑
* [research/frontend-interaction-audit.md](research/frontend-interaction-audit.md) — 9 页面 + 8 组件交互完整性，0 个 404，2 页有导航缺失

## Audit Summary

| 类别       | 严重度 | 计数      |
| ---------- | ------ | --------- |
| 代码冗余（巨型文件）   | 🔴     | 3 个      |
| 重复逻辑 / 静默错误   | 🟡     | 5 个      |
| 路由冲突 / 废弃参数   | 🟡     | 2 个      |
| SSE 无鉴权            | 🟠     | 1 个      |
| 导航缺失 / 移动端适配 | 🟢     | 4 个      |

## Requirements

### P0 — 消除代码冗余（先做）

* [x] 拆分 `web/src/app/page.tsx`（1545→610行）为多组件/多 hook
* [x] 拆分 `web/src/app/settings/page.tsx`（2961→2777行）为按功能模块的组件
* [x] 拆分 `api/app/convert/pptx/generator/main.py`（1664→1594行）为职责清晰的子模块

### P1 — 修复静默错误 + 重复逻辑 + 后端问题

* [x] 提取公共下载工具函数，消除 page/jobs/tracking 三处重复下载逻辑
* [x] `use-settings.ts` 的 `save()` 暴露/传播 API 错误到 UI
* [x] Admin 页拆分 stats 和 users 为独立错误状态
* [x] 合并 `models_router` 和 `model_status_router`（共享同一路由前缀）
* [x] 移除 `POST /api/v1/jobs` 的 4 个废弃表单字段

### P2 — 补充导航和交互

* [x] settings、tracking 页面加"返回首页"链接
* [x] 移动端双栏布局优化（preview-stage.tsx）
* [x] 移动端 settings 表单响应式修复
* [x] SSE endpoint 加鉴权（job owner check）

## Acceptance Criteria

* [x] Lint / typecheck 通过（tsc 0 error, lint 0 error, py_compile pass）
* [x] 三大巨型文件均已拆分为子模块
* [x] 下载逻辑只有一处公共实现（download-utils.ts）
* [x] `save()` 错误可被 UI 感知（throw + toast）
* [x] models 路由无前缀冲突（已合并为一个 router）
* [x] 废弃表单字段已移除
* [x] 核心流程（上传→配置→转换→下载）端到端通畅

## Definition of Done

* Lint / typecheck 通过
* 前后端 API 路径完全对齐（已验证）
* 无巨型单文件（>500行）
* 无重复代码逻辑（下载、错误处理）
* 所有页面有返回导航

## Decision (ADR-lite)

**Context**: 审计发现实际断裂问题极少（0 个 404，API 路径完全对齐），核心痛点是代码组织而非功能缺陷。
**Decision**: 优先拆巨型文件、消除重复 → 修复静默错误 → 补充交互细节。
**Consequences**: 风险低（不做功能变更），收益高（可维护性大幅提升）。

## Out of Scope

* 功能削减或新增（保持功能完整性）
* 测试覆盖（本次不涉及）
* 架构调整（不合并/拆分服务）
* 视觉设计变更
* 认证方式简化（保留 JWT + OAuth 双机制）

## Technical Notes

* 技术栈：FastAPI + Next.js 16 + Redis + SQLite + python-pptx + PyMuPDF
* 前端 spec 指南目录空壳，需要填充
* 所有 API 调用统一走 `/api/v1/` 代理，已验证一致
* SSE 事件类型前后端对齐，已验证
