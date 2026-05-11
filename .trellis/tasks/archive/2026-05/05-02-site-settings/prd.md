# Site Settings & User Preferences System

## Goal

支持两种部署模式：自用模式（简单、localStorage）和公开模式（admin 配置全局 API key，用户独立偏好设置）。让用户开箱即用，不需要自己填 API key。

## Requirements

### 模式切换
- 新增环境变量 `DEPLOY_MODE`（`self` | `public`），默认 `self`
- API 提供 `/api/config/deploy-mode` 端点返回当前模式

### 自用模式（Self-use）
- 保持现有行为：所有设置存 localStorage
- 无配额限制
- 无需任何后端改动

### 公开模式（Public）

#### Admin 全局配置（site_settings 表）
- 新增 `site_settings` 表（key-value 结构）
- Admin 后台新增"站点设置"区域，可配置：
  - API keys（openai、siliconflow、claude、mineru token）
  - Base URLs
  - 默认 model
- Admin 可设置哪些设置项"允许用户覆盖"

#### 用户偏好（user_preferences 表）
- 新增 `user_preferences` 表（user_id + key-value）
- 用户可覆盖的偏好：provider、parseEngineMode、model 等（不含 API key）
- 设置页读取优先级：user_preferences → site_settings → built-in defaults

#### 设置页 UI
- API key 区域：显示但 disabled，附文字"由管理员统一配置"
- 偏好设置：正常可编辑
- 用户修改偏好后保存到 user_preferences 表

### 配额
- 自用模式：无配额
- 公开模式：保持现有 per-user 配额（daily_task_limit 等）

## Acceptance Criteria

- [ ] `DEPLOY_MODE=self` 时，设置页行为与现在完全一致
- [ ] `DEPLOY_MODE=public` 时，API key 区域灰色不可编辑，显示"由管理员统一配置"
- [ ] `DEPLOY_MODE=public` 时，用户可独立修改偏好设置（provider、引擎等）
- [ ] 用户偏好保存到 DB，刷新后保留
- [ ] Admin 可在后台编辑站点全局配置
- [ ] 新用户注册后自动继承 admin 配置，无需填 key

## Out of Scope

- 用户自带 API key（安全风险）
- 用户间设置共享/导入导出
- 自用模式的任何改动

## Technical Notes

- 当前设置系统：`web/src/lib/settings.ts`（582 行），`loadStoredSettings()` + `defaultSettings`
- 设置页：`web/src/app/settings/page.tsx`（2541 行），大量条件渲染
- 用户模型：`api/app/models/user.py`，已有 quota 字段
- 配置：`api/app/config.py`，使用 pydantic Settings
