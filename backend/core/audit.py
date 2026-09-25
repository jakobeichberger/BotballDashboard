from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func, insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from core.exceptions import UnauthorizedError
from core.logging import get_logger

logger = get_logger(__name__)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


async def log_action(
    db: AsyncSession,
    action: str,
    *,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> None:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(entry)
    # Don't commit here – caller controls the transaction


# ── Request audit (successful API mutations) ──────────────────────────────────
#
# Every successful POST/PUT/PATCH/DELETE under /api/ gets one audit row. It
# used to be written by the middleware in a second session of its own after
# the response — a second pool checkout, transaction and commit per write
# request. Now the middleware only announces the entry (a context variable);
# get_db adds it to the request's own transaction right before that commits,
# so it costs one INSERT in a transaction that happens anyway, and it is
# committed exactly when the change it records is. Requests that never open a
# request session (or whose session was replaced, e.g. in tests) fall back to
# a single Core INSERT once the response is complete.


@dataclass
class PendingAudit:
    action: str
    user_id: str | None
    resource_id: str
    ip_address: str | None
    written: bool = False

    def values(self) -> dict:
        return {
            "action": self.action[:100],
            "user_id": self.user_id,
            "resource_type": "api",
            "resource_id": self.resource_id[:100],
            "ip_address": self.ip_address,
        }


_pending_audit: ContextVar[PendingAudit | None] = ContextVar("pending_audit", default=None)


def add_pending_audit_entry(session: AsyncSession) -> None:
    """Add the current request's audit row to `session` (called before commit)."""
    entry = _pending_audit.get()
    if entry is None or entry.written:
        return
    session.add(AuditLog(**entry.values()))
    entry.written = True


_MUTATIONS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _bearer_subject(headers: list[tuple[bytes, bytes]]) -> str | None:
    from core.auth import decode_token

    for name, value in headers:
        if name == b"authorization":
            authorization = value.decode("latin-1")
            if authorization.lower().startswith("bearer "):
                try:
                    return decode_token(authorization.split(" ", 1)[1]).get("sub")
                except UnauthorizedError:
                    return None
    return None


class AuditMiddleware:
    """ASGI middleware recording successful API mutations (see above).

    Audit failures never become user-facing: the fallback write swallows
    every error, and a failing piggy-backed row fails the request's commit
    only in the way any other row of that transaction would.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in _MUTATIONS
            or not scope["path"].startswith("/api/")
            or getattr(scope["app"].state, "testing", False)
        ):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        entry = PendingAudit(
            action=f"{scope['method']} {scope['path']}",
            user_id=_bearer_subject(scope.get("headers") or []),
            resource_id=scope["path"],
            ip_address=client[0] if client else None,
        )
        status = 0

        async def send_with_status(message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        token = _pending_audit.set(entry)
        try:
            await self.app(scope, receive, send_with_status)
        finally:
            _pending_audit.reset(token)
        if 0 < status < 400 and not entry.written:
            await _write_directly(entry)


async def _write_directly(entry: PendingAudit) -> None:
    try:
        from core import database

        async with database.engine.begin() as connection:
            await connection.execute(insert(AuditLog).values(**entry.values()))
        entry.written = True
    except (SQLAlchemyError, OSError) as exc:
        # User-facing mutations must not fail when audit storage is unavailable.
        logger.warning("audit_write_failed", action=entry.action, error=str(exc))
