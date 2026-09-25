# Security Assessment — BotballDashboard

State: `main` at `ccd7a8b` plus the fixes of the September 2026 security review (branch `security-fixes`), migrations `0001`–`0031`. This page covers authentication and authorization, object-level access, file handling, secrets, transport/headers, dependencies, and the risks that remain. The history of the fixes is in [CHANGELOG.md](../CHANGELOG.md) and [audit-2026-09.md](audit-2026-09.md).

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
| Scores | Event and season score entry and the OCR scan upload/retry/accept only for own teams (`scoring:admin`). A score attached to a scheduled (head-to-head) match is refused unless the team plays in it, for organizers too. |
| Practice runs and notes | Match lists, single matches, score history, the event audit trail and the `matches.csv` exports show practice runs and match notes of other teams only to `scoring:admin` (`modules/scoring/visibility.py`); a foreign practice run is 404. |
| Papers | List, detail, download, versions, diff and history only for own teams. Create, upload and submit only for own teams (`papers:admin`). Reviewers see all papers, but can review only assigned ones. |
| Printing | Jobs and quotas only for own teams. Cancel only an own pending job (`printing:admin`). Printer list without URL, serial and notes. |
| Teams | Edit own team (name, school, city, country) and members; team number, level, active flag and organizer notes need `teams:admin`. Linking accounts needs `teams:admin`. Season contact fields only for own teams. Contact data and member e-mails of other teams are hidden. Documents are 404 for other teams. |
| Bots | Unpublished bots only for own teams. External bots only for `teams:admin`. |
| Scouting | Notes and observations only for own teams (organizers see all). |
| Analytics | Performance only for own teams. Practice figures in team history only for the team itself. |
| Announcements | Listed by audience: `teams` → `teams:write`, `reviewers` → `papers:review`, `jurors` → `scoring:admin`, `internal` → organizers (`dashboard:write`, who see every audience). Expired ones are hidden. |

Regression tests: `backend/tests/integration/test_security_scoping.py`, `test_security_regressions_3.py` and the mentor scoping tests. They fail with the checks removed.

### Lifecycle

- Archived seasons and events are read-only (`modules/seasons/lifecycle.py::ensure_writable`, 409).
- Draft seasons and events are hidden from users without `seasons:write` / `events:write`. A router-wide guard (`modules/events/draft_access.py`) answers 404 to every read that names a draft event (or an event of a draft season) in its path or as `?event_id=`; `/scoring/schemas` leaves them out.
- Team documents cannot be edited out of or moved into an archived season; scan upload and retry are refused there as well.
- Public event endpoints only serve events in `published`, `live` or `completed`, and each view requires its `public_*` flag. The public WebSocket requires at least one flag.

## Authentication and sessions

- **JWT:** PyJWT, algorithm pinned to HS256 on decode, `exp` and `sub` required, token type enforced. python-jose and its unpatched `ecdsa` dependency are gone.
- **Access tokens:** 15 min, carry a `jti` and a `tv` (token version).
  - Logout puts the `jti` on a Redis deny-list until expiry (`core/token_denylist.py`).
  - Password change, password reset, deactivation and deletion bump `users.token_version`. That ends every session of the user at once.
- **Refresh tokens:** stored as SHA-256 hashes, rotated on use, revocable. Cookie `HttpOnly`, `Secure` outside development, `SameSite=strict`, path `/api/auth`.
- **Password reset:** single-use token, stored hashed, valid 1 h. The request endpoint always answers 204, so it does not reveal whether an account exists.
- **bcrypt:** runs in a worker thread (`hash_password_async` / `verify_password_async`), never on the event loop. A login for an unknown or inactive address is checked against a dummy hash, so the response time does not reveal which addresses have an account.
- **Password policy:** at least 10 characters, not a single repeated character, not the e-mail address, and not on the bundled list of ~2,300 common/leaked passwords (`backend/modules/auth/common_passwords.txt`, from SecLists, case-insensitive). Applies to account creation, password change, reset and admin-set.
- **Rate limits** (Redis, per client IP): login, refresh, password change, e-mail change, account deletion, password reset request and confirm, and all upload endpoints. Behind Traefik the real client IP is used (`--proxy-headers`, `FORWARDED_ALLOW_IPS`).
- **Self-update:** `PATCH /auth/me` uses a dedicated schema (`display_name`, `preferred_language`, `theme`), so users cannot change their own roles, status or superuser flag. `is_superuser` is absent from all input schemas. `create_admin.py` makes a newly created account a superuser with the admin role. When resetting an existing account (`--reset`), it grants superuser status only with `--superuser`.

## Files and input

- **Uploads:** paper PDFs, print files, team documents, bot images, score-sheet templates and scans.
  - Names are sanitised (`core/files.py::safe_filename`) and paths contained (`ensure_within`).
  - Size is limited (`MAX_UPLOAD_SIZE_MB`, print files `PRINT_UPLOAD_MAX_MB`). A declared `Content-Length` above the limit gets 413 before anything is read; `core/request_limits.py` counts the bytes actually received and aborts chunked bodies at the limit too. Traefik refuses API bodies above `API_MAX_BODY_BYTES`.
  - The type is checked by content: PDF magic bytes, image magic bytes, print file formats.
  - Downloads are served as attachments; `Content-Disposition` names are built with `safe_filename`, never from raw path parameters.
  - Score-sheet scans are validated completely (template, team, scheduled match, season status, content type) before they are written, stored under a name derived from the detected type, and removed again if the transaction rolls back.
  - OCR: images are measured from their header and refused above 40 MP before decoding (`OPENCV_IO_MAX_IMAGE_PIXELS` as a second cap); PDFs are rasterized at 150 dpi, page 1 only, at most 3000 px.
- **SQL:** SQLAlchemy bound parameters only. `LIKE` wildcards in team search are escaped.
- **Subprocesses:** `pdftotext` is called with an argv list, `shell=False`.
- **Formula evaluator:** evaluates admin-supplied expressions.
  - AST whitelist, no `eval`/`exec`, no attribute access or subscripting;
  - length (1000) and depth (40) limits, overflow and recursion caught;
  - at most 60 formulas per set;
  - preview requires `scoring:formulas`.
- **Scores:** totals are always recomputed server-side from the versioned schema. Client totals are ignored, and unknown fields are rejected (422). Paper scores are only writable through `PUT /papers/{id}/score` (`papers:admin`).
- **CSV exports** neutralise cells starting with `=`, `+`, `-`, `@`.
- **PDF exports** (reportlab) escape every piece of user text that becomes a `Paragraph` (`xml.sax.saxutils.escape`); otherwise tags such as `<img src>` would be interpreted.
- **Errors:** `IntegrityError` becomes a generic 409 without SQL details. All errors use `{code, message, fieldErrors, requestId}`.

## Secrets and transport

- Production refuses to start with default or short `APP_SECRET_KEY` / `JWT_SECRET_KEY` or a `PRINTER_CREDENTIAL_ENCRYPTION_KEY` that is not a Fernet key. `APP_ENV` accepts only `development`, `test` and `production`; every value except `development` gets this check.
- Printer credentials are Fernet-encrypted and never returned. Password hashes are never returned or logged.
- API headers:
  - `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`;
  - in production also a restrictive CSP and HSTS.

  nginx sets the security headers on the SPA and assets as well (`security-headers.conf`).
- CORS: `localhost`/`127.0.0.1` in development, the `ALLOWED_ORIGINS` list in production.
- API docs and OpenAPI are disabled in production.
- `/api/system/metrics` is excluded from the Traefik route, and the app rejects requests that carry `X-Forwarded-For`.
- Push notifications need explicit recipients (`userId`, `userIds` or `broadcast`). Restricted-audience announcements are neither pushed to everyone nor published on the public stream.
- Push subscription endpoints must be `https` URLs of a known push service (`core/push_endpoints.py`: FCM, Mozilla autopush, WNS, Apple), without IP literals, credentials or non-default ports. The sender re-checks stored endpoints and drops those that fail (SSRF).

## Containers

- `backend`, `worker`, `worker-ocr`, `beat` and `backup` run as the unprivileged user `app` (uid/gid 10001) with `cap_drop: ALL`, `no-new-privileges` and memory limits. `backend`, `worker`, `worker-ocr` and `beat` have a read-only root filesystem with `/tmp` as tmpfs; the application code is root-owned and not writable for the app.
- The one-shot services `volume-permissions` and `backup-permissions` hand volumes of older (root) releases to uid 10001. They run as root with only `CHOWN` and `DAC_READ_SEARCH`, without network, and never follow symlinks.
- Traefik keeps the Docker socket (read-only) and runs as root; `db` and `redis` use their images' own users.

## Dependencies

The CI workflow (started manually) runs `pip-audit` (no ignores) and `pnpm audit --audit-level high`.

## Residual risks

1. **Fail-open on Redis outage — Low/Medium.** Rate limits and the access-token deny-list let requests through when Redis is unreachable. This keeps login and recovery possible. A logged-out access token then stays valid until it expires (≤ 15 min). Readiness reports Redis as down, and alerts fire on readiness. Every skipped check is also counted in `botball_redis_fail_open_total{component}` and raises the `RedisFailOpen` alert.
2. **Password policy — Low.** No check against a live breach database, no lockout beyond the per-IP rate limit.
3. **Audit depth — Low.** Every successful API mutation is logged as `"<METHOD> <path>"` with user and IP in `audit_logs`, without before/after values. Only scores and DE/aerial/documentation results have full revision history. There is no UI for the audit log.
4. **Card and DQ changes** are only possible through `PATCH /api/scoring/matches/{id}` (`scoring:admin`). They are audited like every other match update (score revision).
5. **Untrusted PDFs in the worker — Low/Medium.** Uploaded score-sheet scans are parsed by poppler (`pdftoppm`), templates by `pdftotext`. A parser vulnerability would run inside the OCR worker (`worker-ocr`, which has no VAPID key); it is contained by the unprivileged user, no capabilities, the read-only root, the memory limit and the 60 s timeout, but it can reach the database and Redis.
6. **Memory pressure from uploads — Low.** The API spools multipart uploads to its tmpfs `/tmp`, which counts towards `BACKEND_MEM_LIMIT`. Several parallel print uploads close to `PRINT_UPLOAD_MAX_MB` (only users with `printing:write`, rate-limited to 20/min per IP) can make the container hit its limit and restart. Raise `BACKEND_MEM_LIMIT`/`BACKEND_TMP_SIZE` for events with many large print files.
7. **Traefik buffering — Info.** The body-limit middleware buffers requests (on disk above 2 MB) and responses before forwarding them; large downloads reach the client only after Traefik has received them completely. The live WebSocket has its own router without it.
8. **Push service allow-list — Info.** Only the push services of Chrome/Edge/Firefox/Safari (FCM, Mozilla, WNS, Apple) are accepted. A browser using another push service cannot subscribe until its host is added to `core/push_endpoints.py`. Host names are not re-resolved against private address ranges at send time.
9. **Legacy score history — Info.** Revisions of matches deleted before migration `0031` have no practice flag (NULL). The event audit trail treats them as practice runs and shows them only to the team and organizers.
10. **Draft guard scope — Info.** The draft-event guard covers reads (GET/HEAD) that name the event in the path or as `?event_id=`. Writes rely on their own permission checks (all need `events:write`, `scoring:write` or a module permission), and season-level routes without an event id (e.g. the season ranking) follow their own rules (`public_scoreboard` and a non-draft status for anonymous access).
11. **Init containers — Low.** `volume-permissions` and `backup-permissions` run as root (with `CHOWN` and `DAC_READ_SEARCH` only) on every start. The `backup` container keeps a writable root filesystem for its scratch space.
