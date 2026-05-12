# R3-G2a: accessibility fixes

## Goal

Fix accessibility gaps across the frontend: add aria-labels to icon buttons, associate labels with checkboxes, add role to dropzone, add skip-to-content link, add alt text for PDF preview.

## Requirements

### C1: Icon buttons need aria-label
- `web/src/components/home/action-buttons.tsx` — any icon-only buttons
- `web/src/components/home/page-range-section.tsx` — any icon-only buttons
- `web/src/components/home/quick-config-panel.tsx` — any icon-only buttons
- `web/src/components/home/preview-stage.tsx` — any icon-only buttons
- `web/src/app/jobs/page.tsx` — action icon buttons (Download, Trash, etc.)
- `web/src/app/manage/page.tsx` — action icon buttons
- `web/src/app/admin/users/[id]/page.tsx` — action icon buttons
- `web/src/app/admin/invites/page.tsx` — action icon buttons
- Search for any other icon buttons across all .tsx files using ArrowLeftIcon, DownloadIcon, TrashIcon, XIcon, CheckIcon, or similar icon components

### C2: Checkboxes need associated labels
- `web/src/app/jobs/page.tsx` — job selection checkboxes

### C3: Upload dropzone needs accessible role
- `web/src/components/home/preview-stage.tsx` — or wherever the dropzone is
- Add `role="region"` or appropriate aria attributes

### C4: Skip-to-content link
- Add to root layout (`web/src/app/layout.tsx`) — a visually hidden link at the top of the page that skips to `<main id="main-content">`

### C5: PDF preview alt text
- `web/src/components/home/preview-stage.tsx` — the PDF preview/embed area needs accessible alt text

## Acceptance Criteria

- [ ] All icon-only buttons have aria-label
- [ ] All form checkboxes have associated labels or aria-label
- [ ] Upload area has accessible description
- [ ] Skip-to-content link present
- [ ] PDF preview has accessible alt text
- [ ] TypeScript compiles, no lint errors

## Out of Scope

- Full WCAG audit
- Color contrast fixes
- Keyboard navigation beyond what's needed for these items

## Technical Notes

- Use `aria-label` for icon buttons (describe the action: "Download result", "Delete job", etc.)
- Use `<label htmlFor={id}>` for checkboxes, or `aria-labelledby`
- Skip-to-content: `<a href="#main-content" className="sr-only focus:not-sr-only ...">Skip to content</a>`
- The `role="region"` for dropzone should have `aria-label="Upload area"` or similar
- PDF preview: add `alt=""` if decorative, or descriptive `aria-label` if conveying info
