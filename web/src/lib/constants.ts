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

/** SSE reconnection base delay (exponential backoff multiplier). */
export const SSE_RECONNECT_BASE_MS = 1000;

// ---------------------------------------------------------------------------
// API query limits
// ---------------------------------------------------------------------------

/** Max jobs to fetch on the home page. */
export const HOME_JOB_LIMIT = 50;

/** Max jobs to fetch on the tracking page. */
export const TRACKING_JOB_LIMIT = 60;

/** Max admin users to fetch. */
export const ADMIN_USERS_LIMIT = 100;

/** Max admin invite codes to fetch. */
export const ADMIN_INVITES_LIMIT = 100;

// ---------------------------------------------------------------------------
// Timeouts
// ---------------------------------------------------------------------------

/** Default API request timeout. */
export const API_REQUEST_TIMEOUT_MS = 30_000;
