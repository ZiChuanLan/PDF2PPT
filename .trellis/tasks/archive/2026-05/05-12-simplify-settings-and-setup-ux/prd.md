# Simplify Settings Page and Setup Wizard UX

## Goal

Improve user experience by simplifying the overwhelming settings page (2809 lines, 50+ config fields) and streamlining the 6-step setup wizard. Add job presets to reduce configuration friction for common use cases.

**Why**: Current UX analysis revealed that new users are overwhelmed by configuration complexity, and power users waste time reconfiguring the same settings for each job.

## What I Already Know

From code review and UX analysis:

**Settings Page Issues**:
- 2809 lines in `web/src/app/settings/page.tsx`
- 50+ configuration fields on a single page
- No progressive disclosure or grouping
- Complex dependencies between fields (e.g., AIOCR requires 10+ sub-fields)
- No validation until job submission
- Changes on upload page don't persist to main settings

**Setup Wizard Issues**:
- 6 steps: Welcome → Deploy Mode → Create Admin → Model Detection → Layout Model → Complete
- Steps 1 (welcome) and 6 (complete) are just text
- Model detection step confuses users
- No clear explanation of what models do
- Deploy mode choice is permanent (no way to change later)

**Missing Features**:
- No job presets/templates
- No "Quick Setup" wizard for first-time users
- No settings validation on save

**Existing Patterns**:
- Settings stored in localStorage (`SETTINGS_STORAGE_KEY`)
- Complex migration logic (400+ lines) for backward compatibility
- Parse engine modes: local_ocr, remote_ocr, baidu_doc, mineru_cloud
- Provider options: OpenAI, Claude, MinerU

## Assumptions (Temporary)

- Users fall into 3 categories: beginners (need guidance), intermediate (want presets), power users (want full control)
- Most users use 2-3 common configurations repeatedly
- Settings can be grouped into Basic/OCR/Advanced without breaking functionality
- Job presets can be stored in localStorage alongside settings

## Open Questions

None - requirements clarified with user.

## Requirements (Evolving)

### 1. Settings Page Simplification

**Grouping**:
- Tab 1: Basic (5-8 fields) - Parse engine, provider, API key, quality preset
- Tab 2: OCR Settings (collapsed by default) - Traditional OCR, AIOCR, Baidu
- Tab 3: Advanced (20+ fields) - Fine-tuning parameters
- Tab 4: Admin (runtime config, admin-only)

**Progressive Disclosure**:
- Show only relevant fields based on parse engine mode
- Collapse advanced sections by default
- Add "Show Advanced" toggle

**Validation**:
- Validate API key format on blur
- Add "Test Connection" button for API keys
- Show validation errors inline

### 2. Setup Wizard Streamlining

**Reduce to 3 steps**:
- Step 1: Welcome + Deploy Mode (combined with clear explanation)
- Step 2: Create Admin Account (with password strength meter)
- Step 3: Optional Model Download (skippable, with explanation)

**Improvements**:
- Add comparison table for deploy modes
- Show password requirements as user types
- Make model download optional with "Skip for now" button
- Auto-redirect after completion

### 3. Job Presets (Built-in + Custom)

**Decision**: Implement built-in presets + user custom presets (stored in localStorage)

**Preset Structure**:
```typescript
type JobPreset = {
  id: string
  name: string
  description: string
  icon?: string
  settings: Partial<Settings>
  isBuiltIn: boolean
  createdAt?: number
  updatedAt?: number
}
```

**Built-in Presets** (3 presets):
1. **快速处理 (Fast)** 
   - Parse engine: local_ocr
   - OCR provider: machine (Tesseract/PaddleOCR)
   - PPT mode: turbo
   - Description: "本地处理，速度最快，无需 API 密钥"

2. **标准质量 (Standard)**
   - Parse engine: remote_ocr
   - OCR provider: aiocr
   - OCR AI chain: layout_block
   - PPT mode: fast
   - Description: "AIOCR 识别，质量与速度平衡"

3. **最佳质量 (Best)**
   - Parse engine: remote_ocr
   - OCR provider: aiocr
   - OCR AI chain: layout_block
   - Layout assist: enabled
   - PPT mode: standard
   - Description: "最高精度，启用版面辅助，适合复杂文档"

**Custom Preset Features**:
- Save current settings as new preset
- Edit preset name/description
- Delete custom presets (built-in presets cannot be deleted)
- Set default preset (auto-selected on upload page)
- Reset to built-in presets

**Preset Storage**:
- localStorage key: `pdf-to-ppt.presets.v1`
- Format: `{ custom: JobPreset[], defaultPresetId: string | null }`
- Built-in presets always loaded from code (not stored)
- Custom presets persisted to localStorage
- Default preset ID stored separately

**Preset Picker UI**:
- Show on upload page before job submission
- Card-based layout with preset name, description, icon
- Default preset auto-selected (if set)
- "Use Preset" button applies settings
- "Customize" button opens settings with preset as base
- "Manage Presets" link to preset management page

## Acceptance Criteria

* [ ] Settings page split into 4 tabs (Basic/OCR/Advanced/Admin)
* [ ] Only relevant fields shown based on parse engine mode
* [ ] API key validation on blur with format checking
* [ ] Setup wizard reduced to 3 meaningful steps
* [ ] Deploy mode comparison table added
* [ ] Password strength meter implemented
* [ ] Job presets implemented (built-in + custom if chosen)
* [ ] Preset picker on upload page
* [ ] Settings validation before save
* [ ] All existing functionality preserved
* [ ] TypeScript compiles without errors
* [ ] Responsive design maintained

## Definition of Done

* Settings page refactored with tab navigation
* Setup wizard streamlined to 3 steps
* Job presets implemented and tested
* User can save/load/delete presets
* Validation works on all input fields
* Documentation updated (if needed)
* No breaking changes to localStorage format
* Backward compatibility maintained

## Out of Scope (Explicit)

* Changing backend API contracts
* Migrating settings from localStorage to backend
* Adding new OCR providers or parse engines
* Redesigning the entire UI theme
* Adding user accounts/profiles (deploy mode handles this)
* Server-side preset storage (localStorage only for now)
* **Preset export/import** (defer to future iteration)
* **Preset sharing/cloud sync** (defer to future iteration)
* **Batch job processing** (separate feature)
* **Expanding beyond PDF2PPT** (future product direction, not in this task)

## Technical Notes

**Files to Modify**:
- `web/src/app/settings/page.tsx` (2809 lines → split into components)
- `web/src/app/setup/page.tsx` (reduce steps)
- `web/src/lib/settings.ts` (add preset types)
- `web/src/app/page.tsx` (upload page preset picker)

**New Components to Create**:
- `web/src/components/settings/basic-settings.tsx`
- `web/src/components/settings/ocr-settings.tsx`
- `web/src/components/settings/advanced-settings.tsx`
- `web/src/components/settings/admin-settings.tsx`
- `web/src/components/preset-picker.tsx`
- `web/src/components/preset-manager.tsx`

**Constraints**:
- Must maintain localStorage backward compatibility
- Settings migration logic must still work
- Existing settings keys cannot change
- Must work with current backend API

**References**:
- UX Analysis: `.trellis/tasks/archive/2026-05/05-12-comprehensive-code-review/ux-architecture-analysis.md`
- Frontend Spec: `.trellis/spec/frontend/component-guidelines.md`
