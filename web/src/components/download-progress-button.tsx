"use client"

import * as React from "react"
import { DownloadIcon, XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import type { DownloadStatusItem } from "@/hooks/use-model-download"

/**
 * Download button that shows progress bar + cancel when downloading,
 * or a simple download button when idle.
 */
export function DownloadProgressButton({
  modelId,
  label,
  downloadState,
  onDownload,
  onCancel,
  size = "sm",
  variant = "outline",
  className,
}: {
  modelId: string
  label?: string
  downloadState: DownloadStatusItem | null
  onDownload: (modelId: string) => void
  onCancel: (modelId: string) => void
  size?: "sm" | "default" | "xs"
  variant?: "outline" | "ghost" | "default"
  className?: string
}) {
  const isDownloading = downloadState?.status === "downloading"
  const progress = downloadState?.progress

  if (isDownloading) {
    return (
      <div className={className}>
        {/* Progress bar */}
        <div className="mb-1 flex items-center gap-2">
          {progress !== null && progress !== undefined ? (
            // Determinate progress (huggingface)
            <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-foreground transition-all duration-300"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
          ) : (
            // Indeterminate progress (paddlex)
            <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <div className="absolute inset-y-0 left-0 w-1/3 animate-pulse rounded-full bg-foreground" />
            </div>
          )}
          <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
            {progress !== null && progress !== undefined
              ? `${Math.round(progress * 100)}%`
              : "下载中..."}
          </span>
        </div>
        {/* Cancel button */}
        <Button
          type="button"
          variant="ghost"
          size="xs"
          className="h-6 text-[10px] text-muted-foreground hover:text-destructive"
          onClick={() => onCancel(modelId)}
        >
          <XIcon className="size-3" />
          取消
        </Button>
        {downloadState?.message ? (
          <div className="mt-0.5 text-[10px] text-muted-foreground">
            {downloadState.message}
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      className={className}
      onClick={() => onDownload(modelId)}
    >
      <DownloadIcon className="size-3" />
      {label ?? "下载"}
    </Button>
  )
}
