"use client"

import * as React from "react"
import Link from "next/link"
import {
  AlertCircleIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  FileIcon,
  XIcon,
} from "lucide-react"

import { cn } from "@/lib/utils"
import { useAuth } from "@/components/auth-provider"
import { LAYOUT_MODELS } from "@/lib/layout-models"
import {
  AIOCR_CHAIN_MODE_LABELS,
  PARSE_ENGINE_MODE_LABELS,
  PPT_GENERATION_MODE_LABELS,
  type ParseEngineMode,
  type Settings,
} from "@/lib/settings"
import { Button } from "@/components/ui/button"
import { HoverHint } from "@/components/ui/hover-hint"
import { Input } from "@/components/ui/input"
import { PdfCanvasPreview } from "@/components/pdf-canvas-preview"
import { Select } from "@/components/ui/select"
import { ModelStatusBadge } from "@/components/model-status-badge"
import type { ModelStatusResponse } from "@/hooks/use-model-status"
import { formatBytes, clampPositiveInt } from "@/lib/home-utils"

interface PreviewStageProps {
  uploadFiles: Array<{ file: File }>
  fileCount: number
  currentPreviewFile: File | null
  previewFileIndex: number
  setPreviewFileIndex: (index: number) => void
  previewPageInput: string
  setPreviewPageInput: (value: string) => void
  previewPageCount: number
  handlePreviewPageCommit: (value: string) => void
  handlePreviewPageCountChange: (count: number) => void
  isImageInput: boolean
  settingsSnapshot: Settings
  updateSettingsSnapshot: (updater: (prev: Settings) => Settings) => void
  modelStatus: ModelStatusResponse | null
  isModelStatusLoading: boolean
  refetchModelStatus: () => void
  usePageRange: boolean
  setUsePageRange: (value: boolean) => void
  pageStartInput: string
  setPageStartInput: (value: string) => void
  pageEndInput: string
  setPageEndInput: (value: string) => void
  retainProcessArtifacts: boolean
  setRetainProcessArtifacts: (value: boolean) => void
  handleResetAll: () => void
  handleConvertAll: () => Promise<void>
  canStart: boolean
  actionError: string | null
  preflightWarning: string | null
  setPreflightAcknowledged: (value: boolean) => void
  downloadedLayoutModels: Set<string>
  removeFile: (index: number) => void
  filePreviewUrl: string
  previewPage: number
}

export function PreviewStage({
  uploadFiles,
  fileCount,
  currentPreviewFile,
  previewFileIndex,
  setPreviewFileIndex,
  previewPageInput,
  setPreviewPageInput,
  previewPageCount,
  handlePreviewPageCommit,
  handlePreviewPageCountChange,
  isImageInput,
  settingsSnapshot,
  updateSettingsSnapshot,
  modelStatus,
  isModelStatusLoading,
  refetchModelStatus,
  usePageRange,
  setUsePageRange,
  pageStartInput,
  setPageStartInput,
  pageEndInput,
  setPageEndInput,
  retainProcessArtifacts,
  setRetainProcessArtifacts,
  handleResetAll,
  handleConvertAll,
  canStart,
  actionError,
  preflightWarning,
  setPreflightAcknowledged,
  downloadedLayoutModels,
  removeFile,
  filePreviewUrl,
  previewPage,
}: PreviewStageProps) {
  const { user, isLoading: isAuthLoading } = useAuth()

  return (
    <div className="py-4">
      {/* Back to upload */}
      <div className="mb-4">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={handleResetAll}
        >
          <ArrowLeftIcon className="mr-1 size-4" />
          重新选择文件
        </Button>
      </div>

      {/* Dual-column layout — stacks on mobile */}
      <div className="grid gap-5 grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px]">
        {/* Left: File list + PDF preview */}
        <div>
          {/* File list */}
          {fileCount > 1 && (
            <div className="mb-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  已选择 {fileCount} 个文件
                </span>
              </div>
              <div className="grid gap-2">
                {uploadFiles.map((entry, index) => (
                  <div
                    key={entry.file.name}
                    className={cn(
                      "flex items-center justify-between gap-3 rounded-md border px-3 py-2 transition-colors",
                      index === previewFileIndex
                        ? "border-destructive/40 bg-destructive/5"
                        : "hover:bg-muted/30"
                    )}
                  >
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-2 text-left"
                      onClick={() => {
                        setPreviewFileIndex(index)
                        setPreviewPageInput("1")
                        handlePreviewPageCountChange(0)
                      }}
                    >
                      <FileIcon className="size-4 shrink-0 text-muted-foreground" />
                      <span className="truncate text-sm">{entry.file.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {formatBytes(entry.file.size)}
                      </span>
                    </button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => {
                        removeFile(index)
                      }}
                    >
                      <XIcon className="size-3" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Single file info (when only 1 file) */}
          {fileCount === 1 && currentPreviewFile && (
            <div className="mb-4 flex items-center justify-between gap-3 rounded-md border px-3 py-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{currentPreviewFile.name}</div>
                <div className="text-xs text-muted-foreground">{formatBytes(currentPreviewFile.size)}</div>
              </div>
              <div className="flex items-center gap-2">
                <Button type="button" variant="ghost" size="sm" onClick={handleResetAll}>
                  清空
                </Button>
              </div>
            </div>
          )}

          {/* PDF preview */}
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              文档预览
              {fileCount > 1 && (
                <span className="ml-2 text-xs">
                  ({previewFileIndex + 1}/{fileCount})
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <Button
                type="button"
                variant="outline"
                size="icon-xs"
                disabled={previewPage <= 1}
                onClick={() => {
                  setPreviewPageInput(String(clampPositiveInt(previewPage - 1, previewPageCount || undefined)))
                }}
                aria-label="预览上一页"
              >
                <ChevronLeftIcon className="size-3" />
              </Button>
              <Input
                inputMode="numeric"
                value={previewPageInput}
                onChange={(e) => setPreviewPageInput(e.target.value)}
                onBlur={(e) => handlePreviewPageCommit(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault()
                    handlePreviewPageCommit((e.target as HTMLInputElement).value)
                  }
                }}
                className="h-8 w-20 text-center"
                aria-label="当前预览页"
              />
              <span className="w-14 text-right font-mono text-xs text-muted-foreground">
                / {previewPageCount || "?"}
              </span>
              <Button
                type="button"
                variant="outline"
                size="icon-xs"
                disabled={previewPageCount > 0 ? previewPage >= previewPageCount : true}
                onClick={() => {
                  setPreviewPageInput(String(clampPositiveInt(previewPage + 1, previewPageCount || undefined)))
                }}
                aria-label="预览下一页"
              >
                <ChevronRightIcon className="size-3" />
              </Button>
            </div>
          </div>

          {filePreviewUrl ? (
            <div className="home-preview-stage">
              <PdfCanvasPreview
                fileUrl={filePreviewUrl}
                mimeType={currentPreviewFile?.type}
                page={previewPage}
                className="w-full"
                onPageCountChange={handlePreviewPageCountChange}
              />
            </div>
          ) : (
            <div className="home-preview-stage home-preview-empty">
              上传 PDF 或图片后会在这里显示预览
            </div>
          )}
        </div>

        {/* Right: Config + actions */}
        <div className="space-y-4">
          {/* Page range */}
          <div className="home-inline-panel px-4 py-3">
            {isImageInput ? (
              <p className="text-xs leading-6 text-muted-foreground">
                图片输入自动包装成单页 PDF，无需设置页码范围。
              </p>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-foreground"
                      checked={usePageRange}
                      onChange={(e) => {
                        const enabled = e.target.checked
                        setUsePageRange(enabled)
                        if (!enabled) {
                          setPageStartInput("")
                          setPageEndInput("")
                        }
                      }}
                    />
                    限定页码范围
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      disabled={!currentPreviewFile}
                      onClick={() => {
                        setUsePageRange(true)
                        const current = String(previewPage)
                        setPageStartInput(current)
                        setPageEndInput(current)
                      }}
                    >
                      单页试跑
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      onClick={() => {
                        setUsePageRange(false)
                        setPageStartInput("")
                        setPageEndInput("")
                      }}
                    >
                      整份
                    </Button>
                  </div>
                </div>
                {usePageRange ? (
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <div className="grid gap-1">
                      <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                        起始页
                      </label>
                      <Input
                        inputMode="numeric"
                        placeholder="1"
                        value={pageStartInput}
                        onChange={(e) => setPageStartInput(e.target.value)}
                        className="h-9"
                      />
                    </div>
                    <div className="grid gap-1">
                      <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                        结束页
                      </label>
                      <Input
                        inputMode="numeric"
                        placeholder="5"
                        value={pageEndInput}
                        onChange={(e) => setPageEndInput(e.target.value)}
                        className="h-9"
                      />
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </div>

          {/* Quick config */}
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
                >
                  <option value="turbo">{PPT_GENERATION_MODE_LABELS.turbo}</option>
                  <option value="fast">{PPT_GENERATION_MODE_LABELS.fast}</option>
                  <option value="standard">{PPT_GENERATION_MODE_LABELS.standard}</option>
                </Select>
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
                      updateSettingsSnapshot((prev) => ({
                        ...prev,
                        parseEngineMode: mode,
                        ...(mode === "remote_ocr" ? { ocrProvider: "aiocr" as const }
                          : mode === "baidu_doc" ? { ocrProvider: "baidu" as const }
                          : mode === "mineru_cloud" ? { ocrProvider: "auto" as const }
                          : {}),
                      }))
                    }}
                  >
                    <option value="local_ocr">{PARSE_ENGINE_MODE_LABELS.local_ocr}</option>
                    <option value="remote_ocr">{PARSE_ENGINE_MODE_LABELS.remote_ocr}</option>
                    <option value="baidu_doc">{PARSE_ENGINE_MODE_LABELS.baidu_doc}</option>
                    <option value="mineru_cloud">{PARSE_ENGINE_MODE_LABELS.mineru_cloud}</option>
                  </Select>
                  <ModelStatusBadge
                    status={modelStatus}
                    isLoading={isModelStatusLoading}
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
                  >
                    <option value="layout_block">{AIOCR_CHAIN_MODE_LABELS.layout_block}</option>
                    <option value="doc_parser">{AIOCR_CHAIN_MODE_LABELS.doc_parser}</option>
                    <option value="direct">{AIOCR_CHAIN_MODE_LABELS.direct}</option>
                  </Select>
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
                  >
                    {Object.values(LAYOUT_MODELS).map((m) => (
                      <option key={m.modelId} value={m.modelId} disabled={!downloadedLayoutModels.has(m.modelId)}>
                        {m.displayName} — {m.speedLabel}
                      </option>
                    ))}
                  </Select>
                  {downloadedLayoutModels.size === 0 && (
                    <span className="text-xs text-muted-foreground">
                      暂无已下载的版面模型，请前往{" "}
                      <Link href="/settings" className="underline">设置</Link>
                      {" "}下载
                    </span>
                  )}
                </div>
              )}
              {settingsSnapshot.parseEngineMode === "remote_ocr" && (
                <div className="grid gap-1">
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span>OCR 模型</span>
                    <HoverHint text="选择用于文字识别的 AI 模型。" />
                  </div>
                  {settingsSnapshot.ocrAiApiKey.trim() && settingsSnapshot.ocrAiBaseUrl.trim() ? (
                    <Select
                      value={
                        ["Qwen/Qwen2.5-VL-7B-Instruct", "Qwen/Qwen2.5-VL-32B-Instruct", "paddleocr/PaddleOCR-VL-1.5", "deepseek-ai/DeepSeek-OCR", "openai/gpt-4o-mini"].includes(settingsSnapshot.ocrAiModel)
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
                      <option value="Qwen/Qwen2.5-VL-7B-Instruct">Qwen2.5-VL-7B</option>
                      <option value="Qwen/Qwen2.5-VL-32B-Instruct">Qwen2.5-VL-32B</option>
                      <option value="paddleocr/PaddleOCR-VL-1.5">PaddleOCR-VL</option>
                      <option value="deepseek-ai/DeepSeek-OCR">DeepSeek-OCR</option>
                      <option value="openai/gpt-4o-mini">GPT-4o-mini</option>
                      {(!["Qwen/Qwen2.5-VL-7B-Instruct", "Qwen/Qwen2.5-VL-32B-Instruct", "paddleocr/PaddleOCR-VL-1.5", "deepseek-ai/DeepSeek-OCR", "openai/gpt-4o-mini"].includes(settingsSnapshot.ocrAiModel) && settingsSnapshot.ocrAiModel.trim()) && (
                        <option value="__custom__">{settingsSnapshot.ocrAiModel}</option>
                      )}
                    </Select>
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

          {/* Action buttons */}
          <div className="space-y-2">
            {preflightWarning && (
              <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                <p className="font-medium">⚠️ {preflightWarning}</p>
                <div className="mt-1.5 flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-6 text-[11px]"
                    onClick={() => {
                      setPreflightAcknowledged(true)
                      void handleConvertAll()
                    }}
                  >
                    仍然转换
                  </Button>
                  <Link href="/settings">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-6 text-[11px]"
                    >
                      去设置
                    </Button>
                  </Link>
                </div>
              </div>
            )}
            {!user && !isAuthLoading ? (
              <Button type="button" variant="outline" className="w-full" asChild>
                <Link href="/login">登录后创建任务</Link>
              </Button>
            ) : (
              <>
                <Button
                  type="button"
                  className="w-full"
                  onClick={handleConvertAll}
                  disabled={!canStart}
                >
                  {fileCount > 1 ? `全部转换 (${fileCount} 个文件)` : "开始转换"}
                </Button>
                {fileCount === 1 && (
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full"
                    onClick={() => {
                      setUsePageRange(true)
                      const current = String(previewPage)
                      setPageStartInput(current)
                      setPageEndInput(current)
                      void handleConvertAll()
                    }}
                    disabled={!canStart}
                  >
                    单页试跑（当前页）
                  </Button>
                )}
              </>
            )}
          </div>

          {actionError ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              {actionError}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
