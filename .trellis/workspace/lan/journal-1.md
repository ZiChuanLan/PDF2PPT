# Journal - lan (Part 1)

> AI development session journal
> Started: 2026-05-01

---



## Session 1: 传统OCR选择器UI重构为卡片列表

**Date**: 2026-05-06
**Task**: 传统OCR选择器UI重构为卡片列表
**Branch**: `main`

### Summary

将传统OCR提供方(PaddleOCR/Tesseract)选择器从Select下拉框重构为卡片列表UI，参照版面切块模型样式。PaddleOCR卡片集成下载按钮，Tesseract显示就绪状态。同时清理后端硬编码魔法数字和前端硬编码颜色。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `281fbd3` | (see git log) |
| `312dcb3` | (see git log) |
| `e182930` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 2: 全流程架构审查与优化：AIOCR链路、硬编码消除、前端超时修复

**Date**: 2026-05-09
**Task**: 全流程架构审查与优化：AIOCR链路、硬编码消除、前端超时修复
**Branch**: `main`

### Summary

全代码库审查 + 13文件优化。后端：Job超时/OCR AI并发/JWT过期可配置化，新建共享字体发现工具。前端：apiFetch强制超时、SSE指数退避、轮询常量统一。Check agent修复2个关键bug（settings未赋值、导入路径错误）。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1c4cf11` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 3: 运行时配置API + 前端设置区域 + 模型下载管理

**Date**: 2026-05-10
**Task**: 运行时配置API + 前端设置区域 + 模型下载管理
**Branch**: `main`

### Summary

两个任务: (1) AIOCR链路优化 — Job超时可配、字体跨平台、前端超时/SSE退避/轮询统一; (2) 环境变量前端可配置化 — runtime config API(13字段)、前端运行时配置区域、模型下载持久化+删除、Layout Assist死代码清理。最后补充回答了28个刻意省略env var的分类明细。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `1c4cf11` | (see git log) |
| `7fe8cf0` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 4: Redis双轨修复 + AIOCR常量外部化 + PPTX生成器拆分 + 前端SSE钩子提取

**Date**: 2026-05-10
**Task**: Redis双轨修复 + AIOCR常量外部化 + PPTX生成器拆分 + 前端SSE钩子提取
**Branch**: `main`

### Summary

6个阶段: (1) InMemoryRedis.pipeline() Bug修复—内存模式限流失效; (2) ~40个P0/P1 AIOCR常量外部化到config.py,消除max_side_px三处重复定义; (3) pptx/generator.py(2221L)拆分为generator/包6文件; (4) 运行时配置API扩展+7字段(默认并发度+OCR保护参数); (5) JobRunner统一调度(_submit_job消除~84行重复分支); (6) page.tsx前端SSE逻辑提取为useSSEJobTracking钩子(~130行) + FileJobState类型共享。所有验证通过: compileall/tsc/lint清洁。

### Main Changes

(Add details)

### Git Commits

| Hash | Message |
|------|---------|
| `36ffaa4` | (see git log) |
| `bb16d52` | (see git log) |
| `a9c5a28` | (see git log) |

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
