# State Management

> How state is managed in the PDF2PPT project.

---

## Overview

The project uses **React's built-in state management** exclusively. There is no Redux, Zustand,
Jotai, or other external state library. State is managed through:

1. **Local component state** — `useState` / `useReducer`
2. **Shared context** — React Context for auth and upload session
3. **localStorage** — Persistence for user settings and preferences
4. **URL state** — Next.js router and search params
5. **Custom hooks** — Encapsulated stateful logic (polling, settings, model status)

---

## State Categories

### Local State (`useState`)

Used for UI-specific state that doesn't need to be shared:
- Form input values
- Loading/error states
- UI toggle states (open/closed panels)
- Temporary selections

```tsx
const [username, setUsername] = React.useState("")
const [isLoading, setIsLoading] = React.useState(false)
const [error, setError] = React.useState<string | null>(null)
```

### Shared Context

Used for state needed across multiple components:

**Auth Context** (`components/auth-provider.tsx`):
- User object (logged-in user info)
- `isLoading` flag
- `refetch()` function to refresh user data

**Upload Session Context** (`components/upload-session-provider.tsx`):
- File upload state
- Session metadata

### localStorage Persistence

Used for settings that survive page reloads and browser sessions:

**Settings** (`hooks/use-settings.ts`):
- `loadStoredSettings()` — reads from localStorage
- Auto-save with debounce (500ms)
- In `self` deploy mode: localStorage only
- In `public` deploy mode: localStorage + API sync

**API Origin** (`lib/api.ts`):
- `getStoredApiOrigin()` / `setStoredApiOrigin()` — user-configured API endpoint
- Falls back to auto-detection

### URL State

Used for navigation and shareable state:
- `useRouter()` — programmatic navigation
- `useSearchParams()` — read URL query parameters
- Route parameters — dynamic segments (e.g., `/admin/users/[id]`)

---

## When to Use Global State

Promote state to context when:
1. It's needed by 3+ components at different levels of the tree
2. Changes to it should trigger updates in multiple places
3. It represents a session-scoped concern (auth, upload session)

Keep state local when:
1. It's only used by one component
2. It's form-specific temporary state
3. It can be passed as props to 1-2 immediate children

---

## Server State

### API Data Caching

There is no structured caching layer (no React Query/SWR). Instead:
- Data is fetched on mount and stored in local state
- Polling via `setInterval` for live updates (job lists, model status)
- SSE for real-time job progress

### Patterns for Server State

```tsx
// Typed API response handling
const [data, setData] = React.useState<MyDataType | null>(null)
const [isLoading, setIsLoading] = React.useState(true)
const [error, setError] = React.useState<string | null>(null)

const fetchData = React.useCallback(async () => {
  setIsLoading(true)
  setError(null)
  try {
    const res = await apiFetch("/endpoint")
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const body = await res.json()
    setData(body as MyDataType)
  } catch (e) {
    console.error("Failed to fetch:", e)
    setError(normalizeFetchError(e, "加载失败"))
  } finally {
    setIsLoading(false)
  }
}, [])
```

---

## Derived State

Use `useMemo` for computationally expensive derivations:

```tsx
const filteredJobs = React.useMemo(() => {
  return jobs.filter((job) => matchesFilter(job, activeFilter))
}, [jobs, activeFilter])
```

For simple derivations, inline computation is fine (no `useMemo` needed).

---

## Common Mistakes

1. **State updates after unmount** → missing `mounted` flag in async effects
2. **Stale closures in `setInterval`** → using stale state values in callbacks
3. **Unnecessary `useMemo`/`useCallback`** → premature optimization for simple values
4. **Forgetting to initialize state** → `useState()` starts as `undefined`, causing controlled/uncontrolled warnings
5. **Mutating state directly** → always use setter functions, never `state.prop = value`
