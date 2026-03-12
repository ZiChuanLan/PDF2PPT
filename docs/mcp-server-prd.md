# Product Requirements Document: PDF2PPT MCP Server

**Version**: 1.0
**Date**: 2026-03-10
**Author**: Codex

## Executive Summary

为 `PDF2PPT` 增加一个 MCP Server，使外部 MCP Client 能直接调用现有 PDF 转 PPT、OCR 检测、模型发现和任务跟踪能力，而不必操作 Web 页面。

基于当前项目结构，最合适的路线不是直接把现有应用改造成公网多租户远程 MCP 平台，而是先做一个薄包装 MCP Server。它优先复用现有 FastAPI API 与 Worker/RQ 长任务机制，第一阶段以本地部署为主，第二阶段再扩展为远程 MCP。

## Current Context

当前项目已经具备以下天然适合 MCP 的能力：

- Web/API/Worker 已分层，后端动作接口清晰
- 已有异步任务模型，适合 MCP 的 `create job -> poll status -> fetch artifacts`
- 已有 OCR 检测、模型列表、产物查询、任务状态等独立接口
- Docker 部署成熟，适合独立增加一个 `mcp` 服务

不适合直接“原封不动暴露”的部分：

- PDF 上传和 PPT 下载涉及二进制，不适合一次 tool call 直接塞完整结果
- 长任务不适合在单个 MCP tool 调用里阻塞等待
- API Key、OCR 配置、任务产物路径需要重新做安全边界

## Recommendation

**建议路线：先本地 MCP，后远程 MCP。**

### Phase 1: Local MCP

目标：

- 支持 Claude Desktop、Cursor、Codex CLI、Cherry Studio 等本地 MCP Client
- transport 使用 `stdio`
- MCP Server 部署在与 `PDF2PPT` 同一台机器
- MCP Server 调用现有 FastAPI `/api/v1/*`

原因：

- 实现成本最低
- 不需要先处理公网认证、租户隔离、限流、对象存储签名等远程问题
- 对现有架构侵入最小
- 最适合验证工具设计是否合理

### Phase 2: Remote MCP

目标：

- 支持团队共享、云端调用、远程 Agent 编排
- transport 使用 `Streamable HTTP`
- 独立部署 `mcp` 服务，对外提供 MCP endpoint

适合在以下条件满足后再做：

- 本地 MCP 工具集已经稳定
- 任务/产物权限模型明确
- 需要多用户或跨机器访问

## Why Local-First

### Local MCP 优势

- 与当前 Docker/本地开发模型高度一致
- 可以直接复用用户本机已有 `.env`、OCR 设置和服务地址
- 二进制文件路径、临时文件、下载链路更容易处理
- 失败排查简单，成本低

### Remote MCP 额外复杂度

- 需要用户认证和会话鉴权
- 需要把本地文件上传转换成远程可接收的附件或 URL
- 需要对任务结果做权限隔离
- 需要处理远程下载、大文件生命周期和存储配额
- 需要更严格的限流和审计

## Product Goals

### Primary Goals

- 让 MCP Client 能直接发起 PDF 转 PPT 任务
- 让 MCP Client 能检测 AIOCR 模型是否可用
- 让 MCP Client 能列出可用 OCR/视觉模型
- 让 MCP Client 能查询任务状态、读取调试信息和下载产物

### Non-Goals

- 第一阶段不重写现有 PDF2PPT 核心业务逻辑
- 第一阶段不做多租户远程共享平台
- 第一阶段不把 Web 设置页完整映射成 MCP GUI 配置中心

## User Personas

### Primary: AI Agent User

- 使用 Claude Desktop / Cursor / Codex CLI 的开发者或运营
- 希望直接让 Agent 调 PDF2PPT，而不是手动开网页
- 关注自动化、脚本化、可编排

### Secondary: Internal Automation Integrator

- 希望把 PDF 转 PPT 接入内部工作流
- 关注稳定的 tool schema、异步任务状态和产物 URI

## Recommended Architecture

### Deployment Mode

#### Local Mode

```text
MCP Client -> MCP Server (stdio) -> FastAPI API -> Redis/RQ -> Worker
```

#### Remote Mode

```text
MCP Client -> MCP Server (Streamable HTTP) -> FastAPI API -> Redis/RQ -> Worker
```

### Packaging Strategy

推荐新增独立服务目录：

```text
mcp/
  server.py
  tools.py
  resources.py
  prompts.py
  settings.py
```

MCP Server 不直接 import Web 代码，也不直接深入 Worker 内部函数；优先走现有 HTTP API。

## MCP Capability Design

### Tools

#### `pdf2ppt.create_job`

作用：

- 上传 PDF
- 创建转换任务
- 返回 `job_id`

输入：

- `file`
- `page_start`
- `page_end`
- `parse_engine_mode`
- `ocr_provider`
- `ocr_ai_provider`
- `ocr_ai_model`
- `ocr_ai_chain_mode`
- `retain_process_artifacts`

输出：

- `job_id`
- `status`
- `created_at`

#### `pdf2ppt.get_job_status`

输入：

- `job_id`

输出：

- `status`
- `stage`
- `progress`
- `message`
- `error`

#### `pdf2ppt.list_ai_ocr_models`

输入：

- `provider`
- `base_url`
- `api_key`
- `capability`

输出：

- `models[]`

#### `pdf2ppt.check_ai_ocr`

输入：

- `provider`
- `base_url`
- `api_key`
- `model`
- `ocr_ai_chain_mode`
- `ocr_ai_layout_model`
- `ocr_ai_prompt_preset`

输出：

- `ok`
- `elapsed_ms`
- `valid_bbox_items`
- `message`
- `error`

#### `pdf2ppt.cancel_job`

输入：

- `job_id`

输出：

- `ok`
- `message`

### Resources

#### `job://{job_id}/status`

- 当前任务状态快照

#### `job://{job_id}/ir`

- `ir.json` 内容

#### `job://{job_id}/ocr-debug`

- OCR 调试信息

#### `job://{job_id}/artifacts`

- 产物列表与相对路径

#### `job://{job_id}/output`

- 输出 PPT 产物元数据
- 本地模式下可返回本机文件路径
- 远程模式下应返回受控下载 URL 或二进制 resource

### Prompts

#### `convert-pdf-to-ppt`

- 引导 Agent 收集参数并调用 `create_job`

#### `diagnose-ocr-model`

- 引导 Agent 调用 `check_ai_ocr` 并解释失败原因

#### `inspect-job-failure`

- 引导 Agent 读取 `status`、`ocr-debug`、`artifacts`

## Local vs Remote Final Decision

### MVP Decision

**MVP 采用本地 MCP。**

原因：

- 与现有架构最匹配
- 只需增加一层协议适配
- 可以最快让 Agent 真正可用

### Future Decision

**远程 MCP 作为二期能力。**

触发条件：

- 需要团队共享服务
- 需要云端 Agent 调用
- 需要跨机器访问同一 PDF2PPT 服务

## API Mapping

推荐 MCP Server 直接复用这些现有后端能力：

- `POST /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs`
- `POST /api/v1/jobs/ocr/ai/check`
- `GET /api/v1/models`
- `GET /api/v1/jobs/{job_id}/artifacts`

这样可以避免在 MCP 层重复实现业务逻辑。

## Security Requirements

### Local MCP

- 默认只监听本地，不开放公网
- API Key 优先读取 MCP Server 自己的环境变量或显式 tool 参数
- 不把完整密钥写入日志

### Remote MCP

- 必须引入用户认证
- 必须做任务隔离
- 必须限制资源访问范围
- 必须增加速率限制与审计日志

## Operational Requirements

### Local MCP

- 支持直接命令启动
- 支持 Docker sidecar 启动
- 支持配置 API base URL

### Remote MCP

- 支持健康检查
- 支持可观测性与请求日志
- 支持横向扩展

## MVP Scope

第一版只做：

- `create_job`
- `get_job_status`
- `list_ai_ocr_models`
- `check_ai_ocr`
- `cancel_job`
- `job://.../status`
- `job://.../artifacts`

第一版不做：

- 复杂资源二进制直传
- 多租户远程共享
- MCP 内完整设置页镜像

## Implementation Plan

### Step 1

- 新建 `mcp/` 服务目录
- 基于官方 Python MCP SDK 实现 `stdio` server
- 通过 HTTP 调现有 FastAPI

### Step 2

- 增加 `tools`
- 增加 `resources`
- 增加 `prompts`

### Step 3

- 增加 Docker service: `mcp`
- 提供本地客户端配置示例

### Step 4

- 评估远程 MCP
- 再决定是否升级到 `Streamable HTTP`

## Success Metrics

- MCP Client 可成功创建并完成一条 PDF 转 PPT 任务
- MCP Client 可成功检测 OCR 配置
- MCP Client 可成功读取任务状态和产物
- 首版无需改动现有核心转换链路

## References

- MCP server concepts: https://modelcontextprotocol.io/docs/learn/server-concepts
- MCP transports: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- Python MCP SDK: https://py.sdk.modelcontextprotocol.io/
