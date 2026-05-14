# Research: Naming & Contract Map (MVP Scope)

- **Query**: Map the same concept across frontend and backend layers — identify mismatches, rename-risk points, and alignment targets for MVP scope (backend chain failures + frontend status/config naming alignment).
- **Scope**: Internal (code inspection)
- **Date**: 2026-05-14

## Findings

### 1. Parse Engine / Parse Provider — 前后端概念错位

| Layer | Field Name | Values | Location |
|---|---|---|---|
| Frontend `Settings` | `parseEngineMode` | `"local_ocr" \| "remote_ocr" \| "baidu_doc" \| "mineru_cloud"` | `web/src/lib/settings.ts:37` |
| Frontend `RunConfig` | `parseProvider` | `"local" \| "baidu_doc" \| "mineru"` | `web/src/lib/run-config.ts:24` |
| Backend Form param | `parse_provider` | `"local" \| "mineru" \| "baidu_doc" \| "v2"` | `api/app/routers/jobs.py:511` |
| Backend Schema `ParseConfig` | `.provider` | `"local" \| "mineru" \| "baidu_doc"` | `api/app/schemas/job_config.py:242` |
| Backend `NormalizedJobOptions` | `parse_provider` | (normalized) | `api/app/job_options.py:115` |

**Mismatch details**:

| Frontend parseEngineMode | Frontend RunConfig.parseProvider | Backend parse_provider |
|---|---|---|
| `local_ocr` | `"local"` | `"local"` |
| `remote_ocr` | `"local"` | `"local"` |
| `baidu_doc` | `"baidu_doc"` | `"baidu_doc"` |
| `mineru_cloud` | `"mineru"` | `"mineru"` |

- Frontend `parseEngineMode` mixes "parser choice" with "OCR hint" — `local_ocr` means "local parser + local OCR", `remote_ocr` means "local parser + AI OCR". The backend only sees the parser selection, not the OCR mode via this field.
- `"v2"` is a legacy value only accepted at the backend form level, normalized to `"local"` in the worker (`api/app/worker.py:351-360`).
- **Rename risk**: The frontend concept `parseEngineMode` doesn't have a 1:1 backend equivalent. If you rename backend `parse_provider` to `parse_engine_mode`, you lose the semantic clarity that the backend values are purely about which parser engine to use.

### 2. OCR Provider — 三层名字但同一组值

| Layer | Field Name | Values | Location |
|---|---|---|---|
| Frontend `Settings` | `ocrProvider` (type `OcrProvider`) | `"auto" \| "aiocr" \| "baidu" \| "machine" \| "tesseract" \| "paddleocr"` | `web/src/lib/settings.ts:69` |
| Frontend `RunConfig` | `effectiveOcrProvider` | same type as above | `web/src/lib/run-config.ts:31` |
| Backend Form param | `ocr_provider` | (normalized) | `api/app/routers/jobs.py:561` |
| Backend Schema `OcrConfig` | `.provider` | `"auto" \| "aiocr" \| "baidu" \| "machine" \| "tesseract" \| "paddle" \| "paddle_local" \| "paddleocr"` | `api/app/schemas/job_config.py:182` |
| Backend `VALID_OCR_PROVIDERS` | — | `{"auto", "aiocr", "baidu", "machine", "tesseract", "paddle", "paddle_local", "paddleocr"}` | `api/app/job_options.py:10` |

**Mismatches**:
- Frontend `OcrProvider` type does NOT include `"paddle"` or `"paddle_local"` (legacy aliases only used in backend migrations).
- Backend `OcrConfig.provider` Accept-List includes both `"paddle"` and `"paddle_local"` — but the frontend normalizes these away before sending (`settings.ts:484-493`):
  - `"paddle"` / `"ai"` / `"remote"` → `"aiocr"`
  - `"paddle_local"` / `"local_paddle"` → `"paddleocr"`
- Frontend `effectiveOcrProvider` is a *derived* field (resolved from `ocrProvider` + `parseEngineMode`), while backend `ocr_provider` is a *passed* parameter. These are generally consistent but the derivation logic is in `run-config.ts`.

**Consistent**: The canonical set `{"auto", "aiocr", "baidu", "machine", "tesseract", "paddleocr"}` matches between frontend and backend.

### 3. enableLayoutAssist — 硬编码阻断（真实链路故障）

| Layer | Field Name | Value/Behavior | Location |
|---|---|---|---|
| Frontend `Settings` | `enableLayoutAssist` | boolean, user-toggle | `web/src/lib/settings.ts:50` |
| Frontend `JobConfig` (API payload) | `enable_layout_assist` | sent as `settings.enableLayoutAssist` | `web/src/lib/run-config.ts:627` |
| Backend Form param | `enable_layout_assist` | received as Form `False` default | `api/app/routers/jobs.py:495` |
| Backend Schema `to_worker_kwargs()` | `"enable_layout_assist"` | **Hardcoded `False`** | `api/app/schemas/job_config.py:390` |
| Backend `NormalizedJobOptions` | **NOT PRESENT** | Not a normalized option | `api/app/job_options.py:113-125` |
| Backend env config | `enable_layout_assist` | `.env` toggle | `api/app/config.py:122` |
| Backend worker | `options.enable_layout_assist` | read from kwargs | `api/app/worker.py:181` |

**Critical bug** (`api/app/schemas/job_config.py:390-391`):
```python
"enable_layout_assist": False,
"layout_assist_apply_image_regions": False,
```
When the v2 API path uses `to_worker_kwargs()`, these are **always False** regardless of what the frontend sends. The form-based v1 path (`jobs.py:495`) correctly receives the user value. This means:
- The new structured API (v2/JSON) silently ignores user's layout assist toggle.
- The frontend sends `enable_layout_assist: true` → `buildJobConfig()` → `to_worker_kwargs()` → always `False`.

**Rename risk analysis**: `enableLayoutAssist` (camelCase) on frontend vs `enable_layout_assist` (snake_case) in API — this is standard JS/Python convention boundary and is **NOT broken** (the frontend correctly converts in `buildJobConfig()`). The real problem is the hardcoded `False`.

### 4. layout_assist_apply_image_regions — 同上硬编码

Same bug pattern as above:
- Frontend `Settings.layoutAssistApplyImageRegions` → `JobConfig.layout_assist_apply_image_regions` → `to_worker_kwargs()` hardcodes `False`
- Worker conditionally uses `options.layout_assist_apply_image_regions` (`worker.py:182`)
- The format is consistent (camelCase ↔ snake_case conversion works correctly in `buildJobConfig()`), but the value is overridden.

### 5. Job Stage Names — "generating" vs "pptx_generating" 前后端漂移

| Layer | Usage | Values | Location |
|---|---|---|---|
| Backend `JobStage` enum | `pptx_generating = "pptx_generating"` | `api/app/models/job.py:30` |
| Backend worker | Sets stage to `JobStage.pptx_generating` | `api/app/worker_helpers/ppt_stage.py:92-165` |
| Frontend `JOB_STAGE_LABELS` | `pptx_generating: "生成 PPTX"` | `web/src/lib/job-status.ts:73` |
| Frontend `JOB_STAGE_FLOW` | `"pptx_generating"` | `web/src/lib/job-status.ts:102` |
| Frontend `JOB_STAGE_COMPACT_LABELS` | `pptx_generating: "PPTX"` | `web/src/lib/job-status.ts:84` |
| **Frontend home page** | `{ code: "generating", label: "生成" }` | **`web/src/app/page.tsx:310`** |

**Mismatch**: The home page step steps display uses `"generating"` (line 310) as a step code, but the actual backend stage is `"pptx_generating"`. The mapping works at runtime through `getJobStageFlowIndex()` + the `flowToStep` array (line 320), but:
- `"generating"` is NOT a real backend stage — it's an abstraction layer in the UI step display
- If someone adds `"generating"` to `JOB_STAGE_FLOW` thinking it's a legitimate stage, it would break
- The step `{ code: "generating", label: "生成" }` actually represents the combined range of `pptx_generating` + `packaging` stages (indices 4-6 map to step index 2)

**Rename risk**: Low (it's a display abstraction, not an API field), but the code value `"generating"` is misleading because it doesn't match any backend `JobStage` and could be confused with the old v1 processing concept.

### 6. "provider" 概念严重过载（跨层风险最高）

The word `provider` is used for **at least 4 distinct concepts** in the same job creation path:

| Concept | Frontend Field(s) | Backend Field(s) | Meaning |
|---|---|---|---|
| Main LLM provider | `Settings.provider`, `RunConfig.llmProvider` | Form `provider`, `NormalizedJobOptions.provider`, schema `LlmConfig.provider` | The LLM service used for layout assist (openai/claude) |
| Parser provider | `RunConfig.parseProvider` | Form `parse_provider`, schema `ParseConfig.provider` | Document parser engine (local/mineru/baidu_doc) |
| OCR provider | `Settings.ocrProvider`, `RunConfig.effectiveOcrProvider` | Form `ocr_provider`, schema `OcrConfig.provider` | OCR engine selection |
| AI OCR vendor | `Settings.ocrAiProvider` | Form `ocr_ai_provider`, schema `OcrAiConfig.provider`, `NormalizedJobOptions.ocr_ai_provider` | AI OCR vendor (siliconflow/deepseek/etc) |

**Specific confusion points**:
- `Settings.provider` means main LLM provider but can be `"mineru"` (which is a parser, not an LLM) — `web/src/lib/settings.ts:35,428-429,459-461`
- Backend `NormalizedJobOptions` has BOTH `parse_provider` AND `provider` as sibling fields (`api/app/job_options.py:115-116`)
- In the frontend legacy migration path, `parsedProvider` and `parsedParseProvider` can both indicate the same thing (`settings.ts:428-431`)

### 7. VisualAssistMode / LayoutAssistMode — 前端术语与后端不一致

| Layer | Field Name | Values | Location |
|---|---|---|---|
| Frontend type | `LayoutAssistMode` (also aliased as `VisionAssistMode`) | `"off" \| "on" \| "auto"` | `web/src/lib/settings.ts:27-28` |
| Frontend settings | `visualAssistModeLocal`, `visualAssistModeRemote`, `visualAssistModeBaiduDoc`, `visualAssistModeMineru` | per-chain policy | `web/src/lib/settings.ts:52-55` |
| Frontend `RunConfig` | `layoutAssistMode` | resolved from settings | `web/src/lib/run-config.ts:45` |
| Backend | No equivalent per-chain field | — | — |

**Mismatch**:
- Frontend uses `"visualAssist"` prefix for per-chain policies, but backend uses `"layout_assist"` everywhere
- These frontend fields (`visualAssistMode*`) appear to be **unused in the current code path** — they're defined in `Settings`, default to `"off"` in the presets, but `RunConfig.layoutAssistMode` is where the actual decision happens. The `layoutAssistMode` field in `RunConfig` links to `enableLayoutAssist` boolean, not to the `visualAssistMode*` per-chain fields.
- **Dead code risk**: `visualAssistMode*` settings may be purely decorative/write-only.

### 8. Layout Model Naming — 基本一致

| Layer | Field Name | Values | Location |
|---|---|---|---|
| Frontend `Settings` | `ocrAiLayoutModel` | `"pp_doclayout_v3" \| "pp_doclayout_s" \| "pp_doclayout_m" \| "pp_doclayout_l" \| "doclayout_yolo"` | `web/src/lib/settings.ts:81` |
| Frontend `RunConfig` | `ocrAiLayoutModel` | same type | `web/src/lib/run-config.ts:37` |
| Frontend `LAYOUT_MODELS` | model id keys | same values | `web/src/lib/layout-models.ts:18-69` |
| Backend Form param | `ocr_ai_layout_model` | same IDs | `api/app/routers/jobs.py:593` |
| Backend `NormalizedJobOptions` | `ocr_ai_layout_model` | (normalized) | `api/app/job_options.py:121` |
| Backend Schema `OcrAiConfig` | `layout_model` | `"pp_doclayout_v3"` default | `api/app/schemas/job_config.py:115-118` |
| Backend `LAYOUT_MODELS` | model id keys | same values | `api/app/convert/ocr/layout_models.py` |

**Consistent**: Both sides share the same model ID values. Both sides have alias normalization. The model IDs match between `web/src/lib/layout-models.ts` and `api/app/convert/ocr/layout_models.py`.

### 9. Home Page → Settings → Run Config — 模型状态/模型下载

| Component | API Endpoint | Response Shape | Location |
|---|---|---|---|
| Backend | `GET /api/v1/models/status` | `{ local: { tesseract, paddleocr, ...layout_models }, remote: { aiocr, baidu_doc, mineru } }` | `api/app/routers/models.py:144-148` |
| Backend | `POST /api/v1/models/download` | trigger download | `api/app/routers/_download_manager.py` |
| Frontend | `useModelStatus` hook | `ModelStatusResponse` | `web/src/hooks/use-model-status.ts` |
| Frontend | `useModelDownload` hook | download state | `web/src/hooks/use-model-download.ts` |
| Frontend | `ModelStatusBadge` | status dot + expandable panel | `web/src/components/model-status-badge.tsx` |
| Frontend | `DownloadProgressButton` | download progress | `web/src/components/download-progress-button.tsx` |

**Consistent**: The model status API names (`local`/`remote` buckets, layout model IDs as keys) match between frontend and backend. The `ENGINE_PROVIDER_MAP` in `model-status-badge.tsx:47-53` correctly maps `parseEngineMode` to relevant provider keys.

### 10. Settings → API Payload Naming Bridge

The frontend `buildJobConfig()` in `run-config.ts:614-765` converts `camelCase` settings to the `snake_case` schema the backend expects:

| Frontend Setting | Payload Field | Backend Schema Path |
|---|---|---|
| `parseEngineMode` → resolved to `parseProvider` | `parse.provider` | `JobConfig.parse.provider` |
| `ocrProvider` / `effectiveOcrProvider` | `ocr.provider` | `JobConfig.ocr.provider` |
| `enableLayoutAssist` | `enable_layout_assist` | `JobConfig.enable_layout_assist` (top-level) |
| `layoutAssistApplyImageRegions` | `layout_assist_apply_image_regions` | (top-level) |
| `ocrAiLayoutModel` | `ocr.ai.layout_model` | `JobConfig.ocr.ai.layout_model` |
| `ocrAiChainMode` | `ocr.ai.chain_mode` | `JobConfig.ocr.ai.chain_mode` |
| `pptGenerationMode` | `ppt.generation_mode` | `JobConfig.ppt.generation_mode` |

**The bridge is structurally correct** — each setting maps to the right field. The problem is value correctness (hardcoded `False` issue in §3-4 above), not naming mismatch in this bridge.

## Summary: Rename-Risk Points (ordered by impact)

| Priority | Issue | Impact | Risk Level |
|---|---|---|---|
| **P0** | `to_worker_kwargs()` hardcodes `enable_layout_assist=False` | Worker never enables layout assist via v2 API | 🔴 **Live bug** |
| **P0** | `to_worker_kwargs()` hardcodes `layout_assist_apply_image_regions=False` | Same class bug | 🔴 **Live bug** |
| **P1** | Home page stage display uses `"generating"` but backend stage is `"pptx_generating"` | Confusing for debugging, potential future stage lookup failure | 🟡 Medium |
| **P1** | `"provider"` overloaded for 4+ concepts (LLM, parser, OCR, AI OCR vendor) | Easy to misinterpret logs/config | 🟡 Medium |
| **P2** | `parseEngineMode` (frontend) vs `parse_provider` (backend) — different names, different value sets | Adds cognitive load, migrations needed | 🟢 Low |
| **P2** | `visualAssistMode*` frontend fields vs backend `layout_assist` naming disagreement | Dead-ish code, cosmetic mismatch | 🟢 Low |
| **P2** | Frontend `OcrProvider` type missing `"paddle"` and `"paddle_local"` | Type strictness mismatch, but harmless (frontend normalizes) | 🟢 Low |

## Recommended First-Wave Alignment Targets

### Must-fix (backend chain failures):
1. **`api/app/schemas/job_config.py:390-391`** — Remove hardcoded `False` for `enable_layout_assist` and `layout_assist_apply_image_regions`. Replace with values passed from `self` (the structured config).
2. **Verify `NormalizedJobOptions`** — confirm these fields should be present in the normalized dataclass, or alternative pass-through mechanism.

### Should-align (naming):
3. **Home page `page.tsx:310`** — Change `"generating"` to `"pptx_generating"` in the step code, or add a comment explaining it's a display abstraction that covers `pptx_generating` + `packaging`.
4. **`web/src/lib/settings.ts:27-28`** — Decide: merge/reconcile `LayoutAssistMode` / `VisionAssistMode` naming and `visualAssistMode*` fields with backend's `layout_assist` terminology, or mark the unused per-chain variants as deprecated.

### Document for future cleanup:
5. **`"provider" overload tracking`** — Create a glossary/ADR mapping which "provider" means what, to prevent future confusion.
6. **`parseEngineMode` vs `parse_provider` bridge** — Add explicit documentation comment in `run-config.ts:buildJobConfig()` showing the full mapping table.

## Related Specs

- `.trellis/spec/backend/index.md` — Backend coding guidelines
- `.trellis/spec/frontend/index.md` — Frontend coding guidelines

## Caveats / Not Found

- Did not inspect `NormalizedJobOptions` for missing `enable_layout_assist` field in detail — the dataclass at `api/app/job_options.py:113-125` has only 11 fields, none related to layout assist. This means layout assist flags flow outside the normalized options path, which is a design inconsistency but not necessarily a bug.
- The `visualAssistMode*` frontend settings may be used in future logic not yet implemented. Code search shows no active consumer besides definition/defaults.
- Did not exhaustively check every Form parameter in `jobs.py:491-610` for naming mismatches — focused on MVP scope fields only.
