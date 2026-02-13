function trimTrailingSlash(value: string): string {
  return value.replace(/\/$/, "")
}

export function getApiOrigin(): string {
  const configured = String(process.env.NEXT_PUBLIC_API_URL || "").trim()
  if (configured) return trimTrailingSlash(configured)

  if (typeof window !== "undefined") {
    const protocol = window.location.protocol || "http:"
    const hostname = window.location.hostname || "localhost"
    const apiPort = String(process.env.NEXT_PUBLIC_API_PORT || "8000").trim() || "8000"
    return `${protocol}//${hostname}:${apiPort}`
  }

  return "http://localhost:8000"
}

export function getApiBaseUrl(): string {
  return `${getApiOrigin()}/api/v1`
}

export function normalizeFetchError(error: unknown, fallback: string): string {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "请求已取消"
  }

  if (error instanceof TypeError) {
    const raw = String(error.message || "").toLowerCase()
    if (raw.includes("network") || raw.includes("fetch") || raw.includes("failed")) {
      return `${fallback}（网络连接失败，请检查 API 地址与后端 CORS 设置）`
    }
  }

  if (error instanceof Error) {
    const message = String(error.message || "").trim()
    if (message) return message
  }
  return fallback
}

