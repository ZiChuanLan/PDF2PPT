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
  const mountedRef = React.useRef(true)

  const refetch = React.useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await apiFetch("/models/status")
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.message || "模型状态查询失败")
      }
      const body = (await res.json()) as ModelStatusResponse
      if (mountedRef.current) {
        setData(body)
      }
    } catch (e) {
      if (mountedRef.current) {
        setError(normalizeFetchError(e, "模型状态查询失败"))
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

  return { data, isLoading, error, refetch }
}
