"use client"

import * as React from "react"
import Link from "next/link"
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  FileIcon,
  Loader2Icon,
  XIcon,
  UploadCloudIcon,
} from "lucide-react"
import { useDropzone } from "react-dropzone"
import { toast } from "sonner"

import { cn } from "@/lib/utils"
import { apiFetch, normalizeFetchError, readResponseErrorMessage } from "@/lib/api"
import { useAuth } from "@/components/auth-provider"
import {
  defaultSettings,
  loadStoredSettings,
  PARSE_ENGINE_MODE_LABELS,
  PPT_GENERATION_MODE_LABELS,
  SETTINGS_STORAGE_KEY,
  type Settings,
} from "@/lib/settings"
import {
  buildJobConfig,
  validateRunConfig,
} from "@/lib/run-config"
import {
  getJobStageFlowIndex,
  JOB_STAGE_LABELS,
  JOB_STATUS_LABELS,
  normalizeJobListResponse,
  normalizeJobStatusResponse,
  TERMINAL_JOB_STATUSES,
  type JobListItem,
  type JobListResponse,
  type JobStatusResponse,
  type JobStatusValue,
} from "@/lib/job-status"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { JobDebugPanel } from "@/components/job-debug-panel"
import { HoverHint } from "@/components/ui/hover-hint"
import { Input } from "@/components/ui/input"
import { Progress } from "@/components/ui/progress"
import { PdfCanvasPreview } from "@/components/pdf-canvas-preview"
import { Select } from "@/components/ui/select"
import { useUploadSession } from "@/components/upload-session-provider"

type JobApiErrorBody = {
  code?: string
  message?: string
} | null

type JobStatusFetchError = Error & {
  statusCode?: number
  errorCode?: string
}

type FileJobState = {
  file: File
  jobId: string | null
  status: JobStatusResponse | null
  error: string | null
  isSubmitting: boolean
}

const ocrProviderLabels: Record<Settings["ocrProvider"], string> = {
  auto: "自动",
  aiocr: "AIOCR",
  baidu: "百度 OCR",
  machine: "本地 OCR",
}

const HOME_ACTIVE_JOB_STORAGE_KEY = "ppt-opencode:home:active-job-id"
const SUPPORTED_UPLOAD_ACCEPT = {
  "application/pdf": [".pdf"],
  "image/png": [".png"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/webp": [".webp"],
} as const
const SUPPORTED_IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"] as const

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B"
  const units = ["B", "KB", "MB", "GB"] as const
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, idx)
  return `${value.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`
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

function clampPositiveInt(value: number, max?: number) {
  const normalized = Number.isFinite(value) ? Math.max(1, Math.floor(value)) : 1
  if (!max || max <= 0) return normalized
  return Math.min(normalized, max)
}

function isImageUploadFile(file: File | null | undefined) {
  if (!file) return false
  const type = String(file.type || "").trim().toLowerCase()
  if (type.startsWith("image/")) return true
  const name = String(file.name || "").trim().toLowerCase()
  return SUPPORTED_IMAGE_EXTENSIONS.some((suffix) => name.endsWith(suffix))
}

export default function Home() {
  const { user, isLoading: isAuthLoading } = useAuth()
  const [settingsSnapshot, setSettingsSnapshot] = React.useState<Settings>(defaultSettings)
  const {
    files: uploadFiles,
    file,
    fileCount,
    pageStartInput,
    setPageStartInput,
    pageEndInput,
    setPageEndInput,
    addFiles,
    removeFile,
    clearUpload,
  } = useUploadSession()

  const [fileJobs, setFileJobs] = React.useState<FileJobState[]>([])
  const [queueSize, setQueueSize] = React.useState(0)
  const [isJobIdHydrated, setIsJobIdHydrated] = React.useState(true)
  const [actionError, setActionError] = React.useState<string | null>(null)
  const [previewPageInput, setPreviewPageInput] = React.useState("1")
  const [previewPageCount, setPreviewPageCount] = React.useState(0)
  const [previewFileIndex, setPreviewFileIndex] = React.useState(0)
  const [usePageRange, setUsePageRange] = React.useState(
    Boolean(pageStartInput.trim() || pageEndInput.trim())
  )
  const [retainProcessArtifacts, setRetainProcessArtifacts] = React.useState(false)
  const [showHomeLog, setShowHomeLog] = React.useState(false)

  const [jobs, setJobs] = React.useState<JobListItem[]>([])
  const lastTerminalToastRef = React.useRef<{
    jobId: string | null
    status: JobStatusValue | null
  }>({
    jobId: null,
    status: null,
  })

  const refreshSettingsSnapshot = React.useCallback(() => {
    setSettingsSnapshot(loadStoredSettings())
  }, [])

  const updateSettingsSnapshot = React.useCallback(
    (updater: (previous: Settings) => Settings) => {
      setSettingsSnapshot((previous) => {
        const next = updater(previous)
        if (typeof window !== "undefined") {
          window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(next))
        }
        return next
      })
    },
    []
  )

  const fetchJobs = React.useCallback(async (silent = true) => {
    try {
      const response = await apiFetch("/jobs?limit=50")
      if (!response.ok) {
        throw new Error("加载任务列表失败")
      }
      const body = (await response.json().catch(() => null)) as JobListResponse | null
      const normalized = normalizeJobListResponse(body)
      const rows = normalized.jobs
      setJobs(rows)
      setQueueSize(normalized.queueSize)
    } catch (e) {
      if (!silent) {
        setActionError(normalizeFetchError(e, "加载任务列表失败"))
      }
    }
  }, [])

  const fetchJobStatus = React.useCallback(async (targetJobId: string) => {
    const response = await apiFetch(`/jobs/${targetJobId}`)
    const body = (await response.json().catch(() => null)) as JobApiErrorBody
    if (!response.ok) {
      const err = new Error(
        body?.message || `查询任务状态失败（HTTP ${response.status}）`
      ) as JobStatusFetchError
      err.statusCode = response.status
      if (typeof body?.code === "string") {
        err.errorCode = body.code
      }
      throw err
    }
    if (!body || typeof body !== "object") {
      throw new Error("任务状态响应异常")
    }
    return normalizeJobStatusResponse(body)
  }, [])

  const onDrop = React.useCallback((accepted: File[]) => {
    if (accepted.length === 0) return
    addFiles(accepted)
    setActionError(null)
    setPreviewPageInput("1")
    setPreviewPageCount(0)
    setPreviewFileIndex(0)
    setUsePageRange(false)
  }, [addFiles])

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    accept: SUPPORTED_UPLOAD_ACCEPT,
    multiple: true,
    onDrop,
  })

  const currentPreviewFile = uploadFiles[previewFileIndex]?.file ?? null
  const isImageInput = isImageUploadFile(currentPreviewFile)

  const handleConvertAll = React.useCallback(async () => {
    if (fileCount === 0) return
    if (!user) {
      setActionError("请先登录后再创建任务")
      return
    }

    setActionError(null)

    const validation = validateRunConfig(settingsSnapshot)
    if (!validation.ok) {
      setActionError(validation.message || "配置校验失败")
      return
    }

    const effectiveUsePageRange = usePageRange && !isImageInput
    const pageStart = effectiveUsePageRange ? toIntOrUndefined(pageStartInput) : undefined
    const pageEnd = effectiveUsePageRange ? toIntOrUndefined(pageEndInput) : undefined
    if (effectiveUsePageRange && ((pageStart && !pageEnd) || (!pageStart && pageEnd))) {
      setActionError("页码范围请同时填写起始页和结束页")
      return
    }
    if (effectiveUsePageRange && pageStart && pageEnd && pageStart > pageEnd) {
      setActionError("页码范围错误：起始页不能大于结束页")
      return
    }

    const initialJobs: FileJobState[] = uploadFiles.map((entry) => ({
      file: entry.file,
      jobId: null,
      status: null,
      error: null,
      isSubmitting: true,
    }))
    setFileJobs(initialJobs)

    const jobConfig = buildJobConfig(settingsSnapshot, pageStart, pageEnd, {
      retainProcessArtifacts,
    })

    let successCount = 0
    let failCount = 0

    const submitOne = async (entry: FileJobState, index: number) => {
      try {
        const formData = new FormData()
        formData.append("file", entry.file)
        formData.append("config", JSON.stringify(jobConfig))
        const response = await apiFetch("/jobs/v2", {
          method: "POST",
          body: formData,
        })
        if (!response.ok) {
          throw new Error(await readResponseErrorMessage(response, "创建任务失败"))
        }
        const body = (await response.json().catch(() => null)) as { job_id?: string } | null
        const nextJobId = typeof body?.job_id === "string" ? body.job_id : ""
        if (!nextJobId) {
          throw new Error("创建任务失败：未返回任务号")
        }
        setFileJobs((prev) =>
          prev.map((j, i) =>
            i === index ? { ...j, jobId: nextJobId, isSubmitting: false } : j
          )
        )
        successCount++
      } catch (e) {
        const msg = normalizeFetchError(e, "创建任务失败")
        setFileJobs((prev) =>
          prev.map((j, i) =>
            i === index ? { ...j, error: msg, isSubmitting: false } : j
          )
        )
        failCount++
      }
    }

    await Promise.all(uploadFiles.map((_, i) => submitOne(initialJobs[i], i)))

    if (successCount > 0) {
      toast.success(`已提交 ${successCount} 个任务${failCount > 0 ? `，${failCount} 个失败` : ""}`)
    } else if (failCount > 0) {
      toast.error(`全部 ${failCount} 个任务提交失败`)
    }

    void fetchJobs(true)
  }, [
    fileCount,
    user,
    settingsSnapshot,
    usePageRange,
    isImageInput,
    pageStartInput,
    pageEndInput,
    retainProcessArtifacts,
    uploadFiles,
    fetchJobs,
  ])

  const handleCancelJob = React.useCallback(async (targetJobId: string) => {
    try {
      await apiFetch(`/jobs/${targetJobId}/cancel`, { method: "POST" })
      toast("已发送取消请求")
      void fetchJobs(true)
    } catch {
      toast.error("取消请求失败")
    }
  }, [fetchJobs])

  const handleDownload = React.useCallback(async (targetJobId: string) => {
    const response = await apiFetch(`/jobs/${targetJobId}/download`)
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new Error(body?.message || `下载失败（HTTP ${response.status}）`)
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

  const handleDownloadAll = React.useCallback(async () => {
    const completedJobs = fileJobs.filter((j) => j.status?.status === "completed" && j.jobId)
    if (completedJobs.length === 0) return
    for (const job of completedJobs) {
      try {
        await handleDownload(job.jobId!)
      } catch (e) {
        toast.error(`${job.file.name}: ${normalizeFetchError(e, "下载失败")}`)
      }
    }
  }, [fileJobs, handleDownload])

  const handleResetAll = React.useCallback(() => {
    clearUpload()
    setFileJobs([])
    setActionError(null)
    setRetainProcessArtifacts(false)
    setPreviewPageInput("1")
    setPreviewPageCount(0)
    setPreviewFileIndex(0)
    setUsePageRange(false)
    setPageStartInput("")
    setPageEndInput("")
  }, [clearUpload, setPageEndInput, setPageStartInput])

  const hasActiveJobs = fileJobs.some(
    (j) => j.isSubmitting || (j.jobId && j.status && !TERMINAL_JOB_STATUSES.has(j.status.status))
  )
  const allCompleted = fileJobs.length > 0 && fileJobs.every(
    (j) => j.status?.status === "completed" || j.error
  )
  const completedCount = fileJobs.filter((j) => j.status?.status === "completed").length
  const failedCount = fileJobs.filter((j) => j.error || j.status?.status === "failed").length

  // Poll all active jobs
  React.useEffect(() => {
    const activeJobIds = fileJobs
      .filter((j) => j.jobId && j.isSubmitting === false && (!j.status || !TERMINAL_JOB_STATUSES.has(j.status.status)))
      .map((j) => j.jobId!)
    if (activeJobIds.length === 0) return

    let mounted = true
    const timer = window.setInterval(async () => {
      if (!mounted) return
      for (const jid of activeJobIds) {
        try {
          const status = await fetchJobStatus(jid)
          if (!mounted) return
          setFileJobs((prev) =>
            prev.map((j) =>
              j.jobId === jid ? { ...j, status } : j
            )
          )
        } catch {
          // ignore poll errors
        }
      }
    }, 2000)

    return () => {
      mounted = false
      window.clearInterval(timer)
    }
  }, [fileJobs, fetchJobStatus])

  // Toast on terminal states
  React.useEffect(() => {
    const newlyCompleted = fileJobs.filter(
      (j) => j.status?.status === "completed" && j.jobId
    )
    if (newlyCompleted.length > 0 && newlyCompleted.length === completedCount && completedCount > 0) {
      const key = newlyCompleted.map((j) => j.jobId).join(",")
      if (lastTerminalToastRef.current.jobId !== key) {
        lastTerminalToastRef.current = { jobId: key, status: "completed" }
        if (newlyCompleted.length === fileJobs.length) {
          toast.success("全部转换完成！")
        } else {
          toast.success(`${newlyCompleted.length} 个文件转换完成`)
        }
      }
    }
  }, [fileJobs, completedCount])

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

  const overallProgress = fileJobs.length > 0
    ? Math.round(fileJobs.reduce((sum, j) => sum + (j.status?.progress || 0), 0) / fileJobs.length)
    : 0
  const inFlightJobs = jobs.filter((row) => row.status === "pending" || row.status === "processing").length
  const canStart = fileCount > 0 && !hasActiveJobs && Boolean(user)

  const [filePreviewUrl, setFilePreviewUrl] = React.useState("")
  React.useEffect(() => {
    if (!currentPreviewFile) {
      setFilePreviewUrl("")
      return
    }
    const nextUrl = URL.createObjectURL(currentPreviewFile)
    setFilePreviewUrl(nextUrl)
    return () => {
      URL.revokeObjectURL(nextUrl)
    }
  }, [currentPreviewFile])

  const previewPage = clampPositiveInt(toIntOrUndefined(previewPageInput) || 1, previewPageCount || undefined)
  const handlePreviewPageCommit = React.useCallback(
    (value: string) => {
      const raw = toIntOrUndefined(value) || 1
      const normalized = clampPositiveInt(raw, previewPageCount || undefined)
      setPreviewPageInput(String(normalized))
    },
    [previewPageCount]
  )
  const handlePreviewPageCountChange = React.useCallback((count: number) => {
    setPreviewPageCount(count)
    setPreviewPageInput((prev) =>
      String(clampPositiveInt(toIntOrUndefined(prev) || 1, count))
    )
  }, [])

  const editionDate = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Shanghai",
  }).format(new Date())

  // Stage logic
  const stage: "upload" | "preview" | "converting" = (() => {
    if (fileJobs.length > 0) return "converting"
    if (fileCount > 0) return "preview"
    return "upload"
  })()

  // Stepped progress for multi-file
  const stageSteps = React.useMemo(() => {
    const STEPS = [
      { code: "parsing", label: "解析" },
      { code: "ocr", label: "OCR" },
      { code: "generating", label: "生成" },
      { code: "done", label: "完成" },
    ] as const

    // Use the "average" stage across all active jobs
    const activeStatuses = fileJobs.filter((j) => j.status).map((j) => j.status!)
    if (activeStatuses.length === 0) {
      return STEPS.map((step, i) => ({ ...step, isDone: false, isCurrent: i === 0 }))
    }

    const avgFlowIndex = activeStatuses.reduce((sum, s) => sum + getJobStageFlowIndex(s.stage), 0) / activeStatuses.length
    const flowToStep = [0, 0, 1, 2, 2, 3, 3, 3]
    const currentStepIndex = avgFlowIndex >= 0 ? flowToStep[Math.round(avgFlowIndex)] ?? -1 : -1

    return STEPS.map((step, i) => {
      const isDone = currentStepIndex >= 0 && i < currentStepIndex
      const isCurrent = i === currentStepIndex
      return { ...step, isDone, isCurrent }
    })
  }, [fileJobs])

  return (
    <div className="min-h-dvh bg-background">
      <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
        <header className="flex items-center justify-between py-4">
          <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
            {editionDate} · 文档工作台
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="outline" className="text-xs">
              队列 {queueSize} · 执行中 {inFlightJobs}
            </Badge>
            <Button type="button" variant="ghost" size="sm" asChild>
              <Link href="/settings">设置</Link>
            </Button>
          </div>
        </header>

        <p className="sr-only" role="status" aria-live="polite">
          {fileJobs.length > 0
            ? `已提交 ${fileJobs.length} 个任务，完成 ${completedCount} 个`
            : "尚无进行中的任务"}
        </p>

        <main className="mt-2">
          {/* ── Stage 1: Upload (empty state) ── */}
          {stage === "upload" && (
            <div>
              {/* Hero section */}
              <div className="relative mx-auto max-w-3xl py-8 md:py-14">
                {/* Subtle gradient backdrop */}
                <div className="pointer-events-none absolute inset-0 -z-10 rounded-2xl bg-gradient-to-b from-[#cc0000]/[0.03] to-transparent" />

                <div className="mb-6 text-center">
                  <h1 className="font-serif text-3xl font-semibold tracking-tight md:text-4xl">
                    PDF2PPT
                  </h1>
                  <p className="mt-2 text-sm text-muted-foreground">
                    上传 PDF 或图片，自动生成演示文稿
                  </p>
                </div>

                <div
                  {...getRootProps()}
                  className={cn(
                    "group flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition-all",
                    "min-h-[240px]",
                    isDragActive && !isDragReject && "border-[#cc0000] bg-[#cc0000]/5 scale-[1.01]",
                    isDragReject && "border-destructive bg-destructive/10",
                    !isDragActive && !isDragReject && "border-border hover:border-[#cc0000]/50 hover:bg-muted/30",
                    (!user && !isAuthLoading) && "pointer-events-none opacity-60"
                  )}
                >
                  <input {...getInputProps()} />
                  <div className="mb-4 flex size-14 items-center justify-center rounded-full bg-[#cc0000]/10 transition-transform group-hover:scale-110">
                    <UploadCloudIcon className="size-7 text-[#cc0000]" />
                  </div>
                  <p className="text-lg font-medium">
                    {isDragActive ? "松开以上传文件" : "拖拽文件到这里"}
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    支持同时上传多个文件 · PDF / PNG / JPG / WebP
                  </p>
                  {!user && !isAuthLoading ? (
                    <p className="mt-3 text-xs text-destructive">请先登录后再上传文件</p>
                  ) : null}
                </div>

                {/* Quick config */}
                <div className="mt-5 flex flex-wrap items-center justify-center gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">模式</span>
                    <Select
                      value={settingsSnapshot.pptGenerationMode}
                      onChange={(e) =>
                        updateSettingsSnapshot((prev) => ({
                          ...prev,
                          pptGenerationMode: e.target.value as Settings["pptGenerationMode"],
                        }))
                      }
                      className="h-9 w-28"
                    >
                      <option value="turbo">{PPT_GENERATION_MODE_LABELS.turbo}</option>
                      <option value="fast">{PPT_GENERATION_MODE_LABELS.fast}</option>
                      <option value="standard">{PPT_GENERATION_MODE_LABELS.standard}</option>
                    </Select>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">OCR</span>
                    <Select
                      value={settingsSnapshot.ocrProvider}
                      onChange={(e) =>
                        updateSettingsSnapshot((prev) => ({
                          ...prev,
                          ocrProvider: e.target.value as Settings["ocrProvider"],
                        }))
                      }
                      className="h-9 w-32"
                    >
                      {Object.entries(ocrProviderLabels).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </Select>
                  </div>
                  <Link
                    href="/settings"
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                  >
                    高级设置 <ArrowRightIcon className="size-3" />
                  </Link>
                </div>
              </div>

              {/* Current config summary */}
              <div className="mx-auto mt-6 flex max-w-3xl flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
                <span>
                  解析引擎{" "}
                  <span className="font-medium text-foreground">
                    {PARSE_ENGINE_MODE_LABELS[settingsSnapshot.parseEngineMode]}
                  </span>
                </span>
                <span>
                  OCR{" "}
                  <span className="font-medium text-foreground">
                    {ocrProviderLabels[settingsSnapshot.ocrProvider]}
                  </span>
                </span>
                <span>
                  生成模式{" "}
                  <span className="font-medium text-foreground">
                    {PPT_GENERATION_MODE_LABELS[settingsSnapshot.pptGenerationMode]}
                  </span>
                </span>
                <Link
                  href="/settings"
                  className="text-[#cc0000] hover:underline"
                >
                  更改
                </Link>
              </div>
            </div>
          )}

          {/* ── Stage 2: Preview + Config (files uploaded) ── */}
          {stage === "preview" && (
            <div className="py-4">
              {/* Back to upload */}
              <div className="mb-4">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleResetAll}
                >
                  <ArrowLeftIcon className="mr-1 size-4" />
                  重新选择文件
                </Button>
              </div>

              {/* Dual-column layout */}
              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
                {/* Left: File list + PDF preview */}
                <div>
                  {/* File list */}
                  {fileCount > 1 && (
                    <div className="mb-4 space-y-2">
                      <div className="text-sm text-muted-foreground">
                        已选择 {fileCount} 个文件
                      </div>
                      <div className="grid gap-2">
                        {uploadFiles.map((entry, index) => (
                          <div
                            key={entry.file.name}
                            className={cn(
                              "flex items-center justify-between gap-3 rounded-md border px-3 py-2 transition-colors",
                              index === previewFileIndex
                                ? "border-[#cc0000]/40 bg-[#cc0000]/5"
                                : "hover:bg-muted/30"
                            )}
                          >
                            <button
                              type="button"
                              className="flex min-w-0 flex-1 items-center gap-2 text-left"
                              onClick={() => {
                                setPreviewFileIndex(index)
                                setPreviewPageInput("1")
                                setPreviewPageCount(0)
                              }}
                            >
                              <FileIcon className="size-4 shrink-0 text-muted-foreground" />
                              <span className="truncate text-sm">{entry.file.name}</span>
                              <span className="shrink-0 text-xs text-muted-foreground">
                                {formatBytes(entry.file.size)}
                              </span>
                            </button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon-xs"
                              onClick={() => {
                                removeFile(index)
                                if (previewFileIndex >= fileCount - 1) {
                                  setPreviewFileIndex(Math.max(0, fileCount - 2))
                                }
                              }}
                            >
                              <XIcon className="size-3" />
                            </Button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Single file info (when only 1 file) */}
                  {fileCount === 1 && currentPreviewFile && (
                    <div className="mb-4 flex items-center justify-between gap-3 rounded-md border px-3 py-2">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{currentPreviewFile.name}</div>
                        <div className="text-xs text-muted-foreground">{formatBytes(currentPreviewFile.size)}</div>
                      </div>
                      <Button type="button" variant="ghost" size="sm" onClick={handleResetAll}>
                        清空
                      </Button>
                    </div>
                  )}

                  {/* PDF preview */}
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <div className="text-sm text-muted-foreground">
                      文档预览
                      {fileCount > 1 && (
                        <span className="ml-2 text-xs">
                          ({previewFileIndex + 1}/{fileCount})
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-xs"
                        disabled={previewPage <= 1}
                        onClick={() => {
                          setPreviewPageInput(String(clampPositiveInt(previewPage - 1, previewPageCount || undefined)))
                        }}
                        aria-label="预览上一页"
                      >
                        <ChevronLeftIcon className="size-3" />
                      </Button>
                      <Input
                        inputMode="numeric"
                        value={previewPageInput}
                        onChange={(e) => setPreviewPageInput(e.target.value)}
                        onBlur={(e) => handlePreviewPageCommit(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault()
                            handlePreviewPageCommit((e.target as HTMLInputElement).value)
                          }
                        }}
                        className="h-8 w-20 text-center"
                        aria-label="当前预览页"
                      />
                      <span className="w-14 text-right font-mono text-xs text-muted-foreground">
                        / {previewPageCount || "?"}
                      </span>
                      <Button
                        type="button"
                        variant="outline"
                        size="icon-xs"
                        disabled={previewPageCount > 0 ? previewPage >= previewPageCount : true}
                        onClick={() => {
                          setPreviewPageInput(String(clampPositiveInt(previewPage + 1, previewPageCount || undefined)))
                        }}
                        aria-label="预览下一页"
                      >
                        <ChevronRightIcon className="size-3" />
                      </Button>
                    </div>
                  </div>

                  {filePreviewUrl ? (
                    <div className="home-preview-stage">
                      <PdfCanvasPreview
                        fileUrl={filePreviewUrl}
                        mimeType={currentPreviewFile?.type}
                        page={previewPage}
                        className="w-full"
                        onPageCountChange={handlePreviewPageCountChange}
                      />
                    </div>
                  ) : (
                    <div className="home-preview-stage home-preview-empty">
                      上传 PDF 或图片后会在这里显示预览
                    </div>
                  )}
                </div>

                {/* Right: Config + actions */}
                <div className="space-y-4">
                  {/* Page range */}
                  <div className="home-inline-panel px-4 py-3">
                    {isImageInput ? (
                      <p className="text-xs leading-6 text-muted-foreground">
                        图片输入自动包装成单页 PDF，无需设置页码范围。
                      </p>
                    ) : (
                      <>
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <label className="flex items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-[#111111]"
                              checked={usePageRange}
                              onChange={(e) => {
                                const enabled = e.target.checked
                                setUsePageRange(enabled)
                                if (!enabled) {
                                  setPageStartInput("")
                                  setPageEndInput("")
                                }
                              }}
                            />
                            限定页码范围
                          </label>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              type="button"
                              variant="outline"
                              size="xs"
                              disabled={!currentPreviewFile}
                              onClick={() => {
                                setUsePageRange(true)
                                const current = String(previewPage)
                                setPageStartInput(current)
                                setPageEndInput(current)
                              }}
                            >
                              单页试跑
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="xs"
                              onClick={() => {
                                setUsePageRange(false)
                                setPageStartInput("")
                                setPageEndInput("")
                              }}
                            >
                              整份
                            </Button>
                          </div>
                        </div>
                        {usePageRange ? (
                          <div className="mt-2 grid grid-cols-2 gap-2">
                            <div className="grid gap-1">
                              <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                                起始页
                              </label>
                              <Input
                                inputMode="numeric"
                                placeholder="1"
                                value={pageStartInput}
                                onChange={(e) => setPageStartInput(e.target.value)}
                                className="h-9"
                              />
                            </div>
                            <div className="grid gap-1">
                              <label className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                                结束页
                              </label>
                              <Input
                                inputMode="numeric"
                                placeholder="5"
                                value={pageEndInput}
                                onChange={(e) => setPageEndInput(e.target.value)}
                                className="h-9"
                              />
                            </div>
                          </div>
                        ) : null}
                      </>
                    )}
                  </div>

                  {/* Quick config */}
                  <div className="home-inline-panel px-4 py-3">
                    <div className="grid gap-3">
                      <div className="grid gap-1">
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                          <span>PPT 生成模式</span>
                          <HoverHint text="极速优先抢时间；快速适合日常转换；精准适合效果优先。" />
                        </div>
                        <Select
                          value={settingsSnapshot.pptGenerationMode}
                          onChange={(e) =>
                            updateSettingsSnapshot((prev) => ({
                              ...prev,
                              pptGenerationMode: e.target.value as Settings["pptGenerationMode"],
                            }))
                          }
                        >
                          <option value="turbo">{PPT_GENERATION_MODE_LABELS.turbo}</option>
                          <option value="fast">{PPT_GENERATION_MODE_LABELS.fast}</option>
                          <option value="standard">{PPT_GENERATION_MODE_LABELS.standard}</option>
                        </Select>
                      </div>
                      <div className="grid gap-1">
                        <div className="text-xs text-muted-foreground">OCR 方式</div>
                        <Select
                          value={settingsSnapshot.ocrProvider}
                          onChange={(e) =>
                            updateSettingsSnapshot((prev) => ({
                              ...prev,
                              ocrProvider: e.target.value as Settings["ocrProvider"],
                            }))
                          }
                        >
                          {Object.entries(ocrProviderLabels).map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                          ))}
                        </Select>
                      </div>
                      <label className="flex items-center gap-2 text-xs">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-[#111111]"
                          checked={retainProcessArtifacts}
                          onChange={(e) => setRetainProcessArtifacts(e.target.checked)}
                        />
                        <span className="flex items-center gap-1.5">
                          保留过程图
                          <HoverHint text="保留每页处理过程图，便于核对中间效果或排查问题。" />
                        </span>
                      </label>
                      <Link
                        href="/settings"
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                      >
                        高级设置 <ArrowRightIcon className="size-3" />
                      </Link>
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="space-y-2">
                    {!user && !isAuthLoading ? (
                      <Button type="button" variant="outline" className="w-full" asChild>
                        <Link href="/login">登录后创建任务</Link>
                      </Button>
                    ) : (
                      <>
                        <Button
                          type="button"
                          className="w-full"
                          onClick={handleConvertAll}
                          disabled={!canStart}
                        >
                          {fileCount > 1 ? `全部转换 (${fileCount} 个文件)` : "开始转换"}
                        </Button>
                        {fileCount === 1 && (
                          <Button
                            type="button"
                            variant="outline"
                            className="w-full"
                            onClick={() => {
                              setUsePageRange(true)
                              const current = String(previewPage)
                              setPageStartInput(current)
                              setPageEndInput(current)
                              void handleConvertAll()
                            }}
                            disabled={!canStart}
                          >
                            单页试跑（当前页）
                          </Button>
                        )}
                      </>
                    )}
                  </div>

                  {actionError ? (
                    <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
                      {actionError}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          )}

          {/* ── Stage 3: Progress + Download (converting/done) ── */}
          {stage === "converting" && (
            <div className="mx-auto max-w-2xl py-8 md:py-12">
              {/* Back button */}
              <div className="mb-6">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    if (!hasActiveJobs) {
                      handleResetAll()
                    }
                  }}
                  disabled={hasActiveJobs}
                >
                  <ArrowLeftIcon className="mr-1 size-4" />
                  返回
                </Button>
              </div>

              {/* Stepped progress indicator (for single file or aggregate) */}
              {fileJobs.length === 1 && (
                <div className="mb-8">
                  <div className="flex items-center">
                    {stageSteps.map((step, index) => {
                      const isDone = step.isDone
                      const isCurrent = step.isCurrent
                      const isLast = index === stageSteps.length - 1
                      return (
                        <React.Fragment key={step.code}>
                          <div className="flex flex-col items-center">
                            <div
                              className={cn(
                                "flex size-8 items-center justify-center rounded-full border-2 text-sm font-medium transition-colors",
                                isDone
                                  ? "border-[#cc0000] bg-[#cc0000] text-white"
                                  : isCurrent
                                    ? "border-[#cc0000] bg-white text-[#cc0000] animate-pulse"
                                    : "border-border bg-background text-muted-foreground"
                              )}
                            >
                              {isDone ? (
                                <CheckIcon className="size-4" />
                              ) : isCurrent ? (
                                <Loader2Icon className="size-4 animate-spin" />
                              ) : (
                                <span>{index + 1}</span>
                              )}
                            </div>
                            <span
                              className={cn(
                                "mt-2 text-xs",
                                isDone
                                  ? "font-medium text-[#cc0000]"
                                  : isCurrent
                                    ? "font-medium text-foreground"
                                    : "text-muted-foreground"
                              )}
                            >
                              {step.label}
                            </span>
                          </div>
                          {!isLast ? (
                            <div
                              className={cn(
                                "mx-1 mb-5 h-0.5 flex-1",
                                isDone ? "bg-[#cc0000]" : "bg-border"
                              )}
                            />
                          ) : null}
                        </React.Fragment>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Overall progress bar */}
              <Progress value={overallProgress} className="mb-3 h-2" />
              <div className="mb-6 text-center text-sm text-muted-foreground">
                {overallProgress}% · {completedCount}/{fileJobs.length} 完成
                {failedCount > 0 && <span className="ml-2 text-destructive">· {failedCount} 失败</span>}
              </div>

              {/* File job list */}
              <div className="mb-6 space-y-2">
                {fileJobs.map((fj, index) => {
                  const isDone = fj.status?.status === "completed"
                  const isFailed = Boolean(fj.error) || fj.status?.status === "failed"
                  const isCancelled = fj.status?.status === "cancelled"
                  const isActive = fj.isSubmitting || (fj.status && !TERMINAL_JOB_STATUSES.has(fj.status.status))
                  const stageLabel = fj.status?.stage
                    ? (JOB_STAGE_LABELS[fj.status.stage] ?? fj.status.stage)
                    : fj.isSubmitting ? "提交中…" : "等待中"

                  return (
                    <div
                      key={`${fj.file.name}-${index}`}
                      className={cn(
                        "flex items-center gap-3 rounded-md border px-3 py-2.5 transition-colors",
                        isDone && "border-green-200 bg-green-50/50",
                        isFailed && "border-destructive/30 bg-destructive/5",
                        isCancelled && "border-muted bg-muted/30",
                        isActive && "border-[#cc0000]/20 bg-[#cc0000]/[0.02]",
                        !isDone && !isFailed && !isCancelled && !isActive && "bg-muted/10"
                      )}
                    >
                      {/* Status icon */}
                      <div className="shrink-0">
                        {fj.isSubmitting ? (
                          <Loader2Icon className="size-4 animate-spin text-muted-foreground" />
                        ) : isDone ? (
                          <div className="flex size-4 items-center justify-center rounded-full bg-green-500">
                            <CheckIcon className="size-3 text-white" />
                          </div>
                        ) : isFailed ? (
                          <XIcon className="size-4 text-destructive" />
                        ) : isActive ? (
                          <Loader2Icon className="size-4 animate-spin text-[#cc0000]" />
                        ) : (
                          <div className="size-4 rounded-full border-2 border-muted-foreground/30" />
                        )}
                      </div>

                      {/* File info */}
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm">{fj.file.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {stageLabel}
                          {fj.status?.progress != null && fj.status.progress > 0 && ` · ${fj.status.progress}%`}
                        </div>
                      </div>

                      {/* Progress or actions */}
                      <div className="shrink-0 flex items-center gap-1.5">
                        {isDone && fj.jobId && (
                          <Button
                            type="button"
                            variant="outline"
                            size="xs"
                            onClick={async () => {
                              try {
                                await handleDownload(fj.jobId!)
                              } catch (e) {
                                toast.error(normalizeFetchError(e, "下载失败"))
                              }
                            }}
                          >
                            <DownloadIcon className="mr-1 size-3" />
                            下载
                          </Button>
                        )}
                        {isActive && fj.jobId && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="xs"
                            onClick={() => handleCancelJob(fj.jobId!)}
                          >
                            取消
                          </Button>
                        )}
                        {(isFailed || isCancelled) && (
                          <span className="text-xs text-muted-foreground">
                            {fj.error || fj.status?.error?.message || (isCancelled ? "已取消" : "失败")}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Action buttons */}
              <div className="flex flex-wrap items-center justify-center gap-3">
                {allCompleted && completedCount > 0 && (
                  <>
                    {completedCount > 1 ? (
                      <Button type="button" size="lg" onClick={handleDownloadAll}>
                        <DownloadIcon className="mr-2 size-5" />
                        全部下载 ({completedCount})
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        size="lg"
                        onClick={async () => {
                          const done = fileJobs.find((j) => j.status?.status === "completed" && j.jobId)
                          if (done?.jobId) {
                            try {
                              await handleDownload(done.jobId)
                            } catch (e) {
                              toast.error(normalizeFetchError(e, "下载失败"))
                            }
                          }
                        }}
                      >
                        <DownloadIcon className="mr-2 size-5" />
                        下载 PPTX
                      </Button>
                    )}
                  </>
                )}
                {!hasActiveJobs && (
                  <Button type="button" variant="outline" size="sm" onClick={handleResetAll}>
                    处理下一批文件
                  </Button>
                )}
              </div>

              {/* Cancel all button */}
              {hasActiveJobs && (
                <div className="mt-4 flex justify-center">
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    onClick={async () => {
                      const activeIds = fileJobs
                        .filter((j) => j.jobId && j.status && !TERMINAL_JOB_STATUSES.has(j.status.status))
                        .map((j) => j.jobId!)
                      for (const jid of activeIds) {
                        await handleCancelJob(jid)
                      }
                    }}
                  >
                    取消所有任务
                  </Button>
                </div>
              )}

              {/* Debug log toggle */}
              {fileJobs.some((j) => j.status?.debug_events?.length) ? (
                <div className="mt-6">
                  <div className="flex items-center justify-center">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setShowHomeLog((prev) => !prev)}
                    >
                      {showHomeLog ? "收起处理日志" : "查看处理日志"}
                    </Button>
                  </div>
                  {showHomeLog ? (
                    <div className="mt-3">
                      {fileJobs
                        .filter((j) => j.status?.debug_events?.length)
                        .map((j) => (
                          <div key={j.jobId} className="mb-3">
                            <div className="mb-1 text-xs text-muted-foreground">{j.file.name}</div>
                            <JobDebugPanel
                              events={j.status?.debug_events || []}
                              compact
                              className="animate-in fade-in slide-in-from-top-2 duration-300"
                            />
                          </div>
                        ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
