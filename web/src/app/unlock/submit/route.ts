import { NextRequest, NextResponse } from "next/server"

import {
  computeWebAccessCookieValue,
  getWebAccessPassword,
  normalizeUnlockRedirectPath,
  WEB_ACCESS_COOKIE_MAX_AGE_SECONDS,
  WEB_ACCESS_COOKIE_NAME,
} from "@/lib/web-access"

function buildRedirectUrl(request: NextRequest, path: string): URL {
  const host = String(
    request.headers.get("x-forwarded-host") || request.headers.get("host") || ""
  ).trim()
  const proto = String(
    request.headers.get("x-forwarded-proto") ||
      request.nextUrl.protocol.replace(/:$/, "") ||
      "http"
  ).trim()
  if (host) {
    return new URL(path, `${proto}://${host}`)
  }
  return new URL(path, request.url)
}

export async function POST(request: NextRequest) {
  const formData = await request.formData()
  const nextPath = normalizeUnlockRedirectPath(String(formData.get("next") || "/"))
  const configuredPassword = getWebAccessPassword()

  if (!configuredPassword) {
    return NextResponse.redirect(buildRedirectUrl(request, nextPath), 303)
  }

  const submittedPassword = String(formData.get("password") || "")
  if (submittedPassword !== configuredPassword) {
    const retryUrl = buildRedirectUrl(request, "/unlock")
    retryUrl.searchParams.set("next", nextPath)
    retryUrl.searchParams.set("error", "1")
    return NextResponse.redirect(retryUrl, 303)
  }

  const response = NextResponse.redirect(buildRedirectUrl(request, nextPath), 303)
  response.cookies.set(WEB_ACCESS_COOKIE_NAME, await computeWebAccessCookieValue(configuredPassword), {
    httpOnly: true,
    maxAge: WEB_ACCESS_COOKIE_MAX_AGE_SECONDS,
    path: "/",
    sameSite: "lax",
    secure: request.nextUrl.protocol === "https:",
  })
  return response
}
