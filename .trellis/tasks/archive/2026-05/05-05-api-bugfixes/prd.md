# fix: API 层高优先级 Bug 修复

## Goal

修复 API 层发现的高优先级 Bug，包括配额检查、API Key 泄露、竞态条件和内存问题。

## Requirements

### Bug 1: Quota 检查未生效
- **位置**: `api/app/routers/jobs.py:create_job`
- **问题**: `daily_task_limit` 和 `concurrent_task_limit` 在 User 模型中存在但未检查
- **修复**: 在 `create_job` 中添加配额检查逻辑

### Bug 2: API Key 泄露风险
- **位置**: `api/app/routers/jobs.py:create_job`
- **问题**: `api_key` 参数传递到 worker kwargs 中
- **修复**: 从 worker kwargs 中移除敏感信息

### Bug 3: Cleanup Daemon 竞态条件
- **位置**: `api/app/services/job_cleanup.py:96-100`
- **问题**: 挂起 24h 的任务可能被误删
- **修复**: 添加更安全的检查机制

### Bug 4: 内存中读取整个文件
- **位置**: `api/app/routers/jobs.py:991`
- **问题**: 大文件完全加载到内存
- **修复**: 使用流式写入

### Bug 5: `.env` 写入无备份
- **位置**: `api/app/routers/admin.py:PUT /admin/env`
- **问题**: 直接覆写无备份
- **修复**: 写入前创建备份

## Acceptance Criteria

- [ ] Quota 检查在 `create_job` 中生效
- [ ] API Key 不再出现在 worker kwargs 中
- [ ] Cleanup daemon 不会删除仍在处理的任务
- [ ] 大文件上传使用流式写入
- [ ] `.env` 写入前自动创建备份

## Technical Notes

- 研究文档：`.trellis/tasks/05-04-architecture-review/research/`
- 相关文件：`api/app/routers/jobs.py`, `api/app/services/job_cleanup.py`, `api/app/routers/admin.py`
