"use client"

import * as React from "react"
import { toast } from "sonner"
import type { FileJobState } from "@/lib/job-types"
import type { Settings } from "@/lib/settings"
import { apiFetch, normalizeFetchError, readResponseErrorMessage } from "@/lib/api"
import { downloadJobOutput } from "@/lib/download-utils"
import { buildJobConfig, validateRunConfig } from "@/lib/run-config"
import { TERMINAL_JOB_STATUSES } from "@/lib/job-status"
import { LAYOUT_MODELS } from "@/lib/layout-models"

type FileEntry = { file: File }

type UseJobSubmissionParams = {
  uploadFiles: FileEntry[]
  fileCount: number
  user: unknown
  settingsSnapshot: Settings
  modelStatus: unknown
  preflightAcknowledged: boolean
  setPreflightAcknowledged: (v: boolean) => void
  usePageRange: boolean
  isImageInput: boolean
  pageStartInput: string
  pageEndInput: string
  retainProcessArtifacts: boolean
  fetchJobs: (silent?: boolean) => Promise<void>
}

export type UseJobSubmissionReturn = {
  fileJobs: FileJobState[]
  setFileJobs: React.Dispatch<React.SetStateAction<FileJobState[]>>
  submitAllJobs: () => Promise<void>
  handleCancelJob: (jobId: string) => Promise<void>
  handleDownload: (jobId: string) => Promise<void>
  handleDownloadAll: () => Promise<void>
  hasActiveJobs: boolean
  allCompleted: boolean
  completedCount: number
  failedCount: number
  preflightWarning: string | null
  handleResetAll: () => void
}

function toIntOrUndefined(value: string): number | undefined {
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const n = Number(trimmed)
  return Number.isFinite(n) ? Math.floor(n) : undefined
}

/**
 * Encapsulates job submission, cancellation, and download logic.
 *
 * Extracted from page.tsx (handleConvertAll was 115 lines with 16 closure
 * dependencies) to keep the main component focused on layout and composition.
 */
export function useJobSubmission(params: UseJobSubmissionParams): UseJobSubmissionReturn {
  const {
    uploadFiles,
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
  } = params

  const [fileJobs, setFileJobs] = React.useState<FileJobState[]>([])
  const [preflightWarning, setPreflightWarning] = React.useState<string | null>(null)

  const submitAllJobs = React.useCallback(async () => {
    if (fileCount === 0) return
    if (!user) {
      return // Auth guard handled by caller
    }

    setPreflightWarning(null)

    const validation = validateRunConfig(settingsSnapshot)
    if (!validation.ok) {
      toast.error(validation.message || "配置校验失败")
      return
    }

    // Pre-flight check: warn if required models aren't ready
    if (modelStatus && !preflightAcknowledged) {
      const status = modelStatus as {
        local: Record<string, { ready: boolean }>
        remote: Record<string, { ready: boolean }>
      }
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
        const bucket = p.kind === "local" ? status.local : status.remote
        const s = bucket[p.key]
        return !s || !s.ready
      })
      if (notReady.length > 0) {
        const names = notReady.map((p) => p.label).join("、")
        setPreflightWarning(`${names} 未就绪，任务可能在运行时失败。是否继续？`)
        return
      }

      // Pre-flight check: warn only when the selected route actually uses a local layout model.
      const localOcrProvider = settingsSnapshot.ocrProvider || "machine"
      const requiresLayoutModel =
        (mode === "local_ocr" && localOcrProvider !== "tesseract") ||
        (mode === "remote_ocr" && settingsSnapshot.ocrAiChainMode === "layout_block")
      if (requiresLayoutModel) {
        const selectedLayoutModel = settingsSnapshot.ocrAiLayoutModel || "pp_doclayout_v3"
        const layoutModelInfo = LAYOUT_MODELS[selectedLayoutModel]
        if (layoutModelInfo) {
          const localEntry = status.local[selectedLayoutModel]
          if (!localEntry || !localEntry.ready) {
            setPreflightWarning(`版面模型 ${layoutModelInfo.displayName} 未下载，任务可能在运行时失败。是否继续？`)
            return
          }
        }
      }
    }
    setPreflightAcknowledged(false)

    const effectiveUsePageRange = usePageRange && !isImageInput
    const pageStart = effectiveUsePageRange ? toIntOrUndefined(pageStartInput) : undefined
    const pageEnd = effectiveUsePageRange ? toIntOrUndefined(pageEndInput) : undefined
    if (effectiveUsePageRange && ((pageStart && !pageEnd) || (!pageStart && pageEnd))) {
      toast.error("页码范围请同时填写起始页和结束页")
      return
    }
    if (effectiveUsePageRange && pageStart && pageEnd && pageStart > pageEnd) {
      toast.error("页码范围错误：起始页不能大于结束页")
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
    setPreflightAcknowledged,
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
    setFileJobs([])
  }, [])

  // Derived state
  const hasActiveJobs = React.useMemo(() =>
    fileJobs.some(
      (j) => j.isSubmitting || (j.jobId && j.status && !TERMINAL_JOB_STATUSES.has(j.status.status))
    ),
    [fileJobs]
  )

  const allCompleted = React.useMemo(() =>
    fileJobs.length > 0 && fileJobs.every(
      (j) => j.status?.status === "completed" || j.error
    ),
    [fileJobs]
  )

  const completedCount = React.useMemo(() =>
    fileJobs.filter((j) => j.status?.status === "completed").length,
    [fileJobs]
  )

  const failedCount = React.useMemo(() =>
    fileJobs.filter((j) => j.error || j.status?.status === "failed").length,
    [fileJobs]
  )

  return {
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
    handleResetAll,
  }
}
