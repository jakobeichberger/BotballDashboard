"""Seed papers:write and let mentors self-submit papers + scores

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-15 00:00:00

The paper routes reference a `papers:write` permission that was never
seeded (migration 0002 only created papers:read/review/admin), so only
superusers could create/submit papers. This migration creates it, grants
it to admin, and lets mentors submit their own team's papers and scores.
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Create the missing papers:write permission.
    op.execute(
        """
        INSERT INTO permissions (id, name, description)
        SELECT gen_random_uuid()::text, 'papers:write', 'Create/submit papers'
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = 'papers:write')
        """
    )
    # 2) Grant papers:write to the admin role (all-access) so non-superuser admins work.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'admin' AND p.name = 'papers:write'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )
    # 3) Let mentors submit their own team's papers and match scores.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'mentor' AND p.name IN ('papers:write', 'scoring:write')
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id = (SELECT id FROM roles WHERE name = 'mentor')
          AND permission_id IN (
              SELECT id FROM permissions WHERE name IN ('papers:write', 'scoring:write')
          )
        """
    )
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id = "
        "(SELECT id FROM permissions WHERE name = 'papers:write')"
    )
    op.execute("DELETE FROM permissions WHERE name = 'papers:write'")
