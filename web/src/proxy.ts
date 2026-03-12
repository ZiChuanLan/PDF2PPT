import { NextRequest, NextResponse } from "next/server"

import {
  DEFAULT_WEB_ACCESS_PASSWORD,
  getApiBearerToken,
  getWebAccessPassword,
  hasValidWebAccessCookieValue,
  isDefaultWebAccessPassword,
  normalizeUnlockRedirectPath,
  WEB_ACCESS_COOKIE_NAME,
} from "@/lib/web-access"

let warnedAboutDefaultWebPassword = false

function withRequestHeaders(request: NextRequest, headers: Headers) {
  return NextResponse.next({
    request: {
      headers,
    },
  })
}

function maybeWarnOnDefaultWebPassword(webAccessPassword: string | null) {
  if (warnedAboutDefaultWebPassword) return
  if (!isDefaultWebAccessPassword(webAccessPassword)) return
  warnedAboutDefaultWebPassword = true
  console.warn(
    `WEB_ACCESS_PASSWORD is using the default value "${DEFAULT_WEB_ACCESS_PASSWORD}". Set a custom value in production.`
  )
}

export async function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl

  if (pathname === "/health" || pathname === "/unlock" || pathname.startsWith("/unlock/")) {
    return NextResponse.next()
  }

  const webAccessPassword = getWebAccessPassword()
  maybeWarnOnDefaultWebPassword(webAccessPassword)
  const hasUnlockedSession =
    !webAccessPassword ||
    (await hasValidWebAccessCookieValue(
      request.cookies.get(WEB_ACCESS_COOKIE_NAME)?.value
    ))

  if (pathname.startsWith("/api/")) {
    const apiBearerToken = getApiBearerToken()
    const hasAuthorizationHeader = request.headers.has("authorization")

    // Explicit API clients such as `ppt-mcp` can authenticate with their own
    // bearer token and do not need a web unlock cookie.
    if (hasAuthorizationHeader && apiBearerToken) {
      return NextResponse.next()
    }

    if (!hasUnlockedSession) {
      return NextResponse.json(
        {
          code: "web_access_required",
          message: "Unlock the site before using API routes",
        },
        { status: 401 }
      )
    }

    if (!apiBearerToken || hasAuthorizationHeader) {
      return NextResponse.next()
    }

    const headers = new Headers(request.headers)
    headers.set("authorization", `Bearer ${apiBearerToken}`)
    return withRequestHeaders(request, headers)
  }

  if (hasUnlockedSession) {
    return NextResponse.next()
  }

  const unlockUrl = request.nextUrl.clone()
  unlockUrl.pathname = "/unlock"
  unlockUrl.search = ""
  unlockUrl.searchParams.set(
    "next",
    normalizeUnlockRedirectPath(`${pathname}${search}`)
  )
  return NextResponse.redirect(unlockUrl)
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|txt|xml)$).*)"],
}
