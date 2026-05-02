import { NextRequest, NextResponse } from "next/server"

const AUTH_COOKIE_NAME = "access_token"

function withRequestHeaders(request: NextRequest, headers: Headers) {
  return NextResponse.next({
    request: {
      headers,
    },
  })
}

export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl

  // Allow health checks, login/register pages, setup wizard, auth callback, and auth API without auth
  if (
    pathname === "/health" ||
    pathname.startsWith("/login") ||
    pathname.startsWith("/register") ||
    pathname.startsWith("/setup") ||
    pathname.startsWith("/auth/") ||
    pathname.startsWith("/api/v1/auth/") ||
    pathname.startsWith("/api/v1/setup/") ||
    pathname.startsWith("/api/v1/config/")
  ) {
    return NextResponse.next()
  }

  const hasAuthToken = Boolean(request.cookies.get(AUTH_COOKIE_NAME)?.value)

  if (pathname.startsWith("/api/")) {
    // API routes: allow through if user has auth cookie or bearer token
    const apiBearerToken = process.env.API_BEARER_TOKEN
    const hasAuthorizationHeader = request.headers.has("authorization")

    if (hasAuthorizationHeader && apiBearerToken) {
      return NextResponse.next()
    }

    if (!hasAuthToken) {
      return NextResponse.json(
        {
          code: "auth_required",
          message: "Please log in to use the API",
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

  // Page routes: redirect to login if no auth cookie
  if (hasAuthToken) {
    return NextResponse.next()
  }

  const loginUrl = request.nextUrl.clone()
  loginUrl.pathname = "/login"
  loginUrl.search = ""
  loginUrl.searchParams.set(
    "next",
    pathname === "/" ? "" : `${pathname}${search}`
  )
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|txt|xml)$).*)"],
}
