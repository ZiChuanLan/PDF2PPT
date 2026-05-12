# 拆分前端设置 + 路由收尾

## Goal

拆分 settings/page.tsx (2787行)、preview-stage.tsx (661行)、jobs.py (1838行)、models.py (1286行)，消除端点重复逻辑。

## Requirements

* [ ] settings/page.tsx：OCR 配置区域 (~995行) → `OcrConfigSection` + 子组件
* [ ] preview-stage.tsx：QuickConfigPanel (~230行) + PageRangeSection (~85行) + ActionButtons (~71行)
* [ ] jobs.py：提取 `_create_job_core()` 消除 ~150 行重复
* [ ] jobs.py：上传工具 (~116行) → `_upload_utils.py`、OCR 检查 (~243行) → `_ocr_check.py`
* [ ] models.py：模型过滤 (~218行) → `_model_filtering.py`、下载子系统 (~653行) → `_model_download.py`

## Acceptance Criteria

* [ ] settings/page.tsx < 1000 行
* [ ] tsc / lint / py_compile 通过
* [ ] 公共 import 路径不变
* [ ] 端点行为不变

## Out of Scope

* 功能变更
* 测试编写

## Research References

* 父任务 research/remaining-large-files.md
