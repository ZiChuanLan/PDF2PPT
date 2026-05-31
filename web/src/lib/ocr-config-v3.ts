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

import type { Settings, MineruModelVersion, OcrAiProvider, OcrAiPromptPreset } from "./settings"

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
// Migration from Settings to V3
// ============================================================================

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

  // Read MinerU configuration
  if (parseMode === "mineru_cloud") {
    parsing.provider = "mineru"
    parsing.mineruApiToken = settings.mineruApiToken
    parsing.mineruBaseUrl = settings.mineruBaseUrl
    parsing.mineruModelVersion = settings.mineruModelVersion
    parsing.enableFormula = settings.mineruEnableFormula
    parsing.enableTable = settings.mineruEnableTable
    parsing.mineruLanguage = settings.mineruLanguage
    parsing.mineruIsOcr = settings.mineruIsOcr
  }
  // Read Baidu Doc configuration
  else if (parseMode === "baidu_doc") {
    parsing.provider = "baidu_doc"
    parsing.baiduDocParseType = settings.baiduDocParseType
  }

  // Layer 2: Layout Detection
  let layoutEnabled = false
  if (parseMode === "remote_ocr" && settings.ocrAiChainMode === "layout_block") {
    layoutEnabled = true
  } else if (ocrProvider === "paddleocr") {
    layoutEnabled = true  // PaddleOCR always uses layout detection
  } else if (ocrProvider === "tesseract" || ocrProvider === "baidu") {
    // Tesseract and Baidu OCR can optionally use layout detection
    layoutEnabled = !!settings.ocrAiLayoutModel
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
  } else if (ocrProvider === "baidu") {
    recognition = {
      provider: "baidu",
      baiduAppId: settings.ocrBaiduAppId,
      baiduApiKey: settings.ocrBaiduApiKey,
      baiduSecretKey: settings.ocrBaiduSecretKey,
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
export function applyOcrConfigV3ToSettings(config: OcrConfigV3, _currentSettings: Settings): Partial<Settings> {
  const updates: Partial<Settings> = {
    ocrRenderDpi: String(config.renderDpi),
    ocrStrictMode: config.strictMode,
  }

  // ============================================================================
  // Layer 1: Document Parsing
  // ============================================================================

  if (config.parsing.provider === "mineru") {
    updates.parseEngineMode = "mineru_cloud"
    updates.provider = "mineru"
    updates.mineruApiToken = config.parsing.mineruApiToken || ""
    updates.mineruBaseUrl = config.parsing.mineruBaseUrl || ""
    updates.mineruModelVersion = (config.parsing.mineruModelVersion as MineruModelVersion) || "vlm"
    updates.mineruEnableFormula = config.parsing.enableFormula ?? true
    updates.mineruEnableTable = config.parsing.enableTable ?? true
    updates.mineruLanguage = config.parsing.mineruLanguage || ""
    updates.mineruIsOcr = config.parsing.mineruIsOcr ?? false
    // MinerU handles everything — clear OCR-specific state
    updates.enableSam = false
  } else if (config.parsing.provider === "baidu_doc") {
    updates.parseEngineMode = "baidu_doc"
    updates.baiduDocParseType = config.parsing.baiduDocParseType || "paddle_vl"
    // Baidu Doc handles everything — clear OCR-specific state
    updates.enableSam = false
  } else {
    // ============================================================================
    // Local parsing — Layer 2 + Layer 3 are relevant
    // ============================================================================

    // Layer 2: Layout Detection — only write layout model when enabled,
    // otherwise migrateSettingsToOcrConfigV3 will re-derive enabled=true
    if (config.layout.enabled) {
      updates.ocrAiLayoutModel = config.layout.model
      updates.enableSam = config.layout.enableSam
    } else {
      updates.ocrAiLayoutModel = undefined
      updates.enableSam = false
    }

    // Layer 3: Text Recognition
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
      updates.ocrAiProvider = config.recognition.aiProvider as OcrAiProvider
      updates.ocrAiApiKey = config.recognition.apiKey || ""
      updates.ocrAiBaseUrl = config.recognition.baseUrl || ""
      updates.ocrAiModel = config.recognition.model || ""
      updates.ocrAiPromptPreset = config.recognition.promptPreset as OcrAiPromptPreset || "auto"
      updates.ocrAiPageConcurrency = String(config.recognition.pageConcurrency ?? 1)
      updates.ocrAiBlockConcurrency = config.recognition.blockConcurrency ? String(config.recognition.blockConcurrency) : ""
      updates.ocrAiMaxRetries = String(config.recognition.maxRetries ?? 0)
      updates.ocrAiRequestsPerMinute = config.recognition.requestsPerMinute ? String(config.recognition.requestsPerMinute) : ""
      updates.ocrAiTokensPerMinute = config.recognition.tokensPerMinute ? String(config.recognition.tokensPerMinute) : ""
    } else if (config.recognition.provider === "baidu") {
      updates.parseEngineMode = "baidu_doc"
      updates.ocrProvider = "baidu"
      updates.ocrBaiduAppId = config.recognition.baiduAppId || ""
      updates.ocrBaiduApiKey = config.recognition.baiduApiKey || ""
      updates.ocrBaiduSecretKey = config.recognition.baiduSecretKey || ""
    }
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
