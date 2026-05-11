# Component Guidelines

> How components are built in the PDF2PPT project.

---

## Overview

Components follow a functional pattern using React hooks. The project uses **Next.js 14 App Router**
with client components marked `"use client"`. All components are in TypeScript with explicit prop types.

---

## Component Structure

### Standard Pattern

```tsx
"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

type MyComponentProps = {
  /** Description of the prop */
  title: string
  className?: string
  children?: React.ReactNode
}

export function MyComponent({ title, className, children }: MyComponentProps) {
  return (
    <div className={cn("base-styles", className)}>
      <h2>{title}</h2>
      {children}
    </div>
  )
}
```

### Key Conventions

1. **Always `"use client"`** at the top for interactive components
2. **Import React as namespace**: `import * as React from "react"` (not destructured imports)
3. **Props as type alias**: Use `type` (not `interface`) for component props
4. **`cn()` for className merging**: Always use the `cn()` utility from `@/lib/utils`
5. **Export named functions**: Prefer named exports over default exports for reusable components

---

## Props Conventions

- All props must have explicit TypeScript types
- Use JSDoc comments for non-obvious props: `/** Description */`
- Accept `className` for style overrides from parent
- Use `React.ComponentProps<"div">` for pass-through HTML attributes in UI primitives
- For event handlers, use the standard React event types (e.g., `React.FormEvent`, `React.MouseEvent`)

---

## Styling Patterns

### Tailwind CSS + Editorial Design Tokens

The project uses Tailwind CSS with a custom editorial design system:

```tsx
// Common class patterns
<header className="editorial-page-header newsprint-texture page-enter border border-border bg-background">
<div className="font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground">
<Badge variant="outline" className="font-sans text-[11px] uppercase tracking-[0.12em]">
<Card className="editorial-panel page-enter page-enter-delay-1 border-border">
```

### Design Tokens
- `editorial-page-header` — page header with editorial styling
- `editorial-panel` — card/panel with editorial styling
- `newsprint-texture` — subtle texture background
- `page-enter` / `page-enter-delay-1` / `page-enter-delay-2` — staggered enter animations
- `editorial-pill` — pill-shaped badge variant
- `editorial-toolbar` — toolbar container

---

## Accessibility

### Required Patterns

1. **Every page must have `<main>`** as the primary content wrapper
2. **Every page must have exactly one `<h1>`** describing the page purpose
3. **Use semantic HTML elements**: `<header>`, `<nav>`, `<main>`, `<section>`, `<article>`
4. **Form inputs must have labels**: Use `<label htmlFor="id">` or `aria-label`
5. **Interactive elements must be keyboard accessible**

### Forbidden Patterns
- Using `<div>` where semantic elements are available
- Missing `alt` text on images
- Color-only information (without text alternatives)
- Empty catch blocks that swallow errors silently (`console.error` at minimum)

---

## Client Components

All interactive components are Client Components. Server Components are NOT used in this project.
Every `.tsx` file that uses hooks, events, or browser APIs must start with `"use client"`.

---

## Common Mistakes

1. **Forgetting `"use client"`** on components that use hooks → runtime error
2. **Using `interface` instead of `type`** for props → inconsistent with project convention
3. **Direct `fetch()` calls** instead of `apiFetch()` → bypasses auth and error handling
4. **Not using `cn()` for className** → no Tailwind class merging
5. **Missing `<main>` or `<h1>`** on new pages → accessibility violation
6. **Silent catch blocks** (`.catch(() => {})`) → errors silently swallowed
