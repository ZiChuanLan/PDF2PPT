"use client"

import * as React from "react"
import {
  ArrowLeftIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  FileIcon,
  XIcon,
} from "lucide-react"

import { cn } from "@/lib/utils"
import {
  type Settings,
} from "@/lib/settings"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PdfCanvasPreview } from "@/components/pdf-canvas-preview"
import type { ModelStatusResponse } from "@/hooks/use-model-status"
import { formatBytes, clampPositiveInt } from "@/lib/home-utils"
import { PageRangeSection } from "@/components/home/page-range-section"
import { QuickConfigPanel } from "@/components/home/quick-config-panel"
import { ActionButtons } from "@/components/home/action-buttons"

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
                      aria-label="删除文件"
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
            <div className="home-preview-stage" role="img" aria-label="PDF 预览">
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
          <PageRangeSection
            isImageInput={isImageInput}
            usePageRange={usePageRange}
            setUsePageRange={setUsePageRange}
            pageStartInput={pageStartInput}
            setPageStartInput={setPageStartInput}
            pageEndInput={pageEndInput}
            setPageEndInput={setPageEndInput}
            currentPreviewFile={currentPreviewFile}
            previewPage={previewPage}
          />

          {/* Quick config */}
          <QuickConfigPanel
            settingsSnapshot={settingsSnapshot}
            updateSettingsSnapshot={updateSettingsSnapshot}
            modelStatus={modelStatus}
            isModelStatusLoading={isModelStatusLoading}
            refetchModelStatus={refetchModelStatus}
            retainProcessArtifacts={retainProcessArtifacts}
            setRetainProcessArtifacts={setRetainProcessArtifacts}
            downloadedLayoutModels={downloadedLayoutModels}
          />

          {/* Action buttons */}
          <ActionButtons
            fileCount={fileCount}
            handleConvertAll={handleConvertAll}
            canStart={canStart}
            actionError={actionError}
            preflightWarning={preflightWarning}
            setPreflightAcknowledged={setPreflightAcknowledged}
            setUsePageRange={setUsePageRange}
            setPageStartInput={setPageStartInput}
            setPageEndInput={setPageEndInput}
            previewPage={previewPage}
          />
        </div>
      </div>
    </div>
  )
}
