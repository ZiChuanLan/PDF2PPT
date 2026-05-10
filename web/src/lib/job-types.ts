import type { JobStatusResponse } from "@/lib/job-status";

export type FileJobState = {
  file: File;
  jobId: string | null;
  status: JobStatusResponse | null;
  error: string | null;
  pollError: string | null;
  isSubmitting: boolean;
};
