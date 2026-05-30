/**
 * OCR Configuration V3 - Three-Layer Architecture
 *
 * This module implements the complete three-layer OCR architecture:
 * 1. Document Parsing Layer (optional, for complex documents)
 * 2. Layout Detection Layer (optional, for page segmentation)
 * 3. Text Recognition Layer (required, for actual OCR)
 *
 * This aligns with the backend's true architecture in job_config.py.
 */

import type { Settings } from "./settings"

// ============================================================================
// Layer 1: Document Parsing (Optional)
// ============================================================================

export type DocumentParsingProvider = "local" | "mineru" | "baidu_doc"

export type DocumentParsingConfig = {
  provider: DocumentParsingProvider
  // MinerU configuration
  mineruApiToken?: string
  mineruBaseUrl?: string
  mineruModelVersion?: string
  enableFormula?: boolean
  enableTable?: boolean
  mineruLanguage?: string
  mineruIsOcr?: boolean
  // Baidu Doc configuration
  baiduDocParseType?: "general" | "paddle_vl"
}

// ============================================================================
// Layer 2: Layout Detection (Optional)
// ============================================================================

export type LayoutDetectionConfig = {
  enabled: boolean
  model: "pp_doclayout_v3" | "pp_doclayout_s" | "pp_doclayout_m" | "pp_doclayout_l" | "doclayout_yolo"
  enableSam: boolean  // SAM polygon refinement for image regions
}

// ============================================================================
// Layer 3: Text Recognition (Required)
// ============================================================================

export type TextRecognitionProvider = "paddleocr" | "tesseract" | "aiocr" | "baidu"

export type TextRecognitionConfig = {
  provider: TextRecognitionProvider
  // Tesseract-specific
  language?: string
  minConfidence?: number
  // AI OCR-specific
  aiProvider?: string
  apiKey?: string
  baseUrl?: string
  model?: string
  promptPreset?: string
  pageConcurrency?: number
  blockConcurrency?: number
  maxRetries?: number
  requestsPerMinute?: number
  tokensPerMinute?: number
  // Baidu OCR-specific
  baiduAppId?: string
  baiduApiKey?: string
  baiduSecretKey?: string
}

// ============================================================================
// Combined OCR Configuration V3
// ============================================================================

export type OcrConfigV3 = {
  parsing: DocumentParsingConfig
  layout: LayoutDetectionConfig
  recognition: TextRecognitionConfig
  renderDpi: number
  strictMode: boolean
}

// ============================================================================
// Mapping to Backend JobConfig
// ============================================================================

/**
 * Map frontend three-layer config to backend nested structure.
 *
 * Backend structure:
 * - parse.provider: "local" | "mineru" | "baidu_doc"
 * - parse.mineru.*: MinerU settings
 * - parse.baidu_doc.*: Baidu doc settings
 * - ocr.provider: "paddleocr" | "tesseract" | "aiocr" | "baidu"
 * - ocr.ai.layout_model: layout model selection
 * - ocr.ai.chain_mode: "direct" | "layout_block"
 * - ocr.baidu.*: Baidu OCR credentials
 * - ocr.enable_sam: SAM polygon refinement
 */
export function mapOcrConfigV3ToBackend(config: OcrConfigV3): any {
  const { parsing, layout, recognition, renderDpi, strictMode } = config

  // Layer 1: Document Parsing
  const parseConfig: any = {
    provider: parsing.provider,
  }

  if (parsing.provider === "mineru") {
    parseConfig.mineru = {
      api_token: parsing.mineruApiToken,
      base_url: parsing.mineruBaseUrl,
      model_version: parsing.mineruModelVersion || "vlm",
      enable_formula: parsing.enableFormula ?? true,
      enable_table: parsing.enableTable ?? true,
      language: parsing.mineruLanguage,
      is_ocr: parsing.mineruIsOcr,
    }
  } else if (parsing.provider === "baidu_doc") {
    parseConfig.baidu_doc = {
      parse_type: parsing.baiduDocParseType || "paddle_vl",
    }
  }

  // Layer 2 & 3: OCR Configuration
  const ocrConfig: any = {
    render_dpi: renderDpi,
    strict_mode: strictMode,
    enable_sam: layout.enableSam,
  }

  // Map recognition provider
  if (recognition.provider === "paddleocr") {
    ocrConfig.provider = "paddleocr"
    // PaddleOCR always uses layout detection internally
    ocrConfig.ai = {
      layout_model: layout.model,
    }
  } else if (recognition.provider === "tesseract") {
    ocrConfig.provider = "tesseract"
    // Tesseract can optionally use layout detection
    if (layout.enabled) {
      ocrConfig.ai = {
        layout_model: layout.model,
      }
    }
    if (recognition.language || recognition.minConfidence !== undefined) {
      ocrConfig.tesseract = {
        language: recognition.language,
        min_confidence: recognition.minConfidence,
      }
    }
  } else if (recognition.provider === "aiocr") {
    ocrConfig.provider = "aiocr"
    ocrConfig.ai = {
      provider: recognition.aiProvider || "auto",
      api_key: recognition.apiKey || "",
      base_url: recognition.baseUrl,
      model: recognition.model,
      chain_mode: layout.enabled ? "layout_block" : "direct",
      layout_model: layout.model,
      prompt_preset: recognition.promptPreset || "auto",
      page_concurrency: recognition.pageConcurrency ?? 1,
      block_concurrency: recognition.blockConcurrency,
      max_retries: recognition.maxRetries ?? 0,
      requests_per_minute: recognition.requestsPerMinute,
      tokens_per_minute: recognition.tokensPerMinute,
    }
  } else if (recognition.provider === "baidu") {
    ocrConfig.provider = "baidu"
    ocrConfig.baidu = {
      app_id: recognition.baiduAppId,
      api_key: recognition.baiduApiKey,
      secret_key: recognition.baiduSecretKey,
    }
    // Baidu OCR can optionally use layout detection
    if (layout.enabled) {
      ocrConfig.ai = {
        layout_model: layout.model,
      }
    }
  }

  return {
    parse: parseConfig,
    ocr: ocrConfig,
  }
}

/**
 * Map backend JobConfig to frontend three-layer config.
 */
export function mapBackendToOcrConfigV3(backend: any): OcrConfigV3 {
  // Layer 1: Document Parsing
  const parseProvider = backend.parse?.provider || "local"
  const parsing: DocumentParsingConfig = {
    provider: parseProvider as DocumentParsingProvider,
  }

  if (parseProvider === "mineru") {
    parsing.mineruApiToken = backend.parse?.mineru?.api_token
    parsing.mineruBaseUrl = backend.parse?.mineru?.base_url
    parsing.mineruModelVersion = backend.parse?.mineru?.model_version
    parsing.enableFormula = backend.parse?.mineru?.enable_formula
    parsing.enableTable = backend.parse?.mineru?.enable_table
    parsing.mineruLanguage = backend.parse?.mineru?.language
    parsing.mineruIsOcr = backend.parse?.mineru?.is_ocr
  } else if (parseProvider === "baidu_doc") {
    parsing.baiduDocParseType = backend.parse?.baidu_doc?.parse_type
  }

  // Layer 2: Layout Detection
  const ocrProvider = backend.ocr?.provider || "paddleocr"
  const chainMode = backend.ocr?.ai?.chain_mode || "direct"
  const layoutModel = backend.ocr?.ai?.layout_model || "pp_doclayout_v3"
  const enableSam = backend.ocr?.enable_sam ?? false

  let layoutEnabled = false
  if (ocrProvider === "paddleocr") {
    layoutEnabled = true  // PaddleOCR always uses layout
  } else if (ocrProvider === "aiocr") {
    layoutEnabled = chainMode === "layout_block"
  } else if (ocrProvider === "tesseract" || ocrProvider === "baidu") {
    layoutEnabled = !!backend.ocr?.ai?.layout_model
  }

  const layout: LayoutDetectionConfig = {
    enabled: layoutEnabled,
    model: layoutModel as LayoutDetectionConfig["model"],
    enableSam,
  }

  // Layer 3: Text Recognition
  let recognition: TextRecognitionConfig
  if (ocrProvider === "paddleocr") {
    recognition = { provider: "paddleocr" }
  } else if (ocrProvider === "tesseract") {
    recognition = {
      provider: "tesseract",
      language: backend.ocr?.tesseract?.language,
      minConfidence: backend.ocr?.tesseract?.min_confidence,
    }
  } else if (ocrProvider === "aiocr") {
    recognition = {
      provider: "aiocr",
      aiProvider: backend.ocr?.ai?.provider || "auto",
      apiKey: backend.ocr?.ai?.api_key || "",
      baseUrl: backend.ocr?.ai?.base_url,
      model: backend.ocr?.ai?.model,
      promptPreset: backend.ocr?.ai?.prompt_preset,
      pageConcurrency: backend.ocr?.ai?.page_concurrency,
      blockConcurrency: backend.ocr?.ai?.block_concurrency,
      maxRetries: backend.ocr?.ai?.max_retries,
      requestsPerMinute: backend.ocr?.ai?.requests_per_minute,
      tokensPerMinute: backend.ocr?.ai?.tokens_per_minute,
    }
  } else if (ocrProvider === "baidu") {
    recognition = {
      provider: "baidu",
      baiduAppId: backend.ocr?.baidu?.app_id,
      baiduApiKey: backend.ocr?.baidu?.api_key,
      baiduSecretKey: backend.ocr?.baidu?.secret_key,
    }
  } else {
    recognition = { provider: "paddleocr" }  // Default fallback
  }

  return {
    parsing,
    layout,
    recognition,
    renderDpi: backend.ocr?.render_dpi ?? 200,
    strictMode: backend.ocr?.strict_mode ?? true,
  }
}

// ============================================================================
// Migration from V2 to V3
// ============================================================================

/**
 * Migrate OcrConfigV2 to OcrConfigV3.
 * V2 only had layout + recognition, V3 adds document parsing layer.
 */
export function migrateV2ToV3(v2Config: any): OcrConfigV3 {
  return {
    parsing: {
      provider: "local",  // V2 didn't have parsing layer
    },
    layout: v2Config.layout,
    recognition: v2Config.recognition,
    renderDpi: v2Config.renderDpi,
    strictMode: v2Config.strictMode,
  }
}

/**
 * Migrate old Settings format to new OcrConfigV3.
 */
export function migrateSettingsToOcrConfigV3(settings: Settings): OcrConfigV3 {
  const parseMode = settings.parseEngineMode
  const ocrProvider = settings.ocrProvider

  // Layer 1: Document Parsing
  const parsing: DocumentParsingConfig = {
    provider: "local",  // Default to local parsing
  }

  // Layer 2: Layout Detection
  let layoutEnabled = false
  if (parseMode === "remote_ocr" && settings.ocrAiChainMode === "layout_block") {
    layoutEnabled = true
  } else if (ocrProvider === "paddleocr") {
    layoutEnabled = true
  }

  const layout: LayoutDetectionConfig = {
    enabled: layoutEnabled,
    model: settings.ocrAiLayoutModel,
    enableSam: settings.enableSam,
  }

  // Layer 3: Text Recognition
  let recognition: TextRecognitionConfig
  if (parseMode === "remote_ocr") {
    recognition = {
      provider: "aiocr",
      aiProvider: settings.ocrAiProvider,
      apiKey: settings.ocrAiApiKey,
      baseUrl: settings.ocrAiBaseUrl,
      model: settings.ocrAiModel,
      promptPreset: settings.ocrAiPromptPreset,
      pageConcurrency: parseInt(settings.ocrAiPageConcurrency) || 1,
      blockConcurrency: settings.ocrAiBlockConcurrency ? parseInt(settings.ocrAiBlockConcurrency) : undefined,
      maxRetries: parseInt(settings.ocrAiMaxRetries) || 0,
      requestsPerMinute: settings.ocrAiRequestsPerMinute ? parseInt(settings.ocrAiRequestsPerMinute) : undefined,
      tokensPerMinute: settings.ocrAiTokensPerMinute ? parseInt(settings.ocrAiTokensPerMinute) : undefined,
    }
  } else if (ocrProvider === "tesseract") {
    recognition = {
      provider: "tesseract",
      language: settings.ocrTesseractLanguage,
      minConfidence: parseInt(settings.ocrTesseractMinConfidence) || 35,
    }
  } else {
    recognition = { provider: "paddleocr" }
  }

  return {
    parsing,
    layout,
    recognition,
    renderDpi: parseInt(settings.ocrRenderDpi) || 200,
    strictMode: settings.ocrStrictMode,
  }
}

/**
 * Apply OcrConfigV3 changes back to Settings format (for backward compatibility).
 */
export function applyOcrConfigV3ToSettings(config: OcrConfigV3, currentSettings: Settings): Partial<Settings> {
  const updates: Partial<Settings> = {
    ocrRenderDpi: String(config.renderDpi),
    ocrStrictMode: config.strictMode,
    enableSam: config.layout.enableSam,
    ocrAiLayoutModel: config.layout.model,
  }

  // Map recognition provider
  if (config.recognition.provider === "paddleocr") {
    updates.parseEngineMode = "local_ocr"
    updates.ocrProvider = "paddleocr"
  } else if (config.recognition.provider === "tesseract") {
    updates.parseEngineMode = "local_ocr"
    updates.ocrProvider = "tesseract"
    if (config.recognition.language) {
      updates.ocrTesseractLanguage = config.recognition.language
    }
    if (config.recognition.minConfidence !== undefined) {
      updates.ocrTesseractMinConfidence = String(config.recognition.minConfidence)
    }
  } else if (config.recognition.provider === "aiocr") {
    updates.parseEngineMode = "remote_ocr"
    updates.ocrProvider = "aiocr"
    updates.ocrAiChainMode = config.layout.enabled ? "layout_block" : "direct"
    updates.ocrAiProvider = config.recognition.aiProvider as any
    updates.ocrAiApiKey = config.recognition.apiKey
    updates.ocrAiBaseUrl = config.recognition.baseUrl || ""
    updates.ocrAiModel = config.recognition.model || ""
    updates.ocrAiPromptPreset = config.recognition.promptPreset as any || "auto"
    updates.ocrAiPageConcurrency = String(config.recognition.pageConcurrency ?? 1)
    updates.ocrAiBlockConcurrency = config.recognition.blockConcurrency ? String(config.recognition.blockConcurrency) : ""
    updates.ocrAiMaxRetries = String(config.recognition.maxRetries ?? 0)
    updates.ocrAiRequestsPerMinute = config.recognition.requestsPerMinute ? String(config.recognition.requestsPerMinute) : ""
    updates.ocrAiTokensPerMinute = config.recognition.tokensPerMinute ? String(config.recognition.tokensPerMinute) : ""
  } else if (config.recognition.provider === "baidu") {
    updates.parseEngineMode = "local_ocr"
    updates.ocrProvider = "baidu"
  }

  return updates
}

// ============================================================================
// UI Helper Functions
// ============================================================================

export function getParsingProviderLabel(provider: DocumentParsingProvider): string {
  const labels: Record<DocumentParsingProvider, string> = {
    local: "本地解析（默认）",
    mineru: "MinerU 解析",
    baidu_doc: "百度文档解析",
  }
  return labels[provider]
}

export function getParsingProviderDescription(provider: DocumentParsingProvider): string {
  const descriptions: Record<DocumentParsingProvider, string> = {
    local: "使用本地 PDF 解析器，适合大多数文档",
    mineru: "使用 MinerU 云端解析，支持复杂公式和表格",
    baidu_doc: "使用百度文档解析 API，支持多种文档格式",
  }
  return descriptions[provider]
}

export function getRecognitionProviderLabel(provider: TextRecognitionProvider): string {
  const labels: Record<TextRecognitionProvider, string> = {
    paddleocr: "PaddleOCR（本地）",
    tesseract: "Tesseract（本地）",
    aiocr: "AI OCR（远程）",
    baidu: "百度 OCR（远程）",
  }
  return labels[provider]
}

export function getRecognitionProviderDescription(provider: TextRecognitionProvider): string {
  const descriptions: Record<TextRecognitionProvider, string> = {
    paddleocr: "百度开源 OCR 引擎，中文识别效果好",
    tesseract: "开源 OCR 引擎，支持多语言",
    aiocr: "使用 AI 视觉模型进行识别，精度最高",
    baidu: "百度 OCR API，识别速度快且稳定",
  }
  return descriptions[provider]
}

export function requiresApiKey(provider: TextRecognitionProvider): boolean {
  return provider === "aiocr" || provider === "baidu"
}

export function supportsBlockConcurrency(config: OcrConfigV3): boolean {
  return config.layout.enabled && config.recognition.provider === "aiocr"
}

export function requiresParsingApiKey(provider: DocumentParsingProvider): boolean {
  return provider === "mineru"
}
