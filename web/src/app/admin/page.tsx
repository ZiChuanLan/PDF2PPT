"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"

import { useAuth } from "@/components/auth-provider"
import { apiFetch, normalizeFetchError } from "@/lib/api"
import { isAdmin, getAvatarUrl, normalizeUser, type AdminUser, type AdminStats } from "@/lib/auth"
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

export default function AdminPage() {
  const router = useRouter()
  const { user, isLoading: isAuthLoading } = useAuth()
  const [users, setUsers] = React.useState<AdminUser[]>([])
  const [stats, setStats] = React.useState<AdminStats | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  // Selection state
  const [selectedIds, setSelectedIds] = React.useState<Set<number>>(new Set())
  const [isDeleting, setIsDeleting] = React.useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = React.useState(false)

  // Add user state
  const [showAddUser, setShowAddUser] = React.useState(false)
  const [addUsername, setAddUsername] = React.useState("")
  const [addPassword, setAddPassword] = React.useState("")
  const [addRole, setAddRole] = React.useState<"user" | "admin">("user")
  const [isAdding, setIsAdding] = React.useState(false)

  // Reset password state
  const [resetPasswordUserId, setResetPasswordUserId] = React.useState<number | null>(null)
  const [resetPasswordUsername, setResetPasswordUsername] = React.useState("")
  const [resetNewPassword, setResetNewPassword] = React.useState("")
  const [isResetting, setIsResetting] = React.useState(false)

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

  const toggleSelect = React.useCallback((userId: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(userId)) {
        next.delete(userId)
      } else {
        next.add(userId)
      }
      return next
    })
  }, [])

  const toggleSelectAll = React.useCallback(() => {
    setSelectedIds((prev) => {
      if (prev.size === users.length) {
        return new Set()
      }
      return new Set(users.map((u) => u.id))
    })
  }, [users])

  const handleBatchDelete = React.useCallback(async () => {
    if (selectedIds.size === 0) return
    setIsDeleting(true)
    try {
      const response = await apiFetch("/admin/users/batch-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_ids: Array.from(selectedIds) }),
      })
      if (!response.ok) {
        throw new Error("Failed to delete users")
      }
      const data = await response.json().catch(() => null)
      toast.success(`已禁用 ${data?.deleted ?? 0} 个用户${data?.skipped ? `（跳过 ${data.skipped} 个）` : ""}`)
      setSelectedIds(new Set())
      setShowDeleteConfirm(false)
      void fetchAdminData()
    } catch (e) {
      toast.error(normalizeFetchError(e, "批量删除失败"))
    } finally {
      setIsDeleting(false)
    }
  }, [selectedIds, fetchAdminData])

  const handleAddUser = React.useCallback(async () => {
    if (!addUsername.trim() || !addPassword.trim()) {
      toast.error("用户名和密码不能为空")
      return
    }
    setIsAdding(true)
    try {
      const response = await apiFetch("/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: addUsername.trim(),
          password: addPassword,
          role: addRole,
        }),
      })
      if (!response.ok) {
        const errBody = await response.json().catch(() => null)
        throw new Error(errBody?.message || "Failed to create user")
      }
      toast.success(`用户 ${addUsername.trim()} 创建成功`)
      setAddUsername("")
      setAddPassword("")
      setAddRole("user")
      setShowAddUser(false)
      void fetchAdminData()
    } catch (e) {
      toast.error(normalizeFetchError(e, "创建用户失败"))
    } finally {
      setIsAdding(false)
    }
  }, [addUsername, addPassword, addRole, fetchAdminData])

  const handleResetPassword = React.useCallback(async () => {
    if (!resetPasswordUserId || !resetNewPassword.trim()) {
      toast.error("请输入新密码")
      return
    }

    if (resetNewPassword.length < 8) {
      toast.error("密码至少需要 8 个字符")
      return
    }

    setIsResetting(true)
    try {
      const response = await apiFetch(`/admin/users/${resetPasswordUserId}/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: resetNewPassword }),
      })

      if (!response.ok) {
        const errBody = await response.json().catch(() => null)
        throw new Error(errBody?.message || "重置密码失败")
      }

      toast.success(`用户 ${resetPasswordUsername} 的密码已重置`)
      setResetPasswordUserId(null)
      setResetPasswordUsername("")
      setResetNewPassword("")
    } catch (e) {
      toast.error(normalizeFetchError(e, "重置密码失败"))
    } finally {
      setIsResetting(false)
    }
  }, [resetPasswordUserId, resetPasswordUsername, resetNewPassword])

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
            <div className="mt-4 flex flex-wrap gap-2">
              <Button type="button" variant="outline" asChild>
                <Link href="/admin/invites">邀请码管理</Link>
              </Button>
              <Button type="button" variant="outline" asChild>
                <Link href="/admin/env">环境变量</Link>
              </Button>
              <Button type="button" variant="outline" asChild>
                <Link href="/">返回首页</Link>
              </Button>
            </div>
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

        {/* Site Settings Section */}
        <Card className="editorial-panel page-enter page-enter-delay-2 mt-6 border-border">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="home-section-kicker">站点配置</div>
                <CardTitle className="mt-2 text-[1.3rem]">全局设置</CardTitle>
                <CardDescription className="mt-1 text-sm leading-6">
                  配置 API 密钥和默认参数，所有用户共享。
                </CardDescription>
              </div>
              <Button type="button" variant="outline" asChild>
                <Link href="/admin/site-settings">编辑配置</Link>
              </Button>
            </div>
          </CardHeader>
        </Card>

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
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowAddUser(!showAddUser)}
                >
                  {showAddUser ? "取消" : "添加用户"}
                </Button>
                {selectedIds.size > 0 && (
                  <Button
                    type="button"
                    variant="destructive"
                    onClick={() => setShowDeleteConfirm(true)}
                  >
                    批量删除 ({selectedIds.size})
                  </Button>
                )}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void fetchAdminData()}
                >
                  刷新
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {showAddUser && (
              <div className="mb-4 border border-border p-4">
                <div className="text-sm font-medium mb-3">添加新用户</div>
                <div className="flex flex-wrap items-end gap-3">
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">用户名</label>
                    <Input
                      value={addUsername}
                      onChange={(e) => setAddUsername(e.target.value)}
                      placeholder="username"
                      className="w-40"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">密码</label>
                    <Input
                      type="password"
                      value={addPassword}
                      onChange={(e) => setAddPassword(e.target.value)}
                      placeholder="password"
                      className="w-40"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground mb-1 block">角色</label>
                    <select
                      value={addRole}
                      onChange={(e) => setAddRole(e.target.value as "user" | "admin")}
                      className="h-9 border border-input bg-background px-3 text-sm"
                    >
                      <option value="user">用户</option>
                      <option value="admin">管理员</option>
                    </select>
                  </div>
                  <Button
                    type="button"
                    onClick={() => void handleAddUser()}
                    disabled={isAdding}
                  >
                    {isAdding ? "创建中..." : "确认创建"}
                  </Button>
                </div>
              </div>
            )}

            {showDeleteConfirm && (
              <div className="mb-4 border border-destructive/30 bg-destructive/10 p-4">
                <div className="text-sm text-destructive font-medium">
                  确认禁用 {selectedIds.size} 个用户？此操作将把这些用户设为禁用状态。
                </div>
                <div className="mt-3 flex gap-2">
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    onClick={() => void handleBatchDelete()}
                    disabled={isDeleting}
                  >
                    {isDeleting ? "处理中..." : "确认禁用"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setShowDeleteConfirm(false)}
                  >
                    取消
                  </Button>
                </div>
              </div>
            )}

            <div className="home-table-shell overflow-x-auto border border-border">
              <table className="w-full min-w-[760px] text-sm">
                <thead className="bg-muted/25 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 w-10">
                      <input
                        type="checkbox"
                        checked={users.length > 0 && selectedIds.size === users.length}
                        onChange={toggleSelectAll}
                        className="size-3.5"
                      />
                    </th>
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
                          <input
                            type="checkbox"
                            checked={selectedIds.has(u.id)}
                            onChange={() => toggleSelect(u.id)}
                            className="size-3.5"
                          />
                        </td>
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
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setResetPasswordUserId(u.id)
                                setResetPasswordUsername(u.username)
                                setResetNewPassword("")
                              }}
                            >
                              重置密码
                            </Button>
                            <Button type="button" variant="ghost" size="sm" asChild>
                              <Link href={`/admin/users/${u.id}`}>详情</Link>
                            </Button>
                          </div>
                        </td>
                       </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={8} className="px-4 py-10 text-center text-sm text-muted-foreground">
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

      {/* Reset Password Dialog */}
      {resetPasswordUserId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="w-full max-w-md border border-border bg-background p-6 shadow-lg">
            <h2 className="font-serif text-xl font-semibold">重置密码</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              为用户 <span className="font-mono font-medium">{resetPasswordUsername}</span> 设置新密码
            </p>
            <div className="mt-4 space-y-4">
              <div className="space-y-2">
                <label className="text-sm text-muted-foreground" htmlFor="reset-new-password">
                  新密码
                </label>
                <Input
                  id="reset-new-password"
                  type="password"
                  placeholder="请输入新密码（至少 8 个字符）"
                  value={resetNewPassword}
                  onChange={(e) => setResetNewPassword(e.target.value)}
                  disabled={isResetting}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setResetPasswordUserId(null)
                    setResetPasswordUsername("")
                    setResetNewPassword("")
                  }}
                  disabled={isResetting}
                >
                  取消
                </Button>
                <Button
                  type="button"
                  onClick={handleResetPassword}
                  disabled={isResetting}
                >
                  {isResetting ? "重置中..." : "确认重置"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
