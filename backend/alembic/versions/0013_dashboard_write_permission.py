"""Seed the dashboard:write permission (used by announcement routes)

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-15 00:00:00

The announcement create/publish routes require dashboard:write, but only
dashboard:read was ever seeded, so only superusers could manage announcements.
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO permissions (id, name, description)
        SELECT gen_random_uuid()::text, 'dashboard:write', 'Create/publish announcements'
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = 'dashboard:write')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'admin' AND p.name = 'dashboard:write'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id = "
        "(SELECT id FROM permissions WHERE name = 'dashboard:write')"
    )
    op.execute("DELETE FROM permissions WHERE name = 'dashboard:write'")
