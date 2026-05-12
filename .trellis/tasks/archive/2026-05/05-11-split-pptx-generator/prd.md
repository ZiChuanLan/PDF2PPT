# 拆分 PPTX 生成器剩余部分

## Goal

拆分 `scanned_page.py` (3971行) 和 `main.py` 剩余分支 (1594行)，消除嵌套闭包。

## Requirements

* [ ] scanned_page.py 拆分为多个子函数/模块
* [ ] main.py 扫描页分支 (~710行) → `generator/_scanned_page.py`
* [ ] main.py 文本页分支 (~560行) → `generator/_text_page.py`
* [ ] 嵌套闭包 → 模块级函数

## Acceptance Criteria

* [ ] scanned_page.py < 1000 行
* [ ] main.py < 500 行
* [ ] py_compile 通过
* [ ] 公共 API 不变

## Out of Scope

* 功能变更
* 测试编写

## Research References

* 父任务 research/remaining-large-files.md
