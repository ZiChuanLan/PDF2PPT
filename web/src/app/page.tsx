"use client"

import * as React from "react"
import Link from "next/link"
import {
  ArrowRightIcon,
  DownloadIcon,
  ExternalLinkIcon,
  FileTextIcon,
  ListChecksIcon,
  Settings2Icon,
  UploadCloudIcon,
  XCircleIcon,
} from "lucide-react"
import { useDropzone } from "react-dropzone"
import { toast } from "sonner"

import { cn } from "@/lib/utils"
import { getApiBaseUrl, normalizeFetchError } from "@/lib/api"
import { SILICONFLOW_BASE_URL, defaultSettings, loadStoredSettings, type Settings } from "@/lib/settings"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { useUploadSession } from "@/components/upload-session-provider"

type JobStatusValue = "pending" | "processing" | "completed" | "failed" | "cancelled"
type JobQueueState = "queued" | "running" | "waiting" | "done"

type JobListItem = {
  job_id: string
  status: JobStatusValue
  stage: string
  progress: number
  created_at: string
  expires_at: string
  message?: string | null
  error?: { code?: string; message?: string } | null
  queue_position?: number | null
  queue_state?: JobQueueState | string | null
}

type JobListResponse = {
  jobs: JobListItem[]
  queue_size: number
  returned: number
}

type JobStatusResponse = {
  job_id: string
  status: JobStatusValue
  stage: string
  progress: number
  created_at: string
  expires_at: string
  message?: string | null
  error?: { code?: string; message?: string } | null
}

type RunConfig = {
  parseProvider: "local" | "mineru"
  llmProvider: "openai" | "claude"
  mainApiKey: string
  mainBaseUrl: string
  mainModel: string
  effectiveOcrProvider: string
  effectiveOcrAiKey: string
  effectiveOcrAiBaseUrl: string
  effectiveOcrAiModel: string
  effectiveOcrAiProvider: string
}

type ValidationResult = {
  ok: boolean
  message?: string
}

const API_BASE_URL = getApiBaseUrl()

const TERMINAL_STATUSES = new Set<JobStatusValue>(["completed", "failed", "cancelled"])

const jobStatusLabels: Record<JobStatusValue, string> = {
  pending: "排队中",
  processing: "处理中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
}

const jobStageLabels: Record<string, string> = {
  upload_received: "上传接收",
  queued: "队列等待",
  parsing: "解析 PDF",
  ocr: "OCR 识别",
  layout_assist: "版式辅助",
  pptx_generating: "生成 PPTX",
  packaging: "打包",
  cleanup: "清理",
  done: "已完成",
}

function formatDateTime(iso: string) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(date)
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"] as const
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, idx)
  return `${value.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`
}

function getMainProviderConfig(settings: Settings) {
  if (settings.provider === "siliconflow") {
    return {
      provider: "openai" as const,
      apiKey: settings.siliconflowApiKey.trim(),
      baseUrl: settings.siliconflowBaseUrl.trim() || SILICONFLOW_BASE_URL,
      model: settings.siliconflowModel.trim(),
    }
  }
  if (settings.provider === "claude") {
    return {
      provider: "claude" as const,
      apiKey: settings.claudeApiKey.trim(),
      baseUrl: "",
      model: "",
    }
  }
  return {
    provider: "openai" as const,
    apiKey: settings.openaiApiKey.trim(),
    baseUrl: settings.openaiBaseUrl.trim(),
    model: settings.openaiModel.trim(),
  }
}

function resolveRunConfig(settings: Settings): RunConfig {
  const parseProvider: RunConfig["parseProvider"] =
    settings.provider === "mineru" ? "mineru" : "local"
  const main = getMainProviderConfig(settings)
  const canReuseMainForOcr = Boolean(main.apiKey) && main.provider === "openai"

  const rawOcrProvider = (settings.ocrProvider || "auto").trim().toLowerCase()
  const effectiveOcrProvider =
    parseProvider === "mineru"
        ? (rawOcrProvider === "aiocr" || rawOcrProvider === "paddle"
            ? "auto"
            : rawOcrProvider)
        : rawOcrProvider

  const effectiveOcrAiKey =
    settings.ocrAiApiKey.trim() || (canReuseMainForOcr ? main.apiKey : "")
  const effectiveOcrAiBaseUrl =
    settings.ocrAiBaseUrl.trim() || (canReuseMainForOcr ? main.baseUrl : "")
  const effectiveOcrAiModel =
    settings.ocrAiModel.trim() || (canReuseMainForOcr ? main.model : "")
  const effectiveOcrAiProvider = (settings.ocrAiProvider || "auto").trim() || "auto"


  return {
    parseProvider,
    llmProvider: main.provider,
    mainApiKey: main.apiKey,
    mainBaseUrl: main.baseUrl,
    mainModel: main.model,
    effectiveOcrProvider,
    effectiveOcrAiKey,
    effectiveOcrAiBaseUrl,
    effectiveOcrAiModel,
    effectiveOcrAiProvider,
  }
}

function validateBeforeRun(settings: Settings): ValidationResult {
  const run = resolveRunConfig(settings)

  if (run.parseProvider === "mineru" && !settings.mineruApiToken.trim()) {
    return { ok: false, message: "当前为 MinerU 解析，请先在设置页填写 MinerU API Token。" }
  }

  if (run.parseProvider === "local") {
    if (run.effectiveOcrProvider === "baidu") {
      const ok =
        Boolean(settings.ocrBaiduAppId.trim()) &&
        Boolean(settings.ocrBaiduApiKey.trim()) &&
        Boolean(settings.ocrBaiduSecretKey.trim())
      if (!ok) {
        return {
          ok: false,
          message: "当前 OCR 提供方为百度，请在设置页补全 app_id / api_key / secret_key。",
        }
      }
    }

    if (run.effectiveOcrProvider === "aiocr") {
      if (!run.effectiveOcrAiKey) {
        return { ok: false, message: "当前 OCR 需要 AI Key，请在设置页补充 OCR API Key。" }
      }
    }

    if (run.effectiveOcrProvider === "paddle") {
      if (!run.effectiveOcrAiKey) {
        return { ok: false, message: "当前 OCR 需要 AI Key，请在设置页补充 OCR API Key。" }
      }
    }
  }

  return { ok: true }
}

function toIntOrUndefined(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const n = Number(trimmed)
  if (!Number.isFinite(n)) return undefined
  const i = Math.floor(n)
  if (i <= 0) return undefined
  return i
}

function createFormData(
  file: File,
  settings: Settings,
  pageStart?: number,
  pageEnd?: number
): FormData {
  const run = resolveRunConfig(settings)
  const form = new FormData()

  form.append("file", file)
  form.append("parse_provider", run.parseProvider)
  form.append("provider", run.llmProvider)

  if (run.mainApiKey) form.append("api_key", run.mainApiKey)
  if (run.mainBaseUrl) form.append("base_url", run.mainBaseUrl)
  if (run.mainModel) form.append("model", run.mainModel)

  form.append("enable_layout_assist", String(Boolean(settings.enableLayoutAssist)))
  form.append(
    "layout_assist_apply_image_regions",
    String(Boolean(settings.layoutAssistApplyImageRegions))
  )
  form.append("enable_ocr", String(Boolean(settings.enableOcr)))
  form.append("text_erase_mode", settings.textEraseMode)
  form.append("scanned_page_mode", settings.scannedPageMode)
  form.append("ocr_strict_mode", String(Boolean(settings.ocrStrictMode)))

  if (run.parseProvider === "mineru") {
    form.append("mineru_api_token", settings.mineruApiToken.trim())
    form.append("mineru_model_version", settings.mineruModelVersion)
    form.append("mineru_enable_formula", String(Boolean(settings.mineruEnableFormula)))
    form.append("mineru_enable_table", String(Boolean(settings.mineruEnableTable)))
    form.append("mineru_is_ocr", String(Boolean(settings.mineruIsOcr)))
    form.append("mineru_hybrid_ocr", String(Boolean(settings.mineruHybridOcr)))
    if (settings.mineruBaseUrl.trim()) form.append("mineru_base_url", settings.mineruBaseUrl.trim())
    if (settings.mineruLanguage.trim()) form.append("mineru_language", settings.mineruLanguage.trim())
  }

  if (run.parseProvider === "local") {
    form.append("ocr_provider", run.effectiveOcrProvider)

    const shouldAttachOcrAiParams =
      run.effectiveOcrProvider === "aiocr" ||
      run.effectiveOcrProvider === "paddle" ||
      Boolean(settings.ocrAiLinebreakAssistMode === "on" && run.effectiveOcrAiKey)
    if (shouldAttachOcrAiParams) {
      if (run.effectiveOcrAiKey) form.append("ocr_ai_api_key", run.effectiveOcrAiKey)
      if (run.effectiveOcrAiBaseUrl) form.append("ocr_ai_base_url", run.effectiveOcrAiBaseUrl)
      if (run.effectiveOcrAiModel) form.append("ocr_ai_model", run.effectiveOcrAiModel)
      form.append("ocr_ai_provider", run.effectiveOcrAiProvider)
    }
    if (settings.ocrAiLinebreakAssistMode === "on") {
      form.append("ocr_ai_linebreak_assist", "true")
    } else if (settings.ocrAiLinebreakAssistMode === "off") {
      form.append("ocr_ai_linebreak_assist", "false")
    }

    if (run.effectiveOcrProvider === "baidu") {
      form.append("ocr_baidu_app_id", settings.ocrBaiduAppId.trim())
      form.append("ocr_baidu_api_key", settings.ocrBaiduApiKey.trim())
      form.append("ocr_baidu_secret_key", settings.ocrBaiduSecretKey.trim())
    }

    if (run.effectiveOcrProvider === "tesseract" || run.effectiveOcrProvider === "auto") {
      if (settings.ocrTesseractLanguage.trim()) {
        form.append("ocr_tesseract_language", settings.ocrTesseractLanguage.trim())
      }
      const minConf = Number(settings.ocrTesseractMinConfidence)
      if (Number.isFinite(minConf)) {
        form.append("ocr_tesseract_min_confidence", String(minConf))
      }
    }
  }

  if (pageStart && pageEnd) {
    form.append("page_start", String(pageStart))
    form.append("page_end", String(pageEnd))
  }

  return form
}

export default function Home() {
  const [settingsSnapshot, setSettingsSnapshot] = React.useState<Settings>(defaultSettings)
  const {
    file,
    setFile,
    pageStartInput,
    setPageStartInput,
    pageEndInput,
    setPageEndInput,
    clearUpload,
  } = useUploadSession()

  const [jobId, setJobId] = React.useState<string | null>(null)
  const [activeJob, setActiveJob] = React.useState<JobStatusResponse | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)
  const [actionError, setActionError] = React.useState<string | null>(null)

  const [jobs, setJobs] = React.useState<JobListItem[]>([])
  const [queueSize, setQueueSize] = React.useState(0)
  const [jobsLoading, setJobsLoading] = React.useState(false)
  const lastTerminalToastRef = React.useRef<{
    jobId: string | null
    status: JobStatusValue | null
  }>({
    jobId: null,
    status: null,
  })

  const runConfig = React.useMemo(() => resolveRunConfig(settingsSnapshot), [settingsSnapshot])
  const runModelLabel = React.useMemo(() => {
    if (
      runConfig.parseProvider === "local" &&
      runConfig.effectiveOcrProvider !== "aiocr" &&
      runConfig.effectiveOcrProvider !== "paddle"
    ) {
      if (settingsSnapshot.ocrAiLinebreakAssistMode === "on" && runConfig.effectiveOcrAiModel) {
        return `${runConfig.effectiveOcrAiModel}（仅用于行级拆分辅助）`
      }
      return "本地 OCR（无需远程模型）"
    }
    return runConfig.effectiveOcrAiModel || runConfig.mainModel || "未设置"
  }, [runConfig, settingsSnapshot.ocrAiLinebreakAssistMode])

  const refreshSettingsSnapshot = React.useCallback(() => {
    setSettingsSnapshot(loadStoredSettings())
  }, [])

  const fetchJobs = React.useCallback(async (silent = true) => {
    if (!silent) setJobsLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/jobs?limit=50`)
      if (!response.ok) {
        throw new Error("加载任务列表失败")
      }
      const body = (await response.json().catch(() => null)) as JobListResponse | null
      const rows = Array.isArray(body?.jobs) ? body.jobs : []
      setJobs(rows)
      setQueueSize(typeof body?.queue_size === "number" ? Math.max(0, body.queue_size) : 0)
    } catch (e) {
      if (!silent) {
        setActionError(normalizeFetchError(e, "加载任务列表失败"))
      }
    } finally {
      if (!silent) setJobsLoading(false)
    }
  }, [])

  const fetchJobStatus = React.useCallback(async (targetJobId: string) => {
    const response = await fetch(`${API_BASE_URL}/jobs/${targetJobId}`)
    if (!response.ok) {
      throw new Error("查询任务状态失败")
    }
    const body = (await response.json().catch(() => null)) as JobStatusResponse | null
    if (!body || typeof body !== "object") {
      throw new Error("任务状态响应异常")
    }
    return body
  }, [])

  const onDrop = React.useCallback((accepted: File[]) => {
    const next = accepted[0] ?? null
    setFile(next)
    setActionError(null)
    if (next) {
      setPageStartInput("")
      setPageEndInput("")
    } else {
      clearUpload()
    }
  }, [clearUpload, setFile, setPageEndInput, setPageStartInput])

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    accept: { "application/pdf": [".pdf"] },
    multiple: false,
    disabled: isSubmitting,
    onDrop,
  })

  const handleConvert = React.useCallback(async () => {
    if (!file) return

    setActionError(null)

    const validation = validateBeforeRun(settingsSnapshot)
    if (!validation.ok) {
      setActionError(validation.message || "配置校验失败")
      return
    }

    const pageStart = toIntOrUndefined(pageStartInput)
    const pageEnd = toIntOrUndefined(pageEndInput)
    if ((pageStart && !pageEnd) || (!pageStart && pageEnd)) {
      setActionError("页码范围请同时填写起始页和结束页")
      return
    }
    if (pageStart && pageEnd && pageStart > pageEnd) {
      setActionError("页码范围错误：起始页不能大于结束页")
      return
    }

    setIsSubmitting(true)
    setJobId(null)
    setActiveJob(null)

    try {
      const formData = createFormData(file, settingsSnapshot, pageStart, pageEnd)
      const response = await fetch(`${API_BASE_URL}/jobs`, {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.message || "创建任务失败")
      }

      const body = (await response.json().catch(() => null)) as { job_id?: string } | null
      const nextJobId = typeof body?.job_id === "string" ? body.job_id : ""
      if (!nextJobId) {
        throw new Error("创建任务失败：未返回任务号")
      }

      setJobId(nextJobId)
      toast.success("任务创建成功，正在处理中")

      try {
        const status = await fetchJobStatus(nextJobId)
        setActiveJob(status)
      } catch {
        // ignore immediate poll failure
      }

      void fetchJobs(true)
    } catch (e) {
      setActionError(normalizeFetchError(e, "创建任务失败"))
      setIsSubmitting(false)
    }
  }, [fetchJobStatus, fetchJobs, file, pageEndInput, pageStartInput, settingsSnapshot])

  const handleCancelCurrentJob = React.useCallback(async () => {
    if (!jobId) return
    try {
      await fetch(`${API_BASE_URL}/jobs/${jobId}/cancel`, { method: "POST" })
      toast("已发送取消请求")
      void fetchJobs(true)
    } catch {
      toast.error("取消请求失败")
    }
  }, [fetchJobs, jobId])

  const handleDownload = React.useCallback(async (targetJobId: string) => {
    const response = await fetch(`${API_BASE_URL}/jobs/${targetJobId}/download`)
    if (!response.ok) {
      throw new Error("下载失败")
    }
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `output-${targetJobId.slice(0, 8)}.pptx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  }, [])

  const handleCancelById = React.useCallback(
    async (targetJobId: string) => {
      try {
        await fetch(`${API_BASE_URL}/jobs/${targetJobId}/cancel`, { method: "POST" })
        toast("取消请求已发送")
        void fetchJobs(true)
      } catch {
        toast.error("取消失败")
      }
    },
    [fetchJobs]
  )

  React.useEffect(() => {
    refreshSettingsSnapshot()
    void fetchJobs(false)

    const onFocus = () => {
      refreshSettingsSnapshot()
      void fetchJobs(true)
    }

    window.addEventListener("focus", onFocus)
    const timer = window.setInterval(() => {
      void fetchJobs(true)
    }, 4000)

    return () => {
      window.removeEventListener("focus", onFocus)
      window.clearInterval(timer)
    }
  }, [fetchJobs, refreshSettingsSnapshot])

  React.useEffect(() => {
    if (!jobId) return

    let mounted = true
    let timer: number | null = null

    const stopPolling = () => {
      if (timer !== null) {
        window.clearInterval(timer)
        timer = null
      }
    }

    const poll = async () => {
      try {
        const status = await fetchJobStatus(jobId)
        if (!mounted) return
        setActiveJob(status)
        if (TERMINAL_STATUSES.has(status.status)) {
          setIsSubmitting(false)
          stopPolling()
          void fetchJobs(true)
        }
      } catch {
        // ignore transient polling error
      }
    }

    void poll()
    timer = window.setInterval(() => {
      void poll()
    }, 2000)

    return () => {
      mounted = false
      stopPolling()
    }
  }, [fetchJobStatus, fetchJobs, jobId])

  React.useEffect(() => {
    if (!activeJob) return
    if (!TERMINAL_STATUSES.has(activeJob.status)) return

    const hasNotified =
      lastTerminalToastRef.current.jobId === activeJob.job_id &&
      lastTerminalToastRef.current.status === activeJob.status
    if (hasNotified) return

    lastTerminalToastRef.current = {
      jobId: activeJob.job_id,
      status: activeJob.status,
    }

    if (activeJob.status === "completed") {
      toast.success("转换完成，可下载 PPTX")
    } else if (activeJob.status === "failed") {
      setActionError(activeJob.error?.message || "转换失败")
      toast.error(activeJob.error?.message || "转换失败")
    } else if (activeJob.status === "cancelled") {
      toast("任务已取消")
    }
  }, [activeJob])

  const progressValue = Math.max(0, Math.min(100, Number(activeJob?.progress || 0)))
  const currentStatus = activeJob?.status || (isSubmitting ? "processing" : "pending")
  const currentStageLabel = activeJob?.stage
    ? (jobStageLabels[activeJob.stage] ?? activeJob.stage)
    : "等待开始"
  const inFlightJobs = jobs.filter((row) => row.status === "pending" || row.status === "processing").length
  const failedJobs = jobs.filter((row) => row.status === "failed").length
  const completedJobs = jobs.filter((row) => row.status === "completed").length
  const recentJobs = jobs.slice(0, 3)

  const canStart = Boolean(file) && !isSubmitting
  const filePreviewUrl = React.useMemo(() => (file ? URL.createObjectURL(file) : ""), [file])
  React.useEffect(() => {
    return () => {
      if (filePreviewUrl) {
        URL.revokeObjectURL(filePreviewUrl)
      }
    }
  }, [filePreviewUrl])
  const previewPage = toIntOrUndefined(pageStartInput)
  const previewSrc = filePreviewUrl
    ? `${filePreviewUrl}#toolbar=1&view=FitH${previewPage ? `&page=${previewPage}` : ""}`
    : ""

  return (
    <div className="min-h-dvh bg-background">
      <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
        <header className="border border-border bg-background p-5 md:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground">
                PDF → 可编辑 PPT
              </div>
              <h1 className="mt-1 text-2xl font-semibold tracking-tight md:text-3xl">
                首页保持简洁，设置页负责专业配置
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                上传文件后直接开始转换；参数细调在独立设置页完成。
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" asChild>
                <Link href="/tracking">
                  <ListChecksIcon className="size-4" />
                  跟踪中心
                </Link>
              </Button>
              <Button type="button" asChild>
                <Link href="/settings">
                  <Settings2Icon className="size-4" />
                  打开设置页
                </Link>
              </Button>
            </div>
          </div>
        </header>

        <main className="mt-6 grid gap-4 lg:grid-cols-12">
          <Card className="lg:col-span-7 border-border">
            <CardHeader>
              <CardTitle className="text-lg">上传与执行</CardTitle>
              <CardDescription>
                首页只做核心操作：选文件、选页码、启动转换。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div
                {...getRootProps()}
                className={cn(
                  "cursor-pointer border border-dashed border-border bg-muted/40 p-5 text-center transition-colors",
                  isDragActive && !isDragReject && "bg-accent/50",
                  isDragReject && "border-destructive bg-destructive/10",
                  isSubmitting && "pointer-events-none opacity-60"
                )}
              >
                <input {...getInputProps()} />
                <UploadCloudIcon className="mx-auto size-8 text-muted-foreground" />
                <p className="mt-2 text-sm font-medium">
                  {isDragActive ? "松开以上传 PDF" : "拖拽 PDF 到这里，或点击选择文件"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">仅支持 .pdf</p>
              </div>

              {file ? (
                <div className="flex items-center justify-between gap-3 border border-border p-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{file.name}</div>
                    <div className="text-xs text-muted-foreground">{formatBytes(file.size)}</div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      clearUpload()
                    }}
                  >
                    清空
                  </Button>
                </div>
              ) : null}

              {filePreviewUrl ? (
                <div className="grid gap-2 border border-border bg-background p-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-xs text-muted-foreground">
                      PDF 预览（可配合“起始页”快速定位）
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => window.open(filePreviewUrl, "_blank", "noopener,noreferrer")}
                    >
                      新窗口预览
                      <ExternalLinkIcon className="size-4" />
                    </Button>
                  </div>
                  <iframe
                    title="上传 PDF 预览"
                    src={previewSrc}
                    className="h-[380px] w-full border border-border bg-white"
                  />
                </div>
              ) : null}

              <div className="grid gap-3 md:grid-cols-2">
                <div className="grid gap-2">
                  <label className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                    起始页（可选）
                  </label>
                  <Input
                    inputMode="numeric"
                    placeholder="例如 1"
                    value={pageStartInput}
                    onChange={(e) => setPageStartInput(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <label className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
                    结束页（可选）
                  </label>
                  <Input
                    inputMode="numeric"
                    placeholder="例如 5"
                    value={pageEndInput}
                    onChange={(e) => setPageEndInput(e.target.value)}
                  />
                </div>
              </div>

              <div className="border border-border bg-muted/30 p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge variant="outline">解析：{runConfig.parseProvider}</Badge>
                  <Badge variant="outline">OCR：{runConfig.effectiveOcrProvider}</Badge>
                  <Badge variant="outline">模型：{runModelLabel}</Badge>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  当前配置已通过基础校验，参数微调请在设置页完成。
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button type="button" variant="ghost" asChild>
                    <Link href="/settings">
                      进入设置页精调
                      <ArrowRightIcon className="size-4" />
                    </Link>
                  </Button>
                </div>
              </div>
            </CardContent>
            <CardFooter className="border-t border-border flex-wrap justify-between gap-2">
              <div className="flex gap-2">
                <Button type="button" onClick={handleConvert} disabled={!canStart}>
                  开始转换
                </Button>
                <Button type="button" variant="outline" onClick={() => {
                  clearUpload()
                  setJobId(null)
                  setActiveJob(null)
                  setIsSubmitting(false)
                  setActionError(null)
                }}>
                  重置
                </Button>
              </div>
              {jobId && !TERMINAL_STATUSES.has(currentStatus as JobStatusValue) ? (
                <Button type="button" variant="destructive" onClick={handleCancelCurrentJob}>
                  <XCircleIcon className="size-4" />
                  取消当前任务
                </Button>
              ) : null}
            </CardFooter>
          </Card>

          <Card className="lg:col-span-5 border-border">
            <CardHeader>
              <CardTitle className="text-lg">当前任务状态</CardTitle>
              <CardDescription>实时轮询后端状态，稳定且便于排查问题。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={currentStatus === "failed" ? "destructive" : currentStatus === "completed" ? "secondary" : "outline"}>
                  {jobStatusLabels[currentStatus as JobStatusValue] || currentStatus}
                </Badge>
                <Badge variant="outline">阶段：{currentStageLabel}</Badge>
                {jobId ? <Badge variant="outline">任务号：{jobId}</Badge> : null}
              </div>

              <Progress value={progressValue} className="h-2" />

              <div className="text-sm text-muted-foreground">
                {activeJob?.message || (isSubmitting ? "任务已提交，正在等待状态更新…" : "尚未开始任务")}
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="border border-border bg-muted/30 p-2">队列总数：{queueSize}</div>
                <div className="border border-border bg-muted/30 p-2">执行中：{inFlightJobs}</div>
                <div className="border border-border bg-muted/30 p-2">已完成：{completedJobs}</div>
                <div className="border border-border bg-muted/30 p-2">失败：{failedJobs}</div>
              </div>

              {!jobId ? (
                <div className="border border-dashed border-border bg-muted/20 p-3 text-xs text-muted-foreground">
                  暂无当前任务。上传 PDF 后点击“开始转换”，状态会在这里实时更新。
                </div>
              ) : null}

              {recentJobs.length ? (
                <div className="grid gap-2 border border-border bg-muted/20 p-3">
                  <div className="text-xs font-medium text-muted-foreground">最近任务快照</div>
                  {recentJobs.map((row) => {
                    const rowStageLabel = jobStageLabels[row.stage] || row.stage
                    return (
                      <div key={row.job_id} className="flex items-start justify-between gap-2 border-t border-border/60 pt-2 first:border-t-0 first:pt-0">
                        <div className="min-w-0">
                          <div className="truncate font-mono text-[11px]">{row.job_id}</div>
                          <div className="text-[11px] text-muted-foreground">{rowStageLabel} · {formatDateTime(row.created_at)}</div>
                        </div>
                        <Badge variant={row.status === "failed" ? "destructive" : row.status === "completed" ? "secondary" : "outline"}>
                          {jobStatusLabels[row.status]}
                        </Badge>
                      </div>
                    )
                  })}
                  <Button type="button" variant="ghost" asChild className="h-auto justify-start px-0 text-xs">
                    <Link href="/tracking">打开跟踪中心查看全部</Link>
                  </Button>
                </div>
              ) : (
                <div className="border border-dashed border-border p-3 text-xs text-muted-foreground">
                  暂无历史任务，转换后这里会显示最近任务快照。
                </div>
              )}

              {activeJob?.error?.message ? (
                <div className="border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
                  {activeJob.error.message}
                </div>
              ) : null}

              {actionError ? (
                <div className="border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
                  {actionError}
                </div>
              ) : null}

              {jobId && currentStatus === "completed" ? (
                <Button
                  type="button"
                  onClick={async () => {
                    try {
                      await handleDownload(jobId)
                    } catch (e) {
                      toast.error(normalizeFetchError(e, "下载失败"))
                    }
                  }}
                >
                  <DownloadIcon className="size-4" />
                  下载 PPTX
                </Button>
              ) : null}
            </CardContent>
          </Card>
        </main>

        <Card className="mt-6 border-border">
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <CardTitle className="text-lg">最近任务</CardTitle>
                <CardDescription>队列总数：{queueSize} · 保留独立跟踪页用于深度排查</CardDescription>
              </div>
              <Button type="button" variant="outline" onClick={() => void fetchJobs(false)} disabled={jobsLoading}>
                刷新列表
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto border border-border">
              <table className="w-full min-w-[760px] text-sm">
                <thead className="bg-muted/40 text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">任务</th>
                    <th className="px-3 py-2">状态</th>
                    <th className="px-3 py-2">进度</th>
                    <th className="px-3 py-2">阶段</th>
                    <th className="px-3 py-2">时间</th>
                    <th className="px-3 py-2 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.length ? (
                    jobs.map((row) => {
                      const stageLabel = jobStageLabels[row.stage] || row.stage
                      const canCancel = row.status === "pending" || row.status === "processing"
                      const canDownload = row.status === "completed"
                      return (
                        <tr key={row.job_id} className="border-t border-border">
                          <td className="px-3 py-2 font-mono text-xs">{row.job_id}</td>
                          <td className="px-3 py-2">
                            <Badge variant={row.status === "failed" ? "destructive" : row.status === "completed" ? "secondary" : "outline"}>
                              {jobStatusLabels[row.status]}
                            </Badge>
                          </td>
                          <td className="px-3 py-2">{Math.max(0, Math.min(100, row.progress || 0))}%</td>
                          <td className="px-3 py-2">{stageLabel}</td>
                          <td className="px-3 py-2 text-muted-foreground">{formatDateTime(row.created_at)}</td>
                          <td className="px-3 py-2">
                            <div className="flex justify-end gap-2">
                              <Button type="button" variant="ghost" asChild>
                                <Link href={`/tracking?job=${encodeURIComponent(row.job_id)}`}>跟踪</Link>
                              </Button>
                              {canDownload ? (
                                <Button
                                  type="button"
                                  variant="outline"
                                  onClick={async () => {
                                    try {
                                      await handleDownload(row.job_id)
                                    } catch (e) {
                                      toast.error(normalizeFetchError(e, "下载失败"))
                                    }
                                  }}
                                >
                                  下载
                                </Button>
                              ) : null}
                              {canCancel ? (
                                <Button
                                  type="button"
                                  variant="destructive"
                                  onClick={() => void handleCancelById(row.job_id)}
                                >
                                  取消
                                </Button>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      )
                    })
                  ) : (
                    <tr>
                      <td colSpan={6} className="px-3 py-8 text-center text-sm text-muted-foreground">
                        暂无任务记录
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
          <CardFooter className="border-t border-border text-xs text-muted-foreground">
            <FileTextIcon className="mr-2 size-4" />
            首页专注执行；高级参数与模型切换请在设置页管理。
          </CardFooter>
        </Card>
      </div>
    </div>
  )
}
