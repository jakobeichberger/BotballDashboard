"""
create_admin.py – Run inside the backend container to create the first admin user.

Usage (called by proxmox-setup.sh – password via env var to avoid shell interpolation):
    docker compose exec -T -e ADMIN_PASSWORD backend python scripts/create_admin.py \
        --email admin@example.com --name "Administrator"

With explicit password argument (manual use):
    docker compose exec backend python scripts/create_admin.py \
        --email admin@example.com --password "securepassword" --name "Administrator"

Reset / force-update an existing user's password (keeps their roles; ends
all of their sessions). Add --superuser to also make them a superuser:
    docker compose exec -T -e ADMIN_PASSWORD backend python scripts/create_admin.py \
        --email admin@example.com --name "Administrator" --reset
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, "/app")


async def main(
    email: str, password: str, display_name: str, reset: bool, superuser: bool = False
) -> None:
    import modules.paper_review.models  # noqa: F401
    import modules.seasons.models  # noqa: F401
    import modules.teams.models  # noqa: F401
    from core.database import AsyncSessionLocal
    from modules.auth.models import RefreshToken, Role, User, UserRole  # noqa: F401
    from modules.auth.service import create_user, hash_password

    for mod in ("modules.scoring.models", "modules.printing.models", "modules.dashboard.models"):
        try:
            __import__(mod)
        except ModuleNotFoundError:
            pass

    from sqlalchemy import delete, select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email.lower()))
        existing = result.scalar_one_or_none()

        if existing:
            if not reset:
                print(
                    f"[INFO] User '{email.lower()}' already exists – skipping. Use --reset to force password update."
                )
                return
            # Reset: new password, reactivate, and end every existing session.
            # Superuser status is only granted on request: resetting a juror's
            # forgotten password must not silently make them an administrator.
            existing.hashed_password = hash_password(password)
            existing.is_active = True
            if superuser:
                existing.is_superuser = True
            await db.execute(delete(RefreshToken).where(RefreshToken.user_id == existing.id))
            await db.commit()
            print(f"[OK] Password reset for: {existing.email} (id={existing.id})")
            return

        admin_role_result = await db.execute(select(Role).where(Role.name == "admin"))
        admin_role = admin_role_result.scalar_one_or_none()
        role_ids = [admin_role.id] if admin_role else []

        user = await create_user(db, email, display_name, password, role_ids)
        user.is_superuser = True
        await db.commit()
        await db.refresh(user)
        print(f"[OK] Admin user created: {user.email} (id={user.id})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or reset a BotballDashboard admin user")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument(
        "--password",
        default=None,
        help="Password (the API password policy applies); or set ADMIN_PASSWORD env var",
    )
    parser.add_argument("--name", default="Administrator", help="Display name")
    parser.add_argument(
        "--reset", action="store_true", help="Force-update password even if user already exists"
    )
    parser.add_argument(
        "--superuser",
        action="store_true",
        help="With --reset: also make the existing user a superuser",
    )
    args = parser.parse_args()

    password = args.password or os.environ.get("ADMIN_PASSWORD", "")

    if not password:
        print(
            "[ERROR] Provide --password or set the ADMIN_PASSWORD environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    # The same policy as the API (length, repetition, e-mail, common
    # passwords). Outside production a weak password only warns, so the dev
    # compose setup keeps working with its throwaway admin.
    from modules.auth.password_policy import password_problem

    problem = password_problem(password, args.email)
    if problem:
        if os.environ.get("APP_ENV", "production") == "production":
            print(f"[ERROR] {problem}", file=sys.stderr)
            sys.exit(1)
        print(f"[WARN] {problem} (accepted because APP_ENV is not production)", file=sys.stderr)

    # Use uvloop if available (installed via uvicorn[standard]).
    # Python's default _UnixSelectorEventLoop calls socket.socketpair(AF_UNIX)
    # during __init__, which is blocked in Proxmox LXC containers by the
    # seccomp/AppArmor profile. uvloop uses libuv and does not have this issue.
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

    asyncio.run(main(args.email, password, args.name, args.reset, args.superuser))
