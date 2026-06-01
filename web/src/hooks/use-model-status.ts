"use client"

import * as React from "react"
import { apiFetch, normalizeFetchError } from "@/lib/api"

/**
 * Model provider status returned by GET /api/v1/models/status.
 */
export interface ModelProviderStatus {
  ready: boolean
  issues: string[]
  provider?: string | null
  configured?: boolean
}

export interface ModelStatusResponse {
  local: Record<string, ModelProviderStatus>
  remote: Record<string, ModelProviderStatus>
}

/**
 * Hook to fetch and cache unified model readiness status.
 *
 * Returns the full status response plus loading/error state and a manual
 * refetch function. Does NOT poll automatically — call `refetch()` on demand
 * (e.g. when the user switches parse engine or before job submission).
 */
export function useModelStatus() {
  const [data, setData] = React.useState<ModelStatusResponse | null>(null)
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [lastError, setLastError] = React.useState<string | null>(null)
  const mountedRef = React.useRef(true)
  const retryCountRef = React.useRef(0)

  const refetch = React.useCallback(async () => {
    setIsLoading(true)
    setError(null)
    setLastError(null)

    const MAX_RETRIES = 3
    const RETRY_DELAYS = [2000, 4000, 8000]

    const attemptFetch = async (attempt: number): Promise<void> => {
      try {
        const res = await apiFetch("/models/status")
        if (!res.ok) {
          const body = await res.json().catch(() => null)
          throw new Error(body?.message || "模型状态查询失败")
        }
        const body = (await res.json()) as ModelStatusResponse
        if (mountedRef.current) {
          setData(body)
          setError(null)
          setLastError(null)
          retryCountRef.current = 0
        }
      } catch (e) {
        // Network errors (TypeError, AbortError) are retryable; HTTP errors (from !res.ok) are not
        const isNetworkError =
          e instanceof TypeError ||
          (typeof DOMException !== "undefined" && e instanceof DOMException && e.name === "AbortError")

        if (isNetworkError && attempt < MAX_RETRIES) {
          retryCountRef.current = attempt + 1
          await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS[attempt]))
          return attemptFetch(attempt + 1)
        }

        // Non-retryable or retries exhausted — rethrow to outer catch
        throw e
      }
    }

    try {
      await attemptFetch(0)
    } catch (e) {
      if (mountedRef.current) {
        const msg = normalizeFetchError(e, "模型状态查询失败")
        setError(msg)
        setLastError(msg)
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false)
      }
    }
  }, [])

  React.useEffect(() => {
    mountedRef.current = true
    void refetch()
    return () => {
      mountedRef.current = false
    }
  }, [refetch])

  return { data, isLoading, error, lastError, refetch }
}

/**
 * Merge backend model status with frontend localStorage-based checks for
 * remote providers.  The backend model-status endpoint checks `site_settings`
 * in the DB, but in self-hosted mode the user's OCR/AI keys are only stored
 * in localStorage.  This hook overrides the `ready` flag for remote providers
 * when the required keys are present in the current Settings snapshot.
 */
export function useEffectiveModelStatus(
  backend: ModelStatusResponse | null,
  settings: {
    ocrAiApiKey: string
    ocrAiBaseUrl: string
    ocrBaiduApiKey: string
    ocrBaiduSecretKey: string
    mineruApiToken: string
  },
): ModelStatusResponse | null {
  return React.useMemo(() => {
    if (!backend) return null

    const remote = { ...backend.remote }

    // AIOCR — needs api_key. Base URL is optional for providers with a
    // built-in/default endpoint such as OpenAI, and SiliconFlow gets its
    // default URL from settings normalization.
    if (remote["aiocr"]) {
      const hasKey = settings.ocrAiApiKey.trim().length > 0
      remote["aiocr"] = {
        ...remote["aiocr"],
        ready: hasKey,
        configured: hasKey,
        issues: hasKey ? [] : [
          ...(!hasKey ? ["api_key_missing"] : []),
        ],
      }
    }

    // Baidu Doc — needs api_key + secret_key
    if (remote["baidu_doc"]) {
      const hasKey = settings.ocrBaiduApiKey.trim().length > 0
      const hasSecret = settings.ocrBaiduSecretKey.trim().length > 0
      remote["baidu_doc"] = {
        ...remote["baidu_doc"],
        ready: hasKey && hasSecret,
        configured: hasKey && hasSecret,
        issues: hasKey && hasSecret ? [] : [
          ...(!hasKey ? ["api_key_missing"] : []),
          ...(!hasSecret ? ["secret_key_missing"] : []),
        ],
      }
    }

    // MinerU — needs api_token
    if (remote["mineru"]) {
      const hasToken = settings.mineruApiToken.trim().length > 0
      remote["mineru"] = {
        ...remote["mineru"],
        ready: hasToken,
        configured: hasToken,
        issues: hasToken ? [] : ["api_token_missing"],
      }
    }

    return { local: backend.local, remote }
  }, [backend, settings.ocrAiApiKey, settings.ocrBaiduApiKey, settings.ocrBaiduSecretKey, settings.mineruApiToken])
}
