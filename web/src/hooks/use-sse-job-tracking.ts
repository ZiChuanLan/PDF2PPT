import { useEffect, useMemo, useRef } from "react";
import { FileJobState } from "@/lib/job-types";
import { createJobEventSource } from "@/lib/api";
import { SSE_RECONNECT_BASE_MS } from "@/lib/constants";
import { TERMINAL_JOB_STATUSES, type JobStatusResponse, type JobStatusValue } from "@/lib/job-status";

export function useSSEJobTracking(
  fileJobs: FileJobState[],
  setFileJobs: (value: React.SetStateAction<FileJobState[]>) => void,
  fetchJobStatusFn: (jobId: string) => Promise<JobStatusResponse>,
): void {
  const activeJobIdsKey = useMemo(
    () =>
      fileJobs
        .filter(
          (j) =>
            j.jobId &&
            j.isSubmitting === false &&
            (!j.status || !TERMINAL_JOB_STATUSES.has(j.status.status)),
        )
        .map((j) => j.jobId!)
        .join(","),
    [fileJobs],
  );

  const sseClosers = useRef<Map<string, EventSource>>(new Map());
  const reconnectTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const reconnectAttempts = useRef<Map<string, number>>(new Map());
  const mounted = useRef(true);

  // SSE: subscribe to active job events
  useEffect(() => {
    const activeJobIds = activeJobIdsKey.split(",").filter(Boolean);
    if (activeJobIds.length === 0) return;

    mounted.current = true;

    // Reset Maps for this effect invocation
    sseClosers.current = new Map();
    reconnectTimers.current = new Map();
    reconnectAttempts.current = new Map();

    const MAX_BACKOFF_MS = 30_000;

    function setupSseForJob(jid: string): void {
      const es = createJobEventSource(jid);
      sseClosers.current.set(jid, es);

      es.onmessage = async (event) => {
        if (!mounted.current) return;
        // Reset backoff on successful delivery.
        reconnectAttempts.current.set(jid, 0);
        try {
          const data = JSON.parse(event.data);
          const status = data.status as JobStatusValue;
          const stage = data.stage as string;
          const progress = data.progress as number;
          const message = data.message as string | null;
          const error = data.error as { code?: string; message?: string } | null;

          setFileJobs((prev) =>
            prev.map((j) => {
              if (j.jobId !== jid) return j;
              const updated: FileJobState = {
                ...j,
                pollError: null,
                status: j.status
                  ? {
                      ...j.status,
                      status,
                      stage,
                      progress,
                      message: message ?? j.status.message,
                      error: error ?? j.status.error,
                    }
                  : {
                      job_id: jid,
                      status,
                      stage,
                      progress,
                      created_at: "",
                      expires_at: "",
                      message,
                      error,
                      debug_events: [],
                    },
              };
              return updated;
            }),
          );

          // On terminal state, fetch full response (includes debug_events)
          if (TERMINAL_JOB_STATUSES.has(status)) {
            try {
              const full = await fetchJobStatusFn(jid);
              if (mounted.current) {
                setFileJobs((prev) =>
                  prev.map((j) => (j.jobId === jid ? { ...j, status: full } : j)),
                );
              }
            } catch {
              // Best-effort; SSE data already has the essentials
            }
            es.close();
            sseClosers.current.delete(jid);
            // Clear any pending reconnect timer.
            const existingTimer = reconnectTimers.current.get(jid);
            if (existingTimer) {
              clearTimeout(existingTimer);
              reconnectTimers.current.delete(jid);
            }
          }
        } catch {
          // JSON parse error — ignore
        }
      };

      es.onerror = () => {
        if (!mounted.current) return;
        es.close();
        sseClosers.current.delete(jid);

        setFileJobs((prev) =>
          prev.map((j) =>
            j.jobId === jid ? { ...j, pollError: "连接中断，正在重试..." } : j,
          ),
        );

        // Exponential backoff: SSE_RECONNECT_BASE_MS * 2^(attempts), capped at MAX_BACKOFF_MS.
        const attempts = reconnectAttempts.current.get(jid) ?? 0;
        const nextAttempts = attempts + 1;
        reconnectAttempts.current.set(jid, nextAttempts);
        const delay = Math.min(
          SSE_RECONNECT_BASE_MS * Math.pow(2, nextAttempts - 1),
          MAX_BACKOFF_MS,
        );

        // Clear any existing retry timer for this job.
        const existingTimer = reconnectTimers.current.get(jid);
        if (existingTimer) {
          clearTimeout(existingTimer);
        }

        const timer = setTimeout(() => {
          if (!mounted.current) return;
          reconnectTimers.current.delete(jid);
          setupSseForJob(jid);
        }, delay);
        reconnectTimers.current.set(jid, timer);
      };
    }

    for (const jid of activeJobIds) {
      setupSseForJob(jid);
    }

    return () => {
      mounted.current = false;
      for (const es of sseClosers.current.values()) {
        es.close();
      }
      for (const timer of reconnectTimers.current.values()) {
        clearTimeout(timer);
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJobIdsKey, fetchJobStatusFn]);
}
