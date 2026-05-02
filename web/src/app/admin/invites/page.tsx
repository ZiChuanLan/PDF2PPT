"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { useAuth } from "@/components/auth-provider"
import { apiFetch, normalizeFetchError, readResponseErrorMessage } from "@/lib/api"
import { isAdmin } from "@/lib/auth"
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

type InviteCode = {
  id: number
  code: string
  created_by: number
  used_by: number | null
  is_used: boolean
  expires_at: string | null
  created_at: string
}

export default function AdminInvitesPage() {
  const router = useRouter()
  const { user, isLoading: isAuthLoading } = useAuth()

  const [invites, setInvites] = React.useState<InviteCode[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [isGenerating, setIsGenerating] = React.useState(false)
  const [expiresDays, setExpiresDays] = React.useState("7")
  const [lastGeneratedCode, setLastGeneratedCode] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (!isAuthLoading && (!user || !isAdmin(user))) {
      router.replace("/")
    }
  }, [user, isAuthLoading, router])

  const fetchInvites = React.useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await apiFetch("/admin/invites?limit=100")
      if (!response.ok) {
        throw new Error("Failed to fetch invite codes")
      }
      const data = await response.json().catch(() => null)
      if (data?.invites && Array.isArray(data.invites)) {
        setInvites(data.invites)
      }
    } catch (e) {
      setError(normalizeFetchError(e, "加载邀请码列表失败"))
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    if (user && isAdmin(user)) {
      void fetchInvites()
    }
  }, [user, fetchInvites])

  const handleGenerate = React.useCallback(async () => {
    setIsGenerating(true)
    setLastGeneratedCode(null)
    try {
      const days = parseInt(expiresDays, 10)
      const body: Record<string, unknown> = {}
      if (!isNaN(days) && days > 0) {
        body.expires_in_days = days
      }

      const response = await apiFetch("/admin/invites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        const message = await readResponseErrorMessage(response, "生成邀请码失败")
        throw new Error(message)
      }

      const data = await response.json().catch(() => null)
      const code = data?.code
      if (code) {
        setLastGeneratedCode(code)
        toast.success("邀请码已生成")
        void fetchInvites()
      }
    } catch (e) {
      toast.error(normalizeFetchError(e, "生成邀请码失败"))
    } finally {
      setIsGenerating(false)
    }
  }, [expiresDays, fetchInvites])

  const handleCopyCode = React.useCallback((code: string) => {
    navigator.clipboard.writeText(code).then(() => {
      toast.success("已复制到剪贴板")
    })
  }, [])

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
                Admin
              </Badge>
            </div>
            <h1 className="mt-3 max-w-4xl font-serif text-4xl leading-[0.92] tracking-tight md:text-6xl">
              邀请码管理
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground md:text-[15px]">
              生成和管理注册邀请码。用户使用邀请码注册新账号。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button type="button" variant="outline" asChild>
                <Link href="/admin">返回用户管理</Link>
              </Button>
            </div>
          </div>
        </header>

        {error ? (
          <div className="mt-4 border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}

        <Card className="editorial-panel page-enter page-enter-delay-1 mt-6 border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-[1.3rem]">生成邀请码</CardTitle>
            <CardDescription className="mt-1 text-sm leading-6">
              生成一个新的邀请码，可设置有效期。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-2">
                <label
                  htmlFor="expires-days"
                  className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
                >
                  有效期（天）
                </label>
                <Input
                  id="expires-days"
                  type="number"
                  min="1"
                  max="365"
                  value={expiresDays}
                  onChange={(e) => setExpiresDays(e.target.value)}
                  className="w-32"
                  disabled={isGenerating}
                />
              </div>
              <Button
                type="button"
                onClick={handleGenerate}
                disabled={isGenerating}
              >
                {isGenerating ? "生成中..." : "生成邀请码"}
              </Button>
            </div>

            {lastGeneratedCode ? (
              <div className="flex items-center gap-3 rounded-md border border-border bg-muted/30 px-4 py-3">
                <code className="font-mono text-sm">{lastGeneratedCode}</code>
                <Button
                  type="button"
                  variant="outline"
                  size="xs"
                  onClick={() => handleCopyCode(lastGeneratedCode)}
                >
                  复制
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="editorial-panel page-enter page-enter-delay-2 mt-6 border-border">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="home-section-kicker">邀请码列表</div>
                <CardTitle className="mt-2 text-[1.3rem]">所有邀请码</CardTitle>
                <CardDescription className="mt-1 text-sm leading-6">
                  查看所有已生成的邀请码及其使用状态。
                </CardDescription>
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={() => void fetchInvites()}
              >
                刷新
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="home-table-shell overflow-x-auto border border-border">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="bg-muted/25 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3">邀请码</th>
                    <th className="px-4 py-3">状态</th>
                    <th className="px-4 py-3">过期时间</th>
                    <th className="px-4 py-3">创建时间</th>
                    <th className="px-4 py-3 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {invites.length ? (
                    invites.map((inv) => (
                      <tr
                        key={inv.id}
                        className="motion-row border-t border-border/80 transition-colors hover:bg-muted/20"
                      >
                        <td className="px-4 py-3">
                          <code className="font-mono text-xs">{inv.code}</code>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={inv.is_used ? "secondary" : "outline"}>
                            {inv.is_used ? "已使用" : "未使用"}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {inv.expires_at
                            ? new Date(inv.expires_at).toLocaleDateString("zh-CN")
                            : "永不过期"}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {inv.created_at
                            ? new Date(inv.created_at).toLocaleDateString("zh-CN")
                            : "-"}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-2">
                            {!inv.is_used ? (
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleCopyCode(inv.code)}
                              >
                                复制
                              </Button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="px-4 py-10 text-center text-sm text-muted-foreground">
                        暂无邀请码
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
