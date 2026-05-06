# 消除硬编码：全面审查并优化项目中的硬编码值和魔法数字

## Goal

项目中存在大量硬编码的魔法数字、魔法字符串和散落的常量定义。这些硬编码值导致：
- 同一个概念在多个文件中有不同的值（如 DPI 在 config.py 是 200，在 llm_adapter.py 是 150）
- 修改一个参数需要同时改多个文件
- 代码可读性差（看到 `0.85` 不知道代表什么）
- 配置能力不足（很多本应可调的值写死在代码里）

目标：系统性地提取、命名、集中管理所有硬编码值，提升代码质量和可维护性。

## What I already know

### 硬编码分布（来自研究）

| 区域         | 硬编码数量 | 严重程度 | 主要文件                                                                                                                              |
| ------------ | ---------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| OCR 管线 (ai_client.py)     | 100+       | **高**     | 置信度阈值、超时、重试、图像处理参数                                                                                                  |
| 本地 OCR (local_providers.py) | 50+        | **高**     | Baidu/Tesseract/PaddleOCR 阈值、噪声检测、合并检测                                                                                    |
| Worker (worker.py)           | 30+        | **高**     | DPI 范围、并发限制、图像处理参数                                                                                                      |
| Auth (auth.py)               | 12         | **中**     | JWT 算法、token 过期、OAuth URL                                                                                                       |
| Vendor 配置 (vendors.py)     | 30+        | **中**     | URL、模型名、token 限制、超时                                                                                                         |
| 前端轮询间隔                 | 9          | **中**     | 2000/3000/4000ms 不一致                                                                                                               |
| 前端查询限制                 | 5          | **中**     | 50/60/100 不一致                                                                                                                      |
| 前端 CSS 颜色                | 20+        | **低**     | `#cc0000` 出现 20+ 次                                                                                                                 |
| 前端 z-index                 | 6          | **低**     | 20-9999 无 scale                                                                                                                      |
| Docker/基础设施              | 20+        | **低**     | 端口、镜像版本、healthcheck                                                                                                           |

### 重复值（跨文件不一致）

1. **`0.85`** — 默认置信度分数，出现在 PaddleOCR、Baidu OCR、local_providers（6+ 处）
2. **`50.0`** — Tesseract 最低置信度（3 处）
3. **`2200`** — PaddleOCR 最大边像素（worker.py + local_providers.py）
4. **`200`** — OCR 渲染 DPI（config.py + perf_policies.py + settings.ts）
5. **`10.0`** — HTTP 客户端超时（auth.py 2 处）
6. **`60.0`** — 速率限制窗口（ai_client.py 2 处）
7. **`3600`** — token cookie max_age（auth.py + setup.py + user model）

### 安全问题

- `admin_default_password = "admin12345678"` 硬编码在 config.py

## Assumptions (temporary)

- 不改动 Docker/基础设施的硬编码（端口、镜像版本等）— 这些属于部署配置，不在本次范围
- 不做 i18n（UI 文字国际化）— 这是独立的大任务
- 不改动 PPTX 常量（EMU_PER_INCH 等物理常数）
- 不改动 vendor URL/模型名（这些是供应商固定的）

## Decision (ADR-lite)

**Context**: 用户确认全量清理范围，包括 OCR 管线 + Auth + Vendor + 前端常量 + 安全修复。同时确认引入 CSS 变量统一品牌色。

**Decision**: 一次性全量清理，引入 CSS 变量系统。

**Consequences**: 
- 改动文件多（15+），需要仔细确保不改变运行时行为
- CSS 变量引入后，后续主题切换等扩展更容易
- 分批提交，每批可独立验证

## Requirements (evolving)

### R1: 提取 OCR 管线硬编码为命名常量
- `ai_client.py` 中 100+ 个魔法数字 → 提取为模块级常量，带清晰命名和注释
- `local_providers.py` 中 50+ 个魔法数字 → 同上
- `worker.py` 中 30+ 个魔法数字 → 同上

### R2: 统一重复值
- 相同概念在多处定义的值 → 提取为共享常量
- DPI、置信度阈值、超时值等 → 单一来源

### R3: 将散落的配置值移入 config.py
- 已有 env var 但代码中仍有硬编码默认值的 → 统一从 config 读取
- 应该可配置但目前写死的 → 添加到 config.py + env var

### R4: 前端常量集中管理
- 创建 `web/src/lib/constants.ts` 集中管理轮询间隔、查询限制、z-index scale
- 品牌色 `#cc0000` → CSS 变量

### R5: 安全修复
- `admin12345678` → 首次运行时随机生成或要求显式配置

## Technical Approach

### 分批策略（5 批）

**批次 1: OCR 管线核心** (ai_client.py)
- 提取 100+ 魔法数字为模块级常量
- 按功能分组：置信度、超时、重试、图像处理、padding、噪声检测
- 文件：`api/app/convert/ocr/ai_client.py`

**批次 2: 本地 OCR + Worker** (local_providers.py + worker.py)
- 提取 80+ 魔法数字
- 统一重复值（如 2200、0.85、50.0）
- 文件：`api/app/convert/ocr/local_providers.py`, `api/app/worker.py`

**批次 3: Vendor + Auth + Config** (vendors.py + auth.py + config.py)
- Vendor 配置集中管理
- Auth 常量提取
- 安全修复：admin 密码
- 文件：`api/app/convert/ocr/vendors.py`, `api/app/auth.py`, `api/app/config.py`

**批次 4: 前端常量** (constants.ts + CSS 变量)
- 创建 `web/src/lib/constants.ts`
- 创建 CSS 变量（品牌色、z-index scale）
- 替换散落的硬编码引用
- 文件：`web/src/lib/constants.ts`, `web/src/app/globals.css`, `web/src/app/page.tsx` 等

**批次 5: 验证 + 清理**
- tsc --noEmit 验证
- Docker 容器重建验证
- 确保无运行时行为变化

## Acceptance Criteria (evolving)

- [ ] OCR 管线中所有魔法数字都有命名常量
- [ ] 跨文件重复值统一为单一来源
- [ ] 前端创建 constants.ts 集中管理 UI 常量
- [ ] 所有常量有清晰的命名（看到名字就知道含义）
- [ ] 不改变任何运行时行为（纯重构）
- [ ] tsc --noEmit 通过
- [ ] Docker 容器正常运行

## Definition of Done

- 所有硬编码值提取为命名常量
- 重复值统一为单一来源
- 不改变运行时行为
- 测试通过
- Docker 容器正常运行

## Out of Scope

- Docker/基础设施配置（端口、镜像版本、healthcheck 参数）
- i18n（UI 文字国际化）
- PPTX 物理常量（EMU_PER_INCH 等）
- Vendor URL/模型名（供应商固定的）
- CSS 设计系统全面重构（仅做品牌色 CSS 变量）

## Technical Notes

### 研究文件
- `.trellis/tasks/05-05-hardcoded-cleanup/research/backend-hardcoded-values.md` — 后端 200+ 硬编码值详细清单
- `.trellis/tasks/05-05-hardcoded-cleanup/research/frontend-hardcoded-values.md` — 前端 100+ 硬编码值
- `.trellis/tasks/05-05-hardcoded-cleanup/research/config-hardcoded-values.md` — 配置/基础设施硬编码

### 关键文件
- `api/app/convert/ocr/ai_client.py` — 最多硬编码（100+），OCR 管线核心
- `api/app/convert/ocr/local_providers.py` — 50+ 硬编码，本地 OCR 提供者
- `api/app/worker.py` — 30+ 硬编码，worker 参数边界
- `api/app/convert/ocr/vendors.py` — vendor 配置（URL、模型、超时）
- `api/app/auth.py` — JWT/OAuth 常量
- `web/src/lib/settings.ts` — 前端默认值
- `web/src/app/page.tsx` — 前端轮询、限制
