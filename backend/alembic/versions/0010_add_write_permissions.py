"""Seed the papers:write and dashboard:write permissions

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-24

modules/paper_review/routes.py and modules/dashboard/routes.py guard their
write endpoints with require_permission("papers:write") / ("dashboard:write"),
but 0002 never seeded those two rows. Because the admin role is granted
"SELECT ... FROM permissions" at seed time, it only ever received the 18
permissions that existed then — so every non-superuser, including a
role-based admin, got 403 on creating/editing papers and announcements.
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO permissions (id, name, description) VALUES
        (gen_random_uuid()::text, 'papers:write', 'Create/edit papers'),
        (gen_random_uuid()::text, 'dashboard:write', 'Create/publish announcements')
        ON CONFLICT (name) DO NOTHING
    """)

    # admin holds every permission
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'admin'
        AND p.name IN ('papers:write','dashboard:write')
        AND NOT EXISTS (
            SELECT 1 FROM role_permissions rp
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
        )
    """)

    # mentors submit their team's paper, matching their existing papers:read
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'mentor'
        AND p.name = 'papers:write'
        AND NOT EXISTS (
            SELECT 1 FROM role_permissions rp
            WHERE rp.role_id = r.id AND rp.permission_id = p.id
        )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE name IN ('papers:write','dashboard:write')
        )
    """)
    op.execute("""
        DELETE FROM permissions WHERE name IN ('papers:write','dashboard:write')
    """)
