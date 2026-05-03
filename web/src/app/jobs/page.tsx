"use client"

import * as React from "react"
import Link from "next/link"
import {
  ArrowLeftIcon,
  DownloadIcon,
  Loader2Icon,
  TrashIcon,
  XIcon,
} from "lucide-react"
import { toast } from "sonner"

import { cn } from "@/lib/utils"
import { apiFetch, normalizeFetchError } from "@/lib/api"
import {
  JOB_STAGE_LABELS,
  JOB_STATUS_LABELS,
  normalizeJobListResponse,
  TERMINAL_JOB_STATUSES,
  type JobListItem,
  type JobListResponse,
  type JobStatusValue,
} from "@/lib/job-status"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"

type StatusFilter = "all" | "processing" | "completed" | "failed"

const STATUS_FILTER_LABELS: Record<StatusFilter, string> = {
  all: "全部",
  processing: "进行中",
  completed: "已完成",
  failed: "失败",
}

function matchesFilter(job: JobListItem, filter: StatusFilter): boolean {
  if (filter === "all") return true
  if (filter === "processing") return job.status === "pending" || job.status === "processing"
  if (filter === "completed") return job.status === "completed"
  if (filter === "failed") return job.status === "failed"
  return true
}

function formatDate(isoString: string): string {
  try {
    const date = new Date(isoString)
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Shanghai",
    }).format(date)
  } catch {
    return isoString
  }
}

export default function JobsPage() {
  const [jobs, setJobs] = React.useState<JobListItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [activeFilter, setActiveFilter] = React.useState<StatusFilter>("all")
  const [selectedJobs, setSelectedJobs] = React.useState<Set<string>>(new Set())
  const [isDeleting, setIsDeleting] = React.useState(false)

  const fetchJobs = React.useCallback(async (silent = false) => {
    try {
      if (!silent) setIsLoading(true)
      setError(null)

      const response = await apiFetch("/jobs?limit=50")
      if (!response.ok) {
        throw new Error("加载任务列表失败")
      }

      const body = (await response.json().catch(() => null)) as JobListResponse | null
      const normalized = normalizeJobListResponse(body)
      setJobs(normalized.jobs)
    } catch (e) {
      setError(normalizeFetchError(e, "加载任务列表失败"))
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void fetchJobs(false)

    const onFocus = () => void fetchJobs(true)
    window.addEventListener("focus", onFocus)
    const timer = window.setInterval(() => void fetchJobs(true), 4000)

    return () => {
      window.removeEventListener("focus", onFocus)
      window.clearInterval(timer)
    }
  }, [fetchJobs])

  const filteredJobs = React.useMemo(
    () => jobs.filter((job) => matchesFilter(job, activeFilter)),
    [jobs, activeFilter]
  )

  const hasActiveJobs = React.useMemo(
    () => jobs.some((job) => !TERMINAL_JOB_STATUSES.has(job.status)),
    [jobs]
  )

  const handleSelectAll = React.useCallback(() => {
    if (selectedJobs.size === filteredJobs.length) {
      setSelectedJobs(new Set())
    } else {
      setSelectedJobs(new Set(filteredJobs.map((job) => job.job_id)))
    }
  }, [filteredJobs, selectedJobs.size])

  const handleToggleSelect = React.useCallback((jobId: string) => {
    setSelectedJobs((prev) => {
      const next = new Set(prev)
      if (next.has(jobId)) {
        next.delete(jobId)
      } else {
        next.add(jobId)
      }
      return next
    })
  }, [])

  const handleDelete = React.useCallback(async (jobId: string) => {
    if (!confirm("确定要删除这个任务吗？")) return

    try {
      const response = await apiFetch(`/jobs/${jobId}`, { method: "DELETE" })
      if (!response.ok) {
        throw new Error("删除失败")
      }
      toast.success("任务已删除")
      void fetchJobs(true)
    } catch (e) {
      toast.error(normalizeFetchError(e, "删除失败"))
    }
  }, [fetchJobs])

  const handleBatchDelete = React.useCallback(async () => {
    if (selectedJobs.size === 0) return
    if (!confirm(`确定要删除选中的 ${selectedJobs.size} 个任务吗？`)) return

    setIsDeleting(true)
    let successCount = 0
    let failCount = 0

    for (const jobId of selectedJobs) {
      try {
        const response = await apiFetch(`/jobs/${jobId}`, { method: "DELETE" })
        if (response.ok) {
          successCount++
        } else {
          failCount++
        }
      } catch {
        failCount++
      }
    }

    setIsDeleting(false)
    setSelectedJobs(new Set())

    if (successCount > 0) {
      toast.success(`成功删除 ${successCount} 个任务`)
    }
    if (failCount > 0) {
      toast.error(`删除失败 ${failCount} 个任务`)
    }

    void fetchJobs(true)
  }, [selectedJobs, fetchJobs])

  const handleCancel = React.useCallback(async (jobId: string) => {
    try {
      const response = await apiFetch(`/jobs/${jobId}/cancel`, { method: "POST" })
      if (!response.ok) {
        throw new Error("取消失败")
      }
      toast.success("已发送取消请求")
      void fetchJobs(true)
    } catch (e) {
      toast.error(normalizeFetchError(e, "取消失败"))
    }
  }, [fetchJobs])

  const handleDownload = React.useCallback(async (jobId: string) => {
    try {
      const response = await apiFetch(`/jobs/${jobId}/download`)
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.message || `下载失败（HTTP ${response.status}）`)
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `output-${jobId.slice(0, 8)}.pptx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
    } catch (e) {
      toast.error(normalizeFetchError(e, "下载失败"))
    }
  }, [])

  return (
    <div className="min-h-dvh bg-background">
      <div className="mx-auto w-full max-w-screen-xl px-4 py-6 md:py-10">
        <header className="flex items-center justify-between py-4">
          <div className="flex items-center gap-3">
            <Button type="button" variant="ghost" size="sm" asChild>
              <Link href="/">
                <ArrowLeftIcon className="mr-1 size-4" />
                返回首页
              </Link>
            </Button>
            <div className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              任务记录
            </div>
          </div>
          <Badge variant="outline" className="text-xs">
            共 {jobs.length} 个任务
          </Badge>
        </header>

        <main className="mt-4">
          {/* Status filter tabs */}
          <div className="mb-6 flex flex-wrap gap-2">
            {(Object.entries(STATUS_FILTER_LABELS) as [StatusFilter, string][]).map(
              ([filter, label]) => (
                <Button
                  key={filter}
                  type="button"
                  variant={activeFilter === filter ? "default" : "outline"}
                  size="sm"
                  onClick={() => {
                    setActiveFilter(filter)
                    setSelectedJobs(new Set())
                  }}
                >
                  {label}
                </Button>
              )
            )}
          </div>

          {/* Batch operations */}
          {filteredJobs.length > 0 && (
            <div className="mb-4 flex items-center gap-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[#111111]"
                  checked={selectedJobs.size === filteredJobs.length && filteredJobs.length > 0}
                  onChange={handleSelectAll}
                />
                全选
              </label>
              {selectedJobs.size > 0 && (
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={handleBatchDelete}
                  disabled={isDeleting}
                >
                  {isDeleting ? (
                    <Loader2Icon className="mr-1 size-4 animate-spin" />
                  ) : (
                    <TrashIcon className="mr-1 size-4" />
                  )}
                  批量删除 ({selectedJobs.size})
                </Button>
              )}
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
            </div>
          )}

          {/* Error state */}
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && !error && filteredJobs.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="text-sm text-muted-foreground">
                {activeFilter === "all" ? "暂无任务记录" : "没有符合条件的任务"}
              </div>
              {activeFilter === "all" && (
                <Button type="button" variant="outline" size="sm" className="mt-4" asChild>
                  <Link href="/">去创建任务</Link>
                </Button>
              )}
            </div>
          )}

          {/* Job cards */}
          {!isLoading && !error && filteredJobs.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filteredJobs.map((job) => {
                const isTerminal = TERMINAL_JOB_STATUSES.has(job.status)
                const isSelected = selectedJobs.has(job.job_id)
                const stageLabel = JOB_STAGE_LABELS[job.stage] ?? job.stage
                const statusLabel = JOB_STATUS_LABELS[job.status]

                return (
                  <div
                    key={job.job_id}
                    className={cn(
                      "relative border bg-card p-4 transition-colors",
                      isSelected && "border-[#cc0000] bg-[#cc0000]/5"
                    )}
                  >
                    {/* Checkbox */}
                    <div className="absolute right-3 top-3">
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-[#111111]"
                        checked={isSelected}
                        onChange={() => handleToggleSelect(job.job_id)}
                      />
                    </div>

                    {/* Status badge and job ID */}
                    <div className="mb-3 flex items-center gap-2">
                      <Badge
                        variant={
                          job.status === "completed"
                            ? "default"
                            : job.status === "failed"
                              ? "destructive"
                              : job.status === "cancelled"
                                ? "outline"
                                : "secondary"
                        }
                        className="text-xs"
                      >
                        {statusLabel}
                      </Badge>
                      <span className="font-mono text-xs text-muted-foreground">
                        任务号: {job.job_id.slice(0, 8)}
                      </span>
                    </div>

                    {/* Progress bar */}
                    <div className="mb-2">
                      <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                        <span>进度</span>
                        <span>{job.progress}%</span>
                      </div>
                      <Progress value={job.progress} className="h-1.5" />
                    </div>

                    {/* Stage */}
                    <div className="mb-1 text-xs text-muted-foreground">
                      阶段: {stageLabel}
                    </div>

                    {/* Created time */}
                    <div className="mb-3 text-xs text-muted-foreground">
                      创建: {formatDate(job.created_at)}
                    </div>

                    {/* Action buttons */}
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        asChild
                      >
                        <Link href={`/tracking?job=${job.job_id}`}>跟踪</Link>
                      </Button>

                      {job.status === "completed" && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => handleDownload(job.job_id)}
                        >
                          <DownloadIcon className="mr-1 size-3" />
                          下载
                        </Button>
                      )}

                      {(job.status === "pending" || job.status === "processing") && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => handleCancel(job.job_id)}
                        >
                          <XIcon className="mr-1 size-3" />
                          取消
                        </Button>
                      )}

                      {isTerminal && (
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          onClick={() => handleDelete(job.job_id)}
                        >
                          <TrashIcon className="mr-1 size-3" />
                          删除
                        </Button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* Auto-refresh indicator */}
          {hasActiveJobs && (
            <div className="mt-6 flex items-center justify-center gap-2 text-xs text-muted-foreground">
              <Loader2Icon className="size-3 animate-spin" />
              <span>自动刷新中</span>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
