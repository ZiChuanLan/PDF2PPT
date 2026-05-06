/**
 * Application-wide constants.
 *
 * Centralizes polling intervals, API limits, and other magic numbers
 * that were previously scattered across components.
 */

// ---------------------------------------------------------------------------
// Polling intervals (milliseconds)
// ---------------------------------------------------------------------------

/** Active job status polling on the home page. */
export const JOB_POLL_INTERVAL_MS = 2000;

/** Job list refresh on the jobs page. */
export const JOB_LIST_POLL_INTERVAL_MS = 4000;

/** Model download progress polling. */
export const MODEL_DOWNLOAD_POLL_INTERVAL_MS = 2000;

/** Model status refetch interval. */
export const MODEL_STATUS_POLL_INTERVAL_MS = 4000;

/** Auto-save debounce delay for settings. */
export const SETTINGS_AUTO_SAVE_DEBOUNCE_MS = 3000;

/** SSE reconnection base delay (exponential backoff multiplier). */
export const SSE_RECONNECT_BASE_MS = 1000;

// ---------------------------------------------------------------------------
// API query limits
// ---------------------------------------------------------------------------

/** Max jobs to fetch on the home page. */
export const HOME_JOB_LIMIT = 50;

/** Max jobs to fetch on the tracking page. */
export const TRACKING_JOB_LIMIT = 60;

/** Max jobs to fetch on the jobs list page. */
export const JOBS_PAGE_LIMIT = 100;

/** Max admin users to fetch. */
export const ADMIN_USERS_LIMIT = 100;

/** Max admin invite codes to fetch. */
export const ADMIN_INVITES_LIMIT = 100;

// ---------------------------------------------------------------------------
// File upload
// ---------------------------------------------------------------------------

/** Maximum file size in bytes (100 MB). */
export const MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024;

/** Human-readable max file size for display. */
export const MAX_FILE_SIZE_LABEL = "100MB";

// ---------------------------------------------------------------------------
// Timeouts
// ---------------------------------------------------------------------------

/** Auth token refresh check interval. */
export const AUTH_REFRESH_CHECK_MS = 5 * 60 * 1000; // 5 minutes

/** Default API request timeout. */
export const API_REQUEST_TIMEOUT_MS = 30_000;

/** Toast auto-dismiss duration. */
export const TOAST_DURATION_MS = 4000;
