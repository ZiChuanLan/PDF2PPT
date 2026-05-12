# Round 3 Refactor: remaining large files + quality gaps from Round 2 audit

## Goal

Round 2 完成了 P0-P1 级别的 4 个子任务（OCR/PPTX 巨型文件拆分、前端+路由收尾、质量债务），但 Round 2 研究审计发现 ~25 项遗漏。本轮处理剩余项，分优先级提取。

## What I already know

**背景**：Round 2 三份研究文件（`remaining-large-files.md`, `untouched-modules.md`, `quality-gaps.md`）覆盖了 40+ 文件、6 个质量维度。已完成项（4 个子任务）vs 未完成项（~25 项）。

**未完成项完整清单（按类别分组）**：

### A. 大文件拆解（P0-P1）

| # | 文件 | 行数 | 拆解目标 |
|---|------|------|---------|
| A1 | `worker.py` | 1178 | 58 参数反模式 → `JobOptions` dataclass；300 行归一化样板 → 独立模块 |
| A2 | `ocr_stage.py` | 1249 | 页面循环、并行 AI OCR、进度追踪 → 子模块 |
| A3 | `mineru_adapter.py` | 1967 | 扁平 41 个私有函数 → 按阶段分组 |
| A4 | `baidu_doc_adapter.py` | 1178 | 同 mineru 模式 → 提取共享基类或工具 |
| A5 | `font_utils.py` | 1038 | 文本测量/换行/字体适配 → 按功能域拆分 |

### B. 重复代码消除（P1）

| # | 内容 | 涉及文件 |
|---|------|---------|
| B1 | `_is_image_like_kind()` 完全相同的实现 | `mineru_adapter.py` line 725 / `baidu_doc_adapter.py` line 463 |
| B2 | `_normalize_bbox_px()` 两份相同拷贝 | `ocr/local_providers.py` / `ocr/result_parsing.py` |
| B3 | `_contains_cjk()` / `_is_cjk_char()` 自身重复 | `font_utils.py` 内 `_contains_cjk` 可直接调用 `_is_cjk_char` |

### C. 可访问性债务（P1-P2）

| # | 内容 |
|---|------|
| C1 | 全局图标按钮(`ArrowLeftIcon`, `DownloadIcon`, `TrashIcon`, `XIcon`, `CheckIcon` 等)无 `aria-label` |
| C2 | jobs 页面复选框无关联 `<label>` 或 `aria-label` |
| C3 | 上传 dropzone 无 `role` 或可访问描述 |
| C4 | 无 skip-to-content 链接 |
| C5 | PDF 预览无可访问替代文本 |

### D. 错误处理债务（P1-P2）

| # | 内容 | 位置 |
|---|------|------|
| D1 | `use-settings.ts` 3 处静默吞错（deploy-mode、settings load、auto-save） | `web/src/hooks/use-settings.ts` |
| D2 | `use-model-download.ts` 轮询错误静默吞 | `web/src/hooks/use-model-download.ts` |
| D3 | `use-sse-job-tracking.ts` 2 处静默 catch | `web/src/hooks/use-sse-job-tracking.ts` |
| D4 | `page.tsx` 轮询 `silent` 模式吞错 | `web/src/app/page.tsx` |
| D5 | `models.py:519` `logger.warning` + `exc_info=True` 不一致（应统一 `logger.exception()`） | `api/app/routers/models.py` |
| D6 | `jobs.py` cleanup 路径裸 `except Exception` 无日志 | `api/app/routers/jobs.py` |

### E. 文档/配置（P2）

| # | 内容 |
|---|------|
| E1 | `.trellis/spec/guides/` 目录为空 | ❌ 已解决 — Round 2 已填充 3 文件 278 行 |
| E2 | Makefile:120-121 "No repository tests" 声明过期（实际有 20 个测试文件） |
| E3 | `.env.example` COOKIE_SECURE=false vs `config.py` default=True 漂移（文档澄清） |
| E4 | `.env.example` JOB_ROOT_DIR=/app/data/jobs (Docker) vs `config.py` default=data/jobs (本地) 不一致 |

### F. 死代码/杂项（P3）

| # | 内容 |
|---|------|
| F1 | `pptx_generator.py` 12 行向后兼容 shim — 验证调用方后可删除 |
| F2 | 11 处条件 `import numpy as np` — 上移到模块顶部（numpy 已是强依赖） |
| F3 | 前端零测试覆盖（`web/package.json` test:unit 是 stub） |

### G. Round 2 自愿跳过项（P2-P3）

| # | 内容 | 原因 |
|---|------|------|
| G1 | `settings/page.tsx` OCR 区域提取 | ~20 useState 耦合太紧 |
| G2 | `jobs.py` 共享 `_create_job_core()` | v1/v2 参数模式不同 |
| G3 | `models.py` download 模块独立 | `_download_tasks` 模块级全局状态 |

## Assumptions (temporary)

* Round 3 可参考 Round 2 成功的拆分模式（mixin、re-export hub、子组件提取）
* A1 (worker.py) 是最高风险变更 — 涉及 RQ job 传递参数
* C 类（可访问性）量小但分散 — 适合批量处理
* D 类（错误处理）已在 Round 2 被部分修复 — 需核对哪些已完成

## Open Questions

* (none — scope confirmed)

## Requirements (confirmed)

### 第一组：大文件拆解 + 重复代码消除 (A+B)

* [ ] A1: worker.py 58 参数 → `JobOptions` dataclass + 300 行归一化独立
* [ ] A2: ocr_stage.py 1249 → 按页面循环/并行AI/进度追踪分子模块
* [ ] A3: mineru_adapter.py 1967 → 按阶段分组（提取/收集/构建/API）
* [ ] A4: baidu_doc_adapter.py 1178 → 同 mineru 模式，提取共享工具
* [ ] A5: font_utils.py 1038 → 按功能域拆分（测量/换行/适配/MinerU/OCR）
* [ ] B1: `_is_image_like_kind()` 去重 → 共享模块
* [ ] B2: `_normalize_bbox_px()` 去重 → 统一到 `ocr/utils.py`
* [ ] B3: `_contains_cjk()` 内部复用 `_is_cjk_char()`

### 第二组：可访问性 + 错误处理 + 文档 (C+D+E)

* [ ] C1-C5: 图标按钮 aria-label + 复选框 label + dropzone role + skip-to-content + PDF 替代文本
* [ ] D1-D6: hooks 静默吞错 + models/jobs logger 不一致 + cleanup 裸 except
* [ ] E2-E4: Makefile 修正 + 配置漂移文档澄清（E1 已由 Round 2 完成）

### 第三组：死代码/杂项 + Round 2 跳过项 (F+G)

* [ ] F1: 删除 `pptx_generator.py` 12 行 shim（验证调用方后）
* [ ] F2: 11 处条件 numpy import → 模块顶部
* [ ] F3: 修正 `web/package.json` test:unit stub（不再声称 "no tests"）
* [ ] G1: `settings/page.tsx` OCR 区域提取
* [ ] G2: `jobs.py` 共享 `_create_job_core()`
* [ ] G3: `models.py` download 模块独立

## Acceptance Criteria (evolving)

* [ ] Lint / typecheck / py_compile 全通过
* [ ] 拆分后的公共 API 向后兼容（import 路径不变）
* [ ] worker.py < 500 行（目标）
* [ ] 所有表单项有可访问标签（aria-label 或关联 label）

## Definition of Done (team quality bar)

* Lint / typecheck / CI green
* 拆分文件 py_compile 通过
* 功能不变（无行为变更）

## Out of Scope (explicit)

* 功能变更
* 架构重设计
* 测试编写（除非用户明确要求 F3）
* CI/CD 搭建

## Technical Notes

* Round 2 已创建 37 个新子模块，4 个子任务全部提交（commit `a57c5dd` + `29ae9f4`）
* Round 2 研究文件位于 `.trellis/tasks/archive/2026-05/05-11-comprehensive-refactor-round2/research/`
* worker.py 58 参数变更需修改 `jobs.py` 中 RQ enqueue 调用处
* mineru/baidu adapter 共享模式可提取 `_adapter_utils.py` 或抽象基类
