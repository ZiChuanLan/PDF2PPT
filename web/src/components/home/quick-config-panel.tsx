"use client"

import * as React from "react"
import Link from "next/link"
import {
  AlertCircleIcon,
  ArrowRightIcon,
  CheckIcon,
  DownloadIcon,
} from "lucide-react"

import { HoverHint } from "@/components/ui/hover-hint"
import { Select } from "@/components/ui/select"
import { ModelStatusBadge } from "@/components/model-status-badge"
import { LAYOUT_MODELS } from "@/lib/layout-models"
import {
  AIOCR_CHAIN_MODE_LABELS,
  PARSE_ENGINE_MODE_LABELS,
  PPT_GENERATION_MODE_LABELS,
  type OcrAiLayoutModel,
  type ParseEngineMode,
  type Settings,
} from "@/lib/settings"
import type { ModelStatusResponse } from "@/hooks/use-model-status"
import { useModelDownload } from "@/hooks/use-model-download"
import { resolveParseEngineOcrProvider } from "@/lib/run-config"
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

  // Fetch real OCR model list from backend (like Settings page does)
  const [availableOcrModels, setAvailableOcrModels] = React.useState<string[]>([])
  const [fetchingOcrModels, setFetchingOcrModels] = React.useState(false)

  React.useEffect(() => {
    if (settingsSnapshot.parseEngineMode !== "remote_ocr") {
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
    settingsSnapshot.parseEngineMode,
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
  return (
    <div className="home-inline-panel px-4 py-3">
      <div className="grid gap-3">
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
        <div className="grid gap-1">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span>解析引擎</span>
            <HoverHint text="传统OCR用本地识别；AIOCR用远程模型；百度/MinerU自带解析。" />
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={settingsSnapshot.parseEngineMode}
              onChange={(e) => {
                const mode = e.target.value as ParseEngineMode
                const ocrProvider = resolveParseEngineOcrProvider(mode)
                updateSettingsSnapshot((prev) => ({
                  ...prev,
                  parseEngineMode: mode,
                  ocrProvider,
                }))
              }}
              options={[
                { id: "local_ocr", label: PARSE_ENGINE_MODE_LABELS.local_ocr },
                { id: "remote_ocr", label: PARSE_ENGINE_MODE_LABELS.remote_ocr },
                { id: "baidu_doc", label: PARSE_ENGINE_MODE_LABELS.baidu_doc },
                { id: "mineru_cloud", label: PARSE_ENGINE_MODE_LABELS.mineru_cloud },
              ]}
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
        {settingsSnapshot.parseEngineMode === "local_ocr" && (
          <div className="grid gap-1">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>OCR 提供方</span>
              <HoverHint text="PaddleOCR 识别精度更高；Tesseract 兼容性更好。" />
            </div>
            <div className="grid gap-1.5">
              {(["paddleocr", "tesseract"] as const).map((providerId) => {
                const isReady = modelStatus?.local?.[providerId]?.ready ?? false
                const isSelected = settingsSnapshot.ocrProvider === providerId
                const label = providerId === "paddleocr" ? "PaddleOCR" : "Tesseract"
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
                      htmlFor={`home-ocr-provider-${providerId}`}
                      className="flex min-w-0 flex-1 cursor-pointer items-center gap-2"
                    >
                      <input
                        type="radio"
                        id={`home-ocr-provider-${providerId}`}
                        name="home-ocr-provider"
                        value={providerId}
                        checked={isSelected}
                        onChange={(e) =>
                          updateSettingsSnapshot((prev) => ({
                            ...prev,
                            ocrProvider: e.target.value as Settings["ocrProvider"],
                          }))
                        }
                        disabled={!!modelStatus && !isReady}
                        className="h-3.5 w-3.5 accent-foreground"
                      />
                      <span className="text-xs font-medium">{label}</span>
                      {modelStatus && (
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
            {/* Hint when no OCR provider is ready */}
            {modelStatus && !modelStatus.local.paddleocr?.ready && !modelStatus.local.tesseract?.ready && (
              <div className="flex items-center gap-1.5 text-xs text-amber-600 mt-1">
                <AlertCircleIcon className="size-3.5" />
                <span>本地 OCR 未就绪，请前往{" "}<Link href="/settings" className="underline">设置</Link>{" "}配置</span>
              </div>
            )}
          </div>
        )}
        {settingsSnapshot.parseEngineMode === "remote_ocr" && (
          <div className="grid gap-1">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>识别链路</span>
              <HoverHint text="版面切块：先切块再逐块识别，推荐默认。文档解析：调用内置文档解析器。直出：整页直接送模型识别。" />
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
                { id: "layout_block", label: AIOCR_CHAIN_MODE_LABELS.layout_block },
                { id: "direct", label: AIOCR_CHAIN_MODE_LABELS.direct },
              ]}
            />
          </div>
        )}
        {settingsSnapshot.parseEngineMode === "remote_ocr" && settingsSnapshot.ocrAiChainMode === "layout_block" && (
          <div className="grid gap-1">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span>版面模型</span>
              <HoverHint text="版面分析模型，用于检测文档中的标题、段落、表格等区域。" />
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
        {settingsSnapshot.parseEngineMode === "remote_ocr" && (
          <div className="grid gap-1">
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
        )}
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
