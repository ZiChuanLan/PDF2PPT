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
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const code = searchParams.get("code")
  const state = searchParams.get("state")

  // Validate required parameters
  if (!code || !state) {
    return NextResponse.redirect(
      new URL("/login?error=missing_params", request.url)
    )
  }

  // Validate state against stored value
  // Note: In production, state should be validated server-side
  // For now, we'll pass it through to the backend

  try {
    // Exchange code for tokens via backend
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    const response = await fetch(`${apiBase}/api/v1/auth/callback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ code, state }),
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => null)
      const errorMessage = errorData?.message || "Authentication failed"
      console.error("OAuth callback error:", errorMessage)
      return NextResponse.redirect(
        new URL(`/login?error=${encodeURIComponent(errorMessage)}`, request.url)
      )
    }

    // Success - backend sets cookies, redirect to home
    const redirectUrl = new URL("/", request.url)
    const nextResponse = NextResponse.redirect(redirectUrl)

    // Forward any cookies set by the backend
    const setCookieHeaders = response.headers.getSetCookie?.() || []
    for (const cookie of setCookieHeaders) {
      nextResponse.headers.append("Set-Cookie", cookie)
    }

    // If no cookies from getSetCookie, try the raw header
    if (setCookieHeaders.length === 0) {
      const rawCookie = response.headers.get("set-cookie")
      if (rawCookie) {
        nextResponse.headers.set("Set-Cookie", rawCookie)
      }
    }

    return nextResponse
  } catch (error) {
    console.error("OAuth callback error:", error)
    return NextResponse.redirect(
      new URL("/login?error=network_error", request.url)
    )
  }
}
