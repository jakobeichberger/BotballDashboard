# Security Assessment — BotballDashboard

State: commit `aa61752`, migrations `0001`–`0029`. This page covers authentication and authorization, object-level access, file handling, secrets, transport/headers, dependencies, and the risks that remain. The history of the fixes is in [CHANGELOG.md](../CHANGELOG.md) and [audit-2026-09.md](audit-2026-09.md).

## Roles and permissions

The permissions and the five system roles are seeded by migrations: `0002` creates them, `0010` adds `events:*`, `0012` and `0014` add `papers:write`, `0013` adds `scoring:formulas`, `0016` adds `teams:admin` and gives mentors `teams:write`, and `0017` adds `dashboard:write`. Later migrations do not change grants. Admins can edit role permissions (`PUT /api/auth/roles/{id}`; the admin role keeps its critical permissions) and create custom roles. Superusers pass every permission check.

| Permission | admin | juror | reviewer | mentor | guest |
|---|:-:|:-:|:-:|:-:|:-:|
| `users:read` / `users:write` | ✅ | – | – | – | – |
| `roles:read` / `roles:write` | ✅ | – | – | – | – |
| `seasons:read` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `seasons:write` | ✅ | – | – | – | – |
| `events:read` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `events:write` | ✅ | ✅ | – | – | – |
| `events:admin` | ✅ | – | – | – | – |
| `teams:read` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `teams:write` | ✅ | – | – | ✅ ¹ | – |
| `teams:admin` | ✅ | – | – | – | – |
| `scoring:read` | ✅ | ✅ | – | ✅ | ✅ |
| `scoring:write` | ✅ | ✅ | – | ✅ ¹ | – |
| `scoring:admin` | ✅ | ✅ | – | – | – |
| `scoring:formulas` | ✅ | – | – | – | – |
| `papers:read` | ✅ | – | ✅ | ✅ ¹ | – |
| `papers:write` | ✅ | – | – | ✅ ¹ | – |
| `papers:review` | ✅ | – | ✅ | – | – |
| `papers:admin` | ✅ | – | – | – | – |
| `printing:read` / `printing:write` | ✅ | – | – | ✅ ¹ | – |
| `printing:admin` | ✅ | – | – | – | – |
| `dashboard:read` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `dashboard:write` | ✅ | – | – | – | – |

¹ Scoped to the mentor's own teams (see below).

### Object-level authorization

`core/auth.py::assert_team_access(db, user, team_id, elevated)` lets holders of the elevated permission act on any team. Everyone else is limited to teams where their account is linked as a `TeamMember.user_id`. Only `teams:admin` can set that link. The check is applied to:

| Area | Rule without the elevated permission |
|---|---|
| Scores | Event and season score entry and the OCR scan upload/retry/accept only for own teams (`scoring:admin`) |
| Papers | List, detail, download, versions, diff and history only for own teams. Create, upload and submit only for own teams (`papers:admin`). Reviewers see all papers, but can review only assigned ones. |
| Printing | Jobs and quotas only for own teams. Cancel only an own pending job (`printing:admin`). Printer list without URL, serial and notes. |
| Teams | Edit own team and members. Linking accounts needs `teams:admin`. Season contact fields only for own teams. Contact data and member e-mails of other teams are hidden. Documents are 404 for other teams. |
| Bots | Unpublished bots only for own teams. External bots only for `teams:admin`. |
| Scouting | Notes and observations only for own teams (organizers see all). |
| Analytics | Performance only for own teams. Practice figures in team history only for the team itself. |

Regression tests: `backend/tests/integration/test_security_scoping.py` and the mentor scoping tests. They fail with the checks removed.

### Lifecycle

- Archived seasons and events are read-only (`modules/seasons/lifecycle.py::ensure_writable`, 409).
- Draft seasons and events are hidden from users without `seasons:write` / `events:write`.
- Public event endpoints only serve events in `published`, `live` or `completed`, and each view requires its `public_*` flag. The public WebSocket requires at least one flag.

## Authentication and sessions

- **JWT:** PyJWT, algorithm pinned to HS256 on decode, `exp` and `sub` required, token type enforced. python-jose and its unpatched `ecdsa` dependency are gone.
- **Access tokens:** 15 min, carry a `jti` and a `tv` (token version).
  - Logout puts the `jti` on a Redis deny-list until expiry (`core/token_denylist.py`).
  - Password change, password reset, deactivation and deletion bump `users.token_version`. That ends every session of the user at once.
- **Refresh tokens:** stored as SHA-256 hashes, rotated on use, revocable. Cookie `HttpOnly`, `Secure` outside development, `SameSite=strict`, path `/api/auth`.
- **Password reset:** single-use token, stored hashed, valid 1 h. The request endpoint always answers 204, so it does not reveal whether an account exists.
- **Password policy:** at least 10 characters, not a single repeated character, not the e-mail address.
- **Rate limits** (Redis, per client IP): login, refresh, password change, e-mail change, account deletion, password reset request and confirm, and all upload endpoints. Behind Traefik the real client IP is used (`--proxy-headers`, `FORWARDED_ALLOW_IPS`).
- **Self-update:** `PATCH /auth/me` uses a dedicated schema (`display_name`, `preferred_language`, `theme`), so users cannot change their own roles, status or superuser flag. `is_superuser` is absent from all input schemas. `create_admin.py` grants it only with `--superuser`.

## Files and input

- **Uploads:** paper PDFs, print files, team documents, bot images, score-sheet templates and scans.
  - Names are sanitised (`core/files.py::safe_filename`) and paths contained (`ensure_within`).
  - Size is limited (`MAX_UPLOAD_SIZE_MB`, print files `PRINT_UPLOAD_MAX_MB`; oversized requests get 413 before the body is read).
  - The type is checked by content: PDF magic bytes, image magic bytes, print file formats.
  - Downloads are served as attachments.
- **SQL:** SQLAlchemy bound parameters only. `LIKE` wildcards in team search are escaped.
- **Subprocesses:** `pdftotext` is called with an argv list, `shell=False`.
- **Formula evaluator:** evaluates admin-supplied expressions.
  - AST whitelist, no `eval`/`exec`, no attribute access or subscripting;
  - length (1000) and depth (40) limits, overflow and recursion caught;
  - at most 60 formulas per set;
  - preview requires `scoring:formulas`.
- **Scores:** totals are always recomputed server-side from the versioned schema. Client totals are ignored, and unknown fields are rejected (422). Paper scores are only writable through `PUT /papers/{id}/score` (`papers:admin`).
- **CSV exports** neutralise cells starting with `=`, `+`, `-`, `@`.
- **Errors:** `IntegrityError` becomes a generic 409 without SQL details. All errors use `{code, message, fieldErrors, requestId}`.

## Secrets and transport

- Production refuses to start with default or short `APP_SECRET_KEY` / `JWT_SECRET_KEY` or a `PRINTER_CREDENTIAL_ENCRYPTION_KEY` that is not a Fernet key.
- Printer credentials are Fernet-encrypted and never returned. Password hashes are never returned or logged.
- API headers:
  - `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`;
  - in production also a restrictive CSP and HSTS.

  nginx sets the security headers on the SPA and assets as well (`security-headers.conf`).
- CORS: `localhost`/`127.0.0.1` in development, the `ALLOWED_ORIGINS` list in production.
- API docs and OpenAPI are disabled in production.
- `/api/system/metrics` is excluded from the Traefik route, and the app rejects requests that carry `X-Forwarded-For`.
- Push notifications need explicit recipients (`userId`, `userIds` or `broadcast`). Restricted-audience announcements are neither pushed to everyone nor published on the public stream.

## Dependencies

CI runs `pip-audit` (no ignores) and `pnpm audit --audit-level high` on every push.

## Residual risks

1. **Public ranking endpoints — Medium (product decision).** `GET /api/scoring/{seasons|events}/{id}/ranking`, `/ranking/extended`, `/ranking/overall` and `/aerial-ranking` need no login. Unlike `/api/v1/public/events/{slug}/…` they ignore the `public_*` flags and the event status. Anyone who knows a season or event id can read the rankings of a draft event. This is intentional so far (`test_ranking_public_no_auth`).
2. **Guests read OCR scans — Low.** `guest` holds `scoring:read`. That covers the score-sheet scans of all teams, including image crops.
3. **Fail-open on Redis outage — Low/Medium.** Rate limits and the access-token deny-list let requests through when Redis is unreachable. This keeps login and recovery possible. A logged-out access token then stays valid until it expires (≤ 15 min). Readiness reports Redis as down, and alerts fire on readiness.
4. **Password policy — Low.** No check against known breached passwords, no lockout beyond the rate limit.
5. **Audit depth — Low.** Every successful API mutation is logged as `"<METHOD> <path>"` with user and IP in `audit_logs`, without before/after values. Only scores and DE/aerial/documentation results have full revision history. There is no UI for the audit log.
6. **Card and DQ changes** are only possible through `PATCH /api/scoring/matches/{id}` (`scoring:write` for own teams, `scoring:admin` for any team). They are audited like every other match update (score revision). There is no UI for them yet.
