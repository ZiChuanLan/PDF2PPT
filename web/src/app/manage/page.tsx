"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { KeyRoundIcon, UserIcon } from "lucide-react"

import { useAuth } from "@/components/auth-provider"
import { apiFetch } from "@/lib/api"
import { isAdmin } from "@/lib/auth"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { toast } from "sonner"

export default function ManagePage() {
  const router = useRouter()
  const { user, isLoading: isAuthLoading } = useAuth()

  // Password change state
  const [currentPassword, setCurrentPassword] = React.useState("")
  const [newPassword, setNewPassword] = React.useState("")
  const [confirmPassword, setConfirmPassword] = React.useState("")
  const [isChangingPassword, setIsChangingPassword] = React.useState(false)
  const [passwordError, setPasswordError] = React.useState<string | null>(null)

  // Redirect if not authenticated
  React.useEffect(() => {
    if (!isAuthLoading && !user) {
      router.replace("/login")
    }
  }, [user, isAuthLoading, router])

  const handleChangePassword = React.useCallback(async () => {
    setPasswordError(null)

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError("请填写所有密码字段")
      return
    }

    if (newPassword !== confirmPassword) {
      setPasswordError("新密码与确认密码不一致")
      return
    }

    if (newPassword.length < 8) {
      setPasswordError("新密码至少需要 8 个字符")
      return
    }

    setIsChangingPassword(true)
    try {
      const response = await apiFetch("/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          old_password: currentPassword,
          new_password: newPassword,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => null)
        throw new Error(errorData?.message || "修改密码失败")
      }

      toast.success("密码修改成功")
      setCurrentPassword("")
      setNewPassword("")
      setConfirmPassword("")
    } catch (e) {
      setPasswordError(e instanceof Error ? e.message : "修改密码失败")
    } finally {
      setIsChangingPassword(false)
    }
  }, [currentPassword, newPassword, confirmPassword])

  if (isAuthLoading) {
    return (
      <div className="min-h-dvh bg-background">
        <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
          <div className="text-sm text-muted-foreground">加载中...</div>
        </div>
      </div>
    )
  }

  if (!user) {
    return null // Will redirect
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "未知"
    try {
      return new Date(dateStr).toLocaleString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    } catch {
      return dateStr
    }
  }

  return (
    <div className="min-h-dvh bg-background">
      <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
        <header className="editorial-page-header newsprint-texture page-enter border border-border bg-background">
          <div className="px-5 py-5 md:px-6 md:py-6">
            <div className="flex flex-wrap items-center gap-2">
              <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                个人中心
              </div>
              <Badge variant="outline" className="font-sans text-[11px] uppercase tracking-[0.12em]">
                Manage
              </Badge>
            </div>
            <h1 className="mt-3 max-w-4xl font-serif text-4xl leading-[0.92] tracking-tight md:text-6xl">
              账号管理
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground md:text-[15px]">
              查看账号信息、修改密码。
            </p>
          </div>
        </header>

        <div className="mt-6 grid gap-6 md:grid-cols-2">
          {/* Account Info Card */}
          <Card className="border border-border">
            <CardHeader>
              <div className="flex items-center gap-2">
                <UserIcon className="size-5 text-muted-foreground" />
                <CardTitle>账号信息</CardTitle>
              </div>
              <CardDescription>当前登录账号的基本信息</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-border/50 pb-3">
                  <span className="text-sm text-muted-foreground">用户名</span>
                  <span className="font-mono text-sm font-medium">{user.username}</span>
                </div>
                {user.name ? (
                  <div className="flex items-center justify-between border-b border-border/50 pb-3">
                    <span className="text-sm text-muted-foreground">昵称</span>
                    <span className="text-sm">{user.name}</span>
                  </div>
                ) : null}
                <div className="flex items-center justify-between border-b border-border/50 pb-3">
                  <span className="text-sm text-muted-foreground">角色</span>
                  <Badge variant={isAdmin(user) ? "default" : "outline"}>
                    {isAdmin(user) ? "管理员" : "用户"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between border-b border-border/50 pb-3">
                  <span className="text-sm text-muted-foreground">每日任务限制</span>
                  <span className="text-sm">{user.daily_task_limit} 个</span>
                </div>
                <div className="flex items-center justify-between border-b border-border/50 pb-3">
                  <span className="text-sm text-muted-foreground">最大文件大小</span>
                  <span className="text-sm">{user.max_file_size_mb} MB</span>
                </div>
                <div className="flex items-center justify-between border-b border-border/50 pb-3">
                  <span className="text-sm text-muted-foreground">并发任务限制</span>
                  <span className="text-sm">{user.concurrent_task_limit} 个</span>
                </div>
                <div className="flex items-center justify-between border-b border-border/50 pb-3">
                  <span className="text-sm text-muted-foreground">注册时间</span>
                  <span className="text-sm">{formatDate(user.created_at)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">最后登录</span>
                  <span className="text-sm">{formatDate(user.last_login_at)}</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Change Password Card */}
          <Card className="border border-border">
            <CardHeader>
              <div className="flex items-center gap-2">
                <KeyRoundIcon className="size-5 text-muted-foreground" />
                <CardTitle>修改密码</CardTitle>
              </div>
              <CardDescription>修改当前账号的登录密码</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm text-muted-foreground" htmlFor="current-password">
                    当前密码
                  </label>
                  <Input
                    id="current-password"
                    type="password"
                    placeholder="请输入当前密码"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    disabled={isChangingPassword}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-muted-foreground" htmlFor="new-password">
                    新密码
                  </label>
                  <Input
                    id="new-password"
                    type="password"
                    placeholder="请输入新密码（至少 8 个字符）"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    disabled={isChangingPassword}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-muted-foreground" htmlFor="confirm-password">
                    确认新密码
                  </label>
                  <Input
                    id="confirm-password"
                    type="password"
                    placeholder="请再次输入新密码"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    disabled={isChangingPassword}
                  />
                </div>
                {passwordError && (
                  <div className="text-sm text-destructive">{passwordError}</div>
                )}
                <Button
                  onClick={handleChangePassword}
                  disabled={isChangingPassword}
                  className="w-full"
                >
                  {isChangingPassword ? "修改中..." : "修改密码"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
