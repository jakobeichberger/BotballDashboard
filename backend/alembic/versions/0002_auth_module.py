"""Auth module: users, roles, permissions, tokens, push subscriptions

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.String(36), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_superuser", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("preferred_language", sa.String(5), nullable=False, server_default="de"),
        sa.Column("theme", sa.String(10), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.Text, nullable=False),
        sa.Column("p256dh", sa.Text, nullable=False),
        sa.Column("auth", sa.Text, nullable=False),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    # Seed default permissions and roles
    op.execute("""
        INSERT INTO permissions (id, name, description) VALUES
        (gen_random_uuid()::text, 'users:read', 'View users'),
        (gen_random_uuid()::text, 'users:write', 'Create/edit users'),
        (gen_random_uuid()::text, 'roles:read', 'View roles'),
        (gen_random_uuid()::text, 'roles:write', 'Create/edit roles'),
        (gen_random_uuid()::text, 'seasons:read', 'View seasons'),
        (gen_random_uuid()::text, 'seasons:write', 'Create/edit seasons'),
        (gen_random_uuid()::text, 'teams:read', 'View teams'),
        (gen_random_uuid()::text, 'teams:write', 'Create/edit teams'),
        (gen_random_uuid()::text, 'scoring:read', 'View scores'),
        (gen_random_uuid()::text, 'scoring:write', 'Enter scores'),
        (gen_random_uuid()::text, 'scoring:admin', 'Manage scoring templates'),
        (gen_random_uuid()::text, 'papers:read', 'View papers'),
        (gen_random_uuid()::text, 'papers:review', 'Review papers'),
        (gen_random_uuid()::text, 'papers:admin', 'Manage paper review process'),
        (gen_random_uuid()::text, 'printing:read', 'View print jobs'),
        (gen_random_uuid()::text, 'printing:write', 'Submit print jobs'),
        (gen_random_uuid()::text, 'printing:admin', 'Manage printers and quotas'),
        (gen_random_uuid()::text, 'dashboard:read', 'View dashboard')
    """)

    op.execute("""
        INSERT INTO roles (id, name, description, is_system) VALUES
        (gen_random_uuid()::text, 'admin', 'Full system access', true),
        (gen_random_uuid()::text, 'juror', 'Tournament juror', true),
        (gen_random_uuid()::text, 'reviewer', 'Paper reviewer', true),
        (gen_random_uuid()::text, 'mentor', 'Team mentor', true),
        (gen_random_uuid()::text, 'guest', 'Read-only guest', true)
    """)

    # Grant all permissions to admin role
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p WHERE r.name = 'admin'
    """)

    # Juror: scoring + teams + dashboard
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'juror'
        AND p.name IN ('scoring:read','scoring:write','scoring:admin','teams:read','dashboard:read','seasons:read')
    """)

    # Reviewer: papers
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'reviewer'
        AND p.name IN ('papers:read','papers:review','teams:read','dashboard:read','seasons:read')
    """)

    # Mentor: own team + printing + papers (own)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'mentor'
        AND p.name IN ('teams:read','scoring:read','papers:read','printing:read','printing:write','dashboard:read','seasons:read')
    """)

    # Guest: read-only
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'guest'
        AND p.name IN ('scoring:read','dashboard:read','seasons:read','teams:read')
    """)


def downgrade() -> None:
    op.drop_table("push_subscriptions")
    op.drop_table("refresh_tokens")
    op.drop_table("user_roles")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
