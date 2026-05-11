import { apiFetch } from "./api"

/**
 * Download a completed job's PPTX output via the browser.
 *
 * Common pattern extracted from page.tsx, jobs/page.tsx, and tracking/page.tsx
 * which all do: apiFetch → blob → createObjectURL → <a> click → revokeObjectURL.
 *
 * Returns `true` on success. Throws on failure so callers can show toasts.
 */
export async function downloadJobOutput(jobId: string): Promise<true> {
  const response = await apiFetch(`/jobs/${jobId}/download`)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.message || `下载失败（HTTP ${response.status}）`)
  }
  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `output-${jobId.slice(0, 8)}.pptx`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
  return true
}
