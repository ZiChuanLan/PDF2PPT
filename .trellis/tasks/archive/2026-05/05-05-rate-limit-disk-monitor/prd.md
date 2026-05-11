# feat: Rate Limiting 和磁盘监控

## Goal

添加 API rate limiting 和磁盘空间监控，防止滥用和磁盘满导致的服务崩溃。

## Requirements

### 1. Rate Limiting
- **位置**: 所有 API 端点
- **实现**: 添加 rate limiter middleware
- **配置**: 可配置的请求频率限制

### 2. 磁盘空间监控
- **位置**: 上传前检查
- **实现**: 在 `create_job` 中添加磁盘空间检查
- **阈值**: 可配置的最低磁盘空间

## Acceptance Criteria

- [ ] API 端点有 rate limiting 保护
- [ ] 上传前检查磁盘空间
- [ ] 磁盘空间不足时返回明确错误
- [ ] Rate limiting 配置可通过环境变量调整

## Technical Notes

- FastAPI middleware: `api/app/main.py`
- 文件上传: `api/app/routers/jobs.py`
- 配置: `api/app/config.py`
