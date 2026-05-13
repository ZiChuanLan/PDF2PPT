"use client"

import * as React from "react"

import {
  JOB_STAGE_LABELS,
  QUEUE_STATE_LABELS,
  type JobStatusResponse,
} from "@/lib/job-status"

export type TrackedJobDetail = (JobStatusResponse & {
  queue_position?: number | null
  queue_state?: string | null
}) | null

/**
 * Compact job detail card showing stage, progress, error message, and queue info.
 */
export function JobDetailCard({ detail }: { detail: TrackedJobDetail }) {
  if (!detail) return null

  const errorMessage =
    detail.status === "failed" &&
    typeof detail.error?.message === "string" &&
    detail.error.message.trim()
      ? detail.error.message.trim()
      : null

  const infoMessage =
    detail.message && detail.message.trim() ? detail.message : null

  return (
    <div className="mt-3 grid gap-1 border border-border bg-muted/40 px-3 py-2">
      <div className="text-xs text-muted-foreground">
        {JOB_STAGE_LABELS[detail.stage] || detail.stage} ·{" "}
        {detail.progress}%
      </div>
      {errorMessage ? (
        <div className="text-xs text-muted-foreground">{errorMessage}</div>
      ) : infoMessage ? (
        <div className="text-xs text-muted-foreground">{infoMessage}</div>
      ) : null}
      {detail.queue_state === "queued" &&
      typeof detail.queue_position === "number" ? (
        <div className="font-mono text-[11px] text-muted-foreground">
          排队位置：第 {detail.queue_position} 位
        </div>
      ) : detail.queue_state ? (
        <div className="font-mono text-[11px] text-muted-foreground">
          队列状态：
          {QUEUE_STATE_LABELS[detail.queue_state] || detail.queue_state}
        </div>
      ) : null}
    </div>
  )
}
