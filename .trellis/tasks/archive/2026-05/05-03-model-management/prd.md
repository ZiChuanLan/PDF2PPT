# Model Management: Setup Wizard + Runtime Detection + Pre-flight Validation

## Goal

把 OCR 模型管理从 env 变量迁移到数据库 + UI，实现：
1. Setup wizard 时选择/预热模型
2. 运行时自动检测模型就绪状态 + 提示下载
3. 提交任务前预检（pre-flight check）+ 早期报错
4. 消除 env 变量配置负担

## Research References

- [`research/job-validation-chain.md`](research/job-validation-chain.md) — 三层验证链：前端 validateRunConfig → API validate_and_normalize → Worker runtime。已有 `/ocr/local/check` 和 `/ocr/ai/check` 端点但提交前未调用。
- [`research/model-readiness-detection.md`](research/model-readiness-detection.md) — 4 个探针函数、2 个预热函数、无统一状态 API、OcrManager 有 fallback 链。

## What I already know

### 两类模型

**远程 API 模型（无需下载）：**
- AIOCR: SiliconFlow/OpenAI/DeepSeek 等 API → 只需 API Key
- PaddleOCR doc parser: 通过 SiliconFlow 等 API 调用 PaddleOCR-VL → 只需 API Key
- "预热" = 验证 API 连通性 + 缓存客户端

**本地模型（需要下载）：**
- PP-DocLayout: 本地版面检测模型，通过 `paddlex.create_model()` 下载
- Local PaddleOCR: 首次使用时自动下载模型文件
- Tesseract: 系统包，无模型下载

### 当前预热机制

- `api/app/services/paddle_prewarm.py` — 两个预热函数：
  - `run_local_paddle_layout_prewarm()`: 需要 `OCR_PADDLE_LAYOUT_PREWARM=true` + `OCR_PADDLE_LAYOUT_PREWARM_MODEL`
  - `run_paddle_doc_prewarm()`: 需要 `OCR_PADDLE_VL_PREWARM=true` + `OCR_PADDLE_VL_PREWARM_MODEL` + `OCR_PADDLE_VL_PREWARM_API_KEY`
- 全部通过 env 变量配置，需要改 docker-compose.yml
- 容器启动时调用 `main()` 执行预热

### 运行时探针

- `api/app/convert/ocr/runtime_probe.py` — 已有探针：
  - `probe_local_tesseract()`: 检查 pytesseract + binary + 语言包
  - `probe_local_paddleocr()`: 检查 paddleocr 包 + runtime
  - `probe_local_paddle_models()`: 检查模型文件是否存在
  - `probe_local_tesseract_models()`: 检查 Tesseract 模型

### 当前验证链（研究发现）

**三层验证：**
1. **前端 `validateRunConfig()`** — 检查配置语法、必填项（MinerU token、百度 keys、AIOCR key/model）
2. **API `validate_and_normalize_job_options()`** — 重复前端检查 + chain mode 兼容性、页码范围
3. **Worker runtime** — 捕获运行时错误：PDF 损坏/加密、本地 OCR binary 缺失、API 不可达、模型不存在

**已有但未使用的预检端点：**
- `POST /api/v1/ocr/local/check` — 检查本地 OCR 环境（Tesseract/PaddleOCR）
- `POST /api/v1/ocr/ai/check` — 检查 AI OCR API 连通性
- 这两个端点存在但**提交任务前从未调用**

**验证重复：** 前端和 API 重复检查 MinerU token、百度 credentials、AIOCR key/model

**运行时才暴露的失败：**
- 本地 OCR binary 缺失
- AI/MinerU/Baidu API 不可达或 credentials 无效
- 模型不存在

### 关键文件

- `api/app/services/paddle_prewarm.py` — 预热逻辑
- `api/app/convert/ocr/runtime_probe.py` — 运行时探针
- `api/app/config.py` — Settings + get_deploy_mode()
- `api/app/routers/setup.py` — Setup wizard API
- `api/app/routers/config.py` — /config/deploy-mode
- `web/src/app/setup/page.tsx` — Setup wizard UI
- `web/src/app/settings/page.tsx` — Settings page
- `web/src/lib/run-config.ts` — validateRunConfig(), resolveOcrSettingsState()
- `api/app/job_options.py` — validate_and_normalize_job_options()

## Requirements

### 1. 统一模型状态 API

新增 `GET /api/v1/models/status` 端点，返回所有模型/API 的就绪状态：

```
{
  "local": {
    "tesseract": { "ready": true, "issues": [] },
    "paddleocr": { "ready": true, "issues": [] },
    "pp_doclayout": { "ready": false, "issues": ["model_not_downloaded"] }
  },
  "remote": {
    "aiocr": { "ready": true, "issues": [], "provider": "siliconflow" },
    "baidu_doc": { "ready": false, "issues": ["api_key_missing"] },
    "mineru": { "ready": true, "issues": [] }
  }
}
```

- 复用 `runtime_probe.py` 的 4 个探针函数
- 新增远程 API 连通性检查（复用已有 `/ocr/ai/check` 逻辑）
- 前端轮询或按需查询

### 2. 提交前预检（Pre-flight Check）

在首页点击"开始转换"时，先调用模型状态 API 检查：
- 所需模型/API 是否就绪
- 未就绪时显示确认对话框："模型 X 未就绪，是否继续？（任务可能失败）"
- 缺少 API Key 时跳转设置页面
- 本地模型未下载时提供一键下载按钮

### 3. Setup Wizard 模型预热

在 setup wizard 完成后，根据用户选择的解析引擎自动预热：

| 解析引擎      | 预热动作                                        |
| ------------- | ----------------------------------------------- |
| local_ocr     | 下载 PP-DocLayout 模型（可选）+ 验证 PaddleOCR |
| remote_ocr    | 验证 AIOCR API 连通性                           |
| baidu_doc     | 验证百度 API 连通性                             |
| mineru_cloud  | 验证 MinerU API 连通性                          |

### 4. 运行时模型检测

用户在首页/设置页切换解析引擎时：
- 自动检测对应模型/API 是否就绪
- 未就绪时显示提示 + 一键下载/配置按钮
- 不阻塞用户操作（允许先提交任务，运行时再检测）

### 5. 模型下载 API

新增 `POST /api/v1/models/download` 端点：
- 触发本地模型下载（PP-DocLayout, PaddleOCR）
- 返回下载进度/结果

### 6. 迁移 env 预热配置到 DB

将 `OCR_PADDLE_VL_PREWARM_*` 和 `OCR_PADDLE_LAYOUT_PREWARM_*` 从 env 迁移到 site_settings：
- 保留 env 作为 fallback（向后兼容）
- Setup wizard 写入 DB
- Admin 站点配置页可修改

### 7. 首页状态指示器

在首页解析引擎选择器旁显示状态指示器：
- 🟢 就绪
- 🟡 需要配置（缺少 API Key）
- 🔴 不可用（本地模型未下载）
- 点击查看详情 + 一键修复

## Acceptance Criteria

- [ ] `GET /api/v1/models/status` 返回各模型就绪状态
- [ ] 首页提交前调用预检，未就绪时显示确认对话框
- [ ] Setup wizard 完成后自动预热所选引擎的模型
- [ ] 首页切换解析引擎时显示模型就绪状态指示器
- [ ] 本地模型未下载时显示提示 + 一键下载按钮
- [ ] 远程 API 未配置时显示配置引导（跳转设置页）
- [ ] `POST /api/v1/models/download` 触发本地模型下载
- [ ] 向后兼容：env 变量仍可使用
- [ ] 前端 `validateRunConfig()` 简化（移除与后端重复的检查）

## Out of Scope

- 模型版本管理/升级
- 模型删除/清理
- 下载进度条（模型下载通常 <30s）
- 前后端验证完全统一（保持两层，但减少重复）

## Technical Approach

### Phase 1: 统一模型状态 API

- 新增 `GET /api/v1/models/status` 端点
- 复用 `runtime_probe.py` 探针 + 新增远程 API 检查
- 返回结构化的模型状态 JSON

### Phase 2: 提交前预检

- 首页 `handleConvert` 调用模型状态 API
- 根据状态显示确认对话框或自动跳转
- 简化 `validateRunConfig()` 中已由后端覆盖的检查

### Phase 3: Setup Wizard 预热

- Setup wizard 完成后调用模型下载/预热 API
- 将预热配置写入 site_settings DB
- 保留 env fallback

### Phase 4: 首页状态指示器

- 解析引擎选择器旁显示状态点
- 点击展开详情 + 一键修复按钮

## Decision (ADR-lite)

**Context**: 当前模型预热全靠 env 变量，提交前不检查模型就绪状态，已有预检端点未使用
**Decision**: 统一模型状态 API + 提交前预检 + 迁移到 DB + UI 状态指示器
**Consequences**: 更好的 UX，早期错误捕获，减少运行时失败

## Key Files

- `api/app/convert/ocr/runtime_probe.py` — 已有探针，需扩展
- `api/app/services/paddle_prewarm.py` — 预热逻辑，需迁移到 DB
- `api/app/routers/jobs.py` — v2 端点，需添加预检调用
- `web/src/app/page.tsx` — 首页，需添加预检 + 状态指示器
- `web/src/lib/run-config.ts` — validateRunConfig()，需简化
- `web/src/app/setup/page.tsx` — Setup wizard，需添加预热步骤
