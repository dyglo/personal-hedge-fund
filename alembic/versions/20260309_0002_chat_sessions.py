"""add chat sessions table"""

from alembic import op
import sqlalchemy as sa


revision = "20260309_0002"
down_revision = "20260308_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
    )
    op.create_index("ix_chat_sessions_updated_at", "chat_sessions", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_updated_at", table_name="chat_sessions")
    op.drop_table("chat_sessions")
