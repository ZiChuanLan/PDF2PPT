"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
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

export default function RegisterPage() {
  const router = useRouter()
  const { user, isLoading, refetch } = useAuth()

  const [inviteCode, setInviteCode] = React.useState("")
  const [username, setUsername] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [confirmPassword, setConfirmPassword] = React.useState("")
  const [isRegistering, setIsRegistering] = React.useState(false)
  const [registerError, setRegisterError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!isLoading && user) {
      router.replace("/")
    }
  }, [user, isLoading, router])

  const handleRegister = React.useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      setRegisterError(null)

      if (!inviteCode.trim()) {
        setRegisterError("请输入邀请码")
        return
      }
      if (!username.trim()) {
        setRegisterError("请输入用户名")
        return
      }
      if (username.trim().length < 3) {
        setRegisterError("用户名至少需要 3 个字符")
        return
      }
      if (username.trim().length > 32) {
        setRegisterError("用户名不能超过 32 个字符")
        return
      }
      if (!password) {
        setRegisterError("请输入密码")
        return
      }
      if (password.length < 6) {
        setRegisterError("密码至少需要 6 个字符")
        return
      }
      if (password !== confirmPassword) {
        setRegisterError("两次输入的密码不一致")
        return
      }

      setIsRegistering(true)
      try {
        const response = await apiFetch("/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            invite_code: inviteCode.trim(),
            username: username.trim(),
            password,
          }),
        })

        if (!response.ok) {
          const message = await readResponseErrorMessage(response, "注册失败")
          throw new Error(message)
        }

        toast.success("注册成功，已自动登录")
        await refetch()
        router.replace("/")
      } catch (e) {
        setRegisterError(e instanceof Error ? e.message : "注册失败")
      } finally {
        setIsRegistering(false)
      }
    },
    [inviteCode, username, password, confirmPassword, refetch, router]
  )

  if (isLoading) {
    return (
      <main className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl items-center justify-center px-4 py-10">
        <div className="text-sm text-muted-foreground">加载中...</div>
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
          <CardTitle>注册新账号</CardTitle>
          <CardDescription>
            使用邀请码注册一个新账号。邀请码由管理员发放。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5 pt-5">
          <form onSubmit={handleRegister} className="space-y-4">
            <div className="space-y-2">
              <label
                htmlFor="register-invite"
                className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
              >
                邀请码
              </label>
              <Input
                id="register-invite"
                type="text"
                placeholder="请输入邀请码"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                disabled={isRegistering}
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="register-username"
                className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
              >
                用户名
              </label>
              <Input
                id="register-username"
                type="text"
                placeholder="3-32 个字符"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                disabled={isRegistering}
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="register-password"
                className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
              >
                密码
              </label>
              <Input
                id="register-password"
                type="password"
                placeholder="至少 6 个字符"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                disabled={isRegistering}
              />
            </div>
            <div className="space-y-2">
              <label
                htmlFor="register-confirm-password"
                className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
              >
                确认密码
              </label>
              <Input
                id="register-confirm-password"
                type="password"
                placeholder="再次输入密码"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                disabled={isRegistering}
              />
            </div>

            {registerError ? (
              <p className="text-xs text-destructive">{registerError}</p>
            ) : null}

            <Button type="submit" disabled={isRegistering} className="w-full">
              {isRegistering ? "注册中..." : "注册"}
            </Button>

            <p className="text-center text-xs text-muted-foreground">
              已有账号？{" "}
              <Link href="/login" className="underline hover:text-foreground">
                去登录
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
