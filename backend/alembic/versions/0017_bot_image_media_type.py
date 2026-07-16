"""Store the validated media type of a bot image

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-16 00:00:00

The image endpoint let Starlette guess the media type from the stored filename,
so an "evil.html" file carrying valid GIF magic bytes was served as text/html.
Persist the type detected from the magic bytes instead.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bots", sa.Column("image_media_type", sa.String(100), nullable=True))
    # Existing rows were validated as images on upload; default them to a
    # non-executable type rather than guessing from the extension.
    op.execute("UPDATE bots SET image_media_type = 'application/octet-stream' WHERE image_name IS NOT NULL")


def downgrade() -> None:
    op.drop_column("bots", "image_media_type")
