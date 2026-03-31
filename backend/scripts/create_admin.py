"""
create_admin.py – Run inside the backend container to create the first admin user.

Usage (called by proxmox-setup.sh):
    docker compose exec -T backend python scripts/create_admin.py \
        --email admin@example.com --password "securepassword" --name "Administrator"

Or interactively:
    docker compose exec backend python scripts/create_admin.py
"""
import argparse
import asyncio
import sys

# Add parent dir to path so core.* imports work
sys.path.insert(0, "/app")


async def main(email: str, password: str, display_name: str) -> None:
    from core.database import AsyncSessionLocal, engine, Base
    from modules.auth.models import User, Role, UserRole  # noqa: F401 – register models
    from modules.auth.service import hash_password, create_user

    # Import ALL models so Base.metadata is complete
    import modules.seasons.models     # noqa: F401
    import modules.teams.models       # noqa: F401
    import modules.scoring.models     # noqa: F401
    import modules.paper_review.models  # noqa: F401
    import modules.printing.models    # noqa: F401
    import modules.dashboard.models   # noqa: F401

    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Check if user already exists
        existing = await db.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"[INFO] User '{email}' already exists – skipping creation.")
            return

        # Find admin role
        admin_role = await db.execute(select(Role).where(Role.name == "admin"))
        admin_role = admin_role.scalar_one_or_none()
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
    parser.add_argument("--password", required=True, help="Admin password (min. 8 chars)")
    parser.add_argument("--name",     default="Administrator", help="Display name")
    args = parser.parse_args()

    if len(args.password) < 8:
        print("[ERROR] Password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(main(args.email, args.password, args.name))
