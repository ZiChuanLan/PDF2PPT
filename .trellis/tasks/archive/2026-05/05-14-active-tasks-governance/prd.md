# 治理 active tasks 边界与收口

## Goal

系统梳理当前仍处于 `planning` / `in_progress` 的 Trellis 任务，并基于任务产物与 git 历史判断哪些任务其实已经完成、只是没有归档；在此基础上执行一轮有边界的任务治理收口，优先把已经落地到 `main` 的 stale tasks 批量归档，降低后续会话和工作流判断噪音。

## What I already know

* 当前仍挂着的 active tasks 有：
  - `05-13-comprehensive-audit`（in_progress）
  - `05-13-fix-all-logic`（in_progress）
  - `05-13-refactor-settings-page-by-backend-flow`（in_progress）
  - `05-13-settings-logic-audit`（planning）
  - `05-14-home-model-sync`（in_progress）
  - 当前任务 `05-14-active-tasks-governance`（planning）
* 上一轮已归档任务 `05-14-architecture-flow-naming-cleanup` 中有一份历史边界研究：
  - `.trellis/tasks/archive/2026-05/05-14-architecture-flow-naming-cleanup/research/active-task-boundaries.md`
  - 该研究当时判断重点是 broken chain / 边界倒挂，但现在已经被新 research 部分覆盖。
* 当前任务下的新 research 已经完成两份：
  - `research/active-task-inventory.md`
  - `research/active-task-disposition-plan.md`
* 新 research 的核心结论已经变化：
  - 旧判断里最严重的 `settings-logic-audit ↔ fix-all-logic` 依赖倒挂，在“任务元数据层”仍然存在，但在“代码结果层”已经失效，因为相关修复已经进了 `main`。
  - 5 个兄弟任务 A/B/C/D/E 基本都已有明确的完成信号，当前主要问题不是“还没做”，而是“已经做完但没归档”。
* per-task 当前强信号：
  - `05-13-comprehensive-audit`：有 PRD / curated jsonl / 3 份 research，发现已被 commit `c8b283d` 消化。
  - `05-13-fix-all-logic`：没有 PRD，但 commit `7a7b950` 与 `7748f15` 已高度对应任务标题；`9481c8d` 还补上了相关 backend fix。
  - `05-13-settings-logic-audit`：无 PRD、seed jsonl，但 3 份 research 已被 `fix-all-logic` 消化。
  - `05-13-refactor-settings-page-by-backend-flow`：PRD / curated jsonl / `implementation-summary.md` 完整，表现为已完成但未归档。
  - `05-14-home-model-sync`：PRD 清晰，虽然 jsonl 仍 seed-only，但多条 commit (`3b00ea2`, `69726b8`, `0365bed` 等) 已覆盖目标。
* 用户已选择本轮治理力度为 **option 3 / 扩展治理**：
  - 先批量归档 5 个 stale sibling tasks
  - 再核验 2 个低优先级残留（`capability` 参数覆盖、3 个 orphaned settings components）
  - 若证据充分，再处理必要的标题/边界/轻量死代码清理
* 当前仍存在两个低优先级残留点：
  - `comprehensive-audit` 中提到的 `capability` 参数缺口是否已被后续提交完全覆盖。
  - `refactor-settings-page-by-backend-flow` 中 3 个旧设置组件仍在磁盘上，但 research 显示它们无 imports、属低风险孤儿文件。

## Research References

* [`research/active-task-inventory.md`](research/active-task-inventory.md) — 当前 6 个 active tasks 的完整清单、完成信号与建议处置
* [`research/active-task-disposition-plan.md`](research/active-task-disposition-plan.md) — 建议的治理策略、任务到 commit 的映射与批量归档执行顺序
* [`../archive/2026-05/05-14-architecture-flow-naming-cleanup/research/active-task-boundaries.md`](../archive/2026-05/05-14-architecture-flow-naming-cleanup/research/active-task-boundaries.md) — 历史边界分析；提供当时的 broken-chain 背景

## Assumptions (temporary)

* 本任务优先解决的是“active task 列表失真”，不是继续推进产品代码开发。
* 当前更高概率的正确动作不是“补救旧任务流程”，而是接受代码已落地这一事实，按证据做批量归档。
* 若扩大范围去补旧 PRD / 补旧 jsonl / 追求历史流程完美，收益很低，且会重新制造治理噪音。
* 当前用户已经明确要求把低优先级残留核验纳入本轮 MVP；但仍应避免把任务扩大成无边界历史修复。

## Open Questions

* 当前已无阻塞性范围问题；本轮按 option 3 执行。

## Requirements (evolving)

* 基于任务产物和 git 历史，确认每个 active task 的真实状态：仍需继续，还是其实已完成只待归档。
* 为每个 active task 给出处置动作，并优先把“已完成但仍 active”的任务从工作流里清掉。
* 对历史 broken chain / scope mismatch 给出结论，但不为追求形式完备去重做已经完成的工作。
* 本轮 MVP 以“批量归档 stale tasks”为主，不扩展成产品功能继续开发。
* 核验 `comprehensive-audit` 中 `capability` 参数残留是否已被后续提交覆盖，并把结果纳入治理结论。
* 核验 `refactor-settings-page-by-backend-flow` 中 3 个旧设置组件是否确实无引用；若证据充分且影响低，可并入本轮轻量清理。
* 若需要调整旧任务标题/边界表述，应仅做最小必要治理，不重写历史实现过程。

## Acceptance Criteria (evolving)

* [ ] 有一份 active tasks 现状清单，能区分“真的未完成”与“已经完成但未归档”
* [ ] 每个 active task 都有基于证据的明确处置动作
* [ ] 5 个 stale sibling tasks 的归档范围和顺序被收敛成可执行计划
* [ ] 历史 broken chain 被重新定性为“历史背景”还是“当前仍需处理的问题”
* [ ] 本轮治理范围被明确限制，不演变成产品功能大修或历史流程补课
* [ ] `capability` 参数残留是否已覆盖有明确结论
* [ ] 3 个 orphaned settings components 是否删除有明确结论，并且若删除则有证据说明是安全的

## Definition of Done (team quality bar)

* PRD 清晰描述本轮治理目标和边界
* 相关研究沉淀到当前任务目录（如需要）
* 若进入执行阶段，implement/check context 已正确整理
* 所有任务级变更都能解释“为什么这样收口”，尤其是为什么选择直接归档而不是补旧流程
* 如发现新的 Trellis 规则或坑点，会沉淀到 spec

## Decision (ADR-lite)

**Context**: 历史边界分析曾把问题定义为 broken chain、缺 PRD、缺 jsonl、scope mismatch。但新的 inventory + disposition research 结合 git 历史显示：多数相关代码已提交到 `main`，active task 列表只是没有及时归档，导致工作流视图失真。

**Decision**: 将本任务的 MVP 从“修复任务链和 metadata 缺口”调整为“批量归档已完成的 stale tasks”，并纳入用户明确选择的两类扩展治理：低优先级残留核验，以及在证据充分时进行最小必要的轻量清理。

**Consequences**:
- 优点：最快恢复 active task 列表的可信度，减少后续 session 的 workflow 噪音。
- 代价：接受少数旧任务没有完美 PRD/jsonl 生命周期的历史事实，不再追求事后补票。
- 风险控制：若发现残留超出“轻量治理”边界，则新建 focused follow-up task，而不是把旧任务重新拉回执行态或在本任务里无限扩张。

## Technical Approach

1. 用 inventory/disposition research 作为本轮治理的主要事实来源。
2. 对 5 个 sibling tasks（A/B/C/D/E）逐个执行 archive，保留其 task 目录与 research 到 archive 区。
3. 不补写旧 PRD / 旧 jsonl；治理重点是基于现状证据做收口，而不是追补历史流程。
4. 对 `capability` 参数残留做轻量核验，确认是否已被后续提交覆盖。
5. 对 D 的 3 个旧孤儿设置组件做引用核验；若确实无引用且删除安全，可一并清理。
6. 若需要修正旧任务标题/边界认知，仅做最小必要修正，避免改写已完成任务的历史叙述。
7. 当前治理任务在 archive / 轻量治理动作完成后，再完成自己的收尾和归档。

## Implementation Plan

* 批次 1：整理 governance 任务的 implement/check context，并启动任务
* 批次 2：核验 `capability` 参数残留与 3 个 orphaned settings components
* 批次 3：视核验结果执行必要的轻量治理/清理
* 批次 4：批量归档 A/B/C/D/E 五个 stale tasks
* 批次 5：验证 active task 列表已收敛，再归档 governance 任务自身

## Out of Scope (explicit)

* 不在本任务里直接继续产品功能实现，除非它是任务治理动作的必要副作用
* 不为了追求流程完整性去给已完成旧任务补写完整 PRD / jsonl / 实施记录
* 不在本轮扩大成全仓库 dead-code 大扫除
* 不在本轮直接重构 Trellis 工作流脚本本身
* 不把所有历史研究重新做一遍

## Technical Notes

* 当前 record context：`python3 ./.trellis/scripts/get_context.py --mode record`
* 当前任务目录：`.trellis/tasks/05-14-active-tasks-governance/`
* 关键 research：
  - `research/active-task-inventory.md`
  - `research/active-task-disposition-plan.md`
  - `.trellis/tasks/archive/2026-05/05-14-architecture-flow-naming-cleanup/research/active-task-boundaries.md`
* 当前默认建议的处置集合：
  - archive `05-13-comprehensive-audit`
  - archive `05-13-fix-all-logic`
  - archive `05-13-settings-logic-audit`
  - archive `05-13-refactor-settings-page-by-backend-flow`
  - archive `05-14-home-model-sync`
* 当前已确认纳入的扩展治理残留：
  - 核验 `capability` 参数缺口是否已被后续提交覆盖
  - 是否顺手删除 D 的 3 个旧孤儿设置组件
