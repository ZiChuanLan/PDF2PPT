"use client"

import * as React from "react"
import { apiFetch, normalizeFetchError } from "@/lib/api"
import { MODEL_DOWNLOAD_POLL_INTERVAL_MS } from "@/lib/constants"
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

// ---------------------------------------------------------------------------
// Singleton: global shared download state & single poller
//
// Multiple components (ocr-strategy-section, model-status-badge) call
// useModelDownload(). The singleton ensures only one polling timer runs
// and all callers observe the same download state.
// ---------------------------------------------------------------------------

type Listener = () => void

let globalDownloads: Record<string, DownloadStatusItem> = {}
const listeners = new Set<Listener>()
let globalPollTimer: ReturnType<typeof setInterval> | null = null
let subscriberCount = 0

function notifyListeners() {
  for (const listener of listeners) {
    listener()
  }
}

function hasActiveDownloads(): boolean {
  return Object.values(globalDownloads).some(
    (d) => d.status === "downloading"
  )
}

async function fetchGlobalStatus() {
  try {
    const res = await apiFetch("/models/download/status")
    if (!res.ok) return
    const body = (await res.json()) as DownloadStatusResponse

    // Check for newly completed/failed/cancelled downloads
    for (const [modelId, item] of Object.entries(body.downloads)) {
      const prev = globalDownloads[modelId]
      if (prev?.status === "downloading" && item.status !== "downloading") {
        if (item.status === "completed") {
          toast.success(`${getModelLabel(modelId)} 下载完成`)
        } else if (item.status === "failed") {
          toast.error(`${getModelLabel(modelId)} 下载失败: ${item.message || "未知错误"}`)
        } else if (item.status === "cancelled") {
          toast(`${getModelLabel(modelId)} 下载已取消`)
        }
      }
    }

    globalDownloads = body.downloads
    notifyListeners()
  } catch (e) {
    console.error("Failed to fetch model download status:", e)
    // Polling will retry
  }
}

function startGlobalPolling() {
  if (globalPollTimer) return // Already polling
  // Fetch immediately
  void fetchGlobalStatus()
  globalPollTimer = setInterval(() => {
    void fetchGlobalStatus()
  }, MODEL_DOWNLOAD_POLL_INTERVAL_MS)
}

function stopGlobalPollingIfIdle() {
  if (!hasActiveDownloads() && globalPollTimer) {
    clearInterval(globalPollTimer)
    globalPollTimer = null
  }
}

/**
 * Hook to manage model downloads with progress tracking and cancellation.
 *
 * Uses a module-level singleton: only one polling timer runs globally
 * regardless of how many components call this hook. All callers share
 * the same download state via a listener subscription pattern.
 */
export function useModelDownload(options?: {
  onDownloadComplete?: (modelId: string) => void
  onDownloadFailed?: (modelId: string, message: string) => void
  onDownloadCancelled?: (modelId: string) => void
}) {
  const [downloads, setDownloads] = React.useState<Record<string, DownloadStatusItem>>(globalDownloads)
  const mountedRef = React.useRef(true)
  const callbacksRef = React.useRef(options)
  callbacksRef.current = options

  // Subscribe to global state changes
  React.useEffect(() => {
    mountedRef.current = true
    subscriberCount++

    const listener = () => {
      if (mountedRef.current) {
        setDownloads({ ...globalDownloads })
      }
    }
    listeners.add(listener)

    // Initial sync
    if (mountedRef.current) {
      setDownloads({ ...globalDownloads })
    }

    return () => {
      mountedRef.current = false
      listeners.delete(listener)
      subscriberCount--
      // If no more subscribers and no active downloads, stop polling
      if (subscriberCount <= 0 && !hasActiveDownloads()) {
        stopGlobalPollingIfIdle()
      }
    }
  }, [])

  // Polling lifecycle: check on every downloads change
  React.useEffect(() => {
    if (hasActiveDownloads()) {
      startGlobalPolling()
    } else {
      stopGlobalPollingIfIdle()
    }
  }, [downloads])

  // Fetch status on mount to pick up any active downloads from other pages
  React.useEffect(() => {
    void fetchGlobalStatus()
  }, [])

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
      await fetchGlobalStatus()
      return true
    } catch (e) {
      toast.error(normalizeFetchError(e, "下载请求失败"))
      return false
    }
  }, [])

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
