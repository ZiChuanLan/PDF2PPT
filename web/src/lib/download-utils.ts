import { apiFetch } from "./api"
import { toast } from "sonner"

/**
 * Download a completed job's PPTX output via the browser.
 *
 * Common pattern extracted from page.tsx, jobs/page.tsx, and tracking/page.tsx
 * which all do: apiFetch → blob → createObjectURL → <a> click → revokeObjectURL.
 *
 * Retries up to `maxRetries` times with 1-second delay between attempts.
 * Shows error toast if all attempts fail.
 *
 * Returns `true` on success. Throws on failure so callers can show toasts.
 */
export async function downloadJobOutput(
  jobId: string,
  filename?: string,
  maxRetries: number = 2
): Promise<true> {
  let lastError: Error | null = null
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const response = await apiFetch(`/jobs/${jobId}/download`)
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.message || `下载失败（HTTP ${response.status}）`)
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename || `output-${jobId.slice(0, 8)}.pptx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
      return true
    } catch (e) {
      lastError = e as Error
      console.error(`Download attempt ${attempt + 1} failed:`, e)
      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, 1000))
      }
    }
  }
  toast.error(`下载失败: ${lastError?.message || "未知错误"}`)
  throw lastError || new Error("下载失败")
}
