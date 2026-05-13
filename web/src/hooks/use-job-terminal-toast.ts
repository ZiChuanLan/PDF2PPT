"use client"

import * as React from "react"
import { toast } from "sonner"
import type { FileJobState } from "@/lib/job-types"

/**
 * Watches fileJobs for terminal statuses (completed, failed, cancelled)
 * and shows appropriate toast notifications.
 *
 * Extracted from page.tsx to reduce main component size.
 */
export function useJobTerminalToast(fileJobs: FileJobState[]): void {
  const lastTerminalToastRef = React.useRef<{
    jobId: string | null
    status: string | null
  }>({ jobId: null, status: null })

  // Toast when all jobs reach terminal state
  React.useEffect(() => {
    const completedJobs = fileJobs.filter((j) => j.status?.status === "completed" && j.jobId)
    const completedCount = completedJobs.length
    const failedJobs = fileJobs.filter((j) => j.error || j.status?.status === "failed")

    if (completedCount > 0) {
      const key = completedJobs.map((j) => j.jobId).join(",")
      if (lastTerminalToastRef.current.jobId !== key) {
        lastTerminalToastRef.current = { jobId: key, status: "completed" }
        if (completedCount === fileJobs.length) {
          toast.success("全部转换完成！")
        } else {
          toast.success(`${completedCount} 个文件转换完成`)
        }
      }
    }

    // Toast for failed jobs — show once per failed job
    for (const job of failedJobs) {
      const jobKey = job.jobId || `error-${job.file.name}`
      if (lastTerminalToastRef.current.jobId !== jobKey) {
        lastTerminalToastRef.current = { jobId: jobKey, status: "failed" }
        if (job.error) {
          toast.error(`${job.file.name}: ${job.error}`)
        } else {
          toast.error(`${job.file.name}: 转换失败`)
        }
      }
    }

    // Also handle cancelled status
    const cancelledJobs = fileJobs.filter((j) => j.status?.status === "cancelled" && j.jobId)
    for (const job of cancelledJobs) {
      const jobKey = `cancelled-${job.jobId}`
      if (lastTerminalToastRef.current.jobId !== jobKey) {
        lastTerminalToastRef.current = { jobId: jobKey, status: "cancelled" }
        toast(`${job.file.name}: 任务已取消`)
      }
    }
  }, [fileJobs])
}
