# 全面优化 Round 2：上轮遗漏项审视

## Goal

Round 1 完成了 P0 巨型文件拆分、P1 静默错误修复、P2 导航交互补充。但审计发现上轮**完全未触及的模块**中存在远比第一轮更大的文件（5581行、4320行、3971行），加上剩余的 settings/jobs/models 文件和质量债务。本轮分 4 个子任务逐一处理。

## What I already know

**上轮未触及的 CRITICAL 文件**：
* `api/app/convert/ocr/ai_client.py` — **5581 行**，项目最大文件，1 个巨类 ~100 方法
* `api/app/convert/ocr/local_providers.py` — **4320 行**，6 个类挤在一个文件
* `api/app/convert/pptx/scanned_page.py` — **3971 行**，单片函数 ~870 行
* `api/app/convert/ocr/` — 4 处重复代码（CJK、bbox 等）、4 个死别名
* `api/app/routers/jobs.py` — 1838 行，create_job/create_job_v2 重复 ~150 行
* `api/app/routers/models.py` — 1286 行，下载子系统 ~653 行可独立

**剩余的前端文件**：
* `web/src/app/settings/page.tsx` — 2787 行，OCR 区域 ~995 行
* `web/src/components/home/preview-stage.tsx` — 661 行，3 个可提取组件 ~386 行

**质量债务**：
* 10/13 页面缺 `<main>` 地标，11/13 缺 `<h1>`
* 7/8 前端 spec 文件为空白占位符
* 20% 前端 catch 块静默吞错
* 2 个弱默认密码（admin/password123）

## Research References

* [research/remaining-large-files.md](research/remaining-large-files.md) — 5 个未彻底拆分的文件详细测量，含具体拆解目标和行数
* [research/untouched-modules.md](research/untouched-modules.md) — 40+ 文件审计，6 项关键发现，4 处重复代码，死代码识别
* [research/quality-gaps.md](research/quality-gaps.md) — 6 维度质量审计：可访问性、错误处理、spec、配置漂移、安全、测试

## Requirements

### 子任务 1：拆分 OCR 后台巨型文件

* [ ] ai_client.py 拆分为：PaddleDoc 解析器 (~1500行)、布局块 OCR (~1000行)、AI chat pipeline (~1200行)、文本精炼器 (~995行)
* [ ] local_providers.py 拆分为：每 OCR provider 独立文件（Baidu ~193行、Tesseract ~325行、Paddle ~357行、OcrManager ~912行）、后处理链 (~700行)
* [ ] 上移 4 处重复工具函数到 `ocr/utils.py`（_contains_cjk、_is_cjk_char、_normalize_bbox_px）
* [ ] 删除 4 个死别名（SiliconFlowAiOcrAdapter 等）
* [ ] `ocr/__init__.py` 保持向后兼容 re-export

### 子任务 2：拆分 PPTX 生成器剩余部分

* [ ] scanned_page.py 拆分为多个子函数/模块
* [ ] main.py 扫描页分支 (~710行) → `generator/_scanned_page.py`
* [ ] main.py 文本页分支 (~560行) → `generator/_text_page.py`
* [ ] 嵌套闭包 → 模块级函数（_compute_text_coverage_ratio、_count_text_inside_bbox）

### 子任务 3：拆分前端 + 路由收尾

* [ ] settings/page.tsx：OCR 配置区域 (~995行) → `OcrConfigSection`
* [ ] settings/page.tsx：子区域（专用 OCR 参数 ~594行、提示词实验 ~128行、并发限流 ~158行）
* [ ] preview-stage.tsx：QuickConfigPanel (~230行)、PageRangeSection (~85行)、ActionButtons (~71行)
* [ ] jobs.py：提取共享 `_create_job_core()` 消除两个端点 ~150 行重复
* [ ] jobs.py：上传工具 (~116行) → `_upload_utils.py`、OCR 检查 (~243行) → `_ocr_check.py`
* [ ] models.py：模型过滤 (~218行) → `_model_filtering.py`、下载子系统 (~653行) → `_model_download.py`

### 子任务 4：质量债务修复

* [ ] 为 settings、setup、tracking、admin、register、manage 页面添加 `<main>` 地标
* [ ] 为缺 `<h1>` 的页面添加语义化标题
* [ ] 填充 7 个空白 spec 文件（基于已有研究内容）
* [ ] 统一前端 20% 静默吞错的 catch 块 → 至少 log 或 toast
* [ ] 修复 2 个弱默认密码（改为随机生成或强制修改）

## Acceptance Criteria

* [ ] Lint / typecheck / py_compile 全通过
* [ ] ai_client.py < 1000 行
* [ ] local_providers.py < 500 行
* [ ] scanned_page.py < 1000 行
* [ ] main.py < 500 行
* [ ] settings/page.tsx < 1000 行
* [ ] 所有拆分的 import 向后兼容（公共 API 不变）
* [ ] 所有页面有 `<main>` + `<h1>`
* [ ] spec 文件非空
* [ ] 无硬编码弱密码

## Decision (ADR-lite)

**Context**: Round 1 只覆盖了表层大文件，深层模块（OCR 引擎、PPTX 生成器、路由）的巨型文件从未被触及。
**Decision**: 按 4 个子任务分批处理：OCR → PPTX → 前端+路由 → 质量债务。每轮独立验证、独立提交。
**Consequences**: 4 轮需要较多提交但风险可控（每轮独立可回滚）。

## Out of Scope

* 功能变更
* 架构调整（不合并服务、不换框架）
* 测试编写
* 视觉设计变更

## Technical Notes

* Round 1 已合并 models/model_status 路由、删除 model_status.py、添加下载公共工具等
* ai_client.py 的拆解需要极度谨慎——它是一个 ~100 方法的巨类，内部闭包密集
* settings OCR 区域有 ~20 个 useState hooks 需要 prop-drill 或 context
* 所有拆分必须保持 `ocr/__init__.py` 的 re-export 向后兼容
