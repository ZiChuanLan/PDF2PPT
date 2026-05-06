# 添加用户名密码登录

## Goal

在现有 LinuxDo OAuth 登录基础上，增加用户名/密码登录方式，让用户可以不依赖第三方平台进行身份验证。

## What I already know

- 当前系统仅支持 LinuxDo OAuth 登录
- 用户模型中 `linuxdo_id` 是 `unique=True, nullable=False`，需要改为 nullable
- JWT 令牌系统与认证方式无关，可直接复用
- 前端登录页只有一个 "使用 LinuxDo 登录" 按钮
- 数据库使用 SQLite，无密码字段

## Assumptions (temporary)

- 用户名/密码用户和 OAuth 用户可以共存
- 不需要邮箱验证（MVP 阶段）
- 不需要忘记密码功能（MVP 阶段）

## Open Questions

1. ~~是否需要同时支持邮箱+密码登录？还是只用用户名+密码？~~
2. ~~密码强度要求？~~ → 用户选择简单要求（最少 8 个字符）
3. ~~是否需要注册功能？~~ → 用户选择邀请码注册

## Requirements (evolving)

* 用户模型增加 `password_hash` 字段
* `linuxdo_id` 改为 nullable
* 添加密码哈希（bcrypt）
* 添加邀请码系统（管理员生成，用户注册时使用）
* 添加注册端点 `POST /api/v1/auth/register`（需要邀请码）
* 添加密码登录端点 `POST /api/v1/auth/login-password`
* 前端登录页默认显示密码表单，下方有 "使用 LinuxDo 登录" 链接
* 前端增加注册页面（需要输入邀请码）
* 管理员后台增加邀请码管理
* 保持 OAuth 登录功能不变
* 密码要求：最少 8 个字符

## Acceptance Criteria (evolving)

- [ ] 管理员可以生成邀请码
- [ ] 用户可以通过邀请码注册账号
- [ ] 用户可以通过用户名/密码登录
- [ ] 登录后 JWT 令牌正常工作
- [ ] 现有 OAuth 用户不受影响
- [ ] 邀请码使用后失效
- [ ] 邀请码有过期时间
- [ ] 密码最少 8 个字符

## Definition of Done

* 测试通过
* Lint / typecheck 通过
* 文档更新
* 可以正常部署

## Out of Scope (explicit)

* 邮箱验证
* 忘记密码/重置密码
* 第三方登录（除 LinuxDo 外）
* 双因素认证

## Technical Notes

* 用户模型在 `api/app/models/user.py`
* 认证逻辑在 `api/app/auth.py`
* 认证端点在 `api/app/routers/auth.py`
* 前端登录页在 `web/src/app/login/page.tsx`
* JWT 令牌系统可直接复用，无需修改
* 需要添加 `bcrypt` 依赖

## Technical Approach

### 后端

1. **用户模型修改**
   - `linuxdo_id` 改为 nullable
   - 添加 `password_hash` 字段（String, nullable）
   - 添加邀请码模型（code, created_by, used_by, expires_at, used_at）

2. **认证模块**
   - 添加 `hash_password()` 和 `verify_password()` 函数
   - 添加 `create_user_with_password()` 函数
   - 添加邀请码生成和验证函数

3. **API 端点**
   - `POST /api/v1/auth/register` — 使用邀请码注册
   - `POST /api/v1/auth/login-password` — 密码登录
   - `POST /api/v1/admin/invites` — 生成邀请码（管理员）
   - `GET /api/v1/admin/invites` — 列出邀请码（管理员）

### 前端

1. **登录页** (`web/src/app/login/page.tsx`)
   - 默认显示用户名/密码表单
   - 下方有 "使用 LinuxDo 登录" 链接
   - 表单验证（用户名长度、密码长度）

2. **注册页** (`web/src/app/register/page.tsx`)
   - 输入邀请码、用户名、密码、确认密码
   - 表单验证

3. **管理员邀请码管理** (`web/src/app/admin/invites/page.tsx`)
   - 生成邀请码
   - 查看邀请码列表和使用情况

## Decision (ADR-lite)

**Context**: 用户希望在 LinuxDo OAuth 之外增加密码登录方式
**Decision**: 采用邀请码注册 + 密码登录方案，保持 OAuth 不变
**Consequences**: 需要修改用户模型、添加邀请码系统、更新前端登录流程

## Implementation Plan

### Phase 1: 后端基础
1. 添加 `bcrypt` 依赖
2. 修改用户模型（`linuxdo_id` nullable, `password_hash`）
3. 添加邀请码模型
4. 添加密码哈希函数
5. 添加注册和密码登录端点
6. 添加管理员邀请码管理端点

### Phase 2: 前端实现
1. 更新登录页（密码表单 + OAuth 链接）
2. 创建注册页
3. 创建管理员邀请码管理页

### Phase 3: 测试和优化
1. 测试注册流程
2. 测试登录流程
3. 测试邀请码管理
4. 优化错误处理和用户体验

## Research References

* [`research/auth-system.md`](research/auth-system.md) — 现有认证系统完整分析
