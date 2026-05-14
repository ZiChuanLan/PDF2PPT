# 梳理架构链路并清理命名与失败任务

## Goal

系统梳理当前项目的前后端架构、任务链路、配置模型与命名体系，找出导致“名称混在一起、链路难理解、任务持续失败”的核心原因，并在此基础上规划并执行一轮有边界的清理、修复与结构优化。

## What I already know

* 项目主链路已经有一版文档：`docs/guide/architecture.md`
  - Browser/Next.js Web → FastAPI API → Redis/RQ Queue → Worker → OCR/Parser Providers → 产出 `output.pptx`
  - 另有 `ppt-mcp` 作为 API 包装层
* 代码级主链路已定位：
  - `web/src/app/page.tsx` → `useJobSubmission` → `apiFetch("/jobs/v2")`
  - → `create_job_v2()` → `_create_job_core()` → `_submit_job()`
  - → `app.worker.process_pdf_job()`
  - → parse / OCR / layout_assist / ppt 四阶段执行
* Worker 中间产物链路已明确：
  - 依次落盘 `ir.parsed.json` → `ir.ocr.json` → `ir.ai.json` → `ir.json`
  - 说明当前系统已经天然具备“按阶段梳理职责”的基础
* 后端入口与路由集中在：`api/app/main.py`
  - 关键路由包括 `jobs_router`、`models_router`、`config_router`、`runtime_config_router`、`setup_router`
* Job 创建与排队逻辑位于：`api/app/routers/_job_create_utils.py`
  - 包含磁盘空间检查、quota 检查、queued 状态写入
* Worker 主处理链路位于：`api/app/worker.py`
  - OCR stage 与 layout assist stage 明确分阶段执行
* 敏感信息传递与任务执行被拆成两段：
  - API keys 不直接塞在 RQ job kwargs 里
  - secrets 独立存 Redis，worker 再拉取并清理
* OCR 相关命名和职责当前分散在多个模块：
  - `api/app/job_options.py`
  - `api/app/worker_helpers/ocr_runtime.py`
  - `api/app/convert/ocr/__init__.py`
  - `api/app/convert/ocr/ai_client.py`
  - `api/app/convert/ocr/_ocr_manager.py`
  - `api/app/convert/ocr/_ocr_remote.py`
  - `api/app/convert/ocr/_ai_layout_block.py`
* 当前已有多个相关活跃任务，说明这次任务需要特别注意边界与整合：
  - `05-13-refactor-settings-page-by-backend-flow/`
  - `05-13-home-model-sync/`
  - `05-13-comprehensive-audit/`
  - `05-13-fix-all-logic/`
  - `05-13-settings-logic-audit/`
* 已发现活跃任务之间存在边界问题：
  - `settings-logic-audit` 与 `fix-all-logic` 存在研究/实施顺序倒挂
  - `layout assist dead code` 被放进 UI 修复任务标题里，但根因实际在后端
* 现有设置页 PRD 已经暴露出一类问题：后端存在 `parse_engine_mode` / `ocr_provider` / `ai_ocr_chain_mode` / `layout_assist` 等概念，但前端展示与用户术语映射不稳定，容易造成理解混乱。
* 已发现至少两个高优先级架构/命名问题：
  - `schemas/job_config.py` 中 `enable_layout_assist` / `layout_assist_apply_image_regions` 在下传 worker 参数时被硬编码为 `False`
  - 首页阶段码使用 `generating`，但后端 JobStage 使用 `pptx_generating`，前后端状态名漂移

## Research References

* [`research/architecture-flow-map.md`](research/architecture-flow-map.md) — 代码级前端→API→队列→worker→OCR/PPT 全链路地图
* [`research/active-task-boundaries.md`](research/active-task-boundaries.md) — 当前 active tasks 的边界、重叠和治理建议
* [`research/naming-contract-map.md`](research/naming-contract-map.md) — 前后端命名/契约映射、错位点与首轮对齐目标

## Assumptions (temporary)

* 这不是“一次性重写整个项目”，而是先完成架构澄清、概念统一与关键故障修复。
* 本任务可能需要拆成“总控治理 + 若干实现批次”，避免与现有 active tasks 完全重叠。
* “任务全部失败”可能同时包含：
  - Trellis 任务边界混乱/重复
  - 前后端配置概念不一致
  - 某些实际代码路径存在缺失、死代码或命名漂移

## Open Questions

* 当前 Phase 1 已无阻塞问题，需求已收敛，可以进入实现。

## Requirements (evolving)

* 本任务采用“治理 + 直接修关键问题”的主策略：
  - 一边梳理架构、链路、命名体系
  - 一边修复最高优先级的真实链路故障与命名漂移
* 首轮 MVP 范围确定为：
  - 修复后端真实链路故障
  - 对齐前端状态名、配置名、流程名与后端实际契约
  - 暂不把 active tasks 治理动作纳入首轮实施范围
* 首轮命名清理采用“中等力度”策略：
  - 统一内部代码映射
  - 对齐前端展示术语与状态名
  - 不在首轮直接 rename schema/API 字段
* 梳理项目端到端链路：前端入口、API、Job 创建、队列、Worker、OCR/Layout、导出。
* 盘点核心领域概念与命名：parse engine、OCR provider、AI OCR chain、layout assist、models/runtime config 等。
* 找出重复、冲突或语义不清的命名与变量组织方式。
* 理清当前活跃任务之间的边界、重叠和依赖关系。
* 形成一套后续可执行的清理/修复计划，并开始处理优先级最高的问题。
* 首轮优先处理的问题类型包括：
  - worker 真实执行链路被错误配置或硬编码覆盖的问题
  - 前后端 job stage / flow stage 命名不一致的问题
  - 首页、设置页、运行配置之间对同一概念使用不同名称的问题

## Decision (ADR-lite)

**Context**: 当前问题不是单一 bug，而是“架构可读性差 + 命名漂移 + 任务边界冲突 + 真实链路故障”叠加。只做文档治理会继续拖住修复，只做救火又会把混乱继续固化。

**Decision**: 采用“治理 + 直接修关键问题”的双轨策略。
- 轨道 1：建立架构图、链路图、命名词典、任务边界
- 轨道 2：直接修复已确认的高优先级故障与前后端命名漂移

**MVP Scope Choice**: 采用“后端链路故障 + 前端状态/配置命名对齐”。
- 包含：后端真实链路修复、前端状态/配置/流程命名对齐
- 不包含：active tasks 的合并/归档/治理执行

**Naming Cleanup Intensity**: 采用“中等力度”。
- 包含：内部映射统一、前端展示术语/状态名对齐
- 不包含：schema/API 字段级大范围 rename

**Consequences**:
- 优点：能同时止血和降复杂度
- 风险：如果范围不收敛，容易演变成全仓库重构
- 控制措施：只处理首轮优先级最高的一批问题，其他问题拆到后续任务

## Technical Approach

1. **修复后端真实链路故障**
   - 检查 `api/app/schemas/job_config.py` 中 `JobConfig.to_worker_kwargs()`
   - 让 `enable_layout_assist` 与 `layout_assist_apply_image_regions` 正确透传到 worker kwargs
   - 保持 v2 JSON 接口与现有 schema 兼容，不做破坏性字段改名

2. **对齐前端任务阶段命名**
   - 对齐首页步骤状态与 `web/src/lib/job-status.ts` 中的 `JOB_STAGE_*` 常量/契约
   - 优先复用现有 stage flow 映射，减少 `page.tsx` 内部重复定义
   - 目标是让 `generating` / `pptx_generating` 这类漂移收敛成单一来源

3. **对齐配置命名桥接**
   - 梳理 `settings` → `run-config` → `JobConfig` → `worker kwargs` 的同义概念
   - 在不改 API 字段的前提下，统一前端内部命名和展示术语
   - 对存在历史别名/桥接层的地方优先补注释、集中映射或复用已有 helper

4. **验证方式**
   - 后端：优先补/改现有单测，覆盖 `to_worker_kwargs()` 与链路相关逻辑
   - 前端：保持 TypeScript 类型一致，必要时补局部测试或最小化逻辑验证
   - 全局：运行 lint / typecheck / 相关测试

## Implementation Plan

* 批次 1：修复 v2 `JobConfig` → worker kwargs 的 layout assist 透传故障
* 批次 2：统一首页任务阶段名与共享 stage flow/label 契约
* 批次 3：清理首轮配置命名桥接中的重复/漂移点，并补验证

## Acceptance Criteria (evolving)

* [ ] 有一份明确的架构/链路说明，覆盖前端到 worker 主流程
* [ ] 有一份命名/概念清单，指出冲突、重复和建议统一方式
* [ ] 有一份 active tasks 边界分析，说明哪些内容应合并、继承或避免重复
* [ ] 至少识别并排序一批最高优先级的实际修复项
* [ ] 后续实施范围被明确收敛，避免“无限大扫除”
* [ ] 首轮后端链路故障已修复且不再被硬编码/错误映射覆盖
* [ ] 首页任务阶段展示与后端 JobStage 契约一致
* [ ] 首页/设置页/提交配置对同一能力使用一致命名或有明确统一映射
* [ ] 不引入 schema/API 破坏性字段 rename

## Definition of Done (team quality bar)

* PRD 明确、边界清晰
* 研究结果落盘到 `research/`
* `implement.jsonl` / `check.jsonl` 具备可执行上下文
* 后续实现阶段的修改可被 lint / typecheck / tests 验证
* 如有新规律，会在 spec 中沉淀

## Out of Scope (explicit)

* 不在本轮直接重写整套 OCR/Worker 架构
* 不把所有历史任务一次性归零重做
* 不在需求未收敛前直接做全仓库大面积 rename
* 不在首轮 MVP 中执行 active tasks 的实际归档/合并动作
* 不在首轮执行 schema/API 字段级破坏性重命名

## Technical Notes

* 架构文档：`docs/guide/architecture.md`
* 研究沉淀：
  - `research/architecture-flow-map.md`
  - `research/active-task-boundaries.md`
* API 入口：`api/app/main.py`
* Job 创建：`api/app/routers/_job_create_utils.py`
* Worker 主流程：`api/app/worker.py`
* OCR 配置与 runtime：`api/app/job_options.py`, `api/app/worker_helpers/ocr_runtime.py`
* OCR 模块聚合与导出：`api/app/convert/ocr/__init__.py`
* 现有相关任务：
  - `.trellis/tasks/05-13-refactor-settings-page-by-backend-flow/`
  - `.trellis/tasks/05-13-home-model-sync/`
  - `.trellis/tasks/05-13-comprehensive-audit/`
  - `.trellis/tasks/05-13-fix-all-logic/`
  - `.trellis/tasks/05-13-settings-logic-audit/`
