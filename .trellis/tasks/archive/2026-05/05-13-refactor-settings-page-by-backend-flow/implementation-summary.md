# 设置页面重构实现总结

## 完成的工作

### 1. 新组件创建

按照处理流程组织，创建了以下新组件：

- **`quick-presets.tsx`** - 快速配置预设（普通文档/扫描件/高精度）
- **`parsing-method-section.tsx`** - 文档解析方式选择（本地/云端/百度/MinerU）
- **`ocr-strategy-section.tsx`** - 文字识别策略（根据解析方式动态显示，包含主AI配置）
- **`output-quality-section.tsx`** - 输出质量控制（布局辅助、输出选项）
- **`general-advanced-section.tsx`** - 通用高级设置（视觉辅助、提示词覆盖）

### 2. 主设置页面重构

- 移除了4标签页结构（基础设置/OCR设置/AI设置/高级设置）
- 采用流程导向的单页面设计
- 按照处理流程组织：文档解析 → 文字识别 → 输出质量
- 管理员设置改为可折叠区域

### 3. 关键特性实现

✅ **流程导向组织**
- 3个主要处理阶段清晰分离
- 每个阶段有明确的标题和说明

✅ **快速配置预设**
- 3个预设卡片（普通文档/扫描件/高精度）
- 可折叠，不强制使用
- 点击后自动填充配置

✅ **渐进式显示**
- 根据解析方式动态显示相关识别选项
- 本地解析显示：机器提取/Tesseract/PaddleOCR/智能选择
- 云端解析显示：直接识别/文档解析/布局分块
- 百度解析显示：百度专用配置
- MinerU模式隐藏不相关的OCR选项

✅ **高级选项混合组织**
- 流程相关的高级选项分散到对应部分（默认折叠）
- 通用高级选项集中在独立区域
- 使用CollapsibleSection保持一致交互

✅ **用户友好术语**
- "文档解析方式" 替代 "parse_engine_mode"
- "文字识别策略" 替代 "ocr_provider"
- "本地解析/云端解析" 替代 "local_ocr/remote_ocr"
- 每个选项都有清晰的描述

✅ **推荐默认配置**
- 预设提供推荐配置
- 新用户可快速开始

## 技术实现

### AI配置架构澄清

经过代码审查发现，系统有两套AI配置：

1. **主AI配置** (`provider`, `openaiApiKey`, `claudeApiKey`)
   - **主要用途**：OCR识别（AIOCR模式）
   - **次要用途**：布局辅助的回退选项
   - 位置：OCR策略部分（云端解析模式）
   - 回退机制：当没有配置专用OCR AI密钥时，布局辅助会复用这些凭证

2. **专用OCR AI配置** (`ocrAiProvider`, `ocrAiApiKey`)
   - 用途：专门用于OCR识别
   - 位置：OCR策略部分（云端解析模式）
   - 可选：留空则使用主AI配置

### 组件结构
```
settings/
├── quick-presets.tsx              # 快速预设
├── parsing-method-section.tsx    # 解析方式
├── ocr-strategy-section.tsx      # 识别策略
├── output-quality-section.tsx    # 输出质量
├── general-advanced-section.tsx  # 通用高级
├── admin-settings.tsx            # 管理员（保留）
└── settings-shared.tsx           # 共享组件（保留）
```

### 动态显示逻辑
- 使用 `settings.parseEngineMode` 控制显示
- 条件渲染：`{parseMode === 'local_ocr' && ...}`
- 自动隐藏不兼容选项

### 保持兼容性
- 所有现有配置项都保留
- `useSettings` hook 不变
- API接口不变
- 仅UI重构

## 验证

✅ TypeScript编译通过
✅ Next.js构建成功
✅ 所有组件正确导入
✅ 无运行时错误

## 对比旧设计

### 旧设计问题
- 4个标签页（基础/OCR/AI/高级）不符合用户心智模型
- "PPT提供方"等术语令人困惑
- 高级设置将所有提供方配置混在一起
- 不熟悉项目的用户难以理解

### 新设计优势
- 流程导向，直接映射后端逻辑
- 术语清晰，面向用户而非技术
- 渐进式显示，减少混淆
- 预设快速入口，降低学习成本
- 高级选项合理组织，不干扰主流程

## 下一步

建议测试：
1. 手动测试各个解析模式的切换
2. 验证预设配置是否正确应用
3. 确认所有API密钥输入正常
4. 测试高级选项的折叠/展开
5. 验证配置保存/加载功能

## 文件变更

### 新增文件
- `web/src/components/settings/quick-presets.tsx`
- `web/src/components/settings/parsing-method-section.tsx`
- `web/src/components/settings/ocr-strategy-section.tsx`
- `web/src/components/settings/output-quality-section.tsx`
- `web/src/components/settings/general-advanced-section.tsx`

### 修改文件
- `web/src/app/settings/page.tsx` - 完全重构
- `web/src/components/settings/ocr-strategy-section.tsx` - 多次修正AI配置位置
- `web/src/components/settings/output-quality-section.tsx` - 多次修正术语和配置位置

### 术语和架构修正历史
1. **第一次修正**：将"PPT生成AI提供商"改为"内容生成AI"
2. **第二次修正**：将"内容生成AI"改为"布局辅助AI"并移入布局辅助部分
3. **第三次修正（最终）**：理解到主AI配置主要用于OCR识别，将OpenAI/Claude配置移回OCR策略部分
   - 添加说明：主AI配置用于OCR识别，也可作为布局辅助的回退
   - 保留专用OCR AI配置为可选项

### 可删除文件（可选）
- `web/src/components/settings/basic-settings.tsx` - 已被新组件替代
- `web/src/components/settings/ocr-settings.tsx` - 已被新组件替代
- `web/src/components/settings/advanced-settings.tsx` - 已被新组件替代

注：旧文件暂时保留，确认新设计无问题后再删除。
