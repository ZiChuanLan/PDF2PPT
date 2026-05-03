"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { CheckIcon, DownloadIcon, Loader2Icon } from "lucide-react"

import { apiFetch, readResponseErrorMessage, normalizeFetchError } from "@/lib/api"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"

type DeployMode = "self" | "public"

type ModelProviderStatus = {
  ready: boolean
  issues: string[]
  configured?: boolean
}

type ModelStatusResponse = {
  local: Record<string, ModelProviderStatus>
  remote: Record<string, ModelProviderStatus>
}

const STEPS = ["欢迎", "部署模式", "创建管理员", "模型检测", "完成"]

export default function SetupPage() {
  const router = useRouter()
  const { user, isLoading, refetch } = useAuth()
  const [step, setStep] = React.useState(0)
  const [deployMode, setDeployMode] = React.useState<DeployMode>("self")
  const [username, setUsername] = React.useState("")
  const [password, setPassword] = React.useState("")
  const [confirmPassword, setConfirmPassword] = React.useState("")
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [needsSetup, setNeedsSetup] = React.useState<boolean | null>(null)
  const [modelStatus, setModelStatus] = React.useState<ModelStatusResponse | null>(null)
  const [modelStatusLoading, setModelStatusLoading] = React.useState(false)
  const [downloadingModel, setDownloadingModel] = React.useState<string | null>(null)

  // Check if setup is needed
  React.useEffect(() => {
    const checkSetup = async () => {
      try {
        const res = await apiFetch("/setup/status")
        if (!res.ok) return
        const data = await res.json().catch(() => null)
        if (data?.needs_setup === false) {
          router.replace("/")
          return
        }
        setNeedsSetup(true)
      } catch {
        // If we can't reach the API, assume setup is needed
        setNeedsSetup(true)
      }
    }
    void checkSetup()
  }, [router])

  // Redirect if already logged in
  React.useEffect(() => {
    if (!isLoading && user) {
      router.replace("/")
    }
  }, [user, isLoading, router])

  const handleCreateAdmin = React.useCallback(async () => {
    setIsSubmitting(true)
    setError(null)
    try {
      const res = await apiFetch("/setup/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deploy_mode: deployMode,
          username: username.trim(),
          password,
        }),
      })

      if (!res.ok) {
        const message = await readResponseErrorMessage(res, "设置失败")
        throw new Error(message)
      }

      // Admin created successfully — now fetch model status
      await refetch()

      // Fetch model status for the prewarm step
      setModelStatusLoading(true)
      try {
        const statusRes = await apiFetch("/models/status")
        if (statusRes.ok) {
          const statusData = (await statusRes.json()) as ModelStatusResponse
          setModelStatus(statusData)
        }
      } catch {
        // Non-fatal — user can skip model setup
      } finally {
        setModelStatusLoading(false)
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : "设置失败"
      setError(message)
      setStep(2) // Go back to form
    } finally {
      setIsSubmitting(false)
    }
  }, [deployMode, username, password, refetch])

  const handleDownloadModel = React.useCallback(async (model: string) => {
    setDownloadingModel(model)
    try {
      const res = await apiFetch("/models/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(body?.message || "下载失败")
      }
      toast.success("模型下载完成")
      // Refresh model status
      const statusRes = await apiFetch("/models/status")
      if (statusRes.ok) {
        const statusData = (await statusRes.json()) as ModelStatusResponse
        setModelStatus(statusData)
      }
    } catch (e) {
      toast.error(normalizeFetchError(e, "模型下载失败"))
    } finally {
      setDownloadingModel(null)
    }
  }, [])

  const handleComplete = React.useCallback(async () => {
    toast.success("设置完成")
    router.replace("/")
  }, [router])

  const handleNext = React.useCallback(() => {
    setError(null)
    if (step === 0) {
      // Welcome → deploy mode
      setStep(1)
    } else if (step === 1) {
      // Deploy mode → create admin
      setStep(2)
    } else if (step === 2) {
      // Validate admin form
      if (!username.trim()) {
        setError("请输入用户名")
        return
      }
      if (username.trim().length < 3) {
        setError("用户名至少 3 个字符")
        return
      }
      if (!password) {
        setError("请输入密码")
        return
      }
      if (password.length < 8) {
        setError("密码至少 8 个字符")
        return
      }
      if (password !== confirmPassword) {
        setError("两次输入的密码不一致")
        return
      }
      // Create admin account first, then go to model detection
      setStep(3)
      void handleCreateAdmin()
    } else if (step === 3) {
      // Model detection → complete
      setStep(4)
      void handleComplete()
    }
  }, [step, username, password, confirmPassword, handleCreateAdmin, handleComplete])

  if (isLoading || needsSetup === null) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-muted-foreground">加载中...</div>
      </main>
    )
  }

  if (user) {
    return null
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <Card className="w-full max-w-xl border-border bg-background/95 backdrop-blur">
        <CardHeader className="border-b border-border">
          <CardTitle>首次部署设置</CardTitle>
          <CardDescription>
            完成以下步骤来初始化您的 PDF2PPT 服务
          </CardDescription>
          {/* Progress bar */}
          <div className="mt-4 flex gap-2">
            {STEPS.map((label, i) => (
              <div key={label} className="flex-1">
                <div
                  className={`h-1.5 rounded-full transition-colors ${
                    i <= step ? "bg-foreground" : "bg-muted"
                  }`}
                />
                <p
                  className={`mt-1.5 text-center text-xs ${
                    i === step
                      ? "font-medium text-foreground"
                      : "text-muted-foreground"
                  }`}
                >
                  {label}
                </p>
              </div>
            ))}
          </div>
        </CardHeader>
        <CardContent className="space-y-5 pt-5">
          {/* Step 0: Welcome */}
          {step === 0 && (
            <div className="space-y-4">
              <div className="space-y-2 text-sm leading-6 text-muted-foreground">
                <p>
                  欢迎使用 <span className="font-medium text-foreground">PDF2PPT</span>！
                </p>
                <p>
                  这是一个将 PDF 文档和图片转换为 PowerPoint 演示文稿的工具。
                  首次使用需要完成一些基本设置。
                </p>
                <p>接下来您将：</p>
                <ul className="list-inside list-disc space-y-1 pl-2">
                  <li>选择部署模式（自用或多用户）</li>
                  <li>创建管理员账号</li>
                </ul>
              </div>
              {error && <p className="text-xs text-destructive">{error}</p>}
              <Button onClick={handleNext} className="w-full">
                开始设置
              </Button>
            </div>
          )}

          {/* Step 1: Deploy Mode */}
          {step === 1 && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                选择您的部署模式。此设置后续可在管理后台修改。
              </p>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setDeployMode("self")}
                  className={`rounded-lg border-2 p-4 text-left transition-colors ${
                    deployMode === "self"
                      ? "border-foreground bg-muted/50"
                      : "border-border hover:border-muted-foreground/50"
                  }`}
                >
                  <h3 className="font-medium">自用模式</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    适合个人使用。登录后自动保持会话，无需每次输入密码。
                  </p>
                </button>
                <button
                  type="button"
                  onClick={() => setDeployMode("public")}
                  className={`rounded-lg border-2 p-4 text-left transition-colors ${
                    deployMode === "public"
                      ? "border-foreground bg-muted/50"
                      : "border-border hover:border-muted-foreground/50"
                  }`}
                >
                  <h3 className="font-medium">公开模式</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    适合团队或公开部署。支持多用户注册、邀请码和配额管理。
                  </p>
                </button>
              </div>
              {error && <p className="text-xs text-destructive">{error}</p>}
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => setStep(0)}
                  className="flex-1"
                >
                  上一步
                </Button>
                <Button onClick={handleNext} className="flex-1">
                  下一步
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: Create Admin */}
          {step === 2 && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                创建管理员账号。此账号拥有系统最高权限。
              </p>
              <div className="space-y-3">
                <div className="space-y-2">
                  <label
                    htmlFor="setup-username"
                    className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
                  >
                    用户名
                  </label>
                  <Input
                    id="setup-username"
                    type="text"
                    placeholder="请输入用户名（至少 3 个字符）"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                  />
                </div>
                <div className="space-y-2">
                  <label
                    htmlFor="setup-password"
                    className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
                  >
                    密码
                  </label>
                  <Input
                    id="setup-password"
                    type="password"
                    placeholder="请输入密码（至少 8 个字符）"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
                <div className="space-y-2">
                  <label
                    htmlFor="setup-confirm-password"
                    className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground"
                  >
                    确认密码
                  </label>
                  <Input
                    id="setup-confirm-password"
                    type="password"
                    placeholder="请再次输入密码"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>
              </div>
              {error && <p className="text-xs text-destructive">{error}</p>}
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => setStep(1)}
                  className="flex-1"
                >
                  上一步
                </Button>
                <Button onClick={handleNext} className="flex-1">
                  完成设置
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Model Detection */}
          {step === 3 && (
            <div className="space-y-4">
              {isSubmitting ? (
                <div className="space-y-3 py-4 text-center">
                  <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-muted-foreground border-t-foreground" />
                  <p className="text-sm text-muted-foreground">正在创建管理员账号...</p>
                </div>
              ) : error ? (
                <div className="space-y-3 py-4 text-center">
                  <p className="text-sm text-destructive">{error}</p>
                  <Button onClick={() => setStep(2)} className="mt-4">
                    返回修改
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    管理员账号已创建。以下是模型就绪状态，本地模型可按需下载。
                  </p>

                  {modelStatusLoading ? (
                    <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                      <Loader2Icon className="size-4 animate-spin" />
                      检测模型状态...
                    </div>
                  ) : modelStatus ? (
                    <div className="space-y-3">
                      {/* Local models */}
                      <div className="space-y-2">
                        <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                          本地模型
                        </div>
                        {[
                          { key: "tesseract", label: "Tesseract OCR" },
                          { key: "paddleocr", label: "PaddleOCR" },
                          { key: "pp_doclayout", label: "PP-DocLayout" },
                        ].map(({ key, label }) => {
                          const prov = modelStatus.local[key]
                          const isReady = prov?.ready ?? false
                          const isDownloadable = key === "pp_doclayout" || key === "paddleocr"
                          return (
                            <div
                              key={key}
                              className="flex items-center justify-between rounded border border-border px-3 py-2"
                            >
                              <div className="flex items-center gap-2">
                                <span
                                  className={`inline-block size-2 rounded-full ${
                                    isReady ? "bg-emerald-500" : "bg-red-500"
                                  }`}
                                />
                                <span className="text-sm">{label}</span>
                              </div>
                              {isReady ? (
                                <span className="flex items-center gap-1 text-xs text-emerald-600">
                                  <CheckIcon className="size-3" />
                                  就绪
                                </span>
                              ) : isDownloadable ? (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="h-7 text-xs"
                                  onClick={() => void handleDownloadModel(key)}
                                  disabled={downloadingModel === key}
                                >
                                  {downloadingModel === key ? (
                                    <Loader2Icon className="size-3 animate-spin" />
                                  ) : (
                                    <DownloadIcon className="size-3" />
                                  )}
                                  下载
                                </Button>
                              ) : (
                                <span className="text-xs text-muted-foreground">
                                  需安装系统包
                                </span>
                              )}
                            </div>
                          )
                        })}
                      </div>

                      {/* Remote APIs */}
                      <div className="space-y-2">
                        <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                          远程 API
                        </div>
                        {[
                          { key: "aiocr", label: "AIOCR" },
                          { key: "baidu_doc", label: "百度文档解析" },
                          { key: "mineru", label: "MinerU" },
                        ].map(({ key, label }) => {
                          const prov = modelStatus.remote[key]
                          const isReady = prov?.ready ?? false
                          const isConfigured = prov?.configured ?? false
                          return (
                            <div
                              key={key}
                              className="flex items-center justify-between rounded border border-border px-3 py-2"
                            >
                              <div className="flex items-center gap-2">
                                <span
                                  className={`inline-block size-2 rounded-full ${
                                    isReady
                                      ? "bg-emerald-500"
                                      : isConfigured
                                        ? "bg-amber-500"
                                        : "bg-muted-foreground/40"
                                  }`}
                                />
                                <span className="text-sm">{label}</span>
                              </div>
                              <span
                                className={`text-xs ${
                                  isReady
                                    ? "text-emerald-600"
                                    : isConfigured
                                      ? "text-amber-600"
                                      : "text-muted-foreground"
                                }`}
                              >
                                {isReady ? "就绪" : isConfigured ? "需要配置" : "未配置"}
                              </span>
                            </div>
                          )
                        })}
                      </div>

                      <p className="text-xs text-muted-foreground">
                        远程 API 的密钥可在「设置」页面配置。本地模型下载后即可离线使用。
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">无法获取模型状态，可稍后在设置页查看。</p>
                  )}

                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      onClick={() => setStep(4)}
                      className="flex-1"
                    >
                      跳过
                    </Button>
                    <Button onClick={() => setStep(4)} className="flex-1">
                      完成设置
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Step 4: Completion */}
          {step === 4 && (
            <div className="space-y-4 py-6 text-center">
              {isSubmitting ? (
                <>
                  <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-muted-foreground border-t-foreground" />
                  <p className="text-sm text-muted-foreground">
                    正在完成设置...
                  </p>
                </>
              ) : error ? (
                <>
                  <p className="text-sm text-destructive">{error}</p>
                  <Button onClick={() => setStep(2)} className="mt-4">
                    返回修改
                  </Button>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  正在进入系统...
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
