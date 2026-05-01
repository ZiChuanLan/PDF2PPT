"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"

import { useAuth } from "@/components/auth-provider"
import { apiFetch, normalizeFetchError } from "@/lib/api"
import { isAdmin, getAvatarUrl, normalizeUser, type AdminUser, type AdminStats } from "@/lib/auth"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

export default function AdminPage() {
  const router = useRouter()
  const { user, isLoading: isAuthLoading } = useAuth()
  const [users, setUsers] = React.useState<AdminUser[]>([])
  const [stats, setStats] = React.useState<AdminStats | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  // Redirect if not admin
  React.useEffect(() => {
    if (!isAuthLoading && (!user || !isAdmin(user))) {
      router.replace("/")
    }
  }, [user, isAuthLoading, router])

  const fetchAdminData = React.useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [usersResponse, statsResponse] = await Promise.all([
        apiFetch("/admin/users?limit=100"),
        apiFetch("/admin/stats"),
      ])

      if (!usersResponse.ok) {
        throw new Error("Failed to fetch users")
      }
      if (!statsResponse.ok) {
        throw new Error("Failed to fetch stats")
      }

      const usersData = await usersResponse.json().catch(() => null)
      const statsData = await statsResponse.json().catch(() => null)

      if (usersData?.users && Array.isArray(usersData.users)) {
        const normalized = usersData.users
          .map((u: unknown) => normalizeUser(u))
          .filter((u: AdminUser | null): u is AdminUser => u !== null)
        setUsers(normalized)
      }

      if (statsData) {
        setStats(statsData)
      }
    } catch (e) {
      setError(normalizeFetchError(e, "加载管理数据失败"))
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    if (user && isAdmin(user)) {
      void fetchAdminData()
    }
  }, [user, fetchAdminData])

  if (isAuthLoading || isLoading) {
    return (
      <div className="min-h-dvh bg-background">
        <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
          <div className="text-sm text-muted-foreground">加载中...</div>
        </div>
      </div>
    )
  }

  if (!user || !isAdmin(user)) {
    return null // Will redirect
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
                Admin
              </Badge>
            </div>
            <h1 className="mt-3 max-w-4xl font-serif text-4xl leading-[0.92] tracking-tight md:text-6xl">
              用户管理
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground md:text-[15px]">
              管理用户账号、查看使用情况、设置配额限制。
            </p>
          </div>
        </header>

        {error ? (
          <div className="mt-4 border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        {stats ? (
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card className="editorial-panel page-enter page-enter-delay-1 border-border">
              <CardHeader className="pb-2">
                <CardTitle className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                  总用户数
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="font-serif text-3xl">{stats.users.total}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  活跃：{stats.users.active} · 管理员：{stats.users.admins}
                </div>
              </CardContent>
            </Card>

            <Card className="editorial-panel page-enter page-enter-delay-1 border-border">
              <CardHeader className="pb-2">
                <CardTitle className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                  总任务数
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="font-serif text-3xl">{stats.jobs.total}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  排队：{stats.jobs.pending} · 处理中：{stats.jobs.processing}
                </div>
              </CardContent>
            </Card>

            <Card className="editorial-panel page-enter page-enter-delay-2 border-border">
              <CardHeader className="pb-2">
                <CardTitle className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                  完成任务
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="font-serif text-3xl">{stats.jobs.completed}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  成功率：{stats.jobs.total > 0 ? Math.round((stats.jobs.completed / stats.jobs.total) * 100) : 0}%
                </div>
              </CardContent>
            </Card>

            <Card className="editorial-panel page-enter page-enter-delay-2 border-border">
              <CardHeader className="pb-2">
                <CardTitle className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                  失败任务
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="font-serif text-3xl">{stats.jobs.failed}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  失败率：{stats.jobs.total > 0 ? Math.round((stats.jobs.failed / stats.jobs.total) * 100) : 0}%
                </div>
              </CardContent>
            </Card>
          </div>
        ) : null}

        <Card className="editorial-panel page-enter page-enter-delay-2 mt-6 border-border">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="home-section-kicker">用户列表</div>
                <CardTitle className="mt-2 text-[1.3rem]">所有用户</CardTitle>
                <CardDescription className="mt-1 text-sm leading-6">
                  点击用户名查看详细信息和配额设置。
                </CardDescription>
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={() => void fetchAdminData()}
              >
                刷新
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="home-table-shell overflow-x-auto border border-border">
              <table className="w-full min-w-[760px] text-sm">
                <thead className="bg-muted/25 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">用户</th>
                    <th className="px-4 py-3">角色</th>
                    <th className="px-4 py-3">信任等级</th>
                    <th className="px-4 py-3">状态</th>
                    <th className="px-4 py-3">每日限额</th>
                    <th className="px-4 py-3">注册时间</th>
                    <th className="px-4 py-3 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {users.length ? (
                    users.map((u) => (
                      <tr
                        key={u.id}
                        className="motion-row border-t border-border/80 transition-colors hover:bg-muted/20"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            {u.avatar_url ? (
                              <img
                                src={getAvatarUrl(u.avatar_url, 24)}
                                alt={u.username}
                                className="size-6 border border-border"
                                width={24}
                                height={24}
                              />
                            ) : null}
                            <div>
                              <div className="font-medium">{u.username}</div>
                              {u.name ? (
                                <div className="text-xs text-muted-foreground">{u.name}</div>
                              ) : null}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={u.role === "admin" ? "default" : "outline"}>
                            {u.role === "admin" ? "管理员" : "用户"}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">L{u.trust_level}</td>
                        <td className="px-4 py-3">
                          <Badge variant={u.active ? "secondary" : "destructive"}>
                            {u.active ? "正常" : "禁用"}
                          </Badge>
                        </td>
                        <td className="px-4 py-3">{u.daily_task_limit}/天</td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {u.created_at ? new Date(u.created_at).toLocaleDateString("zh-CN") : "-"}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-2">
                            <Button type="button" variant="ghost" size="sm" asChild>
                              <Link href={`/admin/users/${u.id}`}>详情</Link>
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} className="px-4 py-10 text-center text-sm text-muted-foreground">
                        暂无用户
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
