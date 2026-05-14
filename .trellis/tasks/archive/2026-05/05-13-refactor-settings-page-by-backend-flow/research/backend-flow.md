# Research: Backend Processing Flow for PDF to PPT Conversion

- **Query**: Complete backend processing flow for PDF to PPT conversion
- **Scope**: Internal codebase analysis
- **Date**: 2026-05-13

---

## Executive Summary

The PDF to PPT conversion pipeline has **4 main parse engine modes** that determine the entire processing flow. Each mode uses different combinations of providers and OCR strategies. The frontend settings map to backend configuration through a complex normalization and validation layer.

---

## 1. Processing Pipeline Overview

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Job Submission                               │
│  (POST /api/v1/jobs or /api/v1/jobs/v2)                            │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Job Creation & Validation                         │
│  • Disk space check                                                  │
│  • User quota check (concurrent/daily limits)                        │
│  • File upload streaming (max 100MB)                                 │
│  • Settings normalization & validation                               │
│  • Secret storage (API keys → Redis)                                 │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Worker Queue Submission                           │
│  • Thread (memory mode) or RQ (Redis mode)                          │
│  • process_pdf_job(job_id, options)                                 │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    STAGE 1: Parsing                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ Parse Engine Mode Selection (parseEngineMode)                │  │
│  │                                                               │  │
│  │  • local_ocr    → PyMuPDF extraction                         │  │
│  │  • remote_ocr   → PyMuPDF extraction                         │  │
│  │  • baidu_doc    → Baidu Document Parser API                  │  │
│  │  • mineru_cloud → MinerU Cloud API                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  Output: IR (Intermediate Representation) JSON                       │
│    - pages[] with elements (text, images, tables)                   │
│    - bbox coordinates, fonts, styles                                │
│    - has_text_layer flag per page                                   │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    STAGE 2: OCR (Conditional)                        │
│  Triggered when:                                                     │
│    - parseEngineMode = local_ocr OR remote_ocr                      │
│    - has_text_layer = false (scanned pages detected)                │
│    - enableOcr = true                                               │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ OCR Provider Selection (ocrProvider)                         │  │
│  │                                                               │  │
│  │  • machine    → PaddleOCR local → Tesseract fallback         │  │
│  │  • tesseract  → Tesseract only                               │  │
│  │  • paddleocr  → PaddleOCR local only                         │  │
│  │  • aiocr      → AI OCR (chain mode determines routing)       │  │
│  │  • baidu      → Baidu OCR API                                │  │
│  │  • auto       → Hybrid (Baidu/Tesseract/Paddle + AI merge)   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  AI OCR Chain Modes (when ocrProvider=aiocr):                       │
│    • direct       → Full-page vision prompt                         │
│    • doc_parser   → PaddleOCR-VL structured parsing                 │
│    • layout_block → Local layout detection → block-level OCR        │
│                                                                       │
│  Output: OCR text + bboxes added to IR pages[]                      │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                STAGE 3: Layout Assist (Optional)                     │
│  Triggered when:                                                     │
│    - enableLayoutAssist = true (env: ENABLE_LAYOUT_ASSIST)         │
│    - AI provider credentials available                              │
│                                                                       │
│  Uses: OpenAI or Claude API for layout refinement                   │
│  Output: Refined element positions in IR                            │
└────────────────┬────────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    STAGE 4: PPT Generation                           │
│  • Text placement with font matching                                 │
│  • Image extraction and positioning                                  │
│  • Table reconstruction                                              │
│  • Background cleanup (textEraseMode: smart/fill)                   │
│  • Image handling (scannedPageMode: segmented/fullpage)             │
│  • Generation speed (pptGenerationMode: standard/fast/turbo)        │
│                                                                       │
│  Output: output.pptx                                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Parse Engine Modes (Primary Decision Point)

The `parseEngineMode` setting is the **primary routing decision** that determines the entire pipeline behavior.

### 2.1 local_ocr (Traditional OCR)

**When to use**: Fast local processing, no cloud dependencies

**Flow**:
```
PDF → PyMuPDF extraction → [OCR if scanned] → PPT
```

**Key characteristics**:
- Uses PyMuPDF for text/image/table extraction
- OCR triggered only for pages without text layer
- OCR provider selection via `ocrProvider` setting
- Supports all OCR providers (machine, tesseract, paddleocr, aiocr, baidu, auto)

**Settings that matter**:
- `ocrProvider`: Which OCR engine to use
- `ocrRenderDpi`: Render quality for scanned pages
- `enableOcr`: Whether to OCR scanned pages at all
- `ocrStrictMode`: Fail fast vs. fallback behavior

### 2.2 remote_ocr (AIOCR)

**When to use**: High-quality OCR with AI models

**Flow**:
```
PDF → PyMuPDF extraction → AI OCR (always) → PPT
```

**Key characteristics**:
- Same PyMuPDF extraction as local_ocr
- Forces `ocrProvider=aiocr` internally
- AI OCR chain mode determines routing strategy
- Requires `ocrAiApiKey` and `ocrAiModel`

**Settings that matter**:
- `ocrAiProvider`: API vendor (openai, siliconflow, deepseek, ppio, novita)
- `ocrAiBaseUrl`: API endpoint
- `ocrAiModel`: Model name
- `ocrAiChainMode`: **Critical routing decision**
  - `direct`: Full-page vision prompt (fastest, least accurate)
  - `doc_parser`: PaddleOCR-VL structured parsing (requires PaddleOCR-VL model)
  - `layout_block`: Local layout detection → block-level OCR (best quality)
- `ocrAiLayoutModel`: Layout detection model (when chain=layout_block)
- `ocrAiPageConcurrency`: Parallel page processing
- `ocrAiBlockConcurrency`: Parallel block processing (layout_block mode)
- `ocrAiRequestsPerMinute`: Rate limiting
- `ocrAiTokensPerMinute`: Token rate limiting

### 2.3 baidu_doc (Baidu Document Parser)

**When to use**: Chinese documents, Baidu ecosystem

**Flow**:
```
PDF → Baidu Document Parser API → IR → PPT
```

**Key characteristics**:
- Bypasses PyMuPDF extraction entirely
- Uses Baidu's cloud document parsing service
- OCR is handled by Baidu (no separate OCR stage)
- Forces `enableOcr=false` and `enableLayoutAssist=false`

**Settings that matter**:
- `baiduDocParseType`: Parser variant
  - `general`: Standard document parsing
  - `paddle_vl`: PaddleOCR-VL enhanced parsing
- `ocrBaiduApiKey`: Baidu API key
- `ocrBaiduSecretKey`: Baidu secret key

**Ignored settings**:
- `ocrProvider` (forced to auto)
- `enableOcr` (forced to false)
- `enableLayoutAssist` (forced to false)

### 2.4 mineru_cloud (Cloud MinerU)

**When to use**: Complex documents with formulas/tables

**Flow**:
```
PDF → MinerU Cloud API → IR → PPT
```

**Key characteristics**:
- Bypasses PyMuPDF extraction entirely
- Uses MinerU's cloud parsing service
- OCR is handled by MinerU (no separate OCR stage)
- Supports formula and table recognition

**Settings that matter**:
- `mineruApiToken`: MinerU API token (required)
- `mineruBaseUrl`: API endpoint
- `mineruModelVersion`: Model variant (pipeline, vlm, MinerU-HTML)
- `mineruEnableFormula`: Formula recognition toggle
- `mineruEnableTable`: Table recognition toggle
- `mineruLanguage`: Language hint (ch, en)
- `mineruIsOcr`: Per-file OCR switch

**Ignored settings**:
- `ocrProvider` (forced to auto)
- `enableOcr` (MinerU handles OCR internally)

---

## 3. OCR Provider Selection (Secondary Decision)

Only applies when `parseEngineMode = local_ocr` or `remote_ocr`.

### OCR Provider Decision Tree

```
ocrProvider setting
│
├─ machine
│  └─ Try PaddleOCR local → fallback to Tesseract
│
├─ tesseract / local
│  └─ Tesseract only (no fallback)
│
├─ paddleocr
│  └─ PaddleOCR local only
│     └─ (non-strict: Tesseract fallback)
│
├─ aiocr
│  └─ AI OCR via ocrAiChainMode
│     ├─ direct: Full-page vision prompt
│     ├─ doc_parser: PaddleOCR-VL structured parsing
│     └─ layout_block: Local layout → block OCR
│     └─ (non-strict: Tesseract/Paddle fallback)
│
├─ baidu
│  └─ Baidu OCR API
│     └─ (non-strict: Tesseract/Paddle fallback)
│
└─ auto (Hybrid Mode)
   └─ Parallel execution:
      ├─ Baidu OCR (if credentials)
      ├─ Tesseract OCR
      ├─ PaddleOCR local
      └─ AI OCR (if credentials)
      └─ Merge results (machine OCR for geometry, AI for text quality)
```

### Strict Mode Behavior

**`ocrStrictMode = true` (default)**:
- No implicit fallbacks
- Fail fast on OCR errors
- Explicit provider stays pure

**`ocrStrictMode = false`**:
- Adds Tesseract/PaddleOCR fallbacks
- Continues on OCR failures
- More resilient but less predictable

---

## 4. Configuration Dependencies & Validation Rules

### 4.1 Parse Engine Mode Constraints

| parseEngineMode | Required Settings | Forbidden Settings | Notes |
|-----------------|-------------------|-------------------|-------|
| local_ocr | None | None | Most flexible |
| remote_ocr | ocrAiApiKey, ocrAiModel | None | Forces ocrProvider=aiocr |
| baidu_doc | ocrBaiduApiKey, ocrBaiduSecretKey | ocrProvider (forced auto) | Disables OCR stage |
| mineru_cloud | mineruApiToken | ocrProvider (forced auto) | Disables OCR stage |

### 4.2 OCR Provider Constraints

| ocrProvider | Required Settings | Model Constraints | Chain Mode |
|-------------|-------------------|-------------------|------------|
| machine | None | N/A | Local only |
| tesseract | None | N/A | Local only |
| paddleocr | None | N/A | Local only |
| aiocr | ocrAiApiKey, ocrAiModel | doc_parser requires PaddleOCR-VL model | ocrAiChainMode |
| baidu | ocrBaiduApiKey, ocrBaiduSecretKey | N/A | Cloud API |
| auto | None (best-effort) | N/A | Hybrid merge |

### 4.3 AI OCR Chain Mode Constraints

| ocrAiChainMode | Model Requirements | Additional Settings | Use Case |
|----------------|-------------------|---------------------|----------|
| direct | Any vision model EXCEPT PaddleOCR-VL | None | Fast, full-page OCR |
| doc_parser | MUST be PaddleOCR-VL model | ocrPaddleVlDocparserMaxSidePx | Structured document parsing |
| layout_block | Any vision model EXCEPT PaddleOCR-VL | ocrAiLayoutModel, ocrAiBlockConcurrency | Best quality, block-level |

### 4.4 Mutual Exclusions

**Cannot combine**:
- `parseEngineMode=mineru_cloud` + `ocrProvider != auto`
- `parseEngineMode=baidu_doc` + `ocrProvider != auto`
- `ocrAiChainMode=doc_parser` + non-PaddleOCR-VL model
- `ocrAiChainMode=direct` + PaddleOCR-VL model
- `ocrGeometryMode != auto` + `ocrProvider != aiocr`

### 4.5 Default Fallback Chains

**When ocrProvider=auto (non-strict mode)**:
```
1. Baidu OCR (if credentials)
2. Tesseract OCR (if available)
3. PaddleOCR local (if available)
4. AI OCR (if credentials)
→ Merge all results (prefer machine OCR geometry, AI for text)
```

**When ocrProvider=aiocr (non-strict mode)**:
```
1. AI OCR (primary)
2. Tesseract (fallback)
3. PaddleOCR local (fallback)
```

---

## 5. User Scenarios → Settings Mapping

### Scenario 1: Fast Local Processing (No API Keys)

**Goal**: Fastest conversion, no cloud dependencies

**Settings**:
```typescript
{
  parseEngineMode: "local_ocr",
  ocrProvider: "machine",
  pptGenerationMode: "turbo",
  enableOcr: true,
  ocrStrictMode: false,
}
```

**Flow**: PyMuPDF → PaddleOCR/Tesseract → PPT (turbo)

---

### Scenario 2: High-Quality AIOCR (Balanced)

**Goal**: Best quality/speed balance with AI OCR

**Settings**:
```typescript
{
  parseEngineMode: "remote_ocr",
  ocrProvider: "aiocr",
  ocrAiChainMode: "layout_block",
  ocrAiProvider: "siliconflow",
  ocrAiModel: "Pro/Qwen/Qwen2-VL-72B-Instruct",
  ocrAiLayoutModel: "pp_doclayout_v3",
  pptGenerationMode: "fast",
  enableOcr: true,
}
```

**Flow**: PyMuPDF → Local layout detection → AI block OCR → PPT (fast)

---

### Scenario 3: Best Quality (Complex Documents)

**Goal**: Maximum accuracy, enable all enhancements

**Settings**:
```typescript
{
  parseEngineMode: "remote_ocr",
  ocrProvider: "aiocr",
  ocrAiChainMode: "layout_block",
  ocrAiProvider: "openai",
  ocrAiModel: "gpt-4o",
  ocrAiLayoutModel: "pp_doclayout_v3",
  enableLayoutAssist: true,
  pptGenerationMode: "standard",
  scannedPageMode: "segmented",
  textEraseMode: "smart",
}
```

**Flow**: PyMuPDF → Layout block AI OCR → AI layout assist → PPT (standard)

---

### Scenario 4: Chinese Documents (Baidu)

**Goal**: Optimized for Chinese text

**Settings**:
```typescript
{
  parseEngineMode: "baidu_doc",
  baiduDocParseType: "paddle_vl",
  ocrBaiduApiKey: "...",
  ocrBaiduSecretKey: "...",
  pptGenerationMode: "fast",
}
```

**Flow**: Baidu Document Parser → PPT (fast)

---

### Scenario 5: Academic Papers (MinerU)

**Goal**: Formula and table recognition

**Settings**:
```typescript
{
  parseEngineMode: "mineru_cloud",
  mineruApiToken: "...",
  mineruModelVersion: "vlm",
  mineruEnableFormula: true,
  mineruEnableTable: true,
  pptGenerationMode: "standard",
}
```

**Flow**: MinerU Cloud → PPT (standard)

---

## 6. Key Concepts & Relationships

### 6.1 Provider Hierarchy

```
Main Provider (provider)
├─ openai  → Used for layout assist (optional)
├─ claude  → Used for layout assist (optional)
└─ mineru  → Alias for parseEngineMode=mineru_cloud

Parse Engine Mode (parseEngineMode)
├─ local_ocr    → Uses PyMuPDF + OCR provider
├─ remote_ocr   → Uses PyMuPDF + AI OCR
├─ baidu_doc    → Uses Baidu Document Parser
└─ mineru_cloud → Uses MinerU Cloud

OCR Provider (ocrProvider)
├─ machine    → PaddleOCR local → Tesseract
├─ tesseract  → Tesseract only
├─ paddleocr  → PaddleOCR local only
├─ aiocr      → AI OCR (chain mode routing)
├─ baidu      → Baidu OCR API
└─ auto       → Hybrid merge

AI OCR Vendor (ocrAiProvider)
├─ openai
├─ siliconflow
├─ deepseek
├─ ppio
└─ novita
```

### 6.2 Settings Inheritance & Overrides

**Legacy compatibility**:
- `provider=v2` → Maps to `parseEngineMode=local_ocr` + `ocrProvider=aiocr` + `scannedPageMode=fullpage`
- `provider=domestic` → Maps to `provider=mineru`
- `ocrProvider=ai/remote/paddle` → Maps to `ocrProvider=aiocr`
- `ocrProvider=paddle-local/local_paddle` → Maps to `ocrProvider=machine`

**Forced overrides**:
- `parseEngineMode=baidu_doc` → Forces `enableOcr=false`, `enableLayoutAssist=false`
- `parseEngineMode=mineru_cloud` → Forces `ocrProvider=auto`
- `parseEngineMode=remote_ocr` → Forces `ocrProvider=aiocr` internally

---

## 7. Files Inspected

### Core Routing & Orchestration

| File | Description |
|------|-------------|
| `api/app/routers/jobs.py` | Job submission endpoints (v1 & v2), validation, worker submission |
| `api/app/routers/_job_create_utils.py` | Shared job creation helpers (disk check, quotas, cleanup) |
| `api/app/worker.py` | Main worker entry point: `process_pdf_job()` |
| `api/app/job_options.py` | Settings normalization & validation rules |

### Parse Engine Implementations

| File | Description |
|------|-------------|
| `api/app/convert/pdf_parser.py` | PyMuPDF extraction (local_ocr, remote_ocr) |
| `api/app/convert/baidu_doc_adapter.py` | Baidu Document Parser integration |
| `api/app/convert/mineru_adapter.py` | MinerU Cloud integration |

### OCR Subsystem

| File | Description |
|------|-------------|
| `api/app/convert/ocr/_ocr_manager.py` | OCR provider orchestration & fallback logic |
| `api/app/convert/ocr/routing.py` | OCR route planning & chain mode logic |
| `api/app/convert/ocr/ai_client.py` | AI OCR client (direct, doc_parser, layout_block) |
| `api/app/convert/ocr/_baidu_ocr.py` | Baidu OCR client |
| `api/app/convert/ocr/_tesseract_ocr.py` | Tesseract OCR client |
| `api/app/convert/ocr/_paddle_ocr.py` | PaddleOCR local client |

### Worker Stages

| File | Description |
|------|-------------|
| `api/app/worker_helpers/ocr_stage.py` | OCR stage orchestration |
| `api/app/worker_helpers/layout_assist_stage.py` | Layout assist stage |
| `api/app/worker_helpers/ppt_stage.py` | PPT generation stage |
| `api/app/worker_helpers/ocr_runtime.py` | OCR runtime setup |

### Frontend Settings

| File | Description |
|------|-------------|
| `web/src/lib/settings.ts` | Frontend settings types & defaults |

---

## 8. Decision Points Summary

### Primary Decision: Parse Engine Mode

**Question**: How should the PDF be parsed?

**Options**:
1. **local_ocr**: PyMuPDF + optional OCR → Best for standard PDFs
2. **remote_ocr**: PyMuPDF + AI OCR → Best for scanned documents
3. **baidu_doc**: Baidu cloud parsing → Best for Chinese documents
4. **mineru_cloud**: MinerU cloud parsing → Best for academic papers

### Secondary Decision: OCR Provider (if local_ocr or remote_ocr)

**Question**: Which OCR engine should process scanned pages?

**Options**:
1. **machine**: Local PaddleOCR → Tesseract fallback
2. **tesseract**: Tesseract only
3. **paddleocr**: PaddleOCR only
4. **aiocr**: AI OCR (requires chain mode selection)
5. **baidu**: Baidu OCR API
6. **auto**: Hybrid merge of all available

### Tertiary Decision: AI OCR Chain Mode (if ocrProvider=aiocr)

**Question**: How should AI OCR process the page?

**Options**:
1. **direct**: Full-page vision prompt (fastest)
2. **doc_parser**: PaddleOCR-VL structured parsing (requires PaddleOCR-VL model)
3. **layout_block**: Local layout → block OCR (best quality)

---

## 9. Caveats & Edge Cases

### 9.1 Settings Ignored by Certain Modes

- **baidu_doc mode**: Ignores `ocrProvider`, `enableOcr`, `enableLayoutAssist`
- **mineru_cloud mode**: Ignores `ocrProvider`, `enableOcr`
- **Turbo generation**: Caps `ocrRenderDpi` to 150
- **Fast generation**: Caps `ocrRenderDpi` to 200

### 9.2 Auto-Enabled Features

- **Linebreak assist**: Auto-enabled for PaddleOCR-VL models
- **Fallback providers**: Auto-added in non-strict mode
- **AI provider reuse**: Layout assist can reuse OCR AI credentials

### 9.3 Runtime Behavior Changes

- **AI OCR failures**: May disable AI OCR for remaining pages (non-strict mode)
- **Low recall detection**: Tesseract may retry with lower confidence
- **Word-level merge**: AI OCR results may be merged to line-level if fragmented

### 9.4 Validation Gotchas

- `page_start` and `page_end` must be provided together or both omitted
- `ocr_geometry_mode` only works with `ocrProvider=aiocr`
- PaddleOCR-VL models cannot use `direct` chain mode
- Non-PaddleOCR-VL models cannot use `doc_parser` chain mode

---

## 10. Recommendations for Frontend UX

### 10.1 Preset-Based Approach

Instead of exposing 90+ settings, provide **scenario-based presets**:

1. **Fast Local** (no API keys needed)
2. **Standard Quality** (AIOCR with layout_block)
3. **Best Quality** (AIOCR + layout assist)
4. **Chinese Documents** (Baidu)
5. **Academic Papers** (MinerU)

### 10.2 Progressive Disclosure

**Level 1: Mode Selection**
- Parse engine mode (4 options)

**Level 2: Provider Selection** (conditional)
- OCR provider (if local_ocr/remote_ocr)
- AI OCR chain mode (if aiocr)

**Level 3: Advanced Tuning** (collapsed by default)
- Concurrency, rate limits, DPI, etc.

### 10.3 Validation Feedback

Show real-time validation:
- "doc_parser requires PaddleOCR-VL model"
- "This mode ignores OCR provider setting"
- "API key required for this configuration"

### 10.4 Dependency Visualization

Show which settings affect which stages:
- Parsing stage: parseEngineMode, provider credentials
- OCR stage: ocrProvider, ocrAi* settings
- Layout stage: enableLayoutAssist, provider
- PPT stage: pptGenerationMode, scannedPageMode, textEraseMode

---

## End of Research Document
