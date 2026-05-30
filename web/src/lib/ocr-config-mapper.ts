/**
 * OCR Configuration Mapper
 *
 * Maps between simplified frontend OCR configuration and backend nested structure.
 * This mapper implements the PRD requirements for simplified OCR mode selection.
 */

import type { JobConfig } from "./run-config"

/**
 * Simplified OCR modes for frontend UI.
 *
 * These 4 modes replace the complex provider + chain_mode combinations:
 * - local_machine: Pure local OCR (PaddleOCR/Tesseract)
 * - ai_direct: AI vision model directly processes full page
 * - ai_layout_block: Local layout detection + AI OCR per block (RECOMMENDED)
 * - auto: Backend auto-selects best strategy
 */
export type SimplifiedOcrMode =
  | "local_machine"
  | "ai_direct"
  | "ai_layout_block"
  | "auto"

/**
 * Simplified OCR configuration for frontend.
 *
 * This flattens the backend's nested ocr.ai.* structure into a single-level config.
 */
export interface SimplifiedOcrConfig {
  mode: SimplifiedOcrMode

  // Local layout detection settings (only for ai_layout_block mode)
  layoutModel?: "pp_doclayout_v3" | "pp_doclayout_s" | "pp_doclayout_m" | "pp_doclayout_l" | "doclayout_yolo"
  enableSam?: boolean

  // AI OCR settings (only for AI modes)
  aiProvider?: string
  aiModel?: string
  aiApiKey?: string
  aiBaseUrl?: string

  // Concurrency settings
  pageConcurrency?: number
  blockConcurrency?: number | null

  // Rate limiting
  requestsPerMinute?: number | null
  tokensPerMinute?: number | null
  maxRetries?: number

  // Common settings
  renderDpi?: number
  strictMode?: boolean
}

/**
 * OCR Configuration Mapper.
 *
 * Provides bidirectional mapping between simplified frontend config
 * and backend JobConfig structure.
 */
export class OcrConfigMapper {
  /**
   * Map simplified frontend config to backend JobConfig structure.
   */
  static toBackend(config: SimplifiedOcrConfig): Partial<JobConfig> {
    const ocrProvider = this.mapProvider(config.mode)
    const chainMode = this.mapChainMode(config.mode)

    const result: Partial<JobConfig> = {
      ocr: {
        provider: ocrProvider,
        render_dpi: config.renderDpi,
        strict_mode: config.strictMode ?? true,
        enable_sam: config.enableSam ?? false,
        ai: {
          layout_model: config.layoutModel || "pp_doclayout_v3",
        },
      },
    }

    // Add AI OCR config for AI modes
    if (config.mode === "ai_direct" || config.mode === "ai_layout_block") {
      result.ocr!.ai = {
        provider: config.aiProvider || "auto",
        api_key: config.aiApiKey,
        base_url: config.aiBaseUrl,
        model: config.aiModel,
        chain_mode: chainMode,
        layout_model: config.layoutModel || "pp_doclayout_v3",
        page_concurrency: config.pageConcurrency ?? 1,
        block_concurrency: config.blockConcurrency ?? undefined,
        requests_per_minute: config.requestsPerMinute ?? undefined,
        tokens_per_minute: config.tokensPerMinute ?? undefined,
        max_retries: config.maxRetries ?? 0,
      }
    }

    return result
  }

  /**
   * Map backend JobConfig to simplified frontend config.
   */
  static fromBackend(backend: JobConfig): SimplifiedOcrConfig {
    const provider = backend.ocr?.provider || "auto"
    const chainMode = backend.ocr?.ai?.chain_mode || "direct"

    const mode = this.reverseMapMode(provider, chainMode)

    return {
      mode,
      layoutModel: backend.ocr?.ai?.layout_model as SimplifiedOcrConfig["layoutModel"],
      enableSam: backend.ocr?.enable_sam ?? false,
      aiProvider: backend.ocr?.ai?.provider,
      aiModel: backend.ocr?.ai?.model,
      aiApiKey: backend.ocr?.ai?.api_key,
      aiBaseUrl: backend.ocr?.ai?.base_url,
      pageConcurrency: backend.ocr?.ai?.page_concurrency,
      blockConcurrency: backend.ocr?.ai?.block_concurrency ?? null,
      requestsPerMinute: backend.ocr?.ai?.requests_per_minute ?? null,
      tokensPerMinute: backend.ocr?.ai?.tokens_per_minute ?? null,
      maxRetries: backend.ocr?.ai?.max_retries,
      renderDpi: backend.ocr?.render_dpi,
      strictMode: backend.ocr?.strict_mode,
    }
  }

  /**
   * Map simplified mode to backend provider.
   */
  private static mapProvider(mode: SimplifiedOcrMode): string {
    switch (mode) {
      case "local_machine":
        return "paddle_local"
      case "ai_direct":
      case "ai_layout_block":
        return "aiocr"
      case "auto":
        return "auto"
    }
  }

  /**
   * Map simplified mode to backend chain_mode.
   */
  private static mapChainMode(mode: SimplifiedOcrMode): string {
    switch (mode) {
      case "ai_direct":
        return "direct"
      case "ai_layout_block":
        return "layout_block"
      default:
        return "direct"
    }
  }

  /**
   * Reverse map backend provider + chain_mode to simplified mode.
   */
  private static reverseMapMode(provider: string, chainMode: string): SimplifiedOcrMode {
    if (provider === "paddle_local" || provider === "machine" || provider === "paddleocr" || provider === "tesseract") {
      return "local_machine"
    }

    if (provider === "aiocr") {
      if (chainMode === "layout_block") {
        return "ai_layout_block"
      }
      // Note: doc_parser is deprecated and maps to direct for backward compatibility
      return "ai_direct"
    }

    return "auto"
  }
}

/**
 * Get user-friendly label for OCR mode.
 */
export function getOcrModeLabel(mode: SimplifiedOcrMode): string {
  const labels: Record<SimplifiedOcrMode, string> = {
    local_machine: "完全本地处理",
    ai_direct: "AI 快速识别",
    ai_layout_block: "AI 高质量识别",
    auto: "自动选择",
  }
  return labels[mode]
}

/**
 * Get description for OCR mode.
 */
export function getOcrModeDescription(mode: SimplifiedOcrMode): string {
  const descriptions: Record<SimplifiedOcrMode, string> = {
    local_machine: "使用本地 PaddleOCR，无需网络",
    ai_direct: "整页直接识别，速度快",
    ai_layout_block: "本地版面检测 + AI OCR，质量最高（推荐）",
    auto: "根据文档类型自动选择最佳方案",
  }
  return descriptions[mode]
}

/**
 * Check if a mode requires AI configuration.
 */
export function requiresAiConfig(mode: SimplifiedOcrMode): boolean {
  return mode === "ai_direct" || mode === "ai_layout_block"
}

/**
 * Check if a mode supports layout model selection.
 */
export function supportsLayoutModel(mode: SimplifiedOcrMode): boolean {
  return mode === "ai_layout_block"
}

/**
 * Check if a mode supports SAM polygon refinement.
 */
export function supportsSam(mode: SimplifiedOcrMode): boolean {
  return mode === "ai_layout_block"
}

/**
 * Check if a mode supports block concurrency.
 */
export function supportsBlockConcurrency(mode: SimplifiedOcrMode): boolean {
  return mode === "ai_layout_block"
}
