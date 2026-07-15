"""Team self-management: teams:admin permission + mentor teams:write

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-15 00:00:00

Adds a teams:admin permission (organizer-level: create/delete teams, confirm
registrations) granted to admin, and grants mentors teams:write so they can
manage their own team's details and members (own-team scoping enforced in the
routes via assert_team_access).
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO permissions (id, name, description)
        SELECT gen_random_uuid()::text, 'teams:admin', 'Create/delete teams, confirm registrations'
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = 'teams:admin')
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'admin' AND p.name = 'teams:admin'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'mentor' AND p.name = 'teams:write'
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
          AND permission_id = (SELECT id FROM permissions WHERE name = 'teams:write')
        """
    )
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id = "
        "(SELECT id FROM permissions WHERE name = 'teams:admin')"
    )
    op.execute("DELETE FROM permissions WHERE name = 'teams:admin'")
