"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense } from "react"
import { toast } from "sonner"

import { useAuth } from "@/components/auth-provider"
import { apiFetch, readResponseErrorMessage } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"

type LoginTab = "password" | "linuxdo"

const ERROR_MESSAGES: Record<string, string> = {
  missing_params: "授权回调参数缺失，请重试。",
  no_token: "授权成功但未获取到令牌，请重试。",
  network_error: "网络错误，无法连接授权服务器。",
  invalid_state: "授权状态验证失败，请重试。",
  auth_failed: "授权失败，请重试。",
}

export default function LoginPage() {
  return (
    <Suspense fallback={<LoginLoading />}>
      <LoginForm />
    </Suspense>
  )
}

function LoginLoading() {
  return (
    <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl items-center justify-center px-4 py-10">
      <div className="text-sm text-muted-foreground">加载中...</div>
    </main>
  )
}

function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, isLoading, refetch } = useAuth()
  const [activeTab, setActiveTab] = React.useState<LoginTab>("password")
  const [isRedirecting, setIsRedirecting] = React.useState(false)
  const [isAutoLoggingIn, setIsAutoLoggingIn] = React.useState(false)
  const [deployMode, setDeployMode] = React.useState<string>("self")

  const [username, setUsername] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [isLoggingIn, setIsLoggingIn] = React.useState(false)
  const [loginError, setLoginError] = React.useState<string | null>(null)

  const callbackError = searchParams.get("error")
  const callbackErrorMessage = callbackError
    ? ERROR_MESSAGES[callbackError] ?? `登录失败：${callbackError}`
    : null

  // Fetch deploy mode on mount
  React.useEffect(() => {
    if (isLoading || user) return

    void (async () => {
      try {
        const configRes = await apiFetch("/config/deploy-mode")
        if (configRes.ok) {
          const config = await configRes.json().catch(() => null)
          if (config?.mode) setDeployMode(config.mode)
        }
      } catch {
        // Ignore - default to self
      }
    })()
  }, [isLoading, user])

  // Auto-login for self-mode
  React.useEffect(() => {
    if (isLoading || user) return

    const tryAutoLogin = async () => {
      try {
        // If user manually logged out, skip auto-login
        if (localStorage.getItem("userLoggedOut") === "true") {
          return
        }

        // First check if setup is needed
        const setupRes = await apiFetch("/setup/status")
        if (setupRes.ok) {
          const setupData = await setupRes.json().catch(() => null)
          if (setupData?.needs_setup === true) {
            router.replace("/setup")
            return
          }
        }

        const configRes = await apiFetch("/config/deploy-mode")
        if (!configRes.ok) return
        const config = await configRes.json().catch(() => null)
        if (config?.mode !== "self") return

        setIsAutoLoggingIn(true)
        const loginRes = await apiFetch("/auth/auto-login", { method: "POST" })
        if (!loginRes.ok) return
        const data = await loginRes.json().catch(() => null)
        if (data?.user) {
          localStorage.removeItem("userLoggedOut")
          await refetch()
          const next = searchParams.get("next")
          router.replace(next || "/")
        }
      } catch {
        // Ignore - show normal login form
      } finally {
        setIsAutoLoggingIn(false)
      }
    }

    void tryAutoLogin()
  }, [isLoading, user, refetch, router, searchParams])

  React.useEffect(() => {
    if (!isLoading && user) {
      const next = searchParams.get("next")
      router.replace(next || "/")
    }
  }, [user, isLoading, router, searchParams])

  // Force password tab in self mode
  React.useEffect(() => {
    if (deployMode === "self" && activeTab === "linuxdo") {
      setActiveTab("password")
    }
  }, [deployMode, activeTab])

  const handlePasswordLogin = React.useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      setLoginError(null)

      if (!username.trim() || !password) {
        setLoginError("请输入用户名和密码")
        return
      }

      setIsLoggingIn(true)
      try {
        const response = await apiFetch("/auth/login-password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: username.trim(),
            password,
          }),
        })

        if (!response.ok) {
          const message = await readResponseErrorMessage(response, "登录失败")
          throw new Error(message)
        }

        toast.success("登录成功")
        localStorage.removeItem("userLoggedOut")
        await refetch()
        router.replace("/")
      } catch (e) {
        setLoginError(e instanceof Error ? e.message : "登录失败")
      } finally {
        setIsLoggingIn(false)
      }
    },
    [username, password, refetch, router]
  )

  const handleLinuxdoLogin = React.useCallback(async () => {
    setIsRedirecting(true)
    try {
      const origin = window.location.origin
      const response = await apiFetch(
        `/auth/login?origin=${encodeURIComponent(origin)}`
      )
      if (!response.ok) {
        throw new Error("Failed to initiate login")
      }
      const data = await response.json().catch(() => null)
      const authorizeUrl = data?.authorize_url
      if (!authorizeUrl || typeof authorizeUrl !== "string") {
        throw new Error("Invalid login response")
      }
      window.location.href = authorizeUrl
    } catch (e) {
      const message = e instanceof Error ? e.message : "登录失败"
      toast.error(message)
      setIsRedirecting(false)
    }
  }, [])

  if (isLoading || isAutoLoggingIn) {
    return (
      <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl items-center justify-center px-4 py-10">
        <div className="text-sm text-muted-foreground">
          {isAutoLoggingIn ? "正在自动登录..." : "加载中..."}
        </div>
      </main>
    )
  }

  if (user) {
    return null
  }

  return (
    <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl items-center justify-center px-4 py-10">
      <Card className="w-full max-w-xl border-border bg-background/95 backdrop-blur">
        <CardHeader className="border-b border-border">
          <CardTitle>用户登录</CardTitle>
          <CardDescription>
            使用账号密码或 LinuxDo 账号登录以访问工作台。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5 pt-5">
          {callbackErrorMessage ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {callbackErrorMessage}
            </div>
          ) : null}
          <div className="flex border-b border-border">
            <button
              type="button"
              onClick={() => setActiveTab("password")}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === "password"
                  ? "border-b-2 border-[#cc0000] text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              密码登录
            </button>
            {deployMode === "public" && (
              <button
                type="button"
                onClick={() => setActiveTab("linuxdo")}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  activeTab === "linuxdo"
                    ? "border-b-2 border-[#cc0000] text-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                LinuxDo 登录
              </button>
            )}
          </div>

          {activeTab === "password" ? (
            <form onSubmit={handlePasswordLogin} className="space-y-4">
              <div className="space-y-2">
                <label
                  htmlFor="login-username"
                  className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
                >
                  用户名
                </label>
                <Input
                  id="login-username"
                  type="text"
                  placeholder="请输入用户名"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  disabled={isLoggingIn}
                />
              </div>
              <div className="space-y-2">
                <label
                  htmlFor="login-password"
                  className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
                >
                  密码
                </label>
                <Input
                  id="login-password"
                  type="password"
                  placeholder="请输入密码"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  disabled={isLoggingIn}
                />
              </div>

              {loginError ? (
                <p className="text-xs text-destructive">{loginError}</p>
              ) : null}

              <Button type="submit" disabled={isLoggingIn} className="w-full">
                {isLoggingIn ? "登录中..." : "登录"}
              </Button>

              {deployMode === "public" && (
                <p className="text-center text-xs text-muted-foreground">
                  还没有账号？{" "}
                  <Link
                    href="/register"
                    className="underline hover:text-foreground"
                  >
                    注册新账号
                  </Link>
                </p>
              )}
            </form>
          ) : (
            <div className="space-y-4">
              <p className="text-sm leading-6 text-muted-foreground">
                点击下方按钮将跳转到 LinuxDo 授权页面。授权完成后会自动返回工作台。
              </p>

              <Button
                type="button"
                onClick={handleLinuxdoLogin}
                disabled={isRedirecting}
                className="w-full"
              >
                {isRedirecting ? "正在跳转..." : "使用 LinuxDo 登录"}
              </Button>

              <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                <p>
                  LinuxDo 是一个技术社区，登录即表示您同意授权本应用访问您的基本信息（用户名、头像）。
                </p>
                <p className="mt-1">
                  还没有账号？前往{" "}
                  <a
                    href="https://linux.do"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline hover:text-foreground"
                  >
                    linux.do
                  </a>{" "}
                  注册。
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
