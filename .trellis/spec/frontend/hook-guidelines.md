# Hook Guidelines

> How hooks are used in the PDF2PPT project.

---

## Overview

The project uses React's built-in hooks (`useState`, `useEffect`, `useCallback`, `useMemo`, `useRef`)
combined with custom hooks for shared stateful logic. No external state management library is used.

---

## Custom Hook Patterns

### Standard Hook Structure

```tsx
// hooks/use-example.ts
import * as React from "react"

type UseExampleOptions = {
  /** Polling interval in ms (default: 5000) */
  pollIntervalMs?: number
  /** Called when data is successfully fetched */
  onSuccess?: (data: unknown) => void
}

type UseExampleReturn = {
  data: unknown | null
  isLoading: boolean
  error: string | null
  refetch: () => Promise<void>
}

export function useExample(options: UseExampleOptions = {}): UseExampleReturn {
  const { pollIntervalMs = 5000, onSuccess } = options

  const [data, setData] = React.useState<unknown | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  const fetchData = React.useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await apiFetch("/api/data")
      if (!res.ok) throw new Error("Fetch failed")
      const result = await res.json()
      if (mounted) {
        setData(result)
        onSuccess?.(result)
      }
    } catch (e) {
      if (mounted) setError(normalizeFetchError(e, "Failed to load"))
    } finally {
      if (mounted) setIsLoading(false)
    }
  }, [onSuccess])

  // Cleanup pattern
  React.useEffect(() => {
    let mounted = true
    // ... async work with mounted checks
    return () => { mounted = false }
  }, [])

  return { data, isLoading, error, refetch: fetchData }
}
```

### Key Conventions

1. **`mounted` flag in effects**: Always use a `mounted` flag in async effects to avoid state updates on unmounted components
2. **`React.useCallback` for async functions**: Wrap async fetch functions in `useCallback` for stable references
3. **Error normalization**: Use `normalizeFetchError()` from `@/lib/api` for consistent error messages
4. **Return stable objects**: Use `useCallback` for returned functions and `useMemo` for derived data
5. **Options as object**: Accept configuration as an options object with defaults

---

## Data Fetching

### Primary Patterns

1. **apiFetch wrapper**: All HTTP requests go through `apiFetch()` from `@/lib/api`. Never use raw `fetch()`.
2. **Polling with `setInterval`**: For periodic data refresh (job lists, model status)
3. **SSE streaming**: For real-time job progress (`useSSEJobTracking`)

### Example: Polling Pattern

```tsx
React.useEffect(() => {
  let mounted = true
  let timer: ReturnType<typeof setInterval> | null = null

  const poll = async () => {
    try {
      const res = await apiFetch("/jobs/list")
      if (!res.ok) throw new Error("Failed")
      const data = await res.json()
      if (mounted) setJobs(data)
    } catch (e) {
      if (mounted) console.error("Poll failed:", e)
    }
  }

  void poll()
  timer = setInterval(poll, POLL_INTERVAL_MS)

  return () => {
    mounted = false
    if (timer) clearInterval(timer)
  }
}, [])
```

### Error Handling in Data Fetching

```tsx
try {
  const res = await apiFetch("/endpoint")
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.message || `HTTP ${res.status}`)
  }
  const data = await res.json()
} catch (e) {
  console.error("Fetch failed:", e)  // ← ALWAYS log
  const message = normalizeFetchError(e, "操作失败")
  setError(message)
}
```

---

## Naming Conventions

- **Hook files**: `use-<name>.ts` (kebab-case)
- **Hook functions**: `use<Name>()` (camelCase with `use` prefix)
- **Return type**: `Use<Name>Return` (PascalCase)
- **Options type**: `Use<Name>Options` (PascalCase)

---

## Common Mistakes

1. **Missing `mounted` flag** → state updates after unmount (React warning)
2. **No cleanup in `useEffect`** → memory leaks from lingering intervals/timers
3. **Silent catch blocks** → errors swallowed, impossible to debug → always `console.error`
4. **Direct `fetch()` instead of `apiFetch()`** → bypasses auth, CORS, and error handling
5. **Unstable callback references** → unnecessary re-renders → wrap in `useCallback`
6. **Not handling `res.ok` check** before `res.json()` → cryptic JSON parse errors on 4xx/5xx
