# Research: Settings UI — Full Page Map & Backend Relationship

- **Query**: Map the frontend settings page UI and its relationship to backend
- **Scope**: internal
- **Date**: 2026-05-09

## Findings

### 1. Settings Page File Map

| File Path | Description |
|---|---|
| `web/src/app/settings/page.tsx` | Main settings page component (2572 lines); single-page, no tabs |
| `web/src/lib/settings.ts` | Settings type definition, default values, loadStoredSettings(), storage key |
| `web/src/lib/run-config.ts` | Settings → RunConfig resolver, OCR state resolver, JobConfig builder, validation |
| `web/src/hooks/use-settings.ts` | useSettings() hook: load, auto-save, deploy-mode aware |
| `web/src/lib/api.ts` | apiFetch() — all API calls go through Next.js rewrite proxy (`/api/v1/*`) |
| `web/src/lib/layout-models.ts` | Layout model registry shared with settings page |
| `web/src/lib/constants.ts` | API_REQUEST_TIMEOUT_MS = 30000, other constants |
| `web/src/app/admin/site-settings/page.tsx` | Admin-only global site settings page (278 lines) |
| `web/src/app/setup/page.tsx` | 6-step setup wizard (642 lines) |
| `web/src/middleware.ts` | Auth middleware: `/api/v1/config/` and `/api/v1/setup/` are unauthenticated |

### 2. Settings Page Structure (settings/page.tsx)

**Page layout** (no tabs — flat, conditional visibility):
```
Header ("处理设置" with badges: 浏览器保存, 可选 OCR, 与首页联动)
├── Toolbar (配置操作: 清空本地配置, 立即保存, auto-save indicator)
├── 解析引擎 Card (4 radio buttons: 传统 OCR, AIOCR, 百度解析, 云端 MinerU)
├── 高级参数与诊断 Toggle (showAdvanced state)
├── 接口配置 (CollapsibleSection, shown when MinerU or showAdvanced)
│   ├── API 地址 override (backend origin picker)
│   └── MinerU fields: Token, Base URL, Model Version, Language, 公式/表格/OCR checkboxes
├── 处理策略 (CollapsibleSection)
│   ├── 文字消除模式 (fill/smart Select)
│   ├── 页面图片处理方式 (segmented/fullpage Select)
│   ├── OCR 渲染 DPI (number input)
│   ├── 删除页脚 NotebookLM (checkbox)
│   └── 图片底图清除与图块阈值 (6 number inputs + reset button)
└── OCR 配置 (CollapsibleSection, conditional on isOcrEnabledForCurrentEngine)
    ├── OCR 提供方 (radio buttons with model readiness badges, download buttons)
    ├── OCR 严格模式 (checkbox)
    ├── AIOCR 厂商适配 (Select, 6 providers: auto/openai/siliconflow/deepseek/ppio/novita)
    ├── 专用 OCR 接口参数 (shown when needsRequiredOcrAiConfig)
    │   ├── OCR API Key (SensitiveInput)
    │   ├── OCR Base URL
    │   ├── AIOCR 识别链路 (Select: layout_block/direct/doc_parser)
    │   ├── 版面切块模型 (radio with download buttons, 5 models)
    │   ├── PaddleOCR-VL 长边上限 (number, when doc_parser)
    │   ├── 视觉/OCR 模型 (Input with portal suggestion dropdown)
    │   ├── 检测 OCR 配置 (button → POST /jobs/ocr/ai/check)
    │   ├── 提示词实验 (nested collapsible)
    │   │   ├── 提示词预设 (Select, 6 presets)
    │   │   ├── 当前链路提示词覆盖 (PromptTextarea, conditionally layout_block vs direct)
    │   │   └── 图片区域检测提示词覆盖 (PromptTextarea)
    │   └── 并发与限流 (page concurrency, block concurrency, RPM, TPM, max retries)
    ├── 百度配置 (API Key, Secret Key, App ID)
    ├── Tesseract 配置 (min confidence, language)
    └── 本地 OCR 综合检测 (Tesseract + PaddleOCR runtime/model check)
```

**All controls are live-bound** — no form submission; every `onChange` calls `setSettings((s) => ({ ...s, [key]: newValue }))`.

### 3. Control Types Used

| Control | Count | Examples |
|---|---|---|
| Input (text) | ~8 | API 地址, MinerU Base URL/Language, OCR Base URL, 视觉/OCR 模型, Tesseract language |
| Input (number) | ~14 | OCR Render DPI, 图片阈值×6, 并发数×2, RPM, TPM, 重试次数, confidence, PaddleOCR-VL 长边 |
| SensitiveInput (password toggle) | ~5 | MinerU Token, OCR API Key, 百度 API Key, 百度 Secret Key |
| Select | ~7 | MinerU Model Version, 文字消除模式, 页面图片处理方式, AIOCR 厂商, 识别链路, 提示词预设, 文档解析类型 |
| Checkbox | ~4 | MinerU 公式/表格/OCR, 删除页脚 NotebookLM, OCR 严格模式 |
| Radio (custom styled) | 2 groups | OCR 提供方, 版面切块模型 |
| PromptTextarea | 3 | 本地切块提示词, 模型直出提示词, 图片区域检测提示词 |
| Button | ~8 | 清空本地配置, 立即保存, 检测 OCR 配置, 检测本地 OCR, 恢复默认阈值, 展开/收起, 候选模型 |
| CollapsibleSection | 3 (conditional) | 接口配置, 处理策略, OCR 配置 |
| AdvancedReveal | ~8 | Animated expand/collapse for "高级参数与诊断" mode |

### 4. State Binding & Auto-Save

**Flow**:
1. `useSettings()` hook loads `loadStoredSettings()` (localStorage) or `GET /api/v1/user/preferences` based on deploy mode
2. All controls mutate `settings` in-memory via `setSettings()`
3. `useSettings()` useEffect debounces auto-save at 500ms (`window.setTimeout(..., 500)`)
   - **Self mode**: `localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))` — entire object saved
   - **Public mode**: `PUT /api/v1/user/preferences` body `{ preferences: {...} }` — only non-sensitive keys saved; sensitive keys (API keys) excluded
4. `isPublicMode` flag disables 6 sensitive inputs: `openaiApiKey`, `claudeApiKey`, `mineruApiToken`, `ocrBaiduApiKey`, `ocrBaiduSecretKey`, `ocrAiApiKey`
5. Manual save button (`onSave`) does the same as auto-save but immediately

**Sensitive key list** (from `web/src/hooks/use-settings.ts:15-22`):
```typescript
SENSITIVE_KEYS = new Set([
  "openaiApiKey", "claudeApiKey", "mineruApiToken",
  "ocrBaiduApiKey", "ocrBaiduSecretKey", "ocrAiApiKey",
])
```

### 5. How Settings Map to Job Config

**`web/src/lib/run-config.ts`** exports key resolver functions:

- **`resolveRunConfig(settings)`** → `RunConfig` (line 313): Resolves all settings into a normalized RunConfig with parsed fields like `parseProvider`, `effectiveOcrAiKey`, `ocrAiChainMode`, etc.
- **`resolveOcrSettingsState(settings)`** → `OcrSettingsState` (line 410): Derives UI visibility flags (`shouldShowOcrProviderSelector`, `needsRequiredOcrAiConfig`, `isOcrAiChainDirect`, etc.) used to show/hide sections conditionally.
- **`buildJobConfig(settings)`** → `JobConfig` (line 657): Builds the JSON payload for the v2 API endpoint. Maps Settings fields to a nested `JobConfig` with `enable_ocr`, `ocr.*`, `parse.*`, `llm.*`, `ppt.*`, `page_range.*`.
- **`validateRunConfig(settings)`** → `ValidationResult` (line 511): Pre-submit validation (checks for missing API keys, incompatible model/chain combinations).
- **`applyParseEngineMode(settings, nextMode)`** → `Settings` (line 974): Transitions settings between 4 parse engine modes with sensible defaults.

### 6. UI Visibility Logic (from resolveOcrSettingsState)

| Condition | Controls When |
|---|---|
| `isMineruProvider` | MinerU-specific fields (接口配置 section, MinerU checkboxes) |
| `isBaiduDocParseMode` | 百度文档解析 fields, hides "OCR 配置" title custom |
| `needsRequiredOcrAiConfig` | 专用 OCR 接口参数 section (API Key, Base URL, model, chain, concurrency, prompts) |
| `shouldShowAiVendorAdapter` | AIOCR 厂商适配 dropdown (same as needsRequiredOcrAiConfig) |
| `shouldShowOcrProviderSelector` | OCR 提供方 radio buttons (local_ocr mode only) |
| `shouldShowBaiduConfig` | 百度 API Key/Secret Key/App ID |
| `shouldShowTesseractConfig` | Tesseract confidence/language (deprecated, only shows when isOcrProviderTesseract) |
| `shouldShowLocalOcrCheck` | 本地 OCR 综合检测 (tesseract + paddle checks) |
| `isOcrAiChainLayoutBlock` | 版面切块模型 radio, 本地切块提示词覆盖 |
| `isOcrAiChainDirect` | 模型直出提示词覆盖 |
| `isOcrAiChainDocParser` | PaddleOCR-VL 设置 |
| `isPromptDrivenOcrChain` | 提示词实验 section (layout_block or direct) |

### 7. API Calls Made from Settings Page

| Endpoint | Method | Purpose | Source |
|---|---|---|---|
| `/config/deploy-mode` | GET | Load deploy mode (self vs public) | `use-settings.ts:55` |
| `/user/preferences` | GET | Load saved preferences (public mode) | `use-settings.ts:82` |
| `/user/preferences` | PUT | Save non-sensitive preferences (autosave/manual) | `use-settings.ts:123`, `use-settings.ts:148` |
| `/models` | POST | Load OCR model list (requires api_key, provider, capability) | `settings/page.tsx:678` |
| `/jobs/ocr/local/check` | POST | Check local OCR runtime/models (per provider) | `settings/page.tsx:797` |
| `/jobs/ocr/ai/check` | POST | Verify AI OCR config | `settings/page.tsx:947` |
| `/models/status` | GET | Check model download/ready state | via `useModelStatus` hook (settings updates trigger refetch) |

### 8. Backend Persistence

Two separate key-value tables in backend:

- **`site_settings`** (`api/app/models/user.py:207`): Global admin settings. Stores `deploy_mode`, API keys (shared across all users). Managed via `GET/PUT /api/v1/admin/site-settings` (admin-only). Sensitive values masked (`••••••••`) on read.
- **`user_preferences`** (`api/app/models/user.py:226`): Per-user non-sensitive preferences. Stores `key` → `value` for each user. Managed via `GET/PUT /api/v1/user/preferences`. Values stored as strings (max 4096 chars), booleans stored as "true"/"1".

### 9. Admin Site Settings Page (`web/src/app/admin/site-settings/page.tsx`)

- 278 lines; admin-only; redirects non-admin to `/`
- 3 cards: Deploy Mode (self/public toggle), API 密钥配置 (5 fields: OpenAI key/base/model, Claude key, MinerU token), OCR 配置 (5 fields: OCR AI key/base/model, Baidu key/secret)
- All inputs are plain text (sensitive ones use `type="password"`)
- Saves via `PUT /api/v1/admin/site-settings`
- If deploy_mode changes, forces logout + redirect to `/login`

### 10. Setup Wizard (`web/src/app/setup/page.tsx`)

- 642 lines; 6-step wizard: Welcome → Deploy Mode → Create Admin → Model Detection → Layout Model → Completion
- Checks `GET /api/v1/setup/status` to decide if setup needed
- Calls `POST /api/v1/setup/complete` with `{ deploy_mode, username, password }` to create admin
- Shows model download status and buttons for local models (tesseract, paddleocr, layout models)
- No settings-to-backend persistence in setup — only creates admin account

### 11. Routing

All frontend API calls go through Next.js rewrite proxy: `fetch(\`/api/v1${path}\`)` → backend. See `apiFetch()` in `web/src/lib/api.ts:252`.

**Middleware** (`web/src/middleware.ts`):
- `/api/v1/config/` — unauthenticated (needed for deploy mode check before login)
- `/api/v1/setup/` — unauthenticated
- All other `/api/v1/*` — requires auth cookie or Bearer token

## Caveats / Not Found

- Settings page has **no tabs** — everything is one long scrollable page. The "高级参数与诊断" toggle is the only significant show/hide mechanism beyond the conditional visibility driven by `resolveOcrSettingsState`.
- **No "Main AI Provider" section** exists on the settings page. The `provider` (openai/claude) and `mainModelsApiKeyRaw` (from `getMainProviderConfig`) only appears indirectly — the main AI API key is never exposed as an input on this page. This is likely because it's configured on the home page or in admin settings. Actually, looking more carefully, the main AI config (openaiApiKey, claudeApiKey, openaiBaseUrl, openaiModel) exists in the Settings type but has NO visible input on the settings page — only OCR-related API keys are shown.
- The settings page **never calls `PUT /api/v1/config/*`** — all persistence is through `PUT /api/v1/user/preferences` (public mode) or `localStorage` (self mode).
- `apiFetch` in `web/src/lib/api.ts` always calls the Next.js rewrite proxy (`/api/v1/*`), not direct backend URLs — this means CORS is never an issue from the settings page.
