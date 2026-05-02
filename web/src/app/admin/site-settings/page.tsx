"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"

import { useAuth } from "@/components/auth-provider"
import { apiFetch, normalizeFetchError } from "@/lib/api"
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

// API key fields that should be masked
const SENSITIVE_KEYS = new Set([
  "openai_api_key",
  "siliconflow_api_key",
  "claude_api_key",
  "mineru_api_token",
  "ocr_baidu_api_key",
  "ocr_baidu_secret_key",
  "ocr_ai_api_key",
])

type SiteSettings = Record<string, string | null>

export default function SiteSettingsPage() {
  const router = useRouter()
  const { user, isLoading: isAuthLoading } = useAuth()
  const [settings, setSettings] = React.useState<SiteSettings>({})
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [isSaving, setIsSaving] = React.useState(false)

  // Redirect if not admin
  React.useEffect(() => {
    if (!isAuthLoading && (!user || !isAdmin(user))) {
      router.replace("/")
    }
  }, [user, isAuthLoading, router])

  // Fetch site settings
  React.useEffect(() => {
    if (!user || !isAdmin(user)) return

    let mounted = true
    void (async () => {
      try {
        const res = await apiFetch("/admin/site-settings")
        if (!res.ok) {
          throw new Error("Failed to fetch site settings")
        }
        const data = await res.json().catch(() => ({}))
        if (mounted) setSettings(data)
      } catch (e) {
        if (mounted) setError(normalizeFetchError(e, "加载站点配置失败"))
      } finally {
        if (mounted) setIsLoading(false)
      }
    })()

    return () => { mounted = false }
  }, [user])

  const handleSave = React.useCallback(async () => {
    setIsSaving(true)
    try {
      const res = await apiFetch("/admin/site-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings }),
      })
      if (!res.ok) {
        throw new Error("Failed to save")
      }
      toast.success("配置已保存")
    } catch (e) {
      toast.error(normalizeFetchError(e, "保存失败"))
    } finally {
      setIsSaving(false)
    }
  }, [settings])

  const handleChange = React.useCallback((key: string, value: string) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }, [])

  const currentDeployMode = settings["deploy_mode"] || "self"

  if (isAuthLoading || isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-muted-foreground">加载中...</div>
      </div>
    )
  }

  if (!user || !isAdmin(user)) {
    return null
  }

  // Group settings by category
  const apiKeys = [
    { key: "openai_api_key", label: "OpenAI API Key", placeholder: "sk-..." },
    { key: "openai_base_url", label: "OpenAI Base URL", placeholder: "https://api.openai.com/v1" },
    { key: "openai_model", label: "OpenAI Model", placeholder: "gpt-4o" },
    { key: "siliconflow_api_key", label: "SiliconFlow API Key", placeholder: "sk-..." },
    { key: "siliconflow_base_url", label: "SiliconFlow Base URL", placeholder: "https://api.siliconflow.cn/v1" },
    { key: "siliconflow_model", label: "SiliconFlow Model", placeholder: "" },
    { key: "claude_api_key", label: "Claude API Key", placeholder: "sk-ant-..." },
    { key: "mineru_api_token", label: "MinerU Token", placeholder: "" },
  ]

  const ocrKeys = [
    { key: "ocr_ai_api_key", label: "OCR AI API Key", placeholder: "sk-..." },
    { key: "ocr_ai_base_url", label: "OCR AI Base URL", placeholder: "https://api.siliconflow.cn/v1" },
    { key: "ocr_ai_model", label: "OCR AI Model", placeholder: "" },
    { key: "ocr_baidu_api_key", label: "百度 OCR API Key", placeholder: "" },
    { key: "ocr_baidu_secret_key", label: "百度 OCR Secret Key", placeholder: "" },
  ]

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <header className="mb-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link href="/admin" className="hover:text-foreground">管理后台</Link>
          <span>/</span>
          <span>站点配置</span>
        </div>
        <h1 className="mt-2 font-serif text-2xl">站点全局配置</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          配置 API 密钥和默认参数，所有用户共享这些配置。
        </p>
      </header>

      {error ? (
        <div className="mb-4 border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <Card className="border-border">
        <CardHeader>
          <CardTitle>部署模式</CardTitle>
          <CardDescription>
            选择系统的部署模式。自用模式适合个人使用，自动登录；公开模式适合团队部署，需要手动登录。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid grid-cols-2 gap-4">
            <button
              type="button"
              className={`cursor-pointer rounded-lg border-2 p-4 text-left transition-colors ${
                currentDeployMode === "self"
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50"
              }`}
              onClick={() => {
                if (currentDeployMode !== "self") {
                  if (!window.confirm("切换到自用模式后，将启用自动登录。确定切换？")) {
                    return
                  }
                }
                handleChange("deploy_mode", "self")
              }}
            >
              <div className="font-medium">自用模式</div>
              <div className="mt-1 text-sm text-muted-foreground">
                适合个人使用。登录后自动保持会话，无需每次输入密码。
              </div>
            </button>
            <button
              type="button"
              className={`cursor-pointer rounded-lg border-2 p-4 text-left transition-colors ${
                currentDeployMode === "public"
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50"
              }`}
              onClick={() => {
                if (currentDeployMode !== "public") {
                  if (!window.confirm("切换到公开模式后，自动登录将禁用，所有用户需要手动输入密码登录。确定切换？")) {
                    return
                  }
                }
                handleChange("deploy_mode", "public")
              }}
            >
              <div className="font-medium">公开模式</div>
              <div className="mt-1 text-sm text-muted-foreground">
                适合团队或公开部署。支持多用户注册、邀请码和配额管理。
              </div>
            </button>
          </div>
        </CardContent>
      </Card>

      <Card className="mt-4 border-border">
        <CardHeader>
          <CardTitle>API 密钥配置</CardTitle>
          <CardDescription>
            配置各服务的 API 密钥，用户无需自行填写。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          {apiKeys.map((item) => (
            <div key={item.key} className="grid gap-2">
              <label className="text-muted-foreground text-xs" htmlFor={`site-${item.key}`}>
                {item.label}
              </label>
              <Input
                id={`site-${item.key}`}
                type={SENSITIVE_KEYS.has(item.key) ? "password" : "text"}
                autoComplete="off"
                value={settings[item.key] || ""}
                onChange={(e) => handleChange(item.key, e.target.value)}
                placeholder={item.placeholder}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="mt-4 border-border">
        <CardHeader>
          <CardTitle>OCR 配置</CardTitle>
          <CardDescription>
            配置 OCR 相关的 API 密钥和参数。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          {ocrKeys.map((item) => (
            <div key={item.key} className="grid gap-2">
              <label className="text-muted-foreground text-xs" htmlFor={`site-${item.key}`}>
                {item.label}
              </label>
              <Input
                id={`site-${item.key}`}
                type={SENSITIVE_KEYS.has(item.key) ? "password" : "text"}
                autoComplete="off"
                value={settings[item.key] || ""}
                onChange={(e) => handleChange(item.key, e.target.value)}
                placeholder={item.placeholder}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="mt-6 flex justify-end gap-2">
        <Button type="button" variant="outline" asChild>
          <Link href="/admin">返回</Link>
        </Button>
        <Button type="button" onClick={() => void handleSave()} disabled={isSaving}>
          {isSaving ? "保存中..." : "保存配置"}
        </Button>
      </div>
    </div>
  )
}
