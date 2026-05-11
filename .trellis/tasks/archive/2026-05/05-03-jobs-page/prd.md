# PRD: Create Jobs Page for Job History Management

## Overview

Create a new `/jobs` page to replace the job history table that was removed from the homepage. This page will display job history as cards with filtering, batch operations, and auto-refresh capabilities.

## Requirements

### 1. New Page: `web/src/app/jobs/page.tsx`

- **Job list displayed as cards** (not table rows)
- Each card shows:
  - Job ID
  - Status badge
  - Progress bar
  - Stage information
  - Created time
  - File name (if available)
- **Action buttons per card**:
  - 跟踪 (track)
  - 下载 (download) - if completed
  - 取消 (cancel) - if pending/processing
  - 删除 (delete) - if terminal state
- **Status filter tabs**: 全部 / 进行中 / 已完成 / 失败
- **Batch operations**:
  - Select multiple jobs with checkboxes
  - "全选" (select all) checkbox at top
  - "批量删除" (batch delete) button when items selected
  - Confirmation before batch delete
- **Auto-refresh**: Polling for jobs in non-terminal state
- **Empty state**: Message when no jobs

### 2. Update Navigation: `web/src/components/workbench-nav.tsx`

- Add "任务记录" link to `/jobs` in the navigation

### 3. Data Source

Use existing API endpoints:
- `GET /api/v1/jobs?limit=50` — fetch job list
- `DELETE /api/v1/jobs/{id}` — delete a job
- `POST /api/v1/jobs/{id}/cancel` — cancel a job
- `GET /api/v1/jobs/{id}/download` — download PPTX

Use `apiFetch` from `@/lib/api` for all API calls.

### 4. Job Card Design

```
┌─────────────────────────────────────────────┐
│ [状态徽章]  任务号: abc123                    │
│                                             │
│ 进度: ████████░░░░░░░░ 45%                  │
│ 阶段: OCR 识别中                             │
│ 创建: 2026-05-03 14:30                      │
│                                             │
│ [跟踪] [下载] [取消] [删除]                   │
└─────────────────────────────────────────────┘
```

### 5. Status Filter

Use simple button tabs (not a Tabs component):
- "全部" — show all jobs
- "进行中" — filter status === "pending" || "processing"
- "已完成" — filter status === "completed"
- "失败" — filter status === "failed"

### 6. Batch Operations

- Checkbox on each card
- "全选" checkbox at the top
- "批量删除" button appears when items selected
- Confirmation before batch delete

### 7. Existing Code to Reuse

From `web/src/app/page.tsx` (the old homepage):
- `normalizeJobListResponse` from `@/lib/job-status`
- `JOB_STATUS_LABELS`, `JOB_STAGE_LABELS` from `@/lib/job-status`
- `apiFetch` from `@/lib/api`
- `formatBytes` (if needed)
- `toast` from `sonner`

## Technical Constraints

- Use existing shadcn/ui components: Button, Card, Badge, Input, Progress
- Use existing patterns from the codebase
- Do NOT add new npm packages
- Keep the same visual style (editorial/newspaper theme, 0px corners, monospace + red accent)

## Acceptance Criteria

- [ ] `/jobs` 页面可以正常访问
- [ ] 任务列表以卡片形式展示，包含状态徽章、进度条、阶段信息、创建时间
- [ ] 每个卡片有跟踪、下载、取消、删除按钮（根据状态显示/隐藏）
- [ ] 状态筛选标签（全部/进行中/已完成/失败）正常工作
- [ ] 批量选择和批量删除功能正常工作
- [ ] 删除前有确认提示
- [ ] 自动刷新正常工作（进行中的任务自动轮询）
- [ ] 空状态显示友好提示
- [ ] 导航栏显示"任务记录"链接

## Definition of Done

- TypeScript 编译通过 (`npx tsc --noEmit`)
- 构建通过 (`npm run build`)
- 代码遵循现有项目风格（editorial/newspaper 主题，0px corners，monospace + red accent）
- 不添加新的 npm 依赖

## Out of Scope

- 分页功能（当前限制 50 条）
- 搜索/过滤功能（仅状态筛选）
- 任务详情页（仅列表视图）
- 导出任务历史

## Technical Notes

- 复用 `web/src/app/page.tsx` 中的 `normalizeJobListResponse`、`JOB_STATUS_LABELS`、`JOB_STAGE_LABELS`
- 复用 `@/lib/api` 中的 `apiFetch`
- 使用 shadcn/ui 组件：Button、Card、Badge、Progress
- 参考 `workbench-nav.tsx` 的导航样式

## Verification

After making changes:
1. Run `cd web && npx tsc --noEmit` to verify TypeScript
2. Run `cd web && npm run build` to verify the build passes

## File to Create

`web/src/app/jobs/page.tsx` — approximately 300-400 lines
