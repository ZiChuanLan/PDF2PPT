import { NextRequest, NextResponse } from "next/server"

/**
 * OAuth callback route handler.
 *
 * This route receives the authorization code from LinuxDo OAuth
 * and exchanges it for tokens via the backend API.
 *
 * The backend sets httponly cookies for JWT storage,
 * so the frontend just needs to redirect after successful auth.
 */
/**
 * Derive the real origin from the Host header.
 *
 * Next.js dev server binds to 0.0.0.0 and may rewrite request.nextUrl.origin
 * to http://0.0.0.0 even when the browser accessed via localhost or 127.0.0.1.
 * The Host header preserves the actual hostname the browser used.
 */
function getRealOrigin(request: NextRequest): string {
  const host = request.headers.get("host")
  if (host) {
    const proto = request.nextUrl.protocol === "https:" ? "https" : "http"
    return `${proto}://${host}`
  }
  return request.nextUrl.origin
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const code = searchParams.get("code")
  const state = searchParams.get("state")

  const origin = getRealOrigin(request)

  // Validate required parameters
  if (!code || !state) {
    return NextResponse.redirect(new URL("/login?error=missing_params", origin))
  }

  try {
    // Exchange code for tokens via backend (server-side, use Docker service name)
    const apiBase = process.env.INTERNAL_API_ORIGIN || "http://api:8000"
    const response = await fetch(`${apiBase}/api/v1/auth/callback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ code, state, origin }),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => null)
      const errorMessage = errorData?.message || "Authentication failed"
      console.error("OAuth callback error:", errorMessage, "status:", response.status)
      return NextResponse.redirect(
        new URL(`/login?error=${encodeURIComponent(errorMessage)}`, origin)
      )
    }

    // Success - extract tokens from response body
    const data = await response.json().catch(() => null)
    const accessToken = data?.access_token as string | undefined
    const refreshToken = data?.refresh_token as string | undefined

    if (!accessToken) {
      console.error(
        "OAuth callback: backend returned 200 but no access_token in body",
        JSON.stringify(data).slice(0, 300)
      )
      return NextResponse.redirect(new URL("/login?error=no_token", origin))
    }

    // Set cookies directly from tokens in response body.
    // This avoids relying on forwarding Set-Cookie headers from a
    // server-side fetch() response, which can be unreliable across
    // Node.js / undici versions.
    const maxAgeAccess = 60 * 60 // 1 hour
    const maxAgeRefresh = 30 * 24 * 60 * 60 // 30 days
    const isSecure = request.nextUrl.protocol === "https:"

    const nextResponse = NextResponse.redirect(new URL("/", origin))
    nextResponse.cookies.set("access_token", accessToken, {
      path: "/",
      httpOnly: true,
      secure: isSecure,
      sameSite: "lax",
      maxAge: maxAgeAccess,
    })
    if (refreshToken) {
      nextResponse.cookies.set("refresh_token", refreshToken, {
        path: "/",
        httpOnly: true,
        secure: isSecure,
        sameSite: "lax",
        maxAge: maxAgeRefresh,
      })
    }

    return nextResponse
  } catch (error) {
    console.error("OAuth callback error:", error)
    return NextResponse.redirect(new URL("/login?error=network_error", origin))
  }
}
