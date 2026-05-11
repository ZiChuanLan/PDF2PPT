# Directory Structure

> How frontend code is organized in the PDF2PPT project.

---

## Overview

This is a **Next.js 14 App Router** project. All source code lives under `web/src/`.

---

## Directory Layout

```
web/
├── public/              # Static assets (favicon, images)
├── src/
│   ├── app/             # Next.js App Router pages
│   │   ├── page.tsx     # Home page (upload + convert)
│   │   ├── layout.tsx   # Root layout (app shell)
│   │   ├── globals.css  # Global styles + Tailwind
│   │   ├── settings/    # Settings page
│   │   ├── jobs/        # Job listing page
│   │   ├── tracking/    # Job tracking + result comparison
│   │   ├── login/       # Login page
│   │   ├── register/    # Register page
│   │   ├── setup/       # First-time setup wizard
│   │   ├── manage/      # Account management
│   │   ├── admin/       # Admin dashboard
│   │   │   ├── page.tsx           # User management
│   │   │   ├── invites/           # Invite code management
│   │   │   ├── env/               # Environment variable editor
│   │   │   ├── site-settings/     # Site-wide settings
│   │   │   └── users/[id]/        # Individual user detail
│   │   └── auth/callback/         # OAuth callback route
│   ├── components/      # Shared React components
│   │   ├── ui/          # UI primitives (Button, Card, Input, etc.)
│   │   ├── home/        # Home page sub-components
│   │   ├── auth-provider.tsx      # Auth context provider
│   │   ├── user-menu.tsx          # User menu dropdown
│   │   ├── workbench-nav.tsx      # Workbench navigation
│   │   ├── job-debug-panel.tsx    # Job debug panel
│   │   ├── model-status-badge.tsx # Model status indicator
│   │   ├── download-progress-button.tsx
│   │   └── upload-session-provider.tsx
│   ├── hooks/           # Custom React hooks
│   │   ├── use-settings.ts          # Settings persistence
│   │   ├── use-model-status.ts      # OCR model status
│   │   ├── use-model-download.ts    # Model download management
│   │   └── use-sse-job-tracking.ts  # SSE job progress tracking
│   ├── lib/             # Shared utilities and types
│   │   ├── api.ts            # HTTP client (apiFetch)
│   │   ├── auth.ts           # Auth utilities
│   │   ├── utils.ts          # General utilities (cn, etc.)
│   │   ├── constants.ts      # App-wide constants
│   │   ├── settings.ts       # Settings type definitions
│   │   ├── run-config.ts     # Job run configuration
│   │   ├── job-status.ts     # Job status types and normalization
│   │   ├── job-types.ts      # Job-related type definitions
│   │   ├── layout-models.ts  # Layout model definitions
│   │   ├── download-utils.ts # File download utilities
│   │   ├── home-utils.ts     # Home page utilities
│   │   └── tracking-artifacts.ts # Tracking page utilities
│   └── middleware.ts   # Next.js middleware (auth redirect)
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## Module Organization

### Pages (app/)
Each page is a directory under `app/` with a `page.tsx` file. Pages are Client Components.
Shared page logic (types, helpers) is either co-located in the page file or extracted
to `lib/` if reused across pages.

### Components
- **`components/ui/`**: Reusable UI primitives (Button, Card, Input, Badge, etc.)
- **`components/home/`**: Home-page-specific sub-components (upload stage, preview stage, converting stage)
- **`components/*.tsx`**: Shared app-level components (auth provider, user menu, etc.)

### Hooks
Custom hooks encapsulate reusable stateful logic:
- `use-settings` — Settings persistence (localStorage/API)
- `use-model-status` — Periodic OCR model status polling
- `use-model-download` — Model download with progress
- `use-sse-job-tracking` — SSE-based job progress tracking

### Lib
Shared utilities grouped by domain. No React hooks in lib (those go in hooks/).

---

## Naming Conventions

- **Files**: kebab-case (e.g., `use-settings.ts`, `job-status.ts`)
- **Components**: PascalCase (e.g., `Button`, `UserMenu`)
- **Hooks**: `use` prefix, camelCase (e.g., `useSettings`, `useModelStatus`)
- **Types**: PascalCase (e.g., `Settings`, `JobListItem`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `JOB_LIST_POLL_INTERVAL_MS`)

---

## Where to Put New Code

| What | Where |
|------|-------|
| New page | `src/app/<route>/page.tsx` |
| Reusable component | `src/components/<name>.tsx` or `src/components/<group>/<name>.tsx` |
| UI primitive | `src/components/ui/<name>.tsx` |
| Custom hook | `src/hooks/use-<name>.ts` |
| Shared utility | `src/lib/<name>.ts` |
| Type definition | `src/lib/<name>.ts` (co-located with related logic) |
