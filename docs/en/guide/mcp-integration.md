# MCP Integration

## What `ppt-mcp` Is

`ppt-mcp` is the MCP access layer for the current `PDF2PPT` service.

It does not reimplement:

- PDF parsing
- OCR
- PPT generation

Instead, it wraps the existing `PDF2PPT` API as MCP tools so that Claude Desktop, Cursor, Codex CLI, and similar clients can call it directly.

In one line:

```text
MCP Client -> ppt-mcp -> PDF2PPT API -> worker
```

## Where It Fits in the System

- the main `PDF2PPT` service provides the conversion core
- `ppt-mcp` provides MCP protocol adaptation and tool wrapping
- the relationship is service + integration layer, not two parallel implementations

If this docs site describes the whole `PDF2PPT` system, `ppt-mcp` should be treated as one of its modules.

## When To Use Web vs MCP

Use the Web UI when:

- you want to upload PDFs manually
- you want interactive parameter control
- you want a human-driven job tracking and download flow

Use `ppt-mcp` when:

- you want AI clients to call conversion directly
- you want to package the flow of upload -> create job -> poll status -> download result into MCP tools
- you want to integrate conversion into automation workflows

## Recommended Usage Modes

### 1. Local stdio MCP, the simplest and most stable

This is the recommended default mode.

- the `PDF2PPT` service runs locally
- `ppt-mcp` also runs locally
- MCP transport uses `stdio`
- `PPT_API_BASE_URL` points to `http://127.0.0.1:8000`

In this mode:

- browser users go through the Web UI
- MCP users go through the local API
- the two paths remain cleanly separated

### 2. Local stdio MCP connected to a remote PDF2PPT service

Useful when:

- the AI client runs locally
- but the conversion service is deployed remotely

In this mode:

- `PPT_API_BASE_URL` points to the remote service root
- `ppt-mcp` still runs locally
- local PDFs are read by `ppt-mcp` and then uploaded to the remote API

### 3. Remote `ppt-mcp-remote`

This mode is closer to deploying the MCP service itself on a server.

Useful when:

- a team needs shared access
- you want one MCP endpoint
- you need Streamable HTTP MCP

But it is also more complex:

- it needs separate entry authentication
- it has to handle upload sources
- it has to handle downloads, permissions, and public exposure

## Address and Auth Rules

### How `PPT_API_BASE_URL` Should Be Written

It should point to the `PDF2PPT` service root, not to `/api/v1`.

Correct examples:

```bash
PPT_API_BASE_URL=http://127.0.0.1:8000
```

or:

```bash
PPT_API_BASE_URL=https://ppt.example.com
```

Do not write:

```bash
PPT_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

And do not use the Web entry by default:

```bash
PPT_API_BASE_URL=http://127.0.0.1:3000
```

That path is usually affected by `WEB_ACCESS_PASSWORD`.

### Bearer Token Mapping

If the main service uses:

```bash
API_BEARER_TOKEN=your-shared-secret
```

then `ppt-mcp` should also use:

```bash
PPT_API_BEARER_TOKEN=your-shared-secret
```

In practice:

- `API_BEARER_TOKEN` is the password required by the main API
- `PPT_API_BEARER_TOKEN` is what `ppt-mcp` sends when calling that API

Those two values usually need to match.

## Common Environment Variables

Minimum for local stdio mode:

```bash
PPT_API_BASE_URL=http://127.0.0.1:8000
PPT_API_TIMEOUT_SECONDS=120
```

If the main API uses Bearer auth, also add:

```bash
PPT_API_BEARER_TOKEN=your-shared-secret
```

Common variables include:

| Variable | Meaning |
| --- | --- |
| `PPT_API_BASE_URL` | `PDF2PPT` service root, without `/api/v1` |
| `PPT_API_TIMEOUT_SECONDS` | API timeout used by `ppt-mcp` |
| `PPT_API_BEARER_TOKEN` | Bearer token for direct API access |
| `MINERU_API_TOKEN` | MinerU cloud parsing token |
| `BAIDU_API_KEY` | Baidu document parsing key |
| `BAIDU_SECRET_KEY` | Baidu document parsing secret |
| `SILICONFLOW_API_KEY` | API key for remote vision/OCR models |

Extra variables for `ppt-mcp-remote` include:

| Variable | Meaning |
| --- | --- |
| `PPT_MCP_BIND_HOST` | Bind host for the remote MCP server, default `0.0.0.0` |
| `PPT_MCP_BIND_PORT` | Remote MCP port, default `8080` |
| `PPT_MCP_PUBLIC_BASE_URL` | Public base URL of the remote MCP server |
| `PPT_MCP_SERVER_TOKEN` | Entry token for the remote MCP server |

## Install and Run

Start the main service first:

```bash
docker compose up -d --build api worker redis
```

Then install and run `ppt-mcp`:

```bash
cd /home/lan/workspace/ppt-mcp
uv sync
uv run ppt-mcp
```

For remote MCP mode:

```bash
cd /home/lan/workspace/ppt-mcp
export PPT_API_BASE_URL=http://127.0.0.1:8000
export PPT_MCP_PUBLIC_BASE_URL=https://your-mcp.example.com
export PPT_MCP_SERVER_TOKEN=change-me
uv run ppt-mcp-remote
```

## Current Tool Coverage

`ppt-mcp` already covers the common task flow of the main service, including:

- route discovery and confirmation
- job creation
- job status checks
- job listing
- cancellation
- result download
- artifact access
- model listing
- AI OCR route checks

In practice, high-level route workflows are recommended over filling raw low-level fields from the start.

## Path Compatibility

In local stdio mode, `ppt-mcp` already converts common path formats such as:

- Windows paths like `C:\Users\...\file.pdf`
- `\\wsl.localhost\distro-name\...` paths

This makes it easier for MCP clients to pass local PDF paths in mixed Windows / WSL environments.

## References

- `ppt-mcp` repository: <https://github.com/ZiChuanLan/ppt-mcp>
- `MCP Server PRD` inside this docs site: [/mcp-server-prd](/mcp-server-prd)
