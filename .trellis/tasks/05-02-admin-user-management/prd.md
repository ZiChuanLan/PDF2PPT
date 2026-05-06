# Admin User Management - Batch Delete & Manual Add

## Goal

Enhance the admin user management page with batch delete users and manual add user capabilities. Currently the admin page only supports viewing users and editing individual user details.

## What I already know

* Current backend has: `GET /users`, `GET /users/{id}`, `PUT /users/{id}`, `GET /users/{id}/tasks`, `GET /stats`
* Current frontend: user list table with "详情" link per row, no batch operations, no add user
* Users can register via invite codes or LinuxDo OAuth
* Backend uses SQLAlchemy + SQLite, UserORM model
* Frontend is Next.js with shadcn/ui components
* Auth uses JWT cookies, admin role check via `require_admin` dependency

## Assumptions (temporary)

* Admin should be able to create users with username + password (no OAuth required)
* Batch delete should have confirmation dialog
* Admin cannot delete themselves
* Batch delete should handle mixed states (some users already inactive)

## Open Questions

* (none yet - will derive from code inspection)

## Requirements (evolving)

* Backend: `DELETE /admin/users/{user_id}` — soft delete (set `active=False`)
* Backend: `POST /admin/users` — create user with username + password + optional role
* Backend: `POST /admin/users/batch-delete` — batch soft delete by list of IDs
* Frontend: Checkbox column in user table for multi-select
* Frontend: "批量删除" button with confirmation dialog
* Frontend: "添加用户" button with modal form (username, password, role)
* Admin cannot delete/deactivate themselves
* Batch delete skips admin's own account

## Acceptance Criteria (evolving)

* [ ] Admin can select multiple users via checkboxes in user table
* [ ] Admin can batch delete selected users with confirmation dialog
* [ ] Batch delete sets `active=False` for selected users (soft delete)
* [ ] Admin's own account is excluded from batch delete
* [ ] Admin can add a new user via modal form (username, password, optional role)
* [ ] Duplicate username shows error message
* [ ] UI shows success/error toast feedback
* [ ] User list refreshes after add/delete operations

## Decision (ADR-lite)

**Context**: Admin needs batch delete and manual add user capabilities
**Decision**: Soft delete (active=False), reuse existing `create_user_with_password()`, checkbox multi-select UI
**Consequences**: Deleted users remain in DB but inactive; can be restored via individual edit

## Definition of Done

* Tests added/updated where appropriate
* Lint / typecheck / CI green
* Docker build succeeds

## Out of Scope (explicit)

* Hard delete / permanent deletion
* User import from CSV/file
* User export
* Bulk role change
* Restore deleted users UI (can be done via individual user edit)

## Technical Notes

* Backend: `api/app/routers/admin.py` - admin endpoints
* Backend: `api/app/models/user.py` - UserORM model (has `active` field for soft delete)
* Backend: `api/app/auth.py` - `create_user_with_password()` at line 200 already exists, can reuse
* Backend: `api/app/auth.py` - `hash_password()` at line 188
* Frontend: `web/src/app/admin/page.tsx` - admin users page with table
* Frontend: `web/src/lib/auth.ts` - AdminUser type
* No existing DELETE endpoint for users
* UserORM has `active` boolean field - suitable for soft delete
