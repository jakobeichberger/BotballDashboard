# Security Assessment — BotballDashboard

Authorized security review of the application (backend FastAPI + frontend React),
covering authentication/authorization, injection, file handling, secrets,
transport/headers, and dependency vulnerabilities. Includes a full role-based
authorization test of all five roles.

## Role-based authorization — verified

A live test creates one user per role and probes the API across all modules
(`105/105` checks pass). The seeded permission matrix is enforced exactly:

| Endpoint (example) | Perm | admin | juror | reviewer | mentor | guest |
|---|---|:--:|:--:|:--:|:--:|:--:|
| `GET /seasons` | seasons:read | ✅ | ✅ | ✅ | ✅ | ✅ |
| `POST /seasons` | seasons:write | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |
| `POST /scoring/.../matches` | scoring:write | ✅ | ✅ | ⛔ | ⛔ | ⛔ |
| `GET /papers` | papers:read | ✅ | ⛔ | ✅ | ✅ | ⛔ |
| `PUT /papers/{id}/reviews` | papers:review | ✅ | ⛔ | ✅ | ⛔ | ⛔ |
| `POST /printing/jobs` | printing:write | ✅ | ⛔ | ⛔ | ✅ | ⛔ |
| `POST /printing/printers` | printing:admin | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |
| `POST /dashboard/announcements` | dashboard:write | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |
| `POST /auth/users` | users:write | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |
| `POST /auth/roles` | roles:write | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |

Unauthenticated and tampered-token requests are rejected with `401`.

## Findings fixed in this review

| # | Severity | Issue | Fix |
|---|---|---|---|
| C-1/C-2 | Critical | Path traversal via `file.filename` in paper upload/download → arbitrary file write/read (RCE). | `core/files.py`: `safe_filename()` (basename only) + `ensure_within()` containment; applied to paper upload, download, and score-sheet upload. |
| H-1 | High | Partial-mitigation path traversal in score-sheet upload. | Same sanitisation + containment check. |
| C1 | Critical | `PATCH /me` reused the admin `UserUpdate` schema; `is_active`/`role_ids` leaked through one fragile `exclude`. | Dedicated `MeUpdate` schema (only `display_name`/`preferred_language`/`theme`) — self-escalation/self-deactivation structurally impossible. |
| H-4 | High | Default secrets (`change-me*`) silently accepted in production → JWT forgery / auth bypass. | `Settings` model-validator fails startup in production when `APP_SECRET_KEY`/`JWT_SECRET_KEY` are default/short. |
| H-2 | High | No size/type validation on uploads (memory-exhaustion DoS, non-PDF). | `validate_pdf()` enforces `MAX_UPLOAD_SIZE_MB` + PDF magic bytes on both upload paths. |
| M-1 | Medium | Dev CORS reflected **any** origin with credentials. | Restricted to a `localhost`/`127.0.0.1` regex in dev. |
| M-2 | Medium | No security response headers. | Middleware adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, HSTS (prod); downloads served `Content-Disposition: attachment`. |
| — | Medium | DB constraint violations (bad `team_id`/`season_id`) returned `500` and leaked SQL. | Global `IntegrityError` handler → clean `409` with a generic message. |
| deps | High | `python-jose` 3.3.0 JWT CVEs (PYSEC-2024-232/233, PYSEC-2025-185), `python-multipart` DoS, `cryptography`. | Upgraded: `python-jose==3.4.0`, `python-multipart==0.0.31`, `cryptography==46.0.7`, `fastapi==0.115.6` (starlette 0.41.3). pip-audit findings reduced 23 → ~12. |

### Verified SAFE (no change needed)
- No SQL injection — all queries use SQLAlchemy bound parameters.
- No command injection — `pdftotext` is invoked with a list argv, `shell=False`.
- JWT: algorithm pinned to `HS256` on decode (no `alg:none`/confusion), token type enforced, expiry validated.
- Refresh tokens stored as SHA-256 hashes, rotated on use, revocable; cookie is `HttpOnly`, `Secure` (prod), `SameSite=strict`.
- Secrets (`hashed_password`, printer `api_key_encrypted`) never appear in any response model; not logged.
- Superuser bypass cannot be reached via mass assignment (`is_superuser` absent from all input schemas).
- API docs/OpenAPI disabled in production.

## Residual risks / recommended follow-ups (not fixed here)

These need product decisions or larger changes and are documented for follow-up:

1. **Object-level authorization (IDOR) — Medium/High.** `papers:read`/`download`
   are gated only by a coarse permission, not by team ownership or reviewer
   assignment, so a reviewer/mentor can read another team's paper. Create
   endpoints accept a caller-supplied `team_id`. Proper fix requires a
   team↔mentor ownership model and per-object checks.
2. **Login rate limiting — Medium.** No throttling/lockout on `/auth/login`
   (Redis is available to back one).
3. **Session revocation — Medium.** Access tokens remain valid until expiry
   (15 min); consider a jti denylist for true logout-everywhere.
4. **Password policy — Low/Medium.** Only length ≥ 8; consider complexity/HIBP.
5. **Starlette DoS CVEs — Medium.** Remaining advisories require a major
   FastAPI/Starlette (1.x) upgrade; mitigated meanwhile by upload size limits
   and the reverse proxy. Track for a future framework bump.
