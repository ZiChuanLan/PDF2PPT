# feat: 前端 SSE 迁移和错误处理优化

## Goal

将前端从轮询迁移到 SSE 实时更新，优化错误处理和用户体验。

## Requirements

### 1. SSE 迁移
- **当前**: 每 2 秒轮询 `GET /jobs/{id}`
- **目标**: 使用后端已有的 SSE 端点 `/jobs/{id}/events`
- **优势**: 实时更新、减少请求量、更好的用户体验

### 2. Poll 错误处理
- **当前**: 轮询错误被空 catch 吞没
- **目标**: 添加错误状态显示和重试机制

### 3. 上传进度指示
- **当前**: 无上传进度
- **目标**: 添加上传进度条

### 4. 下载并行化
- **当前**: `handleDownloadAll` 串行下载
- **目标**: 使用 `Promise.all` 并行下载

## Acceptance Criteria

- [ ] 前端使用 SSE 接收任务状态更新
- [ ] 轮询错误有明确的用户反馈
- [ ] 上传过程有进度指示
- [ ] 多文件下载并行执行

## Technical Notes

- SSE 端点: `GET /api/v1/jobs/{id}/events`
- 前端文件: `web/src/app/page.tsx`
- API 客户端: `web/src/lib/api.ts`
