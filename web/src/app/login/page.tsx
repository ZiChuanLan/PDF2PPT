"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { useAuth } from "@/components/auth-provider"
import { apiFetch } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

export default function LoginPage() {
  const router = useRouter()
  const { user, isLoading } = useAuth()
  const [isRedirecting, setIsRedirecting] = React.useState(false)

  // Redirect if already logged in
  React.useEffect(() => {
    if (!isLoading && user) {
      router.replace("/")
    }
  }, [user, isLoading, router])

  const handleLogin = React.useCallback(async () => {
    setIsRedirecting(true)
    try {
      const response = await apiFetch("/auth/login")
      if (!response.ok) {
        throw new Error("Failed to initiate login")
      }
      const data = await response.json().catch(() => null)
      const authorizeUrl = data?.authorize_url
      if (!authorizeUrl || typeof authorizeUrl !== "string") {
        throw new Error("Invalid login response")
      }
      // Redirect to LinuxDo authorization page
      // (state is validated server-side by the backend)
      window.location.href = authorizeUrl
    } catch (e) {
      const message = e instanceof Error ? e.message : "登录失败"
      toast.error(message)
      setIsRedirecting(false)
    }
  }, [])

  if (isLoading) {
    return (
      <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl items-center justify-center px-4 py-10">
        <div className="text-sm text-muted-foreground">加载中...</div>
      </main>
    )
  }

  if (user) {
    return null // Will redirect
  }

  return (
    <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl items-center justify-center px-4 py-10">
      <Card className="w-full max-w-xl border-border bg-background/95 backdrop-blur">
        <CardHeader className="border-b border-border">
          <CardTitle>用户登录</CardTitle>
          <CardDescription>
            使用 LinuxDo 账号登录以访问工作台。登录后可以创建和管理您的转换任务。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5 pt-5">
          <div className="space-y-4">
            <p className="text-sm leading-6 text-muted-foreground">
              点击下方按钮将跳转到 LinuxDo 授权页面。授权完成后会自动返回工作台。
            </p>

            <Button
              type="button"
              onClick={handleLogin}
              disabled={isRedirecting}
              className="w-full"
            >
              {isRedirecting ? "正在跳转..." : "使用 LinuxDo 登录"}
            </Button>

            <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              <p>LinuxDo 是一个技术社区，登录即表示您同意授权本应用访问您的基本信息（用户名、头像）。</p>
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
        </CardContent>
      </Card>
    </main>
  )
}
