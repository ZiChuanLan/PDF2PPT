# LinuxDo OAuth 登录与用户空间隔离

## Goal

为 PDF2PPT 添加 LinuxDo OAuth 登录，实现按用户隔离的任务空间，并提供 Admin 后台管理用户资源和配额。

## What I already know

- 当前项目**无用户模型**，所有任务全局共享（`job:{id}` 在 Redis 中无用户归属）
- Web 访问密码 (`WEB_ACCESS_PASSWORD`) 是唯一的访问控制，通过 Cookie SHA-256 验证
- API 有 Bearer Token (`API_BEARER_TOKEN`) 保护，但无用户概念
- 前端 Next.js，后端 FastAPI + Redis + RQ Worker
- 任务存储：Redis (`job:{id}`)，文件系统 `data/jobs/{id}/`
- 已有中间件模式：FastAPI middleware 检查 Bearer Token (`api_auth.py`)
- 前端用 `localStorage` 存储设置，`apiFetch` 封装 API 调用
- 任务生命周期：创建 → 处理 → 完成 → 24h 自动清理

## Research References

- [`research/linuxdo-oauth-api.md`](research/linuxdo-oauth-api.md) — LinuxDo OAuth 2.0 完整接口规范

## Assumptions (validated)

- LinuxDo OAuth 2.0 基于标准 Authorization Code 流程
- 授权端点: `https://connect.linux.do/oauth2/authorize`
- Token 端点: `https://connect.linux.do/oauth2/token`
- 用户信息端点: `https://connect.linux.do/api/user`
- Scope: `user`（获取 id, username, name, avatar_template, trust_level 等）
- Token 有效期 1 小时，推荐 5 分钟缓存用户信息
- 需要在 connect.linux.do 自助注册应用获取 client_id/client_secret

## Decision (ADR-lite)

**Context**: 需要选择用户数据持久化方案
**Decision**: 使用 SQLite（零运维，单文件，Docker volume 持久化）
**Consequences**: 单实例部署简单，未来若需多实例可迁移到 PostgreSQL

## Open Questions

（无，全部已确认）

## Requirements (evolving)

### 用户认证
- [ ] LinuxDo OAuth 2.0 登录流程（Authorization Code）
- [ ] JWT Session 管理（access_token + refresh_token）
- [ ] 登录状态持久化（Cookie + 前端状态）
- [ ] 未登录用户重定向到登录页

### 用户模型
- [ ] SQLite 存储用户信息（id, linuxdo_id, username, avatar, role, trust_level）
- [ ] 角色：user / admin
- [ ] 用户信息缓存（5 分钟）

### 任务隔离
- [ ] Job 模型添加 user_id 外键
- [ ] Redis job 数据添加 user_id 字段
- [ ] 用户只能查看/管理自己的任务
- [ ] 前端任务列表按用户过滤

### Admin 管理
- [ ] /admin 页面（内嵌在现有 UI）
- [ ] 用户列表：显示用户名、任务数、存储使用、状态
- [ ] 用户详情：查看单用户的所有任务
- [ ] 配额管理：设置每个用户的限制
- [ ] 用户状态管理：禁用/启用用户

### 配额系统
- [ ] 每日任务数限制（默认 10/天）
- [ ] 最大文件大小限制（默认 100MB）
- [ ] 并发任务数限制（默认 2 个）
- [ ] 配额超限提示

## Acceptance Criteria (evolving)

- [x] 用户可通过 LinuxDo OAuth 登录
- [x] 登录后只能看到自己的任务
- [x] 未登录用户无法创建任务
- [x] Admin 可查看用户列表和资源使用情况
- [x] Admin 可设置每个用户的配额上限
- [x] 超出配额的用户无法创建新任务并收到提示
- [x] 任务取消/删除只能操作自己的任务
- [x] 现有 Web 访问密码机制可与 OAuth 共存（可配置关闭）

## Definition of Done

- 单元测试覆盖核心逻辑
- Lint / typecheck 通过
- 文档更新（README、部署说明）
- 向后兼容：现有部署可平滑升级

## Out of Scope (待确认)

- 多租户远程 MCP 支持（Phase 2 MCP 单独考虑）
- 用户注册/密码登录（仅 OAuth）
- 复杂的 RBAC 权限系统（仅 user / admin 两级）

## Technical Notes

- 当前项目无 ORM，Redis 直接存储 job 数据
- 前端 auth 需要与 Next.js middleware 配合（unlock 页面已有模式）
- LinuxDo OAuth 需要研究其 API 文档
