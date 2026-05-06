# Frontend UX Redesign — 商业化重构

## Goal

从架构链路和使用者角度全面重构前端 UI/UX，使其更商业化、更易用，同时保持简洁美观。

## Current Problems (架构分析)

### 首页问题

当前首页 (`page.tsx`, 1241 行) 混合了太多职责：

1. **上传 + 配置 + 执行** — 左侧区域
2. **配置概览** — 右上卡片（只是设置页的摘要，信息价值低）
3. **任务状态** — 右下卡片（实时轮询，但和"创建"流程混在一起）
4. **任务列表** — 底部表格（历史记录，与当前任务无关）

**核心矛盾**：首页同时承担了"创建新任务"和"查看历史任务"两个完全不同的用户目标。

### 数据流问题

```
当前数据流：
Settings (localStorage) → resolveRunConfig() → buildJobConfig() → POST /jobs/v2
                                                                    ↓
                                              JobStatus (轮询 GET /jobs/{id})
                                                                    ↓
                                              JobList (轮询 GET /jobs?limit=50)
```

- 首页轮询两个不同的 endpoint（任务状态 + 任务列表），资源浪费
- 配置概览卡片只是读 localStorage 显示，没有独立价值
- 任务状态和任务列表有重叠信息

### 用户旅程问题

**当前旅程（太长）**：
1. 上传文件
2. 看预览
3. 设置页码范围
4. 选择 PPT 模式
5. 看配置概览（低价值）
6. 看任务状态（混合）
7. 看任务列表（混合）

**理想旅程（聚焦）**：
1. 上传文件 → 即时反馈
2. 快速配置（最重要的 2-3 个选项）
3. 一键转换
4. 进度追踪 + 下载

### 设置页问题

- 2545 行单文件，90+ 配置项平铺
- 没有分组折叠
- 没有"常用"vs"高级"区分
- API Key 等敏感信息和普通配置混在一起

## What I Already Know

### 技术栈
- Next.js 15 + React + Tailwind CSS + shadcn/ui
- 设计语言：编辑器/报纸风（直角、新闻纸纹理、serif 字体）
- 颜色：纯黑白 + 红色强调 (#cc0000)
- 圆角：0px（全直角）

### API 能力
- `POST /jobs/v2` — 创建任务（file + JSON config）
- `GET /jobs/{id}` — 任务状态（status, progress, stage, message, debug_events）
- `GET /jobs?limit=50` — 任务列表
- `GET /jobs/{id}/download` — 下载 PPTX
- `POST /jobs/{id}/cancel` — 取消任务
- `DELETE /jobs/{id}` — 删除任务

### 现有组件
- shadcn/ui: Button, Card, Badge, Input, Select, Progress, HoverHint
- 自定义: PdfCanvasPreview, JobDebugPanel, UploadSessionProvider
- 导航: WorkbenchNav (sticky top bar)

## Requirements (evolving)

### 首页重构 — 三阶段单页体验

基于调研：所有竞品都采用"上传区为核心 + 零配置转换 + 实时进度反馈"模式。

**阶段一：上传（空状态）**
- Hero 上传区占首屏 70%+，大尺寸拖放区
- 拖拽时有视觉反馈（边框变色、微缩放）
- 下方显示支持格式 + 文件大小限制
- 右侧或下方：2-3 个快速配置（PPT 生成模式、OCR 方式）
- "高级设置" 链接跳转设置页

**阶段二：预览 + 配置（已上传）**
- 保持双列布局：左 PDF 预览 + 右配置/信息
- 左侧：PDF 预览（保留现有 PdfCanvasPreview）
- 右侧：文件信息 + 页码范围 + 快速配置
- 底部：醒目的"开始转换"按钮
- 保留"单页试跑"快捷按钮

**阶段三：进度 + 下载（转换中/完成）**
- 进度区域占据主视觉，用**步骤式进度指示器**（圆圈 + 连线）
- 每个阶段有清晰的中文标签和完成状态
- 完成后：大尺寸下载按钮 + 微动效（如颜色渐变）
- 失败时：错误信息 + 重试按钮

**移出首页**：
- 任务历史列表 → 独立 `/jobs` 页面（卡片式布局）
- 配置概览卡片 → 删除（信息价值低）
- 队列统计 → 移到任务状态区域的小角落

### 视觉升级

- **圆角**：保持 0px 直角风格（用户选择保持编辑器风格）
- **背景**：保持新闻纸纹理
- **卡片**：保持当前卡片样式，但优化间距和层次
- **字体**：保持 serif 标题 + sans 正文
- **品牌**：改为 "PDF2PPT"（简洁直观）
- **进度指示器**：圆圈 + 连线的步骤式进度（而非简单格子）

### 设置页重构

- 分组折叠（Accordion 组件）
- 常用配置优先展示（默认展开）
- 高级配置默认收起
- API Key 等敏感信息用密码输入框 + 显示/隐藏切换
- 内联验证（错误信息在字段下方显示）

### 任务管理

- 任务列表移到独立 `/jobs` 页面
- 每个任务卡片式展示（而非表格行）
- 支持批量操作（批量删除、批量下载）
- 状态筛选（全部/进行中/已完成/失败）

## Open Questions

1. **品牌命名**：用什么产品名？（当前"PDF 编排台"偏技术化）
2. **首页布局**：单列（更聚焦）vs 双列（信息密度高）？
3. **任务历史**：独立页面 vs 首页侧边栏 vs 首页底部折叠面板？
4. **视觉风格**：保持编辑器风格（直角、报纸纹理）vs 转向更现代的风格（圆角、微渐变）？

## Decision (ADR-lite)

**Context**: 需要决定首页布局、任务历史位置、视觉风格、品牌名
**Decision**:
- 首页保持双列布局（左预览+右配置）
- 任务历史移到独立 `/jobs` 页面
- 保持直角视觉风格（0px 圆角、新闻纸纹理）
- 品牌名改为 "PDF2PPT"

**Consequences**: 保持现有视觉风格降低改动量，任务历史独立后首页更聚焦

## Acceptance Criteria (evolving)

- [ ] 首页只展示上传 + 配置 + 转换 + 进度，不混合任务列表
- [ ] 上传区域更大、更醒目，有拖拽反馈动效
- [ ] 快速配置只展示 2-3 个关键选项（PPT 模式、OCR 方式）
- [ ] 转换进度用步骤式进度指示器（圆圈+连线）展示
- [ ] 完成后下载按钮醒目
- [ ] 任务历史移到独立 `/jobs` 页面（卡片式布局）
- [ ] 设置页分组折叠（Accordion），常用配置优先
- [ ] API Key 等敏感信息用密码输入框 + 显示/隐藏切换
- [ ] 品牌名改为 "PDF2PPT"
- [ ] 保持直角视觉风格不变

## Out of Scope

- 不重构后端 API
- 不添加新功能（只优化现有功能的 UX）
- 不做完整的移动端适配（只确保基本可用）
- 不做国际化（保持中文）

## Technical Notes

### Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `web/src/app/page.tsx` | 1241 | 首页（上传+配置+状态+列表） |
| `web/src/app/settings/page.tsx` | 2545 | 设置页 |
| `web/src/app/globals.css` | 653 | 全局样式 |
| `web/src/components/workbench-nav.tsx` | 143 | 顶部导航 |
| `web/src/app/layout.tsx` | 43 | 根布局 |
| `web/src/lib/run-config.ts` | — | 运行配置解析 |
| `web/src/lib/settings.ts` | 582 | 设置类型定义 |
| `web/src/lib/job-status.ts` | — | 任务状态类型 |

### Design System

当前使用的 shadcn/ui 组件：
- Button, Card, Badge, Input, Select, Progress
- HoverHint (自定义)
- PdfCanvasPreview (自定义)
- JobDebugPanel (自定义)

### Constraints

- 保持 shadcn/ui 组件库（不引入新 UI 库）
- 保持 Tailwind CSS（不引入新样式方案）
- 保持现有 API 接口不变
- 保持现有功能完整（不删除功能，只重新组织）
