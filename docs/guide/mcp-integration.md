# MCP 集成

## `ppt-mcp` 是什么

`ppt-mcp` 是当前 `PDF2PPT` 主服务的 MCP 接入层。

它本身不重新实现：

- PDF 解析
- OCR
- PPT 生成

它做的事情是把现有 `PDF2PPT` API 包装成 MCP tools，让 Claude Desktop、Cursor、Codex CLI 等客户端可以直接调用。

一句话理解：

```text
MCP Client -> ppt-mcp -> PDF2PPT API -> worker
```

## 它在整体体系中的位置

- `PDF2PPT` 主服务负责转换核心能力
- `ppt-mcp` 负责 MCP 协议适配和工具封装
- 两者不是重复实现关系，而是主服务与接入层关系

如果文档站描述的是整个 `PDF2PPT` 体系，那 `ppt-mcp` 应该被视为其中一个模块。

## 什么时候用 Web，什么时候用 MCP

更适合用 Web：

- 手动上传 PDF
- 交互式调整参数
- 人工跟踪任务与下载结果

更适合用 `ppt-mcp`：

- 需要让 AI 客户端直接调用转换能力
- 想把“上传 PDF -> 创建任务 -> 轮询状态 -> 下载结果”封装成 MCP tools
- 需要把转换能力纳入自动化工作流

## 推荐使用方式

### 1. 本地 stdio MCP，最简单也最稳

这是当前最推荐的模式。

- `PDF2PPT` 服务跑在本机
- `ppt-mcp` 也跑在本机
- MCP transport 使用 `stdio`
- `PPT_API_BASE_URL` 指向 `http://127.0.0.1:8000`

这时：

- 浏览器用户走 Web 页面
- MCP 用户走本地 API
- 两条链路互不干扰

### 2. 本地 stdio MCP，连接远程 PDF2PPT

适合：

- AI 客户端在本机
- 但转换服务部署在远程服务器

这时：

- `PPT_API_BASE_URL` 指向远程服务根地址
- `ppt-mcp` 仍然在本机运行
- 本地 PDF 由 `ppt-mcp` 读取后再上传到远程 API

### 3. 远程 `ppt-mcp-remote`

这个模式更像“把 MCP 服务也部署到服务器上”。

适合：

- 团队共用
- 统一 MCP 入口
- 需要 Streamable HTTP MCP

但它也更复杂：

- 需要额外入口认证
- 需要处理上传源文件
- 需要考虑下载、权限和公网暴露

## 地址与鉴权的关键点

### `PPT_API_BASE_URL` 应该怎么写

它应该指向 `PDF2PPT` 服务根地址，而不是 `/api/v1`。

正确示例：

```bash
PPT_API_BASE_URL=http://127.0.0.1:8000
```

或者：

```bash
PPT_API_BASE_URL=https://ppt.example.com
```

不建议写成：

```bash
PPT_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

也不建议默认写成 Web 入口：

```bash
PPT_API_BASE_URL=http://127.0.0.1:3000
```

原因是 `3000` 这条链路通常会受到 `WEB_ACCESS_PASSWORD` 影响。

### Bearer Token 的对应关系

如果主服务配置了：

```bash
API_BEARER_TOKEN=your-shared-secret
```

那么 `ppt-mcp` 也要配置：

```bash
PPT_API_BEARER_TOKEN=your-shared-secret
```

可以理解成：

- `API_BEARER_TOKEN` 是主服务 API 要求的密码
- `PPT_API_BEARER_TOKEN` 是 `ppt-mcp` 请求 API 时带上的密码

通常这两个值应保持一致。

## 常用环境变量

本地 stdio 模式最少需要：

```bash
PPT_API_BASE_URL=http://127.0.0.1:8000
PPT_API_TIMEOUT_SECONDS=120
```

如果主服务 API 开了 Bearer，再加：

```bash
PPT_API_BEARER_TOKEN=your-shared-secret
```

常用变量包括：

| 变量 | 说明 |
| --- | --- |
| `PPT_API_BASE_URL` | `PDF2PPT` 服务根地址，不带 `/api/v1` |
| `PPT_API_TIMEOUT_SECONDS` | `ppt-mcp` 请求 API 的超时时间 |
| `PPT_API_BEARER_TOKEN` | 直连 API 时使用的 Bearer |
| `MINERU_API_TOKEN` | MinerU 云解析 token |
| `BAIDU_API_KEY` | 百度文档解析 key |
| `BAIDU_SECRET_KEY` | 百度文档解析 secret |
| `SILICONFLOW_API_KEY` | 通用远程视觉/OCR 模型 key |

远程 `ppt-mcp-remote` 额外变量包括：

| 变量 | 说明 |
| --- | --- |
| `PPT_MCP_BIND_HOST` | 远程 MCP 监听地址，默认 `0.0.0.0` |
| `PPT_MCP_BIND_PORT` | 远程 MCP 端口，默认 `8080` |
| `PPT_MCP_PUBLIC_BASE_URL` | 远程 MCP 对外访问地址 |
| `PPT_MCP_SERVER_TOKEN` | 远程 MCP 自己的入口密码 |

## 安装与运行

先启动主服务：

```bash
docker compose up -d --build api worker redis
```

再安装并运行 `ppt-mcp`：

```bash
cd /home/lan/workspace/ppt-mcp
uv sync
uv run ppt-mcp
```

远程 MCP 服务模式：

```bash
cd /home/lan/workspace/ppt-mcp
export PPT_API_BASE_URL=http://127.0.0.1:8000
export PPT_MCP_PUBLIC_BASE_URL=https://your-mcp.example.com
export PPT_MCP_SERVER_TOKEN=change-me
uv run ppt-mcp-remote
```

## 当前工具能力

当前 `ppt-mcp` 已经覆盖主服务的常见任务流，包括：

- 路线查询与确认
- 创建任务
- 查询任务状态
- 列出任务
- 取消任务
- 下载结果
- 读取产物
- 列出模型
- 检查 AI OCR 路线

从使用方式上，更推荐优先走高层 route workflow，而不是一开始就直接手填所有底层字段。

## 路径兼容性

在本地 stdio 模式下，`ppt-mcp` 现在会对常见路径做转换：

- Windows 路径，例如 `C:\Users\...\file.pdf`
- `\\wsl.localhost\发行版名\...` 路径

这使得 MCP 客户端在 Windows / WSL 混合环境下更容易把本地 PDF 路径传给 `ppt-mcp`。

## 参考仓库

- `ppt-mcp` 仓库：<https://github.com/ZiChuanLan/ppt-mcp>
- 当前文档站内的 `MCP Server PRD`：[/mcp-server-prd](/mcp-server-prd)
