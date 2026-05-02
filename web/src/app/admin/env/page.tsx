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

type EnvVar = {
  key: string
  value: string
  is_sensitive: boolean
}

type EnvVarsResponse = {
  vars: EnvVar[]
  raw: string
}

type EditorMode = "table" | "raw"

export default function AdminEnvPage() {
  const router = useRouter()
  const { user, isLoading: isAuthLoading } = useAuth()

  const [envVars, setEnvVars] = React.useState<EnvVar[]>([])
  const [rawContent, setRawContent] = React.useState("")
  const [isLoading, setIsLoading] = React.useState(true)
  const [isSaving, setIsSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [mode, setMode] = React.useState<EditorMode>("table")
  const [editedValues, setEditedValues] = React.useState<Record<string, string>>({})
  const [editedRaw, setEditedRaw] = React.useState("")
  const [hasChanges, setHasChanges] = React.useState(false)

  React.useEffect(() => {
    if (!isAuthLoading && (!user || !isAdmin(user))) {
      router.replace("/")
    }
  }, [user, isAuthLoading, router])

  const fetchEnv = React.useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await apiFetch("/admin/env")
      if (!response.ok) {
        throw new Error("Failed to fetch env vars")
      }
      const data: EnvVarsResponse = await response.json()
      setEnvVars(data.vars)
      setRawContent(data.raw)
      setEditedRaw(data.raw)
      setEditedValues({})
      setHasChanges(false)
    } catch (e) {
      setError(normalizeFetchError(e, "加载环境变量失败"))
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    if (user && isAdmin(user)) {
      void fetchEnv()
    }
  }, [user, fetchEnv])

  const handleValueChange = React.useCallback((key: string, value: string) => {
    setEditedValues((prev) => ({ ...prev, [key]: value }))
    setHasChanges(true)
  }, [])

  const handleRawChange = React.useCallback((value: string) => {
    setEditedRaw(value)
    setHasChanges(true)
  }, [])

  const handleSave = React.useCallback(async () => {
    setIsSaving(true)
    try {
      let varsToUpdate: Record<string, string>

      if (mode === "table") {
        varsToUpdate = {}
        for (const v of envVars) {
          if (v.key in editedValues) {
            varsToUpdate[v.key] = editedValues[v.key]
          }
        }
        // Include any new keys added in raw mode that aren't in envVars
        for (const [key, value] of Object.entries(editedValues)) {
          if (!(key in varsToUpdate)) {
            varsToUpdate[key] = value
          }
        }
      } else {
        // Parse raw content into key-value pairs
        varsToUpdate = {}
        for (const line of editedRaw.split("\n")) {
          const trimmed = line.trim()
          if (!trimmed || trimmed.startsWith("#")) continue
          const match = trimmed.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/)
          if (match) {
            varsToUpdate[match[1]] = match[2]
          }
        }
      }

      const response = await apiFetch("/admin/env", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vars: varsToUpdate }),
      })

      if (!response.ok) {
        const message = await readResponseErrorMessage(response, "保存失败")
        throw new Error(message)
      }

      const data: EnvVarsResponse = await response.json()
      setEnvVars(data.vars)
      setRawContent(data.raw)
      setEditedRaw(data.raw)
      setEditedValues({})
      setHasChanges(false)
      toast.success("环境变量已保存。重启容器后生效。")
    } catch (e) {
      toast.error(normalizeFetchError(e, "保存失败"))
    } finally {
      setIsSaving(false)
    }
  }, [mode, envVars, editedValues, editedRaw])

  const handleReset = React.useCallback(() => {
    setEditedValues({})
    setEditedRaw(rawContent)
    setHasChanges(false)
  }, [rawContent])

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
              环境变量
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground md:text-[15px]">
              编辑 .env 配置文件。修改后需要重启容器才能生效。
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button type="button" variant="outline" asChild>
                <Link href="/admin">返回用户管理</Link>
              </Button>
              <Button type="button" variant="outline" asChild>
                <Link href="/admin/invites">邀请码管理</Link>
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
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle className="text-[1.3rem]">配置编辑</CardTitle>
                <CardDescription className="mt-1 text-sm leading-6">
                  敏感值（密钥、密码）已隐藏，保存时不会覆盖。
                </CardDescription>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex border border-border">
                  <button
                    type="button"
                    onClick={() => setMode("table")}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                      mode === "table"
                        ? "bg-[#cc0000] text-white"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    键值编辑
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode("raw")}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                      mode === "raw"
                        ? "bg-[#cc0000] text-white"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    原始文本
                  </button>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void fetchEnv()}
                  disabled={isLoading}
                >
                  刷新
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              修改后需重启容器才能生效：{" "}
              <code className="font-mono">docker compose restart api worker</code>
            </div>

            {mode === "table" ? (
              <div className="home-table-shell overflow-x-auto border border-border">
                <table className="w-full min-w-[640px] text-sm">
                  <thead className="bg-muted/25 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3">变量名</th>
                      <th className="px-4 py-3">值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {envVars.length ? (
                      envVars.map((v) => (
                        <tr
                          key={v.key}
                          className="border-t border-border/80 transition-colors hover:bg-muted/20"
                        >
                          <td className="px-4 py-2">
                            <div className="flex items-center gap-2">
                              <code className="font-mono text-xs">{v.key}</code>
                              {v.is_sensitive ? (
                                <Badge variant="outline" className="text-[10px]">
                                  敏感
                                </Badge>
                              ) : null}
                            </div>
                          </td>
                          <td className="px-4 py-2">
                            <Input
                              type={v.is_sensitive ? "password" : "text"}
                              value={
                                v.key in editedValues
                                  ? editedValues[v.key]
                                  : v.value
                              }
                              onChange={(e) =>
                                handleValueChange(v.key, e.target.value)
                              }
                              className="h-8 text-xs"
                              placeholder={v.is_sensitive ? "••••••••" : ""}
                            />
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td
                          colSpan={2}
                          className="px-4 py-10 text-center text-sm text-muted-foreground"
                        >
                          未找到环境变量
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <textarea
                value={editedRaw}
                onChange={(e) => handleRawChange(e.target.value)}
                className="min-h-[500px] w-full border border-border bg-muted/10 p-4 font-mono text-xs leading-relaxed outline-none focus:bg-muted/20"
                spellCheck={false}
              />
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
              <div className="text-xs text-muted-foreground">
                {hasChanges ? "有未保存的修改" : "无修改"}
              </div>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleReset}
                  disabled={!hasChanges || isSaving}
                >
                  重置
                </Button>
                <Button
                  type="button"
                  onClick={handleSave}
                  disabled={!hasChanges || isSaving}
                >
                  {isSaving ? "保存中..." : "保存"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
