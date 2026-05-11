# Frontend Development Guidelines

> Best practices for frontend development in the PDF2PPT project.

---

## Overview

This directory contains guidelines for frontend development. Each sub-file documents real conventions
observed in this codebase, with concrete examples and forbidden patterns.

---

## Technology Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript (strict mode)
- **Styling**: Tailwind CSS + custom `editorial-*` design tokens
- **UI Components**: Custom shadcn-style components under `@/components/ui/`
- **State**: React hooks (`useState`, `useEffect`, `useCallback`) + localStorage
- **HTTP**: Custom `apiFetch` wrapper under `@/lib/api`
- **Forms**: Controlled components (`useState` + `onChange`)
- **Notifications**: `sonner` toast library
- **Icons**: `lucide-react`

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Directory Structure](./directory-structure.md) | Module organization and file layout | ✅ Filled |
| [Component Guidelines](./component-guidelines.md) | Component patterns, props, composition | ✅ Filled |
| [Hook Guidelines](./hook-guidelines.md) | Custom hooks, data fetching patterns | ✅ Filled |
| [State Management](./state-management.md) | Local state, global state, server state | ✅ Filled |
| [Quality Guidelines](./quality-guidelines.md) | Code standards, forbidden patterns | ✅ Filled |
| [Type Safety](./type-safety.md) | Type patterns, validation | ✅ Filled |

---

## How to Use These Guidelines

1. Read the relevant guide before writing code in that area
2. Follow the **actual conventions** documented here (not ideals)
3. Check the **Forbidden Patterns** section to avoid known pitfalls
4. Use the code examples as templates for new code

---

## Pre-Development Checklist

Before writing any frontend code:

- [ ] Read [Component Guidelines](./component-guidelines.md) — component patterns and accessibility rules
- [ ] Read [Hook Guidelines](./hook-guidelines.md) — data fetching and custom hook patterns
- [ ] Read [Quality Guidelines](./quality-guidelines.md) — forbidden patterns and required patterns
- [ ] Read [Type Safety](./type-safety.md) — type conventions and validation
- [ ] Check [Directory Structure](./directory-structure.md) — where to place new files

---

**Language**: All documentation is written in **English**.
