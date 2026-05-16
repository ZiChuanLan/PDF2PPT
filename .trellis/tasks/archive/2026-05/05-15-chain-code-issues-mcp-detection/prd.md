# 治理链路代码问题并用 MCP 检测

## Goal

系统梳理项目中的端到端链路代码，借助 MCP / 本地研究能力找出“链路型问题”——即跨模块、跨层、跨任务边界的断点、错配、遗失导入、配置透传缺失、状态映射漂移、生命周期收尾不一致等问题，并在本轮直接修复首批“已确认、仍然 live、爆炸半径小”的明确问题。

## What I already know

* 用户给出了一个真实失败样本：`ocr_failed ... cause=name 'Path' is not defined`
  - 本地代码扫描已确认高概率根因位于 `api/app/convert/ocr/_ai_layout_block.py`
  - 该文件使用了 `Path(...)`，但文件头当前没有 `from pathlib import Path`
  - 这说明它不是单纯“docker 没重建”，而是当前代码路径本身存在 live bug；如果代码修复后容器仍运行旧镜像，才需要重建/重启来吃到修复
* 用户已明确选择 **option 2**：
  - 先检测链路代码问题
  - 再直接修复首批清晰、低风险、当前仍 live 的问题
  - 不做本轮全面重构
* 端到端主链路本地 research 已落盘：
  - `research/end-to-end-chain-map.md`
  - 主链路为：`web/src/app/page.tsx` → `web/src/hooks/use-job-submission.ts` → `web/src/lib/run-config.ts` → `web/src/lib/api.ts` → `api/app/routers/jobs.py:create_job_v2()` → `_create_job_core()` → `_submit_job()` → `api/app/worker.py:process_pdf_job()`
  - worker 阶段顺序为：parsing → OCR → layout_assist → pptx_generating → packaging → cleanup
* 高风险热点 research 已落盘：
  - `research/high-risk-hotspots.md`
* 当前已确认的高风险区域包括：
  - OCR / AIOCR 模块：高密度可选导入、拆分重构后容易出现 `NameError` / 缺失常量 / 运行时依赖缺失
  - `JobConfig.to_worker_kwargs()`：50+ flat keys 手工拼装，透传遗漏风险高
  - 前后端 stage naming / progress mapping：目前大体对齐，但仍有 magic numbers 与压缩映射逻辑
  - model capability filtering：新模型族可能绕过现有 `ocr` 判定规则
  - task lifecycle / finish-work：git 历史与 task 元数据可能漂移
* 最近仓库里已经出现过若干 OCR 链路修复提交，说明这条链本身确实脆弱：
  - `7c85d6c fix(ocr): add missing adaptive coverage threshold constants lost in refactor`
  - `db14a15 fix(ocr): add missing _CONFIDENCE_BYPASS_* constants in _ai_layout_block.py`
  - `0b7d8dd fix: resolve circular import in OCR modules`
* 检索 MCP 当前返回 `401 Unauthorized`，所以本轮 planning 阶段已改为：
  - 继续用可用 MCP / 本地工具
  - 用 `trellis-research` 子代理把 code-chain 研究结果落到 task `research/` 下

## Research References

* [`research/end-to-end-chain-map.md`](research/end-to-end-chain-map.md) — 端到端主链路、阶段边界与高风险断点地图
* [`research/high-risk-hotspots.md`](research/high-risk-hotspots.md) — 已知高风险模块、为何危险、是否已在 main 上修复

## Assumptions (temporary)

* 这轮任务不是做“全仓库随意大扫除”，而是围绕链路问题建立可执行的检测与修复闭环。
* 用户既关心真实故障（如 `Path is not defined`），也关心“原项目里所有链路代码问题”，但本轮只直接修首批最明确的 live 问题。
* MCP 检测在这里既包括本地代码检索/分析工具，也包括可用的子代理 research；不依赖必须联网的 retrieval 服务。

## Open Questions

* 当前已无阻塞性范围问题；本轮按 **option 2 = 检测 + 首轮 live 修复** 执行。

## Requirements

* 盘点并说明端到端链路中的关键代码路径与边界。
* 用 MCP / 子代理 research 找出链路型问题热点，而不是只看单文件 lint 问题。
* 至少覆盖以下问题类型：
  - 运行时 `NameError` / 遗失导入 / 拆分后缺失符号
  - structured config → flat kwargs / worker options 透传丢失
  - 前后端 stage / status / flow 映射漂移
  - model capability filtering 漏传或错误过滤
  - task lifecycle / archive / finish-work 收尾链路问题
* 对每个热点给出：文件路径、涉及符号、风险原因、当前是否已修复。
* 本轮直接修复首批“当前仍 live 的真实链路故障”，优先级顺序为：
  1. `Path is not defined` 这类已确认现场故障
  2. 同一条 OCR / AIOCR 链路中其他一眼可证实的缺失导入 / 缺失符号 / 明显透传缺口
  3. 不扩大到推测性、需要大重构的风险项

## Acceptance Criteria

* [ ] 有一份清晰的端到端链路地图
* [ ] 有一份高风险链路问题清单，覆盖上述主要类别
* [ ] 每个热点都标明：位置 / 风险 / 当前状态（已修 / 未修 / 待确认）
* [ ] 已明确确认 `Path is not defined` 是否仍是 live 问题
* [ ] 已落实本轮范围为“检测 + 首轮修复”
* [ ] 至少一个当前 live、低风险、明确的链路故障被修复或被证明无需修复

## Definition of Done (team quality bar)

* 研究结果落盘到 `research/`
* PRD 范围清晰
* `implement.jsonl` / `check.jsonl` 已配置
* 首轮修复完成后，相关 lint / typecheck / targeted tests 已运行
* 如发现新规律，应评估是否写入 spec / guides

## Decision (ADR-lite)

**Context**: 用户既要“找原项目里所有链路代码问题”，又给出了一个当前正在爆的真实故障；如果只做报告，止血不够；如果直接全面修，范围会失控。

**Decision**: 本轮采用 **option 2：检测 + 首轮 live 修复**。
- 先基于 MCP / 本地 research 建立链路地图和热点清单
- 再直接修复首批低风险、证据充分、当前仍 live 的问题
- 更大的结构性热点（如大规模 kwargs 自动校验、阶段映射体系重构）只形成检测结论与后续建议，不在本轮重构

**Consequences**:
- 优点：既能止血，也能为后续系统治理留出清晰 backlog
- 风险：可能只修掉最明显的问题，仍留下更深层热点
- 控制措施：首轮修复后必须做 targeted verification，并把未修热点保留在研究/PRD 结论里

## Technical Approach

1. 以 `research/end-to-end-chain-map.md` 作为链路骨架，逐段检查 frontend → API → worker → OCR → layout → PPT 关键边界。
2. 以 `research/high-risk-hotspots.md` 作为优先级来源，优先检查 OCR/AIOCR 和 `to_worker_kwargs()` 这类高风险区域。
3. 首轮实施先处理已经有现场证据的 live fault：
   - `api/app/convert/ocr/_ai_layout_block.py` 缺失 `Path` 导入
4. 在修 live fault 的同时，顺手排查同类明显缺失符号 / 导入问题；仅处理低爆炸半径问题。
5. 对更大的风险项（例如跨 50+ key 的 kwargs 覆盖完整性）保留为本轮检测结论或后续任务，而不是无边界展开。

## Implementation Plan

* 阶段 1：启动任务并派发 implement，完成首轮链路检测与 live fault 修复
* 阶段 2：派发 check，复核 live fault 是否真正闭环，并确认是否还有同类明显缺失符号问题
* 阶段 3：收敛本轮结论，必要时沉淀 spec / guide，再按 Trellis 流程提交和 finish-work

## Out of Scope (explicit)

* 不在本轮直接做全仓库大面积重构
* 不把所有普通代码风格问题都算成“链路问题”
* 不依赖必须联网才能完成的外部 MCP 服务
* 不在没有明确现场证据时展开大规模推测性修复

## Technical Notes

* 当前真实报错样本：
  - `PastedJob ... ocr_failed ... cause=name 'Path' is not defined`
* 高概率现场文件：
  - `api/app/convert/ocr/_ai_layout_block.py`
* 相关主链路文件：
  - `web/src/app/page.tsx`
  - `web/src/hooks/use-job-submission.ts`
  - `web/src/lib/run-config.ts`
  - `web/src/lib/api.ts`
  - `api/app/routers/jobs.py`
  - `api/app/worker.py`
  - `api/app/worker_helpers/ocr_stage.py`
  - `api/app/worker_helpers/layout_assist_stage.py`
  - `api/app/worker_helpers/ppt_stage.py`
  - `api/app/routers/models.py`
  - `api/app/routers/_model_filtering.py`
