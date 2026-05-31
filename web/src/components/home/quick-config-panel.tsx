"use client"

import * as React from "react"
import Link from "next/link"
import {
  AlertCircleIcon,
  ArrowRightIcon,
  CheckIcon,
  DownloadIcon,
  FileTextIcon,
  GlobeIcon,
  InfoIcon,
  ScanIcon,
  SparklesIcon,
} from "lucide-react"

import { HoverHint } from "@/components/ui/hover-hint"
import { SegmentedControl } from "@/components/ui/segmented-control"
import { Toggle } from "@/components/ui/toggle"
import { Callout } from "@/components/ui/callout"
import { AdvancedReveal } from "@/components/settings/settings-shared"
import { ModelStatusBadge } from "@/components/model-status-badge"
import { LAYOUT_MODELS } from "@/lib/layout-models"
import {
  PPT_GENERATION_MODE_LABELS,
  type OcrAiLayoutModel,
  type Settings,
} from "@/lib/settings"
import {
  type OcrConfigV3,
  type DocumentParsingProvider,
  type TextRecognitionProvider,
  migrateSettingsToOcrConfigV3,
  applyOcrConfigV3ToSettings,
} from "@/lib/ocr-config-v3"
import type { ModelStatusResponse } from "@/hooks/use-model-status"
import { useModelDownload } from "@/hooks/use-model-download"
import { fetchModels } from "@/lib/api"
import { cn } from "@/lib/utils"

interface QuickConfigPanelProps {
  settingsSnapshot: Settings
  updateSettingsSnapshot: (updater: (prev: Settings) => Settings) => void
  modelStatus: ModelStatusResponse | null
  modelStatusError: string | null
  isModelStatusLoading: boolean
  refetchModelStatus: () => void
  retainProcessArtifacts: boolean
  setRetainProcessArtifacts: (value: boolean) => void
  downloadedLayoutModels: Set<string>
}

const PPT_MODE_OPTIONS = [
  { id: "turbo", label: "极速" },
  { id: "fast", label: "快速" },
  { id: "standard", label: "精准" },
]

const PARSING_OPTIONS = [
  { id: "local", label: "本地" },
  { id: "mineru", label: "MinerU" },
  { id: "baidu_doc", label: "百度" },
]

const RECOGNITION_OPTIONS: {
  id: TextRecognitionProvider
  label: string
  description: string
  icon: React.ReactNode
}[] = [
  {
    id: "paddleocr",
    label: "PaddleOCR",
    description: "中文效果好",
    icon: <ScanIcon className="size-3.5" />,
  },
  {
    id: "tesseract",
    label: "Tesseract",
    description: "兼容性好",
    icon: <FileTextIcon className="size-3.5" />,
  },
  {
    id: "aiocr",
    label: "AI OCR",
    description: "精度最高",
    icon: <SparklesIcon className="size-3.5" />,
  },
  {
    id: "baidu",
    label: "百度 OCR",
    description: "速度快",
    icon: <GlobeIcon className="size-3.5" />,
  },
]

export function QuickConfigPanel({
  settingsSnapshot,
  updateSettingsSnapshot,
  modelStatus,
  modelStatusError,
  isModelStatusLoading,
  refetchModelStatus,
  retainProcessArtifacts,
  setRetainProcessArtifacts,
  downloadedLayoutModels,
}: QuickConfigPanelProps) {
  const { startDownload, downloads, isDownloading } = useModelDownload({
    onDownloadComplete: () => void refetchModelStatus(),
  })

  // Derive three-layer config from flat settings
  const config = React.useMemo(
    () => migrateSettingsToOcrConfigV3(settingsSnapshot),
    [settingsSnapshot],
  )

  const isLocalParsing = config.parsing.provider === "local"

  // Fetch real OCR model list from backend (for AI OCR model selector)
  const [availableOcrModels, setAvailableOcrModels] = React.useState<string[]>([])
  const [fetchingOcrModels, setFetchingOcrModels] = React.useState(false)

  React.useEffect(() => {
    if (config.recognition.provider !== "aiocr") {
      setAvailableOcrModels([])
      return
    }
    const key = settingsSnapshot.ocrAiApiKey.trim()
    const url = settingsSnapshot.ocrAiBaseUrl.trim()
    if (!key || !url) {
      setAvailableOcrModels([])
      return
    }
    let cancelled = false
    setFetchingOcrModels(true)
    void fetchModels({
      provider: settingsSnapshot.ocrAiProvider,
      apiKey: key,
      baseUrl: url || undefined,
      capability: "vision",
    })
      .then((models) => {
        if (!cancelled) setAvailableOcrModels(models)
      })
      .catch(() => { /* silently keep empty list */ })
      .finally(() => {
        if (!cancelled) setFetchingOcrModels(false)
      })
    return () => { cancelled = true }
  }, [
    config.recognition.provider,
    settingsSnapshot.ocrAiProvider,
    settingsSnapshot.ocrAiApiKey,
    settingsSnapshot.ocrAiBaseUrl,
  ])

  // Reset layout model selection if current model is no longer downloaded
  React.useEffect(() => {
    if (downloadedLayoutModels.size > 0 && settingsSnapshot.ocrAiLayoutModel) {
      if (!downloadedLayoutModels.has(settingsSnapshot.ocrAiLayoutModel)) {
        const first = [...downloadedLayoutModels][0]
        if (first) {
          updateSettingsSnapshot((prev) => ({ ...prev, ocrAiLayoutModel: first as OcrAiLayoutModel }))
        }
      }
    }
  }, [downloadedLayoutModels, settingsSnapshot.ocrAiLayoutModel, updateSettingsSnapshot])

  // Helper: apply a config change back to flat settings
  const applyConfigChange = React.useCallback(
    (newConfig: OcrConfigV3) => {
      const updates = applyOcrConfigV3ToSettings(newConfig, settingsSnapshot)
      updateSettingsSnapshot((prev) => ({ ...prev, ...updates }))
    },
    [settingsSnapshot, updateSettingsSnapshot],
  )

  // Handler: change parsing provider
  const handleParsingChange = React.useCallback(
    (provider: DocumentParsingProvider) => {
      const newConfig: OcrConfigV3 = {
        ...config,
        parsing: { ...config.parsing, provider },
      }
      applyConfigChange(newConfig)
    },
    [config, applyConfigChange],
  )

  // Handler: change recognition provider
  const handleRecognitionChange = React.useCallback(
    (provider: TextRecognitionProvider) => {
      const newConfig: OcrConfigV3 = {
        ...config,
        recognition: { ...config.recognition, provider },
      }
      applyConfigChange(newConfig)
    },
    [config, applyConfigChange],
  )

  // Handler: toggle layout detection
  const handleLayoutToggle = React.useCallback(
    (enabled: boolean) => {
      const newConfig: OcrConfigV3 = {
        ...config,
        layout: { ...config.layout, enabled },
      }
      applyConfigChange(newConfig)
    },
    [config, applyConfigChange],
  )

  return (
    <div className="home-inline-panel px-4 py-3">
      <div className="grid gap-3">
        {/* PPT Generation Mode */}
        <div className="grid gap-1.5">
          <div className="flex items-center gap-1.5">
            <span className="home-stat-label">PPT 模式</span>
            <HoverHint text="极速优先抢时间；快速适合日常转换；精准适合效果优先。" />
          </div>
          <SegmentedControl
            options={PPT_MODE_OPTIONS}
            value={settingsSnapshot.pptGenerationMode}
            onChange={(v) =>
              updateSettingsSnapshot((prev) => ({
                ...prev,
                pptGenerationMode: v as Settings["pptGenerationMode"],
              }))
            }
          />
        </div>

        {/* Layer 1: Document Parsing */}
        <div className="grid gap-1.5">
          <div className="flex items-center gap-1.5">
            <span className="home-stat-label">解析模式</span>
            <HoverHint text="本地解析适合大多数文档；MinerU/百度自带完整解析能力。" />
          </div>
          <div className="flex items-center gap-2">
            <SegmentedControl
              className="flex-1"
              options={PARSING_OPTIONS}
              value={config.parsing.provider}
              onChange={(v) => handleParsingChange(v as DocumentParsingProvider)}
            />
            <ModelStatusBadge
              status={modelStatus}
              isLoading={isModelStatusLoading}
              error={modelStatusError}
              parseEngineMode={settingsSnapshot.parseEngineMode}
              onStatusChange={() => void refetchModelStatus()}
            />
          </div>
        </div>

        {/* Cloud parsing info callouts */}
        <AdvancedReveal show={config.parsing.provider === "mineru"}>
          <Callout variant="info" icon={<InfoIcon />}>
            MinerU 自带完整解析能力，无需额外配置识别引擎
          </Callout>
        </AdvancedReveal>

        <AdvancedReveal show={config.parsing.provider === "baidu_doc"}>
          <Callout variant="info" icon={<InfoIcon />}>
            百度解析自带完整解析能力，无需额外配置识别引擎
          </Callout>
        </AdvancedReveal>

        {/* Layer 3: Text Recognition (only when local parsing) */}
        <AdvancedReveal show={isLocalParsing}>
          <div className="grid gap-1.5">
            <div className="flex items-center gap-1.5">
              <span className="home-stat-label">文字识别</span>
              <HoverHint text="PaddleOCR 中文效果好；Tesseract 兼容性好；AI OCR 精度最高；百度 OCR 速度快。" />
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {RECOGNITION_OPTIONS.map((opt) => {
                const isSelected = config.recognition.provider === opt.id
                const isLocalProvider = opt.id === "paddleocr" || opt.id === "tesseract"
                const isReady = isLocalProvider
                  ? (modelStatus?.local?.[opt.id]?.ready ?? false)
                  : true
                const isDisabled = isLocalProvider && !!modelStatus && !isReady && opt.id !== "paddleocr"

                return (
                  <button
                    key={opt.id}
                    type="button"
                    disabled={isDisabled}
                    onClick={() => handleRecognitionChange(opt.id)}
                    className={cn(
                      "relative flex items-start gap-2 border p-2 text-left transition-all",
                      isSelected
                        ? "border-foreground bg-muted/30"
                        : "border-border/60 hover:border-foreground/30 hover:bg-muted/20",
                      isDisabled && "cursor-not-allowed opacity-40",
                    )}
                  >
                    {/* Checkmark indicator */}
                    {isSelected && (
                      <span className="absolute right-1 top-1 flex size-3.5 items-center justify-center bg-foreground text-primary-foreground">
                        <CheckIcon className="size-2.5" />
                      </span>
                    )}
                    <span
                      className={cn(
                        "mt-0.5 shrink-0",
                        isSelected ? "text-foreground" : "text-muted-foreground",
                      )}
                    >
                      {opt.icon}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={cn(
                            "text-xs font-medium",
                            isSelected ? "text-foreground" : "text-muted-foreground",
                          )}
                        >
                          {opt.label}
                        </span>
                        {isLocalProvider && modelStatus && (
                          isReady ? (
                            <span className="font-mono text-[9px] uppercase tracking-widest text-emerald-600">
                              就绪
                            </span>
                          ) : opt.id === "paddleocr" ? (
                            isDownloading("paddleocr") ? (
                              <span className="font-mono text-[9px] uppercase tracking-widest text-amber-600">
                                下载中{downloads["paddleocr"]?.progress != null ? ` ${Math.round(downloads["paddleocr"]!.progress! * 100)}%` : "..."}
                              </span>
                            ) : (
                              <button
                                type="button"
                                className="font-mono text-[9px] uppercase tracking-widest text-foreground underline underline-offset-2 hover:text-destructive"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  void startDownload("paddleocr")
                                }}
                              >
                                下载
                              </button>
                            )
                          ) : (
                            <span className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                              未就绪
                            </span>
                          )
                        )}
                      </div>
                      <span className="mt-0.5 block text-[10px] leading-snug text-muted-foreground">
                        {opt.description}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
            {/* Warning when no local OCR provider is ready */}
            {modelStatus && !modelStatus.local.paddleocr?.ready && !modelStatus.local.tesseract?.ready && (
              <Callout variant="warning" icon={<AlertCircleIcon />}>
                本地 OCR 未就绪，请前往{" "}
                <Link href="/settings" className="underline font-medium">
                  设置
                </Link>{" "}
                配置
              </Callout>
            )}
          </div>
        </AdvancedReveal>

        {/* AI OCR sub-config */}
        <AdvancedReveal show={isLocalParsing && config.recognition.provider === "aiocr"}>
          <div className="grid gap-2.5">
            {/* Chain mode */}
            <div className="grid gap-1.5">
              <div className="flex items-center gap-1.5">
                <span className="home-stat-label">识别链路</span>
                <HoverHint text="版面切块：先切块再逐块识别，推荐默认。直出：整页直接送模型识别。" />
              </div>
              <SegmentedControl
                options={[
                  { id: "layout_block", label: "版面切块" },
                  { id: "direct", label: "直出" },
                ]}
                value={settingsSnapshot.ocrAiChainMode}
                onChange={(v) =>
                  updateSettingsSnapshot((prev) => ({
                    ...prev,
                    ocrAiChainMode: v as Settings["ocrAiChainMode"],
                  }))
                }
              />
            </div>

            {/* Layout model selector (when chain mode = layout_block) */}
            <AdvancedReveal show={settingsSnapshot.ocrAiChainMode === "layout_block"}>
              <div className="grid gap-1.5">
                <span className="home-stat-label">版面模型</span>
                <SegmentedControl
                  options={Object.values(LAYOUT_MODELS)
                    .filter((m) => downloadedLayoutModels.has(m.modelId))
                    .map((m) => ({
                      id: m.modelId,
                      label: m.displayName.replace("PP-DocLayout", "").trim() || m.displayName,
                      badge: "已下载",
                    }))}
                  value={
                    downloadedLayoutModels.has(settingsSnapshot.ocrAiLayoutModel)
                      ? settingsSnapshot.ocrAiLayoutModel
                      : ([...downloadedLayoutModels][0] ?? "")
                  }
                  onChange={(v) =>
                    updateSettingsSnapshot((prev) => ({
                      ...prev,
                      ocrAiLayoutModel: v as OcrAiLayoutModel,
                    }))
                  }
                />
                {downloadedLayoutModels.size === 0 && (() => {
                  const currentModel = settingsSnapshot.ocrAiLayoutModel
                  const modelInfo = LAYOUT_MODELS[currentModel]
                  const displayName = modelInfo?.displayName ?? currentModel
                  const busy = isDownloading(currentModel)
                  const dlState = downloads[currentModel]

                  return (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>暂无已下载的版面模型</span>
                      {busy ? (
                        <span className="text-[10px] text-amber-600">
                          下载中... {dlState?.progress != null ? `${Math.round(dlState.progress * 100)}%` : ""}
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="inline-flex items-center gap-0.5 border px-1.5 py-0.5 text-[10px] text-foreground transition-colors hover:bg-muted"
                          onClick={() => void startDownload(currentModel)}
                        >
                          <DownloadIcon className="size-2.5" />
                          下载 {displayName}
                        </button>
                      )}
                      <Link href="/settings" className="underline">设置</Link>
                    </div>
                  )
                })()}
              </div>
            </AdvancedReveal>

            {/* OCR model selector */}
            <div className="grid gap-1.5">
              <div className="flex items-center gap-1.5">
                <span className="home-stat-label">OCR 模型</span>
                <HoverHint text="选择用于文字识别的 AI 模型。" />
              </div>
              {settingsSnapshot.ocrAiApiKey.trim() && settingsSnapshot.ocrAiBaseUrl.trim() ? (
                availableOcrModels.length > 0 ? (
                  <select
                    className="h-8 w-full min-w-0 border-b-2 border-input bg-transparent px-2 font-sans text-xs text-foreground outline-none transition-colors focus-visible:bg-[#f0f0f0]"
                    value={
                      availableOcrModels.includes(settingsSnapshot.ocrAiModel)
                        ? settingsSnapshot.ocrAiModel
                        : "__custom__"
                    }
                    onChange={(e) => {
                      const val = e.target.value
                      updateSettingsSnapshot((prev) => ({
                        ...prev,
                        ocrAiModel: val === "__custom__" ? prev.ocrAiModel : val,
                      }))
                    }}
                  >
                    {availableOcrModels.map((id) => (
                      <option key={id} value={id}>{id}</option>
                    ))}
                    {!availableOcrModels.includes(settingsSnapshot.ocrAiModel) && settingsSnapshot.ocrAiModel.trim() && (
                      <option value="__custom__">{settingsSnapshot.ocrAiModel}</option>
                    )}
                  </select>
                ) : fetchingOcrModels ? (
                  <div className="text-xs text-muted-foreground">正在查询可用模型…</div>
                ) : (
                  <Callout variant="warning" icon={<AlertCircleIcon />}>
                    未获取到可用模型，请检查 API Key 和 Base URL
                    <Link href="/settings" className="ml-1 underline font-medium">去设置</Link>
                  </Callout>
                )
              ) : (
                <Callout variant="warning" icon={<AlertCircleIcon />}>
                  请先配置 API Key 和 Base URL
                  <Link href="/settings" className="ml-1 underline font-medium">去设置</Link>
                </Callout>
              )}
            </div>
          </div>
        </AdvancedReveal>

        {/* Baidu OCR: credentials warning */}
        <AdvancedReveal show={isLocalParsing && config.recognition.provider === "baidu"}>
          {(!settingsSnapshot.ocrBaiduAppId.trim() || !settingsSnapshot.ocrBaiduApiKey.trim() || !settingsSnapshot.ocrBaiduSecretKey.trim()) && (
            <Callout variant="warning" icon={<AlertCircleIcon />}>
              请先配置百度 OCR 凭证
              <Link href="/settings" className="ml-1 underline font-medium">去设置</Link>
            </Callout>
          )}
        </AdvancedReveal>

        {/* Layer 2: Layout Detection (only when local parsing) */}
        <AdvancedReveal show={isLocalParsing}>
          <div className="grid gap-1.5">
            <div className="flex items-center gap-1.5">
              <span className="home-stat-label">版面检测</span>
              <HoverHint text="检测文档中的标题、段落、表格等区域，提升排版质量。" />
            </div>
            {config.recognition.provider === "paddleocr" ? (
              <Callout variant="info" icon={<InfoIcon />}>
                PaddleOCR 自动启用版面检测
              </Callout>
            ) : config.recognition.provider === "aiocr" ? (
              config.layout.enabled ? (
                <Callout variant="info" icon={<InfoIcon />}>
                  版面切块模式自动启用版面检测
                </Callout>
              ) : (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <InfoIcon className="size-3 shrink-0" />
                  <span>直出模式不使用版面检测</span>
                </div>
              )
            ) : (
              <Toggle
                checked={config.layout.enabled}
                onChange={handleLayoutToggle}
                label="启用版面检测"
              />
            )}
          </div>
        </AdvancedReveal>

        {/* Divider */}
        <div className="border-t border-border/30" />

        {/* Retain process artifacts */}
        <Toggle
          checked={retainProcessArtifacts}
          onChange={setRetainProcessArtifacts}
          label="保留过程图"
          hint="保留每页处理过程图，便于核对中间效果或排查问题。"
        />

        {/* Settings link */}
        <Link
          href="/settings"
          className="group flex items-center justify-between pt-0.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <span className="home-stat-label">高级设置</span>
          <ArrowRightIcon className="size-3 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </div>
  )
}
