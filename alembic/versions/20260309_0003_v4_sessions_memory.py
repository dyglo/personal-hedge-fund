"""add sessions and prophet memory tables"""

from alembic import op
import sqlalchemy as sa


revision = "20260309_0003"
down_revision = "20260309_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("messages", sa.Text(), nullable=False),
    )
    op.create_index("ix_sessions_started_at", "sessions", ["started_at"])
    op.create_index("ix_sessions_ended_at", "sessions", ["ended_at"])

    op.create_table(
        "prophet_memory",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_prophet_memory_updated_at", "prophet_memory", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_prophet_memory_updated_at", table_name="prophet_memory")
    op.drop_table("prophet_memory")
    op.drop_index("ix_sessions_ended_at", table_name="sessions")
    op.drop_index("ix_sessions_started_at", table_name="sessions")
    op.drop_table("sessions")
