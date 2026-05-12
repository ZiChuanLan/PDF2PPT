"use client"

import * as React from "react"
import Link from "next/link"
import { toast } from "sonner"

import { useDropzone } from "react-dropzone"

import { cn } from "@/lib/utils"
import { apiFetch, normalizeFetchError, readResponseErrorMessage } from "@/lib/api"
import { downloadJobOutput } from "@/lib/download-utils"
import { useAuth } from "@/components/auth-provider"
import { HOME_JOB_LIMIT, JOB_LIST_POLL_INTERVAL_MS } from "@/lib/constants"
import { LAYOUT_MODELS } from "@/lib/layout-models"
import {
  defaultSettings,
  loadStoredSettings,
  SETTINGS_STORAGE_KEY,
  type Settings,
} from "@/lib/settings"
import {
  buildJobConfig,
  validateRunConfig,
} from "@/lib/run-config"
import {
  getJobStageFlowIndex,
  normalizeJobListResponse,
  normalizeJobStatusResponse,
  TERMINAL_JOB_STATUSES,
  type JobListItem,
  type JobListResponse,
  type JobStatusValue,
} from "@/lib/job-status"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useUploadSession } from "@/components/upload-session-provider"
import { useModelStatus, useEffectiveModelStatus } from "@/hooks/use-model-status"
import { useSSEJobTracking } from "@/hooks/use-sse-job-tracking"
import type { FileJobState } from "@/lib/job-types"
import { UploadStage } from "@/components/home/upload-stage"
import { PreviewStage } from "@/components/home/preview-stage"
import { ConvertingStage } from "@/components/home/converting-stage"
import {
  formatBytes,
  toIntOrUndefined,
  clampPositiveInt,
  isImageUploadFile,
  SUPPORTED_UPLOAD_ACCEPT,
} from "@/lib/home-utils"

type JobApiErrorBody = {
  code?: string
  message?: string
} | null

type JobStatusFetchError = Error & {
  statusCode?: number
  errorCode?: string
}

const HOME_ACTIVE_JOB_STORAGE_KEY = "ppt-opencode:home:active-job-id"

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

  // Clamp previewFileIndex when file count changes (e.g., after removal)
  React.useEffect(() => {
    if (fileCount === 0) {
      setPreviewFileIndex(0)
    } else if (previewFileIndex >= fileCount) {
      setPreviewFileIndex(fileCount - 1)
    }
  }, [fileCount, previewFileIndex])

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
      const response = await apiFetch(`/jobs?limit=${HOME_JOB_LIMIT}`)
      if (!response.ok) {
        throw new Error("加载任务列表失败")
      }
      const body = (await response.json().catch(() => null)) as JobListResponse | null
      const normalized = normalizeJobListResponse(body)
      const rows = normalized.jobs
      setJobs(rows)
      setQueueSize(normalized.queueSize)
    } catch (e) {
      console.error("Failed to fetch jobs:", e)
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

    // Frontend file size check (100MB default, matches backend)
    const MAX_FILE_SIZE_MB = 100
    const oversized = accepted.filter((f) => f.size > MAX_FILE_SIZE_MB * 1024 * 1024)
    if (oversized.length > 0) {
      const names = oversized.map((f) => f.name).join(", ")
      toast.error(`文件过大（超过 ${MAX_FILE_SIZE_MB}MB）: ${names}`)
      return
    }

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

  const { data: backendModelStatus, isLoading: isModelStatusLoading, refetch: refetchModelStatus } = useModelStatus()
  const modelStatus = useEffectiveModelStatus(backendModelStatus, settingsSnapshot)
  const [preflightWarning, setPreflightWarning] = React.useState<string | null>(null)
  const [preflightAcknowledged, setPreflightAcknowledged] = React.useState(false)

  const downloadedLayoutModels = React.useMemo(() => {
    if (!modelStatus) return new Set<string>()
    return new Set(
      Object.entries(modelStatus.local)
        .filter(([key, p]) => p.ready && Object.keys(LAYOUT_MODELS).includes(key))
        .map(([key]) => key)
    )
  }, [modelStatus])

  const handleConvertAll = React.useCallback(async () => {
    if (fileCount === 0) return
    if (!user) {
      setActionError("请先登录后再创建任务")
      return
    }

    setActionError(null)
    setPreflightWarning(null)

    const validation = validateRunConfig(settingsSnapshot)
    if (!validation.ok) {
      setActionError(validation.message || "配置校验失败")
      return
    }

    // Pre-flight check: warn if required models aren't ready
    if (modelStatus && !preflightAcknowledged) {
      const mode = settingsSnapshot.parseEngineMode
      const requiredProviders: Array<{ key: string; kind: "local" | "remote"; label: string }> = []
      if (mode === "local_ocr") {
        const ocrKey = settingsSnapshot.ocrProvider === "tesseract" ? "tesseract" : "paddleocr"
        const ocrLabel = settingsSnapshot.ocrProvider === "tesseract" ? "Tesseract" : "PaddleOCR"
        requiredProviders.push({ key: ocrKey, kind: "local", label: ocrLabel })
      } else if (mode === "remote_ocr") {
        requiredProviders.push({ key: "aiocr", kind: "remote", label: "AIOCR" })
      } else if (mode === "baidu_doc") {
        requiredProviders.push({ key: "baidu_doc", kind: "remote", label: "百度文档解析" })
      } else if (mode === "mineru_cloud") {
        requiredProviders.push({ key: "mineru", kind: "remote", label: "MinerU" })
      }
      const notReady = requiredProviders.filter((p) => {
        const bucket = p.kind === "local" ? modelStatus.local : modelStatus.remote
        const status = bucket[p.key]
        return !status || !status.ready
      })
      if (notReady.length > 0) {
        const names = notReady.map((p) => p.label).join("、")
        setPreflightWarning(`${names} 未就绪，任务可能在运行时失败。是否继续？`)
        return
      }
    }
    setPreflightAcknowledged(false)

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
      pollError: null,
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
    modelStatus,
    preflightAcknowledged,
  ])

  const handleCancelJob = React.useCallback(async (targetJobId: string) => {
    try {
      await apiFetch(`/jobs/${targetJobId}/cancel`, { method: "POST" })
      toast("已发送取消请求")
      void fetchJobs(true)
    } catch (e) {
      console.error("Failed to cancel job:", e)
      toast.error("取消请求失败")
    }
  }, [fetchJobs])

  const handleDownload = React.useCallback(async (targetJobId: string) => {
    try {
      await downloadJobOutput(targetJobId)
    } catch (e) {
      toast.error(normalizeFetchError(e, "下载失败"))
    }
  }, [])

  const handleDownloadAll = React.useCallback(async () => {
    const completedJobs = fileJobs.filter((j) => j.status?.status === "completed" && j.jobId)
    if (completedJobs.length === 0) return
    const results = await Promise.allSettled(
      completedJobs.map((job) => handleDownload(job.jobId!))
    )
    results.forEach((result, i) => {
      if (result.status === "rejected") {
        toast.error(`${completedJobs[i].file.name}: ${normalizeFetchError(result.reason, "下载失败")}`)
      }
    })
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

  // SSE: subscribe to active job events
  useSSEJobTracking(fileJobs, setFileJobs, fetchJobStatus);

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
    }, JOB_LIST_POLL_INTERVAL_MS)

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
          <div>
            <h1 className="font-serif text-2xl leading-tight tracking-tight">PDF2PPT 工作台</h1>
            <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              {editionDate} · 文档工作台
            </div>
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

        <section className="mt-2">
          {stage === "upload" && (
            <UploadStage
              getRootProps={getRootProps}
              getInputProps={getInputProps}
              isDragActive={isDragActive}
              isDragReject={isDragReject}
              settingsSnapshot={settingsSnapshot}
              updateSettingsSnapshot={updateSettingsSnapshot}
            />
          )}

          {stage === "preview" && (
            <PreviewStage
              uploadFiles={uploadFiles}
              fileCount={fileCount}
              currentPreviewFile={currentPreviewFile}
              previewFileIndex={previewFileIndex}
              setPreviewFileIndex={setPreviewFileIndex}
              previewPageInput={previewPageInput}
              setPreviewPageInput={setPreviewPageInput}
              previewPageCount={previewPageCount}
              handlePreviewPageCommit={handlePreviewPageCommit}
              handlePreviewPageCountChange={handlePreviewPageCountChange}
              isImageInput={isImageInput}
              settingsSnapshot={settingsSnapshot}
              updateSettingsSnapshot={updateSettingsSnapshot}
              modelStatus={modelStatus}
              isModelStatusLoading={isModelStatusLoading}
              refetchModelStatus={refetchModelStatus}
              usePageRange={usePageRange}
              setUsePageRange={setUsePageRange}
              pageStartInput={pageStartInput}
              setPageStartInput={setPageStartInput}
              pageEndInput={pageEndInput}
              setPageEndInput={setPageEndInput}
              retainProcessArtifacts={retainProcessArtifacts}
              setRetainProcessArtifacts={setRetainProcessArtifacts}
              handleResetAll={handleResetAll}
              handleConvertAll={handleConvertAll}
              canStart={canStart}
              actionError={actionError}
              preflightWarning={preflightWarning}
              setPreflightAcknowledged={setPreflightAcknowledged}
              downloadedLayoutModels={downloadedLayoutModels}
              removeFile={removeFile}
              filePreviewUrl={filePreviewUrl}
              previewPage={previewPage}
            />
          )}

          {stage === "converting" && (
            <ConvertingStage
              fileJobs={fileJobs}
              overallProgress={overallProgress}
              completedCount={completedCount}
              failedCount={failedCount}
              hasActiveJobs={hasActiveJobs}
              allCompleted={allCompleted}
              stageSteps={stageSteps}
              showHomeLog={showHomeLog}
              setShowHomeLog={setShowHomeLog}
              handleResetAll={handleResetAll}
              handleCancelJob={handleCancelJob}
              handleDownload={handleDownload}
              handleDownloadAll={handleDownloadAll}
            />
          )}
        </section>
      </div>
    </div>
  )
}
