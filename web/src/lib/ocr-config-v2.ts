/**
 * OCR Configuration V2 - Two-Layer Architecture
 *
 * This module implements the correct two-layer OCR architecture:
 * 1. Layout Detection Layer (optional, independent)
 * 2. Text Recognition Layer (required)
 *
 * Any OCR engine can optionally use layout detection first.
 */

import type { Settings } from "./settings"

// ============================================================================
// Layer 1: Layout Detection (Optional)
// ============================================================================

export type LayoutDetectionConfig = {
  enabled: boolean
  model: "pp_doclayout_v3" | "pp_doclayout_s" | "pp_doclayout_m" | "pp_doclayout_l" | "doclayout_yolo"
  enableSam: boolean  // SAM polygon refinement for image regions
}

// ============================================================================
// Layer 2: Text Recognition (Required)
// ============================================================================

export type TextRecognitionProvider = "paddleocr" | "tesseract" | "aiocr"

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
}

// ============================================================================
// Combined OCR Configuration
// ============================================================================

export type OcrConfigV2 = {
  layout: LayoutDetectionConfig
  recognition: TextRecognitionConfig
  renderDpi: number
  strictMode: boolean
}

// ============================================================================
// Mapping to Backend JobConfig
// ============================================================================

/**
 * Map frontend two-layer config to backend nested structure.
 *
 * Backend mapping rules:
 * 1. Layout enabled + PaddleOCR → provider="paddleocr", layout_model set
 * 2. Layout enabled + Tesseract → provider="tesseract", layout_model set (future support)
 * 3. Layout enabled + AI OCR → provider="aiocr", chain_mode="layout_block"
 * 4. Layout disabled + AI OCR → provider="aiocr", chain_mode="direct"
 * 5. Layout disabled + PaddleOCR → provider="paddleocr" (still uses layout internally)
 */
export function mapOcrConfigV2ToBackend(config: OcrConfigV2): any {
  const { layout, recognition, renderDpi, strictMode } = config

  // Base OCR config
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
    // Future: backend should support layout detection for Tesseract
    if (layout.enabled) {
      ocrConfig.ai = {
        layout_model: layout.model,
      }
    }
    if (recognition.language) {
      ocrConfig.tesseract = {
        language: recognition.language,
      }
    }
    if (recognition.minConfidence !== undefined) {
      ocrConfig.tesseract = {
        ...ocrConfig.tesseract,
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
  }

  return { ocr: ocrConfig }
}

/**
 * Map backend JobConfig to frontend two-layer config.
 */
export function mapBackendToOcrConfigV2(backend: any): OcrConfigV2 {
  const ocrProvider = backend.ocr?.provider || "paddleocr"
  const chainMode = backend.ocr?.ai?.chain_mode || "direct"
  const layoutModel = backend.ocr?.ai?.layout_model || "pp_doclayout_v3"
  const enableSam = backend.ocr?.enable_sam ?? false

  // Determine if layout detection is enabled
  let layoutEnabled = false
  if (ocrProvider === "paddleocr") {
    // PaddleOCR always uses layout
    layoutEnabled = true
  } else if (ocrProvider === "aiocr") {
    layoutEnabled = chainMode === "layout_block"
  } else if (ocrProvider === "tesseract") {
    // Check if layout_model is set (future support)
    layoutEnabled = !!backend.ocr?.ai?.layout_model
  }

  const layout: LayoutDetectionConfig = {
    enabled: layoutEnabled,
    model: layoutModel as LayoutDetectionConfig["model"],
    enableSam,
  }

  // Map recognition config
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
  } else {
    // Default fallback
    recognition = { provider: "paddleocr" }
  }

  return {
    layout,
    recognition,
    renderDpi: backend.ocr?.render_dpi ?? 200,
    strictMode: backend.ocr?.strict_mode ?? true,
  }
}

// ============================================================================
// Migration from old Settings format
// ============================================================================

/**
 * Migrate old Settings format to new OcrConfigV2.
 */
export function migrateSettingsToOcrConfigV2(settings: Settings): OcrConfigV2 {
  const parseMode = settings.parseEngineMode
  const ocrProvider = settings.ocrProvider

  // Determine layout config
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

  // Determine recognition config
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
    layout,
    recognition,
    renderDpi: parseInt(settings.ocrRenderDpi) || 200,
    strictMode: settings.ocrStrictMode,
  }
}

/**
 * Apply OcrConfigV2 changes back to Settings format (for backward compatibility).
 */
export function applyOcrConfigV2ToSettings(config: OcrConfigV2, currentSettings: Settings): Partial<Settings> {
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
  }

  return updates
}

// ============================================================================
// UI Helper Functions
// ============================================================================

export function getRecognitionProviderLabel(provider: TextRecognitionProvider): string {
  const labels: Record<TextRecognitionProvider, string> = {
    paddleocr: "PaddleOCR（本地）",
    tesseract: "Tesseract（本地）",
    aiocr: "AI OCR（远程）",
  }
  return labels[provider]
}

export function getRecognitionProviderDescription(provider: TextRecognitionProvider): string {
  const descriptions: Record<TextRecognitionProvider, string> = {
    paddleocr: "百度开源 OCR 引擎，中文识别效果好",
    tesseract: "开源 OCR 引擎，支持多语言",
    aiocr: "使用 AI 视觉模型进行识别，精度最高",
  }
  return descriptions[provider]
}

export function supportsLayoutDetection(provider: TextRecognitionProvider): boolean {
  // Currently all providers can use layout detection
  // (Tesseract support is planned for backend)
  return true
}

export function requiresApiKey(provider: TextRecognitionProvider): boolean {
  return provider === "aiocr"
}

export function supportsBlockConcurrency(config: OcrConfigV2): boolean {
  return config.layout.enabled && config.recognition.provider === "aiocr"
}
