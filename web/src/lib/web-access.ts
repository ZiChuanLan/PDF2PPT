const WEB_ACCESS_COOKIE_NAME = "ppt_web_access"
const WEB_ACCESS_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
const DEFAULT_WEB_ACCESS_PASSWORD = "123456"

function trimToNull(value: string | undefined): string | null {
  const trimmed = String(value || "").trim()
  return trimmed ? trimmed : null
}

export function getWebAccessPassword(): string | null {
  const configured = trimToNull(process.env.WEB_ACCESS_PASSWORD)
  if (configured) return configured
  return DEFAULT_WEB_ACCESS_PASSWORD
}

export function isDefaultWebAccessPassword(value?: string | null): boolean {
  return String(value ?? getWebAccessPassword() ?? "") === DEFAULT_WEB_ACCESS_PASSWORD
}

export function getApiBearerToken(): string | null {
  return trimToNull(process.env.API_BEARER_TOKEN)
}

export function normalizeUnlockRedirectPath(raw: string | null | undefined): string {
  const value = String(raw || "").trim()
  if (!value.startsWith("/") || value.startsWith("//")) return "/"
  if (value.startsWith("/unlock")) return "/"
  return value
}

export async function computeWebAccessCookieValue(password: string): Promise<string> {
  const data = new TextEncoder().encode(`ppt-web-access:${password}`)
  const digest = await crypto.subtle.digest("SHA-256", data)
  return Array.from(new Uint8Array(digest))
    .map((part) => part.toString(16).padStart(2, "0"))
    .join("")
}

export async function getExpectedWebAccessCookieValue(): Promise<string | null> {
  const password = getWebAccessPassword()
  if (!password) return null
  return computeWebAccessCookieValue(password)
}

export async function hasValidWebAccessCookieValue(
  cookieValue: string | null | undefined
): Promise<boolean> {
  const expectedCookieValue = await getExpectedWebAccessCookieValue()
  const actualCookieValue = String(cookieValue || "")
  return Boolean(expectedCookieValue && actualCookieValue === expectedCookieValue)
}

export {
  DEFAULT_WEB_ACCESS_PASSWORD,
  WEB_ACCESS_COOKIE_NAME,
  WEB_ACCESS_COOKIE_MAX_AGE_SECONDS,
}
