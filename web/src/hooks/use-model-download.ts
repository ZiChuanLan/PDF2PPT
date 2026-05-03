"use client"

import * as React from "react"
import { apiFetch, normalizeFetchError } from "@/lib/api"
import { toast } from "sonner"

/**
 * Download task status returned by GET /api/v1/models/download/status.
 */
export interface DownloadStatusItem {
  model_id: string
  status: "downloading" | "completed" | "failed" | "cancelled"
  progress: number | null // 0.0-1.0 for huggingface, null for paddlex
  message: string | null
  started_at: number
}

export interface DownloadStatusResponse {
  downloads: Record<string, DownloadStatusItem>
}

/**
 * Hook to manage model downloads with progress tracking and cancellation.
 *
 * Polls GET /api/v1/models/download/status every second while there are
 * active downloads. Provides startDownload() and cancelDownload() actions.
 */
export function useModelDownload(options?: {
  onDownloadComplete?: (modelId: string) => void
  onDownloadFailed?: (modelId: string, message: string) => void
  onDownloadCancelled?: (modelId: string) => void
}) {
  const [downloads, setDownloads] = React.useState<Record<string, DownloadStatusItem>>({})
  const pollTimerRef = React.useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = React.useRef(true)
  const callbacksRef = React.useRef(options)
  callbacksRef.current = options

  // Cleanup on unmount
  React.useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const fetchStatus = React.useCallback(async () => {
    try {
      const res = await apiFetch("/models/download/status")
      if (!res.ok) return
      const body = (await res.json()) as DownloadStatusResponse
      if (!mountedRef.current) return

      setDownloads((prev) => {
        // Check for newly completed/failed/cancelled downloads
        for (const [modelId, item] of Object.entries(body.downloads)) {
          const prevItem = prev[modelId]
          if (prevItem?.status === "downloading" && item.status !== "downloading") {
            if (item.status === "completed") {
              toast.success(`${getModelLabel(modelId)} 下载完成`)
              callbacksRef.current?.onDownloadComplete?.(modelId)
            } else if (item.status === "failed") {
              toast.error(`${getModelLabel(modelId)} 下载失败: ${item.message || "未知错误"}`)
              callbacksRef.current?.onDownloadFailed?.(modelId, item.message || "下载失败")
            } else if (item.status === "cancelled") {
              toast(`${getModelLabel(modelId)} 下载已取消`)
              callbacksRef.current?.onDownloadCancelled?.(modelId)
            }
          }
        }
        return body.downloads
      })
    } catch {
      // Silent fail — polling will retry
    }
  }, [])

  // Start/stop polling based on active downloads
  React.useEffect(() => {
    const hasActiveDownloads = Object.values(downloads).some(
      (d) => d.status === "downloading"
    )

    if (hasActiveDownloads && !pollTimerRef.current) {
      // Start polling
      pollTimerRef.current = setInterval(() => {
        void fetchStatus()
      }, 1000)
      // Immediate fetch
      void fetchStatus()
    } else if (!hasActiveDownloads && pollTimerRef.current) {
      // Stop polling
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [downloads, fetchStatus])

  /**
   * Start downloading a model. Returns immediately — poll downloads state
   * for progress updates.
   */
  const startDownload = React.useCallback(async (modelId: string): Promise<boolean> => {
    try {
      const res = await apiFetch("/models/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelId }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.message || "下载请求失败")
      }

      // Immediately fetch status to start tracking
      await fetchStatus()
      return true
    } catch (e) {
      toast.error(normalizeFetchError(e, "下载请求失败"))
      return false
    }
  }, [fetchStatus])

  /**
   * Cancel an active download.
   */
  const cancelDownload = React.useCallback(async (modelId: string): Promise<boolean> => {
    try {
      const res = await apiFetch("/models/download/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modelId }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.message || "取消请求失败")
      }
      return true
    } catch (e) {
      toast.error(normalizeFetchError(e, "取消下载失败"))
      return false
    }
  }, [])

  /**
   * Get the download state for a specific model.
   */
  const getDownloadState = React.useCallback(
    (modelId: string): DownloadStatusItem | null => {
      return downloads[modelId] ?? null
    },
    [downloads]
  )

  /**
   * Check if a model is currently downloading.
   */
  const isDownloading = React.useCallback(
    (modelId: string): boolean => {
      return downloads[modelId]?.status === "downloading"
    },
    [downloads]
  )

  return {
    downloads,
    startDownload,
    cancelDownload,
    getDownloadState,
    isDownloading,
  }
}

/**
 * Get a human-readable label for a model ID.
 */
function getModelLabel(modelId: string): string {
  const labels: Record<string, string> = {
    pp_doclayout_s: "PP-DocLayout-S",
    pp_doclayout_m: "PP-DocLayout-M",
    pp_doclayout_l: "PP-DocLayout-L",
    pp_doclayout_v3: "PP-DocLayoutV3",
    doclayout_yolo: "DocLayout-YOLO",
    paddleocr: "PaddleOCR",
  }
  return labels[modelId] ?? modelId
}
