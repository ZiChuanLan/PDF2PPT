# 首次部署安装向导 (Setup Wizard)

## Goal

为首次部署用户提供 Step-by-Step 安装向导。首次访问时阻断式引导：选择部署模式、创建管理员账号，完成后自动登录进入系统。API key 等业务配置不在向导中处理，进入系统后去设置页面按需配置。

## Requirements

### 前端
- [ ] 新增 `/setup` 页面，全屏 Step 向导（非弹窗）
- [ ] Step 1：欢迎页，介绍项目
- [ ] Step 2：选择部署模式（self / public），卡片式选择
- [ ] Step 3：创建管理员账号（用户名 + 密码 + 确认密码）
- [ ] Step 4：完成页，显示"正在进入系统..."
- [ ] 顶部显示步骤进度条
- [ ] 已有用户时访问 /setup → 重定向到首页

### 后端
- [ ] `GET /api/v1/setup/status` — 检查是否需要初始化（返回 `{ needs_setup: bool }`）
- [ ] `POST /api/v1/setup/complete` — 一次性完成设置（deploy_mode + admin 账号），返回 user + tokens
- [ ] deploy_mode 写入 `site_settings` 表（DB 优先，env 作 fallback）
- [ ] 创建管理员账号写入 `users` 表
- [ ] 完成后设置 auth cookies，返回用户信息

### 路由/重定向（方案 3：不改 middleware）
- [ ] `/setup` 路径加入 middleware allowlist（无需认证）
- [ ] middleware 保持现状，未认证用户仍重定向到 /login
- [ ] login 页面内部调 `GET /api/v1/setup/status`，如果 needs_setup=true 则 `router.replace("/setup")`
- [ ] setup 页面内部也检查 status，已完成则重定向首页

### 与现有功能的关系
- [ ] self-mode 的 auto-login 逻辑保持不变（向导完成后走正常 auto-login）
- [ ] public-mode 下向导完成后走正常 login 流程
- [ ] `/auth/auto-login` 端点需要适配：如果无用户且不在 self-mode，不应自动创建 admin

## Acceptance Criteria

- [ ] 全新部署（空数据库）访问 `http://localhost:3000` → 重定向到 /setup
- [ ] 向导 3 步完成（欢迎 → 选模式 → 建账号）→ 自动登录 → 首页
- [ ] 选择 self-mode → 后续访问自动登录（现有行为）
- [ ] 选择 public-mode → 后续访问需手动登录
- [ ] 已有用户时访问 /setup → 重定向到首页
- [ ] deploy_mode 写入 DB，重启后保持
- [ ] 管理员可在站点配置页面修改 deploy_mode

## Definition of Done

- 前后端代码完成
- Docker 构建成功
- 全新部署流程手动验证通过
- 已有部署不受影响（auto-login 等现有功能正常）

## Out of Scope

- 向导中配置 API key
- 向导的多语言支持
- 向导跳过功能
- 修改环境变量方式
- 欢迎页的复杂内容（保持简单）

## Technical Approach

### 数据流
```
首次访问 → middleware 未检测到 cookie → 重定向到 /login
→ login 页面调 GET /setup/status → needs_setup=true
→ router.replace("/setup") → 用户填写 → POST /setup/complete
→ 写 site_settings.deploy_mode + 创建 admin user
→ 设置 cookies → 重定向首页
```

### 关键决策
- deploy_mode 存 `site_settings` 表，`get_settings()` 读取时 DB 优先、env fallback
- `/setup/status` 用 `users` 表记录数判断是否需要初始化
- `/setup/complete` 事务性：先写 deploy_mode，再创建用户，再设 cookies
- **不改 middleware 核心逻辑**，仅添加 /setup 到 allowlist。login 页面作为"路由器"判断该去 /setup 还是显示登录表单

### 需要修改的文件
- `web/src/app/setup/page.tsx` — 新增向导页面
- `web/src/app/login/page.tsx` — 添加 setup 状态检测 + 重定向
- `web/src/middleware.ts` — 仅添加 /setup 到 allowlist（一行改动）
- `api/app/routers/setup.py` — 新增 setup API router
- `api/app/routers/__init__.py` — 注册 setup_router
- `api/app/main.py` — 挂载 setup_router
- `api/app/config.py` — deploy_mode 读取逻辑改为 DB 优先
- `api/app/routers/auth.py` — auto-login 适配（无用户且非 self-mode 不自动创建）

## Technical Notes

- 现有 `site_settings` 表已存在，直接复用
- 现有 `create_user_with_password()` 函数可复用
- 现有 middleware allowlist 模式清晰，添加路径即可
- 无 Dialog 组件，使用全屏页面方案
