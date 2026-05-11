# Type Safety

> Type safety patterns in the PDF2PPT frontend.

---

## Overview

The project uses **TypeScript with strict mode**. All code is typed. The type system is used to:
- Define component props
- Type API request/response shapes
- Provide autocomplete for settings and configuration
- Catch data shape mismatches at compile time

---

## Type Organization

### Where Types Are Defined

Types are **co-located with the code that uses them**:

| Location | What |
|----------|------|
| `lib/settings.ts` | `Settings`, `OcrAiProvider`, `OcrAiPromptPreset`, etc. |
| `lib/job-status.ts` | `JobListItem`, `JobListResponse`, `JobStatusValue`, etc. |
| `lib/job-types.ts` | `FileJobState`, job-related enums |
| `lib/auth.ts` | `AdminUser`, `AdminStats`, auth-related types |
| `lib/run-config.ts` | Run configuration types |
| `lib/layout-models.ts` | `LayoutModelInfo` |
| Page files | Page-specific types (e.g., `JobApiErrorBody`, `StatusFilter`) |

### Type Aliases vs Interfaces

The project **strongly prefers `type` over `interface`**:

```tsx
// ✅ PREFERRED
type Settings = {
  apiKey: string
  model: string
}

// ⚠️ EXISTS in codebase but not preferred for new code
interface Settings {
  apiKey: string
  model: string
}
```

---

## Validation

### API Response Validation

The project uses **manual type narrowing** rather than a schema validation library (no Zod, Yup, io-ts):

```tsx
// Pattern 1: Type assertion with null fallback
const body = await response.json().catch(() => null) as JobListResponse | null

// Pattern 2: Runtime key checks (for critical data)
const data: unknown = await res.json()
if (
  typeof data === "object" &&
  data !== null &&
  "job_id" in data &&
  typeof (data as Record<string, unknown>).job_id === "string"
) {
  // Safe to use
}

// Pattern 3: Normalization functions (preferred for complex data)
const normalized = normalizeJobListResponse(raw)
```

### Normalization Functions

For complex API responses, normalization functions validate and transform data:

```tsx
// lib/job-status.ts
export function normalizeJobListResponse(raw: unknown): JobListResponse {
  // Validate shape, provide defaults, handle malformed data
}
```

These functions are the **recommended pattern** for new code.

---

## Common Patterns

### Type Guards

```tsx
function isJobStatus(value: unknown): value is JobStatusValue {
  return typeof value === "string" && TERMINAL_JOB_STATUSES.includes(value as JobStatusValue)
}
```

### Discriminated Unions

```tsx
type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: string }
```

### Generic Utilities

```tsx
// cn() utility is properly typed
export function cn(...inputs: ClassValue[]): string
```

---

## Forbidden Patterns

### 1. `any` Type

```tsx
// ❌ FORBIDDEN
const data: any = await res.json()
function handle(data: any) { ... }

// ✅ USE `unknown` and narrow
const data: unknown = await res.json()
if (typeof data === "object" && data !== null) { ... }
```

### 2. Non-null Assertions Without Validation

```tsx
// ❌ FORBIDDEN (unless guaranteed by control flow)
const name = user!.name

// ✅ PREFERRED
const name = user?.name ?? "Unknown"
```

### 3. Type Assertions Without Runtime Safety

```tsx
// ❌ DANGEROUS (no runtime check)
const data = await res.json() as MyType

// ✅ SAFER
const raw: unknown = await res.json()
const data = normalizeResponse(raw)  // Runtime validation inside
```

### 4. Empty Interfaces

```tsx
// ❌ POINTLESS
interface Props {}

// ✅ USE type for empty shapes too
type Props = Record<string, never>
// Or omit the type when truly empty
```

---

## Configuring TypeScript

The project's `tsconfig.json` enforces:
- `strict: true`
- `noUncheckedIndexedAccess: true`
- `noImplicitReturns: true`
- `noFallthroughCasesInSwitch: true`

These settings catch common bugs at compile time. Never relax them.

---

## Common Mistakes

1. **Using `any` as escape hatch** → defeats the purpose of TypeScript
2. **Asserting API response types without validation** → runtime errors when API shape changes
3. **Not handling `null` in API responses** → `null` is a valid JSON value, always handle it
4. **Using `interface` for props** → inconsistent with project convention (`type` preferred)
5. **Forgetting to type `useState`** → `useState()` is `undefined`, `useState<Type>(initial)` is properly typed
