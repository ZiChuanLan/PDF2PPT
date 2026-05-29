import {
  BAIDU_DOC_PARSE_TYPE_LABELS,
  DEFAULT_AIOCR_CHAIN_MODE,
  DEFAULT_AIOCR_MODEL,
  DEFAULT_AIOCR_PROVIDER,
  isPaddleOcrVlModelName,
  PARSE_ENGINE_MODE_LABELS as SETTINGS_PARSE_ENGINE_MODE_LABELS,
  SILICONFLOW_BASE_URL,
  type OcrAiChainMode,
  type OcrAiLayoutModel,
  type BaiduDocParseType,
  type MainProvider,
  type OcrProvider,
  type PptGenerationMode,
  type ParseEngineMode,
  type Settings,
} from "./settings.ts"

export type OcrConfigSource = "dedicated" | "none"
export type { ParseEngineMode } from "./settings.ts"

export type RunConfig = {
  parseProvider: "local" | "baidu_doc" | "mineru"
  baiduDocParseType: BaiduDocParseType
  llmProvider: "openai" | "claude"
  mainApiKey: string
  mainBaseUrl: string
  mainModel: string
  selectedOcrProvider: OcrProvider
  effectiveOcrProvider: OcrProvider
  effectiveOcrAiKey: string
  effectiveOcrAiBaseUrl: string
  effectiveOcrAiModel: string
  effectiveOcrAiProvider: string
  ocrAiChainMode: OcrAiChainMode
  ocrAiLayoutModel: OcrAiLayoutModel
  ocrAiPageConcurrency: number
  ocrAiBlockConcurrency: number | null
  ocrAiRequestsPerMinute: number | null
  ocrAiTokensPerMinute: number | null
  ocrAiMaxRetries: number
  ocrAiConfigSource: OcrConfigSource
  shouldAttachOcrAiParams: boolean
  pptGenerationMode: PptGenerationMode
}

export type ValidationResult = {
  ok: boolean
  message?: string
}

export type CreateJobOptions = {
  retainProcessArtifacts?: boolean
}

export type OcrSettingsState = {
  isMineruProvider: boolean
  isBaiduDocParseMode: boolean
  isOcrEnabledForCurrentEngine: boolean
  hasBaiduCredentials: boolean
  canUseAiOcr: boolean
  selectedOcrProvider: OcrProvider
  parseEngineMode: ParseEngineMode
  isOcrProviderPaddleLocal: boolean
  isOcrProviderBaidu: boolean
  isOcrProviderTesseract: boolean
  needsRequiredOcrAiConfig: boolean
  shouldShowAiVendorAdapter: boolean
  shouldShowOcrProviderSelector: boolean
  shouldShowBaiduConfig: boolean
  shouldShowTesseractConfig: boolean
  shouldShowLocalOcrCheck: boolean
  availableOcrProviders: OcrProvider[]
  ocrModelsConfigSource: OcrConfigSource
  ocrModelsApiKey: string
  ocrModelsBaseUrl: string
  isOcrAiChainDirect: boolean
  isOcrAiChainDocParser: boolean
  isOcrAiChainLayoutBlock: boolean
  runConfig: RunConfig
}

export const OCR_PROVIDER_LABELS: Record<OcrProvider, string> = {
  auto: "自动（混合）",
  aiocr: "AIOCR",
  machine: "本地 OCR",
  baidu: "百度 OCR",
  tesseract: "Tesseract",
  paddleocr: "PaddleOCR",
}

const OCR_CONFIG_SOURCE_LABELS: Record<OcrConfigSource, string> = {
  dedicated: "OCR 独立配置",
  none: "未配置",
}

export const PARSE_ENGINE_MODE_LABELS = SETTINGS_PARSE_ENGINE_MODE_LABELS

export const PARSE_ENGINE_OPTIONS: Array<{ id: ParseEngineMode; label: string }> = [
  { id: "baidu_doc", label: PARSE_ENGINE_MODE_LABELS.baidu_doc },
  { id: "remote_ocr", label: PARSE_ENGINE_MODE_LABELS.remote_ocr },
  { id: "local_ocr", label: PARSE_ENGINE_MODE_LABELS.local_ocr },
  { id: "mineru_cloud", label: PARSE_ENGINE_MODE_LABELS.mineru_cloud },
]

export const LOCAL_PARSE_OCR_PROVIDERS: OcrProvider[] = ["paddleocr", "tesseract"]

export const REMOTE_PARSE_OCR_PROVIDERS: OcrProvider[] = ["aiocr"]
export const BAIDU_DOC_PARSE_OCR_PROVIDERS: OcrProvider[] = []
export const MINERU_OCR_PROVIDERS: OcrProvider[] = []

export function getOcrConfigSourceLabel(source: OcrConfigSource): string {
  return OCR_CONFIG_SOURCE_LABELS[source]
}

export function resolveAutoOcrAiPageConcurrency(
  settings: Pick<
    Settings,
    "parseEngineMode" | "pptGenerationMode" | "ocrAiChainMode" | "ocrAiModel"
  >
): number {
  if (settings.parseEngineMode !== "remote_ocr") {
    return 1
  }
  if (isPaddleOcrVlModelName(settings.ocrAiModel)) {
    return 1
  }
  if (settings.pptGenerationMode === "turbo") {
    if (settings.ocrAiChainMode === "direct") {
      return 4
    }
    if (settings.ocrAiChainMode === "layout_block") {
      return 2
    }
  }
  if (
    settings.pptGenerationMode === "fast" &&
    settings.ocrAiChainMode === "layout_block"
  ) {
    return 2
  }
  return 1
}

export function resolveAutoOcrAiBlockConcurrency(
  settings: Pick<Settings, "parseEngineMode" | "ocrAiChainMode">,
  pageConcurrency: number
): number | null {
  if (settings.parseEngineMode !== "remote_ocr") {
    return null
  }
  if (settings.ocrAiChainMode !== "layout_block") {
    return null
  }
  return Math.min(8, Math.max(1, Number(pageConcurrency) || 1))
}

function getResolvedMainProvider(settings: Settings): MainProvider {
  return settings.parseEngineMode === "mineru_cloud" || settings.provider === "mineru"
    ? settings.preferredMainProvider
    : settings.provider
}

function getPreferredLocalOcrProvider(settings: Settings): OcrProvider {
  const rawProvider = (settings.ocrProvider || "").trim().toLowerCase()
  if (rawProvider === "tesseract" || rawProvider === "paddleocr") {
    return rawProvider as OcrProvider
  }
  if (rawProvider === "machine") {
    return "machine"
  }
  // Backward compat: old paddle_local → paddleocr
  if (rawProvider === "paddle_local") {
    return "paddleocr"
  }
  return "paddleocr"
}

function resolveParseEngineMode(settings: Settings): ParseEngineMode {
  const mode = settings.parseEngineMode
  if (
    mode === "local_ocr" ||
    mode === "remote_ocr" ||
    mode === "baidu_doc" ||
    mode === "mineru_cloud"
  ) {
    return mode
  }
  if (settings.provider === "mineru") {
    return "mineru_cloud"
  }
  if (settings.ocrProvider === "baidu") {
    return "baidu_doc"
  }
  if (settings.ocrProvider === "aiocr") {
    return "remote_ocr"
  }
  return "local_ocr"
}

export function getMainProviderConfig(settings: Settings) {
  const provider = getResolvedMainProvider(settings)
  if (provider === "claude") {
    return {
      provider: "claude" as const,
      ocrAdapter: null,
      apiKey: settings.claudeApiKey.trim(),
      baseUrl: "",
      model: "",
    }
  }
  return {
    provider: "openai" as const,
    ocrAdapter: "openai" as const,
    apiKey: settings.openaiApiKey.trim(),
    baseUrl: settings.openaiBaseUrl.trim(),
    model: settings.openaiModel.trim(),
  }
}

export function normalizeVisibleOcrProvider(settings: Settings): OcrProvider {
  const parseEngineMode = resolveParseEngineMode(settings)

  if (parseEngineMode === "mineru_cloud" || settings.provider === "mineru") {
    return "auto"
  }

  if (parseEngineMode === "remote_ocr") {
    return "aiocr"
  }

  if (parseEngineMode === "baidu_doc") {
    return "baidu"
  }

  return getPreferredLocalOcrProvider(settings)
}

function resolveOcrAiConfigSource({
  explicitAiOcrSelected,
  dedicatedApiKey,
}: {
  explicitAiOcrSelected: boolean
  dedicatedApiKey: string
}): OcrConfigSource {
  if (!explicitAiOcrSelected) return "none"
  return dedicatedApiKey ? "dedicated" : "none"
}

function toFinitePositiveIntOrNull(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const n = Number(trimmed)
  if (!Number.isFinite(n) || n <= 0) return null
  return Math.round(n)
}

function getDedicatedOcrAiBaseUrl(settings: Settings): string {
  const baseUrl = settings.ocrAiBaseUrl.trim()
  if (baseUrl) return baseUrl
  return settings.ocrAiProvider === "siliconflow" ? SILICONFLOW_BASE_URL : ""
}

export function resolveRunConfig(settings: Settings): RunConfig {
  const parseEngineMode = resolveParseEngineMode(settings)
  const parseProvider: RunConfig["parseProvider"] =
    parseEngineMode === "mineru_cloud"
      ? "mineru"
      : parseEngineMode === "baidu_doc"
        ? "baidu_doc"
        : "local"
  const main = getMainProviderConfig(settings)
  const selectedOcrProvider = normalizeVisibleOcrProvider(settings)
  const effectiveOcrProvider = selectedOcrProvider
  const explicitAiOcrSelected = parseEngineMode === "remote_ocr"
  const dedicatedOcrAiKey = settings.ocrAiApiKey.trim()
  const ocrAiConfigSource = resolveOcrAiConfigSource({
    explicitAiOcrSelected,
    dedicatedApiKey: dedicatedOcrAiKey,
  })
  const effectiveOcrAiKey =
    ocrAiConfigSource === "dedicated"
      ? dedicatedOcrAiKey
      : ""
  const effectiveOcrAiBaseUrl =
    ocrAiConfigSource === "dedicated"
      ? getDedicatedOcrAiBaseUrl(settings)
      : ""
  const effectiveOcrAiModel = explicitAiOcrSelected ? settings.ocrAiModel.trim() : ""
  const effectiveOcrAiProvider = explicitAiOcrSelected
    ? (settings.ocrAiProvider || "auto").trim() || "auto"
    : "auto"
  const ocrAiChainMode: OcrAiChainMode = explicitAiOcrSelected
    ? settings.ocrAiChainMode
    : "direct"
  const ocrAiLayoutModel: OcrAiLayoutModel = settings.ocrAiLayoutModel || "pp_doclayout_v3"
  const explicitOcrAiPageConcurrency = Math.min(
    8,
    Math.max(1, Number(settings.ocrAiPageConcurrency) || 1)
  )
  const ocrAiPageConcurrency = settings.ocrAiPageConcurrencyAuto
    ? resolveAutoOcrAiPageConcurrency({
        parseEngineMode,
        pptGenerationMode: settings.pptGenerationMode,
        ocrAiChainMode,
        ocrAiModel: settings.ocrAiModel,
      })
    : explicitOcrAiPageConcurrency
  const explicitOcrAiBlockConcurrency = toFinitePositiveIntOrNull(
    settings.ocrAiBlockConcurrency
  )
  const ocrAiBlockConcurrency =
    explicitOcrAiBlockConcurrency ??
    resolveAutoOcrAiBlockConcurrency(
      {
        parseEngineMode,
        ocrAiChainMode,
      },
      ocrAiPageConcurrency
    )
  const ocrAiRequestsPerMinute = toFinitePositiveIntOrNull(settings.ocrAiRequestsPerMinute)
  const ocrAiTokensPerMinute = toFinitePositiveIntOrNull(settings.ocrAiTokensPerMinute)
  const ocrAiMaxRetries = Math.min(8, Math.max(0, Number(settings.ocrAiMaxRetries) || 0))

  const shouldAttachOcrAiParams = explicitAiOcrSelected && Boolean(effectiveOcrAiKey)

  return {
    parseProvider,
    baiduDocParseType: settings.baiduDocParseType,
    llmProvider: main.provider,
    mainApiKey: main.apiKey,
    mainBaseUrl: main.baseUrl,
    mainModel: main.model,
    selectedOcrProvider,
    effectiveOcrProvider,
    effectiveOcrAiKey,
    effectiveOcrAiBaseUrl,
    effectiveOcrAiModel,
    effectiveOcrAiProvider,
    ocrAiChainMode,
    ocrAiLayoutModel,
    ocrAiPageConcurrency,
    ocrAiBlockConcurrency,
    ocrAiRequestsPerMinute,
    ocrAiTokensPerMinute,
    ocrAiMaxRetries,
    ocrAiConfigSource,
    shouldAttachOcrAiParams,
    pptGenerationMode: settings.pptGenerationMode,
  }
}

export function resolveOcrSettingsState(settings: Settings): OcrSettingsState {
  const runConfig = resolveRunConfig(settings)
  const parseEngineMode = runConfig.parseProvider === "mineru"
    ? "mineru_cloud" as ParseEngineMode
    : runConfig.parseProvider === "baidu_doc"
      ? "baidu_doc" as ParseEngineMode
      : settings.parseEngineMode
  const isMineruProvider = parseEngineMode === "mineru_cloud"
  const isBaiduDocParseMode = parseEngineMode === "baidu_doc"
  const isOcrEnabledForCurrentEngine = !isMineruProvider
  const hasBaiduCredentials =
    Boolean(settings.ocrBaiduApiKey.trim()) &&
    Boolean(settings.ocrBaiduSecretKey.trim())
  const canUseAiOcr = parseEngineMode === "local_ocr" || parseEngineMode === "remote_ocr"
  const selectedOcrProvider = runConfig.selectedOcrProvider
  const isOcrProviderMachine = selectedOcrProvider === "machine"
  const isOcrProviderBaidu = selectedOcrProvider === "baidu"
  const isOcrProviderTesseract = false  // deprecated, use machine
  const needsRequiredOcrAiConfig = parseEngineMode === "remote_ocr"
  const shouldShowAiVendorAdapter = needsRequiredOcrAiConfig
  const shouldShowOcrProviderSelector = parseEngineMode === "local_ocr"
  const shouldShowBaiduConfig = isBaiduDocParseMode || isOcrProviderBaidu
  const shouldShowTesseractConfig = false  // deprecated, machine handles local OCR
  const shouldShowLocalOcrCheck =
    !isMineruProvider &&
    !isBaiduDocParseMode &&
    isOcrProviderMachine
  const availableOcrProviders = isMineruProvider
    ? MINERU_OCR_PROVIDERS
    : isBaiduDocParseMode
      ? BAIDU_DOC_PARSE_OCR_PROVIDERS
    : parseEngineMode === "remote_ocr"
      ? REMOTE_PARSE_OCR_PROVIDERS
      : LOCAL_PARSE_OCR_PROVIDERS
  const ocrModelsConfigSource = needsRequiredOcrAiConfig
    ? settings.ocrAiApiKey.trim()
      ? "dedicated"
      : "none"
    : "none"
  const ocrModelsApiKey =
    ocrModelsConfigSource === "dedicated"
      ? settings.ocrAiApiKey.trim()
      : ""
  const ocrModelsBaseUrl =
    ocrModelsConfigSource === "dedicated"
      ? getDedicatedOcrAiBaseUrl(settings)
      : ""

  return {
    isMineruProvider,
    isBaiduDocParseMode,
    isOcrEnabledForCurrentEngine,
    hasBaiduCredentials,
    canUseAiOcr,
    selectedOcrProvider,
    parseEngineMode,
    isOcrProviderPaddleLocal: isOcrProviderMachine,  // backward compat alias
    isOcrProviderBaidu,
    isOcrProviderTesseract,
    needsRequiredOcrAiConfig,
    shouldShowAiVendorAdapter,
    shouldShowOcrProviderSelector,
    shouldShowBaiduConfig,
    shouldShowTesseractConfig,
    shouldShowLocalOcrCheck,
    availableOcrProviders,
    ocrModelsConfigSource,
    ocrModelsApiKey,
    ocrModelsBaseUrl,
    isOcrAiChainDirect: runConfig.ocrAiChainMode === "direct",
    isOcrAiChainDocParser: runConfig.ocrAiChainMode === "doc_parser",
    isOcrAiChainLayoutBlock: runConfig.ocrAiChainMode === "layout_block",
    runConfig,
  }
}

export const deriveSettingsUiState = resolveOcrSettingsState

export function getRunParseEngineLabel(runConfig: RunConfig): string {
  const mode = runConfig.parseProvider === "mineru"
    ? "mineru_cloud" as ParseEngineMode
    : runConfig.parseProvider === "baidu_doc"
      ? "baidu_doc" as ParseEngineMode
      : "local_ocr" as ParseEngineMode
  return PARSE_ENGINE_MODE_LABELS[mode]
}

export function getRunModelLabel(runConfig: RunConfig): string {
  if (runConfig.parseProvider === "mineru") {
    return "MinerU 云端解析"
  }
  if (runConfig.parseProvider === "baidu_doc") {
    return BAIDU_DOC_PARSE_TYPE_LABELS[runConfig.baiduDocParseType]
  }
  if (runConfig.effectiveOcrProvider === "machine") {
    return "本地 OCR（无需远程模型）"
  }
  if (runConfig.effectiveOcrProvider === "baidu") {
    return "百度 OCR"
  }
  if (runConfig.effectiveOcrProvider === "aiocr" && !runConfig.effectiveOcrAiModel) {
    return "未设置 OCR 模型"
  }
  if (runConfig.effectiveOcrProvider === "aiocr" && runConfig.ocrAiChainMode === "layout_block") {
    const model = runConfig.effectiveOcrAiModel || "未设置"
    return `PP-DocLayoutV3 + ${model}`
  }
  return runConfig.effectiveOcrAiModel || "未设置"
}

export function validateRunConfig(settings: Settings): ValidationResult {
  const ui = resolveOcrSettingsState(settings)
  const run = ui.runConfig

  if (run.parseProvider === "mineru" && !settings.mineruApiToken.trim()) {
    return { ok: false, message: "当前为 MinerU 解析，请先在设置页填写 MinerU API Token。" }
  }

  if (run.parseProvider === "mineru") return { ok: true }

  if (run.parseProvider === "baidu_doc") {
    const ok =
      Boolean(settings.ocrBaiduApiKey.trim()) &&
      Boolean(settings.ocrBaiduSecretKey.trim())
    if (!ok) {
      return {
        ok: false,
        message: "当前为百度解析，请在设置页补全 api_key / secret_key。",
      }
    }
    return { ok: true }
  }

  if (run.effectiveOcrProvider === "baidu") {
    const ok =
      Boolean(settings.ocrBaiduApiKey.trim()) &&
      Boolean(settings.ocrBaiduSecretKey.trim())
    if (!ok) {
      return {
        ok: false,
        message: "当前 OCR 提供方为百度，请在设置页补全 api_key / secret_key。",
      }
    }
  }

  if (run.effectiveOcrProvider === "aiocr") {
    if (!settings.ocrAiApiKey.trim()) {
      return {
        ok: false,
        message: "AIOCR 不再复用主 AI 配置，请在设置页单独填写 OCR API Key。",
      }
    }
    if (!settings.ocrAiModel.trim()) {
      return { ok: false, message: "当前链路为 AIOCR，请先在设置页选择 OCR 模型。" }
    }
    if (
      run.ocrAiChainMode === "doc_parser" &&
      !settings.ocrAiModel.trim().toLowerCase().includes("paddleocr-vl")
    ) {
      return { ok: false, message: "内置文档解析链路仅支持 PaddleOCR-VL 模型。" }
    }
    if (
      run.ocrAiChainMode === "direct" &&
      isPaddleOcrVlModelName(settings.ocrAiModel)
    ) {
      return { ok: false, message: "模型直出链路不支持 PaddleOCR-VL，请切换到内置文档解析。" }
    }
  }

  return { ok: true }
}

/** Structured JobConfig matching the backend Pydantic schema. */
export type JobConfig = {
  enable_ocr?: boolean
  retain_process_artifacts?: boolean
  remove_footer_notebooklm?: boolean
  ocr?: {
    provider?: string
    ai?: {
      provider?: string
      api_key?: string
      base_url?: string
      model?: string
      chain_mode?: string
      layout_model?: string
      prompt_preset?: string
      direct_prompt_override?: string
      layout_block_prompt_override?: string
      image_region_prompt_override?: string
      paddle_vl_docparser_max_side_px?: number
      page_concurrency?: number
      block_concurrency?: number
      requests_per_minute?: number
      tokens_per_minute?: number
      max_retries?: number
      linebreak_assist?: boolean
    }
    baidu?: {
      app_id?: string
      api_key?: string
      secret_key?: string
    }
    tesseract?: {
      language?: string
      min_confidence?: number
    }
    render_dpi?: number
    strict_mode?: boolean
  }
  parse?: {
    provider?: string
    mineru?: {
      api_token?: string
      base_url?: string
      model_version?: string
      enable_formula?: boolean
      enable_table?: boolean
      language?: string
      is_ocr?: boolean
    }
    baidu_doc?: {
      parse_type?: string
    }
  }
  llm?: {
    provider?: string
    api_key?: string
    base_url?: string
    model?: string
  }
  ppt?: {
    generation_mode?: string
    text_erase_mode?: string
    scanned_page_mode?: string
    image_regions?: {
      bg_clear_expand_min_pt?: number
      bg_clear_expand_max_pt?: number
      bg_clear_expand_ratio?: number
      scanned_image_region_min_area_ratio?: number
      scanned_image_region_max_area_ratio?: number
      scanned_image_region_max_aspect_ratio?: number
    }
  }
  page_range?: {
    start?: number
    end?: number
  }
}

/**
 * Build a structured JobConfig JSON object from RunConfig + Settings.
 *
 * This replaces the flat FormData approach for the v2 API endpoint.
 * Only includes non-default/non-empty values to keep the payload compact.
 */
export function buildJobConfig(
  settings: Settings,
  pageStart?: number,
  pageEnd?: number,
  options?: CreateJobOptions
): JobConfig {
  const ui = resolveOcrSettingsState(settings)
  const run = ui.runConfig

  const config: JobConfig = {
    enable_ocr: run.parseProvider === "local" ? Boolean(settings.enableOcr) : false,
    retain_process_artifacts: Boolean(options?.retainProcessArtifacts),
    remove_footer_notebooklm: Boolean(settings.removeFooterNotebooklm),
  }

  // LLM config (main provider)
  if (run.mainApiKey || run.mainBaseUrl || run.mainModel) {
    config.llm = {
      provider: run.llmProvider,
    }
    if (run.mainApiKey) config.llm.api_key = run.mainApiKey
    if (run.mainBaseUrl) config.llm.base_url = run.mainBaseUrl
    if (run.mainModel) config.llm.model = run.mainModel
  }

  // Parse config
  config.parse = {
    provider: run.parseProvider,
  }

  if (run.parseProvider === "mineru") {
    config.parse.mineru = {
      api_token: settings.mineruApiToken.trim(),
      model_version: settings.mineruModelVersion,
      enable_formula: Boolean(settings.mineruEnableFormula),
      enable_table: Boolean(settings.mineruEnableTable),
      is_ocr: Boolean(settings.mineruIsOcr),
    }
    if (settings.mineruBaseUrl.trim()) {
      config.parse.mineru.base_url = settings.mineruBaseUrl.trim()
    }
    if (settings.mineruLanguage.trim()) {
      config.parse.mineru.language = settings.mineruLanguage.trim()
    }
  }

  if (run.parseProvider === "baidu_doc") {
    config.parse.baidu_doc = {
      parse_type: settings.baiduDocParseType,
    }
  }

  // OCR config
  config.ocr = {
    provider: run.effectiveOcrProvider,
    render_dpi: toFinitePositiveIntOrNull(settings.ocrRenderDpi) ?? undefined,
    strict_mode: Boolean(settings.ocrStrictMode),
    // Always send layout_model so local PaddleOCR can use the user's choice
    ai: { layout_model: run.ocrAiLayoutModel },
  }

  // AI OCR config
  if (run.shouldAttachOcrAiParams) {
    const ai: NonNullable<JobConfig["ocr"]>["ai"] = {
      provider: run.effectiveOcrAiProvider,
      chain_mode: run.ocrAiChainMode,
      layout_model: run.ocrAiLayoutModel,
      prompt_preset: settings.ocrAiPromptPreset,
      page_concurrency: run.ocrAiPageConcurrency,
      max_retries: run.ocrAiMaxRetries,
    }
    if (run.effectiveOcrAiKey) ai.api_key = run.effectiveOcrAiKey
    if (run.effectiveOcrAiBaseUrl) ai.base_url = run.effectiveOcrAiBaseUrl
    if (run.effectiveOcrAiModel) ai.model = run.effectiveOcrAiModel
    if (settings.ocrAiDirectPromptOverride.trim()) {
      ai.direct_prompt_override = settings.ocrAiDirectPromptOverride.trim()
    }
    if (settings.ocrAiLayoutBlockPromptOverride.trim()) {
      ai.layout_block_prompt_override = settings.ocrAiLayoutBlockPromptOverride.trim()
    }
    if (settings.ocrAiImageRegionPromptOverride.trim()) {
      ai.image_region_prompt_override = settings.ocrAiImageRegionPromptOverride.trim()
    }
    const paddleDocMaxSidePx = toFinitePositiveIntOrNull(settings.ocrPaddleVlDocparserMaxSidePx)
    if (paddleDocMaxSidePx !== null) {
      ai.paddle_vl_docparser_max_side_px = paddleDocMaxSidePx
    }
    if (run.ocrAiBlockConcurrency !== null) {
      ai.block_concurrency = run.ocrAiBlockConcurrency
    }
    const rpm = toFinitePositiveIntOrNull(settings.ocrAiRequestsPerMinute)
    if (rpm !== null) ai.requests_per_minute = rpm
    const tpm = toFinitePositiveIntOrNull(settings.ocrAiTokensPerMinute)
    if (tpm !== null) ai.tokens_per_minute = tpm
    config.ocr.ai = ai
  }

  // Baidu OCR
  if (run.effectiveOcrProvider === "baidu" || run.parseProvider === "baidu_doc") {
    config.ocr.baidu = {
      app_id: settings.ocrBaiduAppId.trim() || undefined,
      api_key: settings.ocrBaiduApiKey.trim() || undefined,
      secret_key: settings.ocrBaiduSecretKey.trim() || undefined,
    }
  }

  // Tesseract / Machine (local OCR)
  if (run.effectiveOcrProvider === "machine" || run.effectiveOcrProvider === "auto") {
    const lang = settings.ocrTesseractLanguage.trim()
    const minConf = toFinitePositiveIntOrNull(settings.ocrTesseractMinConfidence)
    if (lang || minConf !== null) {
      config.ocr.tesseract = {}
      if (lang) config.ocr.tesseract.language = lang
      if (minConf !== null) config.ocr.tesseract.min_confidence = minConf
    }
  }

  // PPT config
  config.ppt = {
    generation_mode: settings.pptGenerationMode,
    text_erase_mode: settings.textEraseMode,
    scanned_page_mode: settings.scannedPageMode,
  }

  // Image region tuning
  const imgMin = toFiniteFloat(settings.imageBgClearExpandMinPt)
  const imgMax = toFiniteFloat(settings.imageBgClearExpandMaxPt)
  const imgRatio = toFiniteFloat(settings.imageBgClearExpandRatio)
  const scannedMin = toFiniteFloat(settings.scannedImageRegionMinAreaRatio)
  const scannedMax = toFiniteFloat(settings.scannedImageRegionMaxAreaRatio)
  const scannedAspect = toFiniteFloat(settings.scannedImageRegionMaxAspectRatio)
  if (imgMin !== null || imgMax !== null || imgRatio !== null ||
      scannedMin !== null || scannedMax !== null || scannedAspect !== null) {
    config.ppt.image_regions = {}
    if (imgMin !== null) config.ppt.image_regions.bg_clear_expand_min_pt = imgMin
    if (imgMax !== null) config.ppt.image_regions.bg_clear_expand_max_pt = imgMax
    if (imgRatio !== null) config.ppt.image_regions.bg_clear_expand_ratio = imgRatio
    if (scannedMin !== null) config.ppt.image_regions.scanned_image_region_min_area_ratio = scannedMin
    if (scannedMax !== null) config.ppt.image_regions.scanned_image_region_max_area_ratio = scannedMax
    if (scannedAspect !== null) config.ppt.image_regions.scanned_image_region_max_aspect_ratio = scannedAspect
  }

  // Page range
  if (pageStart && pageEnd) {
    config.page_range = {
      start: pageStart,
      end: pageEnd,
    }
  }

  return config
}

function toFiniteFloat(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const n = Number(trimmed)
  if (!Number.isFinite(n)) return null
  return n
}

export function applyParseEngineMode(
  settings: Settings,
  nextMode: ParseEngineMode
): Settings {
  const mainProvider = getResolvedMainProvider(settings)

  if (nextMode === "mineru_cloud") {
    return {
      ...settings,
      parseEngineMode: nextMode,
      provider: "mineru",
      preferredMainProvider: mainProvider,
    }
  }

  if (nextMode === "remote_ocr") {
    const nextProvider =
      settings.ocrAiProvider === "auto"
        ? DEFAULT_AIOCR_PROVIDER
        : settings.ocrAiProvider
    const nextChainMode =
      settings.ocrAiChainMode || DEFAULT_AIOCR_CHAIN_MODE
    const needsDefaultModel =
      !settings.ocrAiModel.trim() ||
      (nextChainMode === "direct" && isPaddleOcrVlModelName(settings.ocrAiModel))
    return {
      ...settings,
      parseEngineMode: nextMode,
      provider: mainProvider,
      preferredMainProvider: mainProvider,
      ocrAiProvider: nextProvider,
      ocrAiBaseUrl:
        settings.ocrAiBaseUrl.trim() ||
        (nextProvider === "siliconflow" ? SILICONFLOW_BASE_URL : ""),
      ocrAiChainMode: nextChainMode,
      ocrAiModel: needsDefaultModel ? DEFAULT_AIOCR_MODEL : settings.ocrAiModel,
    }
  }

  if (nextMode === "baidu_doc") {
    return {
      ...settings,
      parseEngineMode: nextMode,
      provider: mainProvider,
      preferredMainProvider: mainProvider,
    }
  }

  return {
    ...settings,
    parseEngineMode: nextMode,
    provider: mainProvider,
    preferredMainProvider: mainProvider,
    ocrProvider: getPreferredLocalOcrProvider(settings),
  }
}

/**
 * Map a parse engine mode to the recommended OCR provider.
 *
 * Centralizes the mapping that was previously duplicated across
 * upload-stage, quick-config-panel, and settings.
 */
export function resolveParseEngineOcrProvider(mode: ParseEngineMode): OcrProvider {
  switch (mode) {
    case "remote_ocr":
      return "aiocr"
    case "baidu_doc":
      return "baidu"
    case "mineru_cloud":
      return "auto"
    case "local_ocr":
    default:
      return "machine"
  }
}
