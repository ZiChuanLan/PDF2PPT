"use client"

import * as React from "react"
import {
  ArrowLeftIcon,
  CheckIcon,
  DownloadIcon,
  Loader2Icon,
  XIcon,
} from "lucide-react"
import { toast } from "sonner"

import { cn } from "@/lib/utils"
import { normalizeFetchError } from "@/lib/api"
import {
  JOB_STAGE_LABELS,
  TERMINAL_JOB_STATUSES,
} from "@/lib/job-status"
import { Button } from "@/components/ui/button"
import { JobDebugPanel } from "@/components/job-debug-panel"
import { Progress } from "@/components/ui/progress"
import type { FileJobState } from "@/lib/job-types"

interface StageStep {
  code: string
  label: string
  isDone: boolean
  isCurrent: boolean
}

interface ConvertingStageProps {
  fileJobs: FileJobState[]
  overallProgress: number
  completedCount: number
  failedCount: number
  hasActiveJobs: boolean
  allCompleted: boolean
  stageSteps: StageStep[]
  showHomeLog: boolean
  setShowHomeLog: (value: boolean) => void
  handleResetAll: () => void
  handleCancelJob: (jobId: string) => Promise<void>
  handleDownload: (jobId: string) => Promise<void>
  handleDownloadAll: () => Promise<void>
}

export function ConvertingStage({
  fileJobs,
  overallProgress,
  completedCount,
  failedCount,
  hasActiveJobs,
  allCompleted,
  stageSteps,
  showHomeLog,
  setShowHomeLog,
  handleResetAll,
  handleCancelJob,
  handleDownload,
  handleDownloadAll,
}: ConvertingStageProps) {
  return (
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
                          ? "border-destructive bg-destructive text-white"
                          : isCurrent
                            ? "border-destructive bg-white text-destructive animate-pulse"
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
                          ? "font-medium text-destructive"
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
                        isDone ? "bg-destructive" : "bg-border"
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
                isActive && "border-destructive/20 bg-destructive/[0.02]",
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
                  <Loader2Icon className="size-4 animate-spin text-destructive" />
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
                {fj.pollError && (
                  <div className="text-xs text-amber-600">{fj.pollError}</div>
                )}
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
              onClick={() => setShowHomeLog(!showHomeLog)}
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
  )
}
