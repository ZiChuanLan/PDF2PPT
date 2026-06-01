"use client"

import * as React from "react"
import Link from "next/link"
import { toast } from "sonner"

import { useDropzone } from "react-dropzone"

import { apiFetch, normalizeFetchError, readResponseErrorMessage } from "@/lib/api"
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
  getJobStageFlowIndex,
  normalizeJobListResponse,
  normalizeJobStatusResponse,
  type JobListItem,
  type JobListResponse,
} from "@/lib/job-status"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useUploadSession } from "@/components/upload-session-provider"
import { useModelStatus, useEffectiveModelStatus } from "@/hooks/use-model-status"
import { useSSEJobTracking } from "@/hooks/use-sse-job-tracking"
import { useJobTerminalToast } from "@/hooks/use-job-terminal-toast"
import { useJobSubmission } from "@/hooks/use-job-submission"
import { UploadStage } from "@/components/home/upload-stage"
import { PreviewStage } from "@/components/home/preview-stage"
import { ConvertingStage } from "@/components/home/converting-stage"
import {
  clampPositiveInt,
  toIntOrUndefined,
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

export default function Home() {
  const { user, isLoading: isAuthLoading } = useAuth()
  const [settingsSnapshot, setSettingsSnapshot] = React.useState<Settings>(defaultSettings)
  const {
    files: uploadFiles,
    fileCount,
    pageStartInput,
    setPageStartInput,
    pageEndInput,
    setPageEndInput,
    addFiles,
    removeFile,
    clearUpload,
  } = useUploadSession()

  const [queueSize, setQueueSize] = React.useState(0)
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

  // Settings snapshot management
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

  // Job fetching + polling
  const fetchJobs = React.useCallback(async (silent = true) => {
    if (isAuthLoading) return
    if (!user) {
      setJobs([])
      setQueueSize(0)
      return
    }

    try {
      const response = await apiFetch(`/jobs?limit=${HOME_JOB_LIMIT}`)
      if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response, "加载任务列表失败"))
      }
      const body = (await response.json().catch(() => null)) as JobListResponse | null
      const normalized = normalizeJobListResponse(body)
      setJobs(normalized.jobs)
      setQueueSize(normalized.queueSize)
    } catch (e) {
      console.error("Failed to fetch jobs:", e)
      if (!silent) {
        setActionError(normalizeFetchError(e, "加载任务列表失败"))
      }
    }
  }, [isAuthLoading, user])

  const fetchJobStatus = React.useCallback(async (targetJobId: string) => {
    const response = await apiFetch(`/jobs/${targetJobId}`)
    const body = (await response.json().catch(() => null)) as JobApiErrorBody
    if (!response.ok) {
      const err = new Error(
        body?.message || `查询任务状态失败（HTTP ${response.status}）`
      ) as JobStatusFetchError
      err.statusCode = response.status
      if (typeof body?.code === "string") err.errorCode = body.code
      throw err
    }
    if (!body || typeof body !== "object") {
      throw new Error("任务状态响应异常")
    }
    return normalizeJobStatusResponse(body)
  }, [])

  // Dropzone
  const onDrop = React.useCallback((accepted: File[]) => {
    if (accepted.length === 0) return
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

  // File preview
  const currentPreviewFile = uploadFiles[previewFileIndex]?.file ?? null
  const isImageInput = isImageUploadFile(currentPreviewFile)

  // Model status
  const { data: backendModelStatus, isLoading: isModelStatusLoading, error: modelStatusError, refetch: refetchModelStatus } = useModelStatus()
  const modelStatus = useEffectiveModelStatus(backendModelStatus, settingsSnapshot)
  const [preflightAcknowledged, setPreflightAcknowledged] = React.useState(false)

  const downloadedLayoutModels = React.useMemo(() => {
    if (!modelStatus) return new Set<string>()
    return new Set(
      Object.entries(modelStatus.local)
        .filter(([key, p]) => p.ready && Object.keys(LAYOUT_MODELS).includes(key))
        .map(([key]) => key)
    )
  }, [modelStatus])

  // Job submission hook (extracted from inline handleConvertAll + related callbacks)
  const {
    fileJobs,
    setFileJobs,
    submitAllJobs,
    handleCancelJob,
    handleDownload,
    handleDownloadAll,
    hasActiveJobs,
    allCompleted,
    completedCount,
    failedCount,
    preflightWarning,
  } = useJobSubmission({
    uploadFiles: uploadFiles.map((entry) => ({ file: entry.file })),
    fileCount,
    user,
    settingsSnapshot,
    modelStatus,
    preflightAcknowledged,
    setPreflightAcknowledged,
    usePageRange,
    isImageInput,
    pageStartInput,
    pageEndInput,
    retainProcessArtifacts,
    fetchJobs,
  })

  // Terminal toast notifications (extracted from inline useEffect)
  useJobTerminalToast(fileJobs)

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
  }, [clearUpload, setFileJobs, setPageStartInput, setPageEndInput])

  // Job polling + initial setup
  React.useEffect(() => {
    refreshSettingsSnapshot()
    if (isAuthLoading) return

    void fetchJobs(false)
    if (!user) return

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
  }, [fetchJobs, isAuthLoading, refreshSettingsSnapshot, user])

  // SSE: subscribe to active job events
  useSSEJobTracking(fileJobs, setFileJobs, fetchJobStatus)

  // Derived UI state
  const overallProgress = fileJobs.length > 0
    ? Math.round(fileJobs.reduce((sum, j) => sum + (j.status?.progress || 0), 0) / fileJobs.length)
    : 0
  const inFlightJobs = jobs.filter((row) => row.status === "pending" || row.status === "processing").length
  const canStart = fileCount > 0 && !hasActiveJobs && Boolean(user)

  // File preview URL
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
  // Maps backend JobStage values (JOB_STAGE_FLOW) to frontend display steps.
  // flowToStep index corresponds to JOB_STAGE_FLOW index:
  //   0=queued, 1=parsing, 2=ocr, 3=pptx_generating, 4=packaging, 5=cleanup, 6=done
  // Step codes match backend JobStage values where possible for debuggability.
  const stageSteps = React.useMemo(() => {
    const STEPS = [
      { code: "parsing", label: "解析" },
      { code: "ocr", label: "OCR" },
      { code: "pptx_generating", label: "生成" },
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
              modelStatusError={modelStatusError}
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
              handleConvertAll={submitAllJobs}
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
