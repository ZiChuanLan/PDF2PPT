"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { useAuth } from "@/components/auth-provider"
import { apiFetch, normalizeFetchError } from "@/lib/api"
import { isAdmin, getAvatarUrl, type AdminUser } from "@/lib/auth"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"

type UserDetailPageProps = {
  params: Promise<{ id: string }>
}

export default function UserDetailPage({ params }: UserDetailPageProps) {
  const router = useRouter()
  const { user: currentUser, isLoading: isAuthLoading } = useAuth()
  const [targetUser, setTargetUser] = React.useState<AdminUser | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [isSaving, setIsSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [userId, setUserId] = React.useState<string | null>(null)

  // Form state
  const [dailyTaskLimit, setDailyTaskLimit] = React.useState("10")
  const [maxFileSizeMb, setMaxFileSizeMb] = React.useState("100")
  const [concurrentTaskLimit, setConcurrentTaskLimit] = React.useState("2")
  const [isActive, setIsActive] = React.useState(true)
  const [role, setRole] = React.useState<"user" | "admin">("user")

  // Redirect if not admin
  React.useEffect(() => {
    if (!isAuthLoading && (!currentUser || !isAdmin(currentUser))) {
      router.replace("/")
    }
  }, [currentUser, isAuthLoading, router])

  // Resolve params
  React.useEffect(() => {
    params.then((p) => setUserId(p.id)).catch(() => {})
  }, [params])

  const fetchUser = React.useCallback(async (id: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await apiFetch(`/admin/users/${id}`)
      if (!response.ok) {
        if (response.status === 404) {
          throw new Error("用户不存在")
        }
        throw new Error("Failed to fetch user")
      }
      const data = await response.json().catch(() => null)
      if (data) {
        setTargetUser(data)
        setDailyTaskLimit(String(data.daily_task_limit ?? 10))
        setMaxFileSizeMb(String(data.max_file_size_mb ?? 100))
        setConcurrentTaskLimit(String(data.concurrent_task_limit ?? 2))
        setIsActive(data.active !== false)
        setRole(data.role === "admin" ? "admin" : "user")
      }
    } catch (e) {
      setError(normalizeFetchError(e, "加载用户信息失败"))
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    if (userId && currentUser && isAdmin(currentUser)) {
      void fetchUser(userId)
    }
  }, [userId, currentUser, fetchUser])

  const handleSave = React.useCallback(async () => {
    if (!userId || !targetUser) return

    setIsSaving(true)
    try {
      const payload: Record<string, unknown> = {}

      const parsedDailyLimit = parseInt(dailyTaskLimit, 10)
      if (!isNaN(parsedDailyLimit) && parsedDailyLimit >= 0) {
        payload.daily_task_limit = parsedDailyLimit
      }

      const parsedMaxFileSize = parseFloat(maxFileSizeMb)
      if (!isNaN(parsedMaxFileSize) && parsedMaxFileSize >= 0) {
        payload.max_file_size_mb = parsedMaxFileSize
      }

      const parsedConcurrentLimit = parseInt(concurrentTaskLimit, 10)
      if (!isNaN(parsedConcurrentLimit) && parsedConcurrentLimit >= 0) {
        payload.concurrent_task_limit = parsedConcurrentLimit
      }

      payload.active = isActive
      payload.role = role

      const response = await apiFetch(`/admin/users/${userId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        throw new Error("Failed to update user")
      }

      const data = await response.json().catch(() => null)
      if (data) {
        setTargetUser(data)
        toast.success("用户信息已更新")
      }
    } catch (e) {
      toast.error(normalizeFetchError(e, "更新用户信息失败"))
    } finally {
      setIsSaving(false)
    }
  }, [userId, targetUser, dailyTaskLimit, maxFileSizeMb, concurrentTaskLimit, isActive, role])

  if (isAuthLoading || isLoading) {
    return (
      <div className="min-h-dvh bg-background">
        <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
          <div className="text-sm text-muted-foreground">加载中...</div>
        </div>
      </div>
    )
  }

  if (!currentUser || !isAdmin(currentUser)) {
    return null // Will redirect
  }

  if (error) {
    return (
      <div className="min-h-dvh bg-background">
        <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
          <div className="border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
          <Button
            type="button"
            variant="outline"
            className="mt-4"
            onClick={() => router.push("/admin")}
          >
            返回管理后台
          </Button>
        </div>
      </div>
    )
  }

  if (!targetUser) {
    return null
  }

  return (
    <div className="min-h-dvh bg-background">
      <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
        <header className="editorial-page-header newsprint-texture page-enter border border-border bg-background">
          <div className="px-5 py-5 md:px-6 md:py-6">
            <div className="flex flex-wrap items-center gap-2">
              <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
                管理后台
              </div>
              <Badge variant="outline" className="font-sans text-[11px] uppercase tracking-[0.12em]">
                用户详情
              </Badge>
            </div>
            <h1 className="mt-3 font-serif text-3xl leading-[0.92] tracking-tight md:text-4xl">
              {targetUser.username}
            </h1>
            {targetUser.name ? (
              <p className="mt-2 text-sm text-muted-foreground">{targetUser.name}</p>
            ) : null}
          </div>
        </header>

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Card className="editorial-panel page-enter page-enter-delay-1 border-border">
            <CardHeader className="pb-3">
              <CardTitle>配额设置</CardTitle>
              <CardDescription>调整用户的任务配额和限制。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                    每日任务限制
                  </label>
                  <Input
                    type="number"
                    min="0"
                    value={dailyTaskLimit}
                    onChange={(e) => setDailyTaskLimit(e.target.value)}
                    placeholder="10"
                  />
                  <p className="text-xs text-muted-foreground">
                    每天允许创建的任务数量
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                    最大文件大小 (MB)
                  </label>
                  <Input
                    type="number"
                    min="0"
                    value={maxFileSizeMb}
                    onChange={(e) => setMaxFileSizeMb(e.target.value)}
                    placeholder="100"
                  />
                  <p className="text-xs text-muted-foreground">
                    单个文件的最大大小限制
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                    并发任务限制
                  </label>
                  <Input
                    type="number"
                    min="0"
                    value={concurrentTaskLimit}
                    onChange={(e) => setConcurrentTaskLimit(e.target.value)}
                    placeholder="2"
                  />
                  <p className="text-xs text-muted-foreground">
                    同时进行的任务数量上限
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <label className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                  用户角色
                </label>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant={role === "user" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setRole("user")}
                  >
                    用户
                  </Button>
                  <Button
                    type="button"
                    variant={role === "admin" ? "default" : "outline"}
                    size="sm"
                    onClick={() => setRole("admin")}
                  >
                    管理员
                  </Button>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="user-active"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  className="h-4 w-4 accent-[#111111]"
                />
                <label htmlFor="user-active" className="text-sm">
                  账号启用
                </label>
              </div>

              <div className="flex gap-2 border-t border-border pt-4">
                <Button
                  type="button"
                  onClick={handleSave}
                  disabled={isSaving}
                >
                  {isSaving ? "保存中..." : "保存修改"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => router.push("/admin")}
                >
                  返回列表
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card className="editorial-panel page-enter page-enter-delay-2 border-border">
            <CardHeader className="pb-3">
              <CardTitle>用户信息</CardTitle>
              <CardDescription>LinuxDo 账号基本信息。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {targetUser.avatar_url ? (
                <div className="flex justify-center">
                  <img
                    src={getAvatarUrl(targetUser.avatar_url, 96)}
                    alt={targetUser.username}
                    className="size-20 border border-border"
                    width={80}
                    height={80}
                  />
                </div>
              ) : null}

              <div className="grid gap-2 text-sm">
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground">用户 ID</span>
                  <span className="font-mono">{targetUser.id}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground">LinuxDo ID</span>
                  <span className="font-mono">{targetUser.linuxdo_id}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground">用户名</span>
                  <span>{targetUser.username}</span>
                </div>
                {targetUser.name ? (
                  <div className="flex justify-between gap-2">
                    <span className="text-muted-foreground">显示名</span>
                    <span>{targetUser.name}</span>
                  </div>
                ) : null}
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground">信任等级</span>
                  <span>L{targetUser.trust_level}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground">角色</span>
                  <Badge variant={targetUser.role === "admin" ? "default" : "outline"}>
                    {targetUser.role === "admin" ? "管理员" : "用户"}
                  </Badge>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground">状态</span>
                  <Badge variant={targetUser.active ? "secondary" : "destructive"}>
                    {targetUser.active ? "正常" : "禁用"}
                  </Badge>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-muted-foreground">注册时间</span>
                  <span>
                    {targetUser.created_at
                      ? new Date(targetUser.created_at).toLocaleDateString("zh-CN")
                      : "-"}
                  </span>
                </div>
                {targetUser.last_login_at ? (
                  <div className="flex justify-between gap-2">
                    <span className="text-muted-foreground">最后登录</span>
                    <span>
                      {new Date(targetUser.last_login_at).toLocaleDateString("zh-CN")}
                    </span>
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
