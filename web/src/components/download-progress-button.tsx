"use client"

import * as React from "react"
import { DownloadIcon, CheckIcon, RefreshCwIcon, XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { DownloadStatusItem } from "@/hooks/use-model-download"
import { LAYOUT_MODELS } from "@/lib/layout-models"

/**
 * Download button that shows progress bar + cancel when downloading,
 * or a simple download button when idle.
 */
export function DownloadProgressButton({
  modelId,
  label,
  downloadState,
  isReady = false,
  onDownload,
  onCancel,
  onRefreshStatus,
  size = "sm",
  variant = "outline",
  className,
}: {
  modelId: string
  label?: string
  downloadState: DownloadStatusItem | null
  isReady?: boolean
  onDownload: (modelId: string) => void
  onCancel: (modelId: string) => void
  onRefreshStatus?: () => void
  size?: "sm" | "default" | "xs"
  variant?: "outline" | "ghost" | "default"
  className?: string
}) {
  const isDownloading = downloadState?.status === "downloading"
  const progress = downloadState?.progress
  const modelInfo = LAYOUT_MODELS[modelId]
  const modelLabel = modelInfo?.displayName ?? label ?? modelId
  const sizeMb = modelInfo?.sizeMb

  // Elapsed time estimation for indeterminate (PaddleX) downloads
  const elapsedRef = React.useRef<number | null>(null)
  const [elapsedLabel, setElapsedLabel] = React.useState<string>("")
  React.useEffect(() => {
    if (!isDownloading || progress !== null && progress !== undefined) {
      elapsedRef.current = null
      setElapsedLabel("")
      return
    }
    if (elapsedRef.current === null && downloadState?.started_at) {
      elapsedRef.current = downloadState.started_at
    }
    const timer = window.setInterval(() => {
      if (elapsedRef.current) {
        const secs = Math.floor((Date.now() / 1000) - elapsedRef.current)
        const mins = Math.floor(secs / 60)
        const remainSecs = secs % 60
        let label = `已用时 ${mins}m ${remainSecs}s`
        if (sizeMb && sizeMb > 0) {
          // Rough estimate: ~1MB/s for typical PaddleX downloads
          const estimatedTotal = sizeMb * 1.0 // seconds per MB
          const remaining = Math.max(0, estimatedTotal - secs)
          if (remaining > 0) {
            const remMins = Math.floor(remaining / 60)
            const remSecs = Math.floor(remaining % 60)
            label += ` · 预计剩余 ${remMins}m ${remSecs}s`
          }
        }
        setElapsedLabel(label)
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [isDownloading, progress, downloadState?.started_at, sizeMb])

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
            // Indeterminate progress (paddlex) — show pulsing bar
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
        {/* Model info line for PaddleX indeterminate downloads */}
        {progress === null && sizeMb ? (
          <div className="mb-0.5 text-[10px] text-muted-foreground">
            {modelLabel} · {sizeMb} MB · {elapsedLabel || "正在下载中 (估算)"}
          </div>
        ) : null}
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

  if (isReady) {
    return (
      <span className={cn("inline-flex items-center gap-1 text-xs text-muted-foreground", className)}>
        <CheckIcon className="size-3" />
        已下载
      </span>
    )
  }

  if (downloadState?.status === "completed") {
    if (onRefreshStatus) {
      return (
        <Button
          type="button"
          variant={variant}
          size={size}
          className={className}
          onClick={onRefreshStatus}
        >
          <RefreshCwIcon className="size-3" />
          刷新状态
        </Button>
      )
    }

    return (
      <span className={cn("inline-flex items-center gap-1 text-xs text-muted-foreground", className)}>
        <CheckIcon className="size-3" />
        下载完成，待校验
      </span>
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
