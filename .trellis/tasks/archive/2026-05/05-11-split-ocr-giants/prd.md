# 拆分 OCR 后台巨型文件

## Goal

拆分项目中最大的两个文件：`ai_client.py` (5581行) 和 `local_providers.py` (4320行)，消除重复代码和死代码。

## Requirements

* [ ] ai_client.py 拆分为：PaddleDoc 解析器 (~1500行)、布局块 OCR (~1000行)、AI chat pipeline (~1200行)、文本精炼器 (~995行)
* [ ] local_providers.py 拆分为：BaiduOcr (~193行)、TesseractOcr (~325行)、PaddleOcr (~357行)、OcrManager (~912行)、后处理链 (~700行)
* [ ] 上移 4 处重复工具函数到 `ocr/utils.py`
* [ ] 删除 4 个死别名
* [ ] `ocr/__init__.py` 保持向后兼容 re-export

## Acceptance Criteria

* [ ] ai_client.py < 1000 行
* [ ] local_providers.py < 500 行
* [ ] py_compile 通过
* [ ] 公共 import 路径不变

## Out of Scope

* 功能变更
* 测试编写

## Research References

* 父任务 research/untouched-modules.md
