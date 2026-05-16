"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { CheckIcon, Loader2Icon } from "lucide-react"

import { apiFetch, readResponseErrorMessage } from "@/lib/api"
import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  LAYOUT_MODELS,
  type LayoutModelInfo,
} from "@/lib/layout-models"
import { useModelDownload } from "@/hooks/use-model-download"
import { DownloadProgressButton } from "@/components/download-progress-button"
import { PasswordStrengthMeter } from "@/components/password-strength-meter"
import { DeployModeComparison } from "@/components/deploy-mode-comparison"

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

const STEPS = ["部署模式", "创建管理员", "模型下载"]

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
  const refetchModelStatus = React.useCallback(async () => {
    setModelStatusLoading(true)
    try {
      const statusRes = await apiFetch("/models/status")
      if (statusRes.ok) {
        const statusData = (await statusRes.json()) as ModelStatusResponse
        setModelStatus(statusData)
      }
    } catch {
      // Non-fatal
    } finally {
      setModelStatusLoading(false)
    }
  }, [])
  const { startDownload, cancelDownload, getDownloadState } = useModelDownload({
    onDownloadComplete: () => void refetchModelStatus(),
  })

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

      // Fetch model status for the model download step
      await refetchModelStatus()

      // Move to model download step
      setStep(2)
    } catch (e) {
      const message = e instanceof Error ? e.message : "设置失败"
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }, [deployMode, username, password, refetch, refetchModelStatus])

  const handleDownloadModel = React.useCallback(async (model: string) => {
    const modelInfo = LAYOUT_MODELS[model]
    const label = modelInfo?.displayName ?? model
    const sizeMb = modelInfo?.sizeMb
    const confirmMsg = sizeMb
      ? `下载 ${label}（${sizeMb}MB）？\n下载完成后可在设置中切换使用。`
      : `下载 ${label}？\n下载完成后可在设置中切换使用。`
    if (!window.confirm(confirmMsg)) {
      return
    }
    await startDownload(model)
  }, [startDownload])

  const handleComplete = React.useCallback(async () => {
    toast.success("设置完成")
    router.replace("/")
  }, [router])

  const handleNext = React.useCallback(() => {
    setError(null)
    if (step === 0) {
      // Deploy mode → create admin
      setStep(1)
    } else if (step === 1) {
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
      // Create admin account and proceed to model download
      void handleCreateAdmin()
    } else if (step === 2) {
      // Model download → complete
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
          <h1 className="font-serif text-2xl leading-none tracking-tight">首次部署设置</h1>
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
          {/* Step 0: Deploy Mode + Welcome */}
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
              </div>

              <div className="space-y-2">
                <h3 className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                  选择部署模式
                </h3>
                <DeployModeComparison
                  selectedMode={deployMode}
                  onModeChange={setDeployMode}
                />
              </div>

              {error && <p className="text-xs text-destructive">{error}</p>}
              <Button onClick={handleNext} className="w-full">
                下一步
              </Button>
            </div>
          )}

          {/* Step 1: Create Admin */}
          {step === 1 && (
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
                    disabled={isSubmitting}
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
                    disabled={isSubmitting}
                  />
                  <PasswordStrengthMeter password={password} />
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
                    disabled={isSubmitting}
                  />
                </div>
              </div>
              {error && <p className="text-xs text-destructive">{error}</p>}
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => setStep(0)}
                  className="flex-1"
                  disabled={isSubmitting}
                >
                  上一步
                </Button>
                <Button onClick={handleNext} className="flex-1" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <Loader2Icon className="mr-2 size-4 animate-spin" />
                      创建中...
                    </>
                  ) : (
                    "创建管理员"
                  )}
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: Optional Model Download */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="space-y-2">
                <h3 className="text-sm font-medium">下载本地模型（可选）</h3>
                <p className="text-sm text-muted-foreground">
                  本地模型可用于离线 OCR 识别和版面分析。如果您计划使用远程 API（如 AIOCR、百度文档解析），可以跳过此步骤。
                </p>
              </div>

              {modelStatusLoading ? (
                <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                  <Loader2Icon className="size-4 animate-spin" />
                  检测模型状态...
                </div>
              ) : modelStatus ? (
                <div className="space-y-3">
                  {/* Local OCR models */}
                  <div className="space-y-2">
                    <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                      本地 OCR 模型
                    </div>
                    {[
                      { key: "tesseract", label: "Tesseract OCR" },
                      { key: "paddleocr", label: "PaddleOCR" },
                    ].map(({ key, label }) => {
                      const prov = modelStatus.local[key]
                      const isReady = prov?.ready ?? false
                      const isDownloadable = key === "paddleocr"
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
                            <DownloadProgressButton
                              modelId={key}
                              downloadState={getDownloadState(key)}
                              isReady={isReady}
                              onDownload={(id) => void handleDownloadModel(id)}
                              onCancel={cancelDownload}
                              onRefreshStatus={() => void refetchModelStatus()}
                            />
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              需安装系统包
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>

                  {/* Layout models */}
                  <div className="space-y-2">
                    <div className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                      版面分析模型
                    </div>
                    {Object.values(LAYOUT_MODELS).map((model: LayoutModelInfo) => {
                      const isDownloaded = modelStatus?.local?.[model.modelId]?.ready ?? false
                      return (
                        <div
                          key={model.modelId}
                          className="flex items-center justify-between rounded border border-border px-3 py-2"
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <span
                                className={`inline-block size-2 rounded-full ${
                                  isDownloaded ? "bg-emerald-500" : "bg-muted-foreground/40"
                                }`}
                              />
                              <span className="text-sm font-medium">{model.displayName}</span>
                              <span className="text-[11px] text-muted-foreground">
                                {model.sizeMb} MB
                              </span>
                              {model.recommended ? (
                                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
                                  推荐
                                </span>
                              ) : null}
                            </div>
                            <div className="mt-0.5 pl-4 text-[11px] text-muted-foreground">
                              {model.description} · {model.speedLabel} · {model.accuracy}
                            </div>
                          </div>
                          <div className="flex shrink-0 items-center gap-1">
                            {isDownloaded ? (
                              <span className="flex items-center gap-1 text-xs text-emerald-600">
                                <CheckIcon className="size-3" />
                                已下载
                              </span>
                            ) : (
                              <DownloadProgressButton
                                modelId={model.modelId}
                                downloadState={getDownloadState(model.modelId)}
                                isReady={isDownloaded}
                                onDownload={(id) => void handleDownloadModel(id)}
                                onCancel={cancelDownload}
                                onRefreshStatus={() => void refetchModelStatus()}
                              />
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  <div className="rounded-lg border border-border bg-muted/30 p-3">
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">提示：</span>
                      模型下载后可在「设置」页面切换使用。如果您使用远程 API（AIOCR、百度文档解析、MinerU），无需下载本地模型。
                    </p>
                  </div>
                </div>
              ) : (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  无法获取模型状态，可稍后在设置页查看。
                </p>
              )}

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={handleComplete}
                  className="flex-1"
                >
                  跳过，稍后配置
                </Button>
                <Button onClick={handleNext} className="flex-1">
                  完成设置
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
