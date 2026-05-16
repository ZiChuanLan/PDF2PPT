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

### Relative Artifact URLs Stay Relative

Tracking/debug artifact payloads from the backend already return same-origin relative URLs such as
`/api/v1/jobs/<job_id>/artifacts/file?...`.
When rendering artifact images, PDFs, or download links in the frontend, use those paths directly.

```tsx
// ❌ FORBIDDEN
const src = `${apiOrigin}${artifact.url}`
const pdfHref = `${apiOrigin}${sourcePdfUrl}`

// ✅ REQUIRED
const src = artifact.url
const pdfHref = sourcePdfUrl
```

**Why**: regular API traffic already goes through the frontend's same-origin `/api/v1` rewrite.
Prefixing artifact URLs with a resolved/manual API origin reintroduces unnecessary cross-origin
dependencies, can bypass the frontend domain, and turns a valid relative artifact path into a
deployment-sensitive network/CORS failure.

**Applies to**:
- tracking artifact image components
- inline PDF preview URLs
- "open in new window" links for job artifacts

### Model Readiness Must Come From `/models/status`

For OCR/layout model UX, treat download-task progress and runtime readiness as **different contracts**:

- `/api/v1/models/download/status` tells you whether a download job is running / completed / failed.
- `/api/v1/models/status` tells you whether the model is actually ready for use.

```tsx
// ❌ FORBIDDEN
const isReady = downloadState?.status === "completed"
const label = isReady ? "已下载" : "下载"

// ✅ REQUIRED
const isReady = modelStatus?.local[modelId]?.ready ?? false
const label = isReady
  ? "已下载"
  : downloadState?.status === "completed"
    ? "刷新状态"
    : "下载"
```

**Why**: a download task can finish while the runtime probe still reports the model unavailable
(for example, model root missing, install incomplete, or readiness check failed). Showing `已下载`
from download-task completion alone creates a false-positive success state.

### Transient Status Errors Must Clear After Successful Refetch

If a status hook exposes both current error state and historical error state, UI error badges must render from the
**current** error and clear when a later refetch succeeds.

```tsx
// ❌ FORBIDDEN
const { lastError } = useModelStatus()
<ModelStatusBadge error={lastError} />

// ✅ REQUIRED
const { error } = useModelStatus()
<ModelStatusBadge error={error} />
```

**Why**: request aborts during navigation are common. Reusing sticky historical errors keeps the UI stuck on
`状态获取失败` even after `/models/status` starts returning healthy responses again.

### Single Source of Truth for Job Stages

Job stage displays must derive from shared stage contracts in `web/src/lib/job-status.ts`.
Do not invent divergent stage codes in page-local arrays when the backend already exposes
the real stage name.

```tsx
// ❌ FORBIDDEN
const steps = [
  { code: "parsing", label: "解析" },
  { code: "ocr", label: "OCR" },
  { code: "generating", label: "生成" },
]

// ✅ REQUIRED
const steps = [
  { code: "parsing", label: "解析" },
  { code: "ocr", label: "OCR" },
  { code: "pptx_generating", label: "生成" },
]
```

**Why**: local aliases like `"generating"` drift away from backend `JobStage` values,
make flow debugging harder, and encourage duplicate mapping logic.

If the UI needs a compact or grouped display, keep the grouping layer separate, but anchor
the codes to the shared `JOB_STAGE_FLOW` / `JOB_STAGE_LABELS` contract.

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
- [ ] Job stage UIs reuse shared stage contracts instead of local divergent codes
