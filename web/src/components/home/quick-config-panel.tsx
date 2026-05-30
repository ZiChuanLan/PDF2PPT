"use client"

import * as React from "react"
import Link from "next/link"
import {
  AlertCircleIcon,
  ArrowRightIcon,
  CheckIcon,
  DownloadIcon,
  InfoIcon,
} from "lucide-react"

import { HoverHint } from "@/components/ui/hover-hint"
import { Select } from "@/components/ui/select"
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

const PARSING_OPTIONS: { id: DocumentParsingProvider; label: string }[] = [
  { id: "local", label: "本地解析" },
  { id: "mineru", label: "MinerU" },
  { id: "baidu_doc", label: "百度解析" },
]

const RECOGNITION_OPTIONS: { id: TextRecognitionProvider; label: string }[] = [
  { id: "paddleocr", label: "PaddleOCR" },
  { id: "tesseract", label: "Tesseract" },
  { id: "aiocr", label: "AI OCR" },
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
      .catch(() => { /* silently keep empty list — user can retry by tab switch */ })
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

  // Handler: toggle layout detection (for tesseract/baidu, not paddleocr which is always on)
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
        {/* PPT Generation Mode — unchanged */}
        <div className="grid gap-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span>PPT 生成模式</span>
            <HoverHint text="极速优先抢时间；快速适合日常转换；精准适合效果优先。" />
          </div>
          <Select
            value={settingsSnapshot.pptGenerationMode}
            onChange={(e) =>
              updateSettingsSnapshot((prev) => ({
                ...prev,
                pptGenerationMode: e.target.value as Settings["pptGenerationMode"],
              }))
            }
            options={[
              { id: "turbo", label: PPT_GENERATION_MODE_LABELS.turbo },
              { id: "fast", label: PPT_GENERATION_MODE_LABELS.fast },
              { id: "standard", label: PPT_GENERATION_MODE_LABELS.standard },
            ]}
          />
        </div>

        {/* Layer 1: Document Parsing */}
        <div className="grid gap-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span>解析模式</span>
            <HoverHint text="本地解析适合大多数文档；MinerU/百度自带完整解析能力。" />
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={config.parsing.provider}
              onChange={(e) => handleParsingChange(e.target.value as DocumentParsingProvider)}
              options={PARSING_OPTIONS}
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

        {/* Info for MinerU */}
        {config.parsing.provider === "mineru" && (
          <div className="flex items-center gap-1.5 text-xs text-blue-700">
            <InfoIcon className="size-3 shrink-0" />
            <span>MinerU 自带完整解析能力</span>
          </div>
        )}

        {/* Info for Baidu Doc */}
        {config.parsing.provider === "baidu_doc" && (
          <div className="flex items-center gap-1.5 text-xs text-blue-700">
            <InfoIcon className="size-3 shrink-0" />
            <span>百度解析自带完整解析能力</span>
          </div>
        )}

        {/* Layer 3: Text Recognition (only when local parsing) */}
        {config.parsing.provider === "local" && (
          <div className="grid gap-1">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>文字识别</span>
              <HoverHint text="PaddleOCR 中文效果好；Tesseract 兼容性好；AI OCR 精度最高；百度 OCR 速度快。" />
            </div>
            <div className="grid gap-1.5">
              {RECOGNITION_OPTIONS.map((opt) => {
                const providerId = opt.id
                const isSelected = config.recognition.provider === providerId
                // For local providers, show readiness from modelStatus
                const isLocalProvider = providerId === "paddleocr" || providerId === "tesseract"
                const isReady = isLocalProvider
                  ? (modelStatus?.local?.[providerId]?.ready ?? false)
                  : true
                return (
                  <div
                    key={providerId}
                    className={`flex items-center gap-2 rounded border px-2.5 py-1.5 transition-colors ${
                      isSelected
                        ? "border-foreground bg-muted/50"
                        : "border-border hover:border-muted-foreground/50"
                    }`}
                  >
                    <label
                      htmlFor={`home-recognition-${providerId}`}
                      className="flex min-w-0 flex-1 cursor-pointer items-center gap-2"
                    >
                      <input
                        type="radio"
                        id={`home-recognition-${providerId}`}
                        name="home-recognition"
                        value={providerId}
                        checked={isSelected}
                        onChange={() => handleRecognitionChange(providerId)}
                        disabled={isLocalProvider && !!modelStatus && !isReady}
                        className="h-3.5 w-3.5 accent-foreground"
                      />
                      <span className="text-xs font-medium">{opt.label}</span>
                      {isLocalProvider && modelStatus && (
                        isReady ? (
                          <span className="flex items-center gap-0.5 text-[10px] text-emerald-600">
                            <CheckIcon className="size-2.5" />
                            就绪
                          </span>
                        ) : (
                          <span className="text-[10px] text-muted-foreground">
                            未就绪
                          </span>
                        )
                      )}
                    </label>
                  </div>
                )
              })}
            </div>
            {/* Hint when no local OCR provider is ready */}
            {modelStatus && !modelStatus.local.paddleocr?.ready && !modelStatus.local.tesseract?.ready && (
              <div className="flex items-center gap-1.5 text-xs text-amber-600 mt-1">
                <AlertCircleIcon className="size-3.5" />
                <span>本地 OCR 未就绪，请前往{" "}<Link href="/settings" className="underline">设置</Link>{" "}配置</span>
              </div>
            )}
          </div>
        )}

        {/* AI OCR: API Key / Model info when selected */}
        {config.parsing.provider === "local" && config.recognition.provider === "aiocr" && (
          <div className="grid gap-1">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>识别链路</span>
              <HoverHint text="版面切块：先切块再逐块识别，推荐默认。直出：整页直接送模型识别。" />
            </div>
            <Select
              value={settingsSnapshot.ocrAiChainMode}
              onChange={(e) =>
                updateSettingsSnapshot((prev) => ({
                  ...prev,
                  ocrAiChainMode: e.target.value as Settings["ocrAiChainMode"],
                }))
              }
              options={[
                { id: "layout_block", label: "版面切块" },
                { id: "direct", label: "直出" },
              ]}
            />
            {settingsSnapshot.ocrAiChainMode === "layout_block" && (
              <div className="grid gap-1 mt-1">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span>版面模型</span>
                </div>
                <Select
                  value={settingsSnapshot.ocrAiLayoutModel}
                  onChange={(e) =>
                    updateSettingsSnapshot((prev) => ({
                      ...prev,
                      ocrAiLayoutModel: e.target.value as Settings["ocrAiLayoutModel"],
                    }))
                  }
                  options={Object.values(LAYOUT_MODELS)
                    .filter((m) => downloadedLayoutModels.has(m.modelId))
                    .map((m) => ({
                      id: m.modelId,
                      label: `${m.displayName} — ${m.speedLabel}`,
                    }))}
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
                          className="inline-flex items-center gap-0.5 rounded border px-1.5 py-0.5 text-[10px] text-foreground hover:bg-muted transition-colors"
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
            )}
            <div className="grid gap-1 mt-1">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span>OCR 模型</span>
                <HoverHint text="选择用于文字识别的 AI 模型。" />
              </div>
              {settingsSnapshot.ocrAiApiKey.trim() && settingsSnapshot.ocrAiBaseUrl.trim() ? (
                availableOcrModels.length > 0 ? (
                  <Select
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
                    options={[
                      ...availableOcrModels.map((id) => ({ id, label: id })),
                      ...(!availableOcrModels.includes(settingsSnapshot.ocrAiModel) && settingsSnapshot.ocrAiModel.trim()
                        ? [{ id: "__custom__", label: settingsSnapshot.ocrAiModel }]
                        : []),
                    ]}
                  />
                ) : fetchingOcrModels ? (
                  <div className="text-xs text-muted-foreground">正在查询可用模型…</div>
                ) : (
                  <div className="flex items-center gap-1.5 text-xs text-amber-600">
                    <AlertCircleIcon className="size-3.5" />
                    <span>未获取到可用模型，请检查 API Key 和 Base URL</span>
                    <Link href="/settings" className="underline hover:text-amber-800">去设置</Link>
                  </div>
                )
              ) : (
                <div className="flex items-center gap-2 text-xs text-amber-600">
                  <AlertCircleIcon className="size-3.5" />
                  <span>请先配置 API Key 和 Base URL</span>
                  <Link href="/settings" className="underline hover:text-amber-800">去设置</Link>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Layer 2: Layout Detection (only when local parsing) */}
        {config.parsing.provider === "local" && (
          <div className="grid gap-1">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>版面检测</span>
              <HoverHint text="检测文档中的标题、段落、表格等区域，提升排版质量。" />
            </div>
            {config.recognition.provider === "paddleocr" ? (
              <div className="flex items-center gap-1.5 text-xs text-blue-700">
                <InfoIcon className="size-3 shrink-0" />
                <span>PaddleOCR 自动启用版面检测</span>
              </div>
            ) : config.recognition.provider === "aiocr" ? (
              config.layout.enabled ? (
                <div className="flex items-center gap-1.5 text-xs text-blue-700">
                  <InfoIcon className="size-3 shrink-0" />
                  <span>版面切块模式自动启用版面检测</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <InfoIcon className="size-3 shrink-0" />
                  <span>直出模式不使用版面检测</span>
                </div>
              )
            ) : (
              /* tesseract: optional toggle */
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 accent-foreground"
                  checked={config.layout.enabled}
                  onChange={(e) => handleLayoutToggle(e.target.checked)}
                />
                <span>启用版面检测</span>
              </label>
            )}
          </div>
        )}

        {/* Retain process artifacts — unchanged */}
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            className="h-4 w-4 accent-foreground"
            checked={retainProcessArtifacts}
            onChange={(e) => setRetainProcessArtifacts(e.target.checked)}
          />
          <span className="flex items-center gap-1.5">
            保留过程图
            <HoverHint text="保留每页处理过程图，便于核对中间效果或排查问题。" />
          </span>
        </label>
        <Link
          href="/settings"
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          高级设置 <ArrowRightIcon className="size-3" />
        </Link>
      </div>
    </div>
  )
}
