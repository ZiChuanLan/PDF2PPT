// Shared utilities for the Home page

export const SUPPORTED_UPLOAD_ACCEPT = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/webp": [".webp"],
} as const

export const SUPPORTED_IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"] as const

export function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"] as const
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, idx)
  return `${value.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`
}

export function toIntOrUndefined(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const n = Number(trimmed)
  if (!Number.isFinite(n)) return undefined
  const i = Math.floor(n)
  if (i <= 0) return undefined
  return i
}

export function clampPositiveInt(value: number, max?: number) {
  const normalized = Number.isFinite(value) ? Math.max(1, Math.floor(value)) : 1
  if (!max || max <= 0) return normalized
  return Math.min(normalized, max)
}

export function isImageUploadFile(file: File | null | undefined) {
  if (!file) return false
  const type = String(file.type || "").trim().toLowerCase()
  if (type.startsWith("image/")) return true
  const name = String(file.name || "").trim().toLowerCase()
  return SUPPORTED_IMAGE_EXTENSIONS.some((suffix) => name.endsWith(suffix))
}
