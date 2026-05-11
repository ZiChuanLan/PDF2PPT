# Fix: Deploy Mode Behavior Improvements

## Goal

Fix deploy mode switching bugs and improve self-mode vs public-mode UX distinction.

## Requirements

1. **Logout prevents auto-login**: After manual logout, set `localStorage.userLoggedOut=true`. Login page checks this flag — if set, skip auto-login and show login form. Flag cleared on successful login.

2. **Self-mode hide user management**: In self-mode, hide "注册" link on login page, hide user management nav item for regular users. Admin still sees admin page.

3. **Nav shows deploy mode**: Replace "Unified Workbench" badge with deploy mode label ("自用模式" / "公开模式"), fetched from `/config/deploy-mode`.

4. **Switch deploy mode confirmation**: Site-settings page shows confirmation dialog when switching deploy mode (especially self→public warning about login requirements).

## Acceptance Criteria

- [ ] Logout → login page shows form (no auto-login)
- [ ] Login after logout → auto-login works again on next visit
- [ ] Self-mode → no register link, no user management for regular users
- [ ] Nav shows "自用模式" or "公开模式" badge
- [ ] Switching deploy mode shows confirmation
- [ ] Switching to public mode and logging out → can log back in with password

## Technical Notes

- `web/src/components/auth-provider.tsx` — logout function
- `web/src/app/login/page.tsx` — auto-login logic, register link
- `web/src/components/workbench-nav.tsx` — "Unified Workbench" badge
- `web/src/app/admin/site-settings/page.tsx` — deploy mode selector
- `web/src/hooks/use-settings.ts` — may need deploy mode hook
