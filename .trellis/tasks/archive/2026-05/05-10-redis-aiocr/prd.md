# PRD: 深入重构优化 — Bug 修复 + AIOCR参数外部化 + PPTX生成器拆分

## Goal

修复一处真实 Bug（内存模式限流失效），将 AIOCR 管线中 ~40 个 P0/P1 级硬编码常量外部化到 config.py，并将 `generator.py` (2221 行) 拆分为 7 个职责清晰的子模块。

## Research Base

- [01-dual-redis-backend.md](research/01-dual-redis-backend.md) — 4 处 is_memory_backend() 调用点, InMemoryRedis 缺 pipeline()
- [02-pptx-generator-split.md](research/02-pptx-generator-split.md) — 13 辅助函数 + 主函数双分支, 天然 DAG 结构
- [04-aiocr-constants-audit.md](research/04-aiocr-constants-audit.md) — ~200+ 常量仅 15% 外部化, 38 个 env-var 绕过 Settings

## Requirements

### Phase 1: Bug 修复 — InMemoryRedis.pipeline() (P0)

- `_InMemoryRedis` 添加 `pipeline()` 方法实现，确保 `check_rate_limit()` 在内存模式下正常工作
- 修复后 `redis_service.py:461` 的 `except Exception` 不再静默吞掉限流错误

### Phase 2: AIOCR 常量外部化 (P0+P1)

将以下 ~20 个最高优先级常量提升到 `config.py` Settings：

**P0 (影响行为的):**
- `OCR_AI_REQUEST_TIMEOUT_S` (25.0) — AIOCR 请求超时
- `OCR_PADDLE_VL_DOCPARSER_MAX_SIDE_PX` (2200) — 消除 3 文件重复定义
- `OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S` (120.0)
- `OCR_AI_LAYOUT_MODEL_PREDICT_TIMEOUT_S` (45.0)
- `OCR_AI_LAYOUT_BLOCK_REQUEST_TIMEOUT_S` (40.0)
- AiOcrTextRefiner 的 `timeout_s=60.0` 硬编码

**P1 (消除跨文件重复):**
- ~38 个 `os.getenv()` 调用统一迁移到 pydantic Settings（含类型验证+默认值）
- 合并跨文件的重复常量（max_side_px、置信度、重复阈值等）

### Phase 3: pptx/generator.py 拆分为子模块

```
convert/pptx/generator/     (新建包)
├── __init__.py             -> 重新导出 generate_pptx_from_ir
├── main.py                 (~170 LOC) 入口+前处理+验证
├── scanned_pipeline.py     (~780 LOC) 扫描页渲染管线
├── text_pipeline.py        (~570 LOC) 文本页渲染管线
├── footer.py               (~280 LOC) NotebookLM 尾注检测
├── text_erase.py           (~130 LOC) 文字擦除合并
├── markdown_utils.py       (~40 LOC)  Markdown 剥离
└── probing.py              (~170 LOC) 视觉换行/颜色采样探测
```

- 零行为变更，纯结构调整
- 更新 `tests/test_generator_perf_guards.py` 的导入路径
- 保持 `pptx_generator.py` 兼容 shim 有效

## Acceptance Criteria

- [ ] `check_rate_limit()` 在 `REDIS_URL=memory://` 模式下正常工作
- [ ] 新增 Settings 字段均有对应 env var（含默认值+类型+描述）
- [ ] 38 个 `os.getenv()` 调用迁移完毕，类型安全
- [ ] `_PADDLE_DOC_VLM_BASE_MAX_SIDE_PX` 等重复常量统一为 config.py 单一来源
- [ ] `AiOcrTextRefiner._chat_completion` 的 timeout 可配
- [ ] `generator.py` 拆为 7 个文件，导入路径全部更新
- [ ] 现有测试全部通过（含路径更新后的 test_generator_perf_guards）
- [ ] Python compileall 通过
- [ ] TypeScript typecheck 通过（前端无变更，仅验证）

## Definition of Done

- Tests: 更新导入路径后的已有的 + 新增限流 bug 的回归测试
- Lint / typecheck / compileall 绿色
- PRD 更新为最终状态

## Out of Scope

- Redis 双轨统一（JobRunner 抽象）— 保留为后续任务
- 前端巨型组件拆分 — 保留为后续任务
- `scanned_page.py` (3971 LOC) 拆分 — 保留为后续任务
- Layout Assist 功能启用 — 保留为后续任务

## Technical Notes

- InMemoryRedis pipeline() 实现参考 real redis pipeline: 返回一个 mock 对象支持 `.incr()` `.ttl()` `.execute()` 链式调用
- 常量外部化注意不能破坏 worker.py 中已有的 `_resolve_ocr_ai_concurrency_defaults()` 调用链
- generator 拆分的核心约束：`__init__.py` 必须白名单导出，`pptx_generator.py` shim 路径必须保持
