"""
create_admin.py – Run inside the backend container to create the first admin user.

Usage (called by proxmox-setup.sh – password via env var to avoid shell interpolation):
    docker compose exec -T -e ADMIN_PASSWORD backend python scripts/create_admin.py \
        --email admin@example.com --name "Administrator"

Or with explicit password argument (manual use):
    docker compose exec backend python scripts/create_admin.py \
        --email admin@example.com --password "securepassword" --name "Administrator"

Or interactively:
    docker compose exec backend python scripts/create_admin.py
"""
import argparse
import asyncio
import os
import sys

# Add parent dir to path so core.* imports work
sys.path.insert(0, "/app")


async def main(email: str, password: str, display_name: str) -> None:
    from core.database import AsyncSessionLocal  # noqa: F401
    from modules.auth.models import User, Role, UserRole  # noqa: F401 – register models
    from modules.auth.service import create_user

    # Import ALL models so Base.metadata is complete
    import modules.seasons.models       # noqa: F401
    import modules.teams.models         # noqa: F401
    import modules.paper_review.models  # noqa: F401

    # Optional models – present on main but not required on all branches
    for mod in ("modules.scoring.models", "modules.printing.models", "modules.dashboard.models"):
        try:
            __import__(mod)
        except ModuleNotFoundError:
            pass

    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Check if user already exists (email is stored lowercase)
        existing = await db.execute(select(User).where(User.email == email.lower()))
        if existing.scalar_one_or_none():
            print(f"[INFO] User '{email.lower()}' already exists – skipping creation.")
            return

        # Find admin role
        admin_role_result = await db.execute(select(Role).where(Role.name == "admin"))
        admin_role = admin_role_result.scalar_one_or_none()
        role_ids = [admin_role.id] if admin_role else []

        user = await create_user(db, email, display_name, password, role_ids)

        # Also set is_superuser so they have all permissions without explicit role checks
        user.is_superuser = True
        await db.commit()
        await db.refresh(user)

        print(f"[OK] Admin user created: {user.email} (id={user.id})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the first BotballDashboard admin user")
    parser.add_argument("--email",    required=True, help="Admin email address")
    parser.add_argument("--password", default=None,  help="Admin password (min. 8 chars); falls back to ADMIN_PASSWORD env var")
    parser.add_argument("--name",     default="Administrator", help="Display name")
    args = parser.parse_args()

    # Prefer CLI arg; fall back to env var so proxmox-setup.sh can avoid
    # shell-interpolation of special characters ($, !, etc.) in passwords.
    password = args.password or os.environ.get("ADMIN_PASSWORD", "")

    if not password:
        print("[ERROR] Provide --password or set the ADMIN_PASSWORD environment variable.", file=sys.stderr)
        sys.exit(1)

    if len(password) < 8:
        print("[ERROR] Password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(main(args.email, password, args.name))
