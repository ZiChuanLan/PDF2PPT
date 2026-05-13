# Quality Guidelines

> Code quality standards for frontend development in PDF2PPT.

---

## Overview

These are the enforced quality standards. All code must pass `tsc --noEmit` and `npm run lint`
before being committed.

---

## Forbidden Patterns

### 1. Silent Error Handling

**Never** use empty catch blocks or catch blocks without error logging:

```tsx
// ❌ FORBIDDEN
.catch(() => {})
.catch(() => { /* silent */ })

// ✅ REQUIRED: at minimum, log the error
.catch((e) => {
  console.error("Operation failed:", e)
  // Set error state or show toast as needed
})
```

### 2. Direct `fetch()` Calls

Always use `apiFetch()` from `@/lib/api`:

```tsx
// ❌ FORBIDDEN
const res = await fetch("/api/endpoint")

// ✅ REQUIRED
const res = await apiFetch("/endpoint")
```

### 3. Raw `any` Types

Avoid `any`. Use `unknown` and narrow with type guards:

```tsx
// ❌ FORBIDDEN
const data: any = await res.json()

// ✅ PREFERRED
const data: unknown = await res.json()
if (typeof data === "object" && data !== null && "key" in data) { ... }
```

### 4. Missing `<main>` or `<h1>`

Every page must have semantic landmarks:

```tsx
// ✅ REQUIRED
export default function MyPage() {
  return (
    <main className="...">
      <h1>Page Title</h1>
      {/* content */}
    </main>
  )
}
```

### 5. Hardcoded Secrets

Never hardcode passwords, API keys, or secrets in code or example files:

```tsx
// ❌ FORBIDDEN
const PASSWORD = "admin123"
const API_KEY = "sk-xxx"

// ✅ REQUIRED
// Read from env: process.env.NEXT_PUBLIC_API_URL
// Or from user input / settings
```

### 6. Uncontrolled vs Controlled Inputs

Never mix uncontrolled and controlled input patterns:

```tsx
// ❌ FORBIDDEN (switching between controlled/uncontrolled)
<input value={value} />  // starts as undefined → controlled, then becomes ""

// ✅ REQUIRED: Always initialize with empty string
const [value, setValue] = React.useState("")
```

### 7. All-Mounted Hidden Tab Panels

**Never** mount all tab panels simultaneously with CSS hiding. This causes all hooks
(API fetches, polling, model downloads) to run on page load regardless of which tab is active:

```tsx
// ❌ FORBIDDEN — all 4 panels mount on load, all hooks fire, all API calls happen
<div role="tabpanel" className={activeTab !== "parse" ? "hidden" : ""}>
  <ExpensiveComponent />
</div>
<div role="tabpanel" className={activeTab !== "ocr" ? "hidden" : ""}>
  <ExpensiveComponent />
</div>

// ✅ REQUIRED: Conditional rendering — only active tab mounts
{activeTab === "parse" && (
  <div role="tabpanel"><ExpensiveComponent /></div>
)}
{activeTab === "ocr" && (
  <div role="tabpanel"><ExpensiveComponent /></div>
)}
```

**Why**: CSS `hidden` does not unmount components. Hooks with side effects (API calls,
polling intervals, WebSocket connections) run regardless. Conditional rendering
(`{condition && <Component/>}`) unmounts inactive tabs, preventing unnecessary
network requests and background work.

**Trade-off accepted**: Fold/collapse state within tabs is lost on tab switch.

---

## Required Patterns

### Error Boundaries for Page-Level Errors

Pages should handle loading, error, and empty states:

```tsx
if (isLoading) return <LoadingState />
if (error) return <ErrorState message={error} />
if (!data) return <EmptyState />
return <DataView data={data} />
```

### Toast Notifications for User Actions

Use `sonner` toast for user-visible feedback:

```tsx
import { toast } from "sonner"

try {
  await operation()
  toast.success("操作成功")
} catch (e) {
  toast.error(normalizeFetchError(e, "操作失败"))
}
```

### Cleanup in Effects

Always clean up subscriptions, intervals, and timers:

```tsx
React.useEffect(() => {
  const timer = setInterval(poll, INTERVAL)
  return () => clearInterval(timer)  // ← REQUIRED
}, [])
```

### Mounted Flag for Async Operations

Prevent state updates after unmount:

```tsx
React.useEffect(() => {
  let mounted = true
  async function load() {
    const data = await fetchData()
    if (mounted) setState(data)  // ← REQUIRED guard
  }
  void load()
  return () => { mounted = false }
}, [])
```

---

## Testing Requirements

Tests are out of scope for the current phase. When tests are added:
- Component tests should verify rendering and user interactions
- Hook tests should verify state transitions and async behavior
- Utility tests should verify edge cases

---

## Code Review Checklist

Before merging any frontend change, verify:

- [ ] `tsc --noEmit` passes with no errors
- [ ] `npm run lint` passes with no warnings
- [ ] Every new page has `<main>` and `<h1>`
- [ ] All `.catch()` blocks have `console.error` or equivalent logging
- [ ] No hardcoded secrets or passwords
- [ ] All `useEffect` callbacks have cleanup where needed
- [ ] No direct `fetch()` calls — use `apiFetch()`
- [ ] Input fields are always controlled (initialized with string values)
- [ ] Async operations check `mounted` flag before updating state
- [ ] Error messages are user-friendly (Chinese for UI-facing, English for logs)
