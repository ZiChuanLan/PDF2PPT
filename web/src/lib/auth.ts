/**
 * Auth types and helpers for LinuxDo OAuth authentication.
 *
 * The backend stores JWT in httponly cookies, so the frontend
 * only needs to check auth status via /api/v1/auth/me.
 */

export type UserRole = "user" | "admin"

export type User = {
  id: number
  linuxdo_id: number
  username: string
  name: string | null
  avatar_url: string | null
  role: UserRole
  trust_level: number
  active: boolean
  created_at: string
  last_login_at: string | null
  daily_task_limit: number
  max_file_size_mb: number
  concurrent_task_limit: number
}

export type QuotaInfo = {
  daily_task_limit: number
  max_file_size_mb: number
  concurrent_task_limit: number
  tasks_today: number
  active_tasks: number
}

export type AdminUser = User

export type AdminStats = {
  users: {
    total: number
    active: number
    admins: number
  }
  jobs: {
    total: number
    pending: number
    processing: number
    completed: number
    failed: number
  }
}

/**
 * Normalize user data from API response.
 */
export function normalizeUser(raw: unknown): User | null {
  if (!raw || typeof raw !== "object") return null

  const data = raw as Record<string, unknown>
  const id = typeof data.id === "number" ? data.id : null
  const linuxdoId = typeof data.linuxdo_id === "number" ? data.linuxdo_id : null
  const username = typeof data.username === "string" ? data.username : ""

  if (id === null || linuxdoId === null || !username) return null

  return {
    id,
    linuxdo_id: linuxdoId,
    username,
    name: typeof data.name === "string" ? data.name : null,
    avatar_url: typeof data.avatar_url === "string" ? data.avatar_url : null,
    role: data.role === "admin" ? "admin" : "user",
    trust_level: typeof data.trust_level === "number" ? data.trust_level : 0,
    active: typeof data.active === "boolean" ? data.active : true,
    created_at: typeof data.created_at === "string" ? data.created_at : "",
    last_login_at: typeof data.last_login_at === "string" ? data.last_login_at : null,
    daily_task_limit: typeof data.daily_task_limit === "number" ? data.daily_task_limit : 10,
    max_file_size_mb: typeof data.max_file_size_mb === "number" ? data.max_file_size_mb : 100,
    concurrent_task_limit: typeof data.concurrent_task_limit === "number" ? data.concurrent_task_limit : 2,
  }
}

/**
 * Build avatar URL with size parameter.
 * LinuxDo avatars support {size} placeholder.
 */
export function getAvatarUrl(template: string | null | undefined, size = 48): string {
  if (!template) return ""
  // LinuxDo avatar templates use {size} placeholder
  return template.replace(/\{size\}/g, String(size))
}

/**
 * Check if user has admin role.
 */
export function isAdmin(user: User | null | undefined): boolean {
  return user?.role === "admin"
}
