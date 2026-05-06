# feat: 文件存储优化和缓存清理

## Goal

优化文件存储机制，添加缓存清理，防止存储无限增长。

## Requirements

### 1. 流式文件上传
- **当前**: `await file.read()` 完全加载到内存
- **目标**: 流式写入磁盘

### 2. Paddle 模型缓存清理
- **当前**: 缓存无限增长
- **目标**: 添加缓存大小限制或定期清理

### 3. `ir.parsed.json` 清理
- **当前**: 中间文件未清理
- **目标**: 在 cleanup 阶段删除

### 4. 磁盘空间预检查
- **位置**: 上传前
- **目标**: 检查可用空间是否足够

## Acceptance Criteria

- [ ] 大文件上传使用流式写入
- [ ] Paddle 模型缓存有清理机制
- [ ] `ir.parsed.json` 在 cleanup 时删除
- [ ] 上传前检查磁盘空间

## Technical Notes

- 文件上传: `api/app/routers/jobs.py`
- Worker 清理: `api/app/worker.py`
- 清理守护进程: `api/app/services/job_cleanup.py`
