# 全面代码审计：发现死代码和缺失功能

## Goal

全面审计前后端代码，发现：死代码（无引用模块/函数/组件）、缺失的 UI（后端有但前端没暴露）、功能不一致。

## What I already know

- 模型过滤（`_model_filtering.py`）已有但前端没传 `capability` 参数
- 布局辅助后端已实现但硬编码禁用（已修复）
- 4 个 Settings 字段无 UI：`preferredMainProvider`, `ocrPaddleVlDocparserMaxSidePx`, `ocrAiPageConcurrencyAuto`, `ocrAiBlockConcurrency`
- 已删除 3 个孤儿组件：basic-settings.tsx, ocr-settings.tsx, advanced-settings.tsx

## Research Tasks

见 research/ 子目录

## Requirements (evolving)

* 列出所有死代码模块
* 列出所有前端未暴露的后端功能
* 列出设置类型中有但无 UI 的字段

## Out of Scope

* 修复死代码（仅记录）
