# PRD: 环境变量前端可配置化 + 模型下载管理优化

## 概述

将合理的后端环境变量暴露到前端设置页，优化模型下载体验，消除布局助手死代码。

---

## 分类判断

### A. 真实缺口 — 应添加到前端设置

| 后端 env | 原因 |
|---|---|
| `JOB_TIMEOUT_SECONDS` | 转换超时用户需要感知和控制 |
| `OCR_PAGE_TIMEOUT_S` | OCR 慢文档需要延长 |
| `OCR_TOTAL_TIMEOUT_S` | 同上 |
| `OCR_PADDLE_VL_PREDICT_TIMEOUT_S` | AI OCR 请求可能超时 |
| `OCR_AI_RETRY_BACKOFF_BASE_S` | 重试策略可调 |
| `OCR_AI_RATE_LIMITED_MIN_DELAY_S` | 限流等待可调 |
| `ENABLE_LAYOUT_ASSIST` | 前端硬编码关闭，后端开关无效 — 应前后端统一 |
| `MODEL_CACHE_DIR` | 模型下载路径应可看见 |
| `SCANNED_RENDER_DPI` | PPTX 底图渲染质量 |
| `scannedImageRegion*` 并发上限 | 前后端各自硬编码，应同步 |
| `ocr_ai_*_default/max` 并发上限 | 同上 |

### B. 刻意省略 — 不应暴露到前端

| 后端 env | 原因 |
|---|---|
| `api_bind_host`, `redis_url`, `sqlite_path`, `cors_allow_origins`, `log_level` | 基础设施，部署时一次性配置 |
| `jwt_secret`, `linuxdo_client_secret`, `cookie_secure`, `api_bearer_token` | 安全密钥，绝不应暴露前端 |
| `admin_default_password`, `admin_usernames` | 只在 setup wizard / admin 管理 |
| `linuxdo_client_id`, `linuxdo_redirect_uri` | OAuth 部署配置，不应随意改动 |
| `rate_limit_requests/work/format_interval*` | 服务器端限流，全局策略 |
| Debug export flags (`EXPORT_*`) | 开发调试用 |

### C. 已是设计选择 — 不需改

| 项 | 解释 |
|---|---|
| `openaiApiKey` 等主 AI 密钥无 UI | 首页隐式读取，admin 站点设置可配，自用模式靠 localStorage — 简洁设计 |
| `pptGenerationMode` 无设置页 UI | 首页选择，即时配置即可 |
| `enableOcr` 无独立开关 | 由 parseEngineMode 推导，设计合理 |
| `mineruHybridOcr` | 已废弃，worker 有 deprecation warning |

---

## 实施计划

### Phase 1: 后端新增 GET/PUT `/api/v1/config/runtime` 端点
- 暴露 A 类中合理可前端读写的配置
- 排除安全敏感项
- 写入 `.env` 文件（已有 admin env editor 能力可复用）

### Phase 2: 前端设置页新增「运行时配置」区域
- 展示/编辑 A 类配置项
- 说明文字 + 默认值展示
- 自用模式存 localStorage 回退

### Phase 3: 模型下载优化
- 下载状态持久化到文件（`api/data/downloads/`）
- PaddleX 下载增加轮询进度估算（按文件大小）
- 新增「删除模型」按钮（清理缓存）

### Phase 4: 清理
- Layout Assist 死代码：前端 settings.ts 不再强制关闭，尊重后端 env 开关
- 前后端并发上限统一从后端读取

---

## 验收标准

1. `GET /api/v1/config/runtime` 返回 A 类配置项
2. `PUT /api/v1/config/runtime` 可修改并持久化
3. 前端设置页有「运行时配置」区域，展示 10+ 项
4. 前端不再对 `enableLayoutAssist` 强制写死 `false`
5. 模型下载状态重启后不丢失
6. 模型可从前端删除
