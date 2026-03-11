"""add user profile table"""

from alembic import op
import sqlalchemy as sa


revision = "20260311_0004"
down_revision = "20260309_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("device_token", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("experience_level", sa.String(length=20), nullable=False),
        sa.Column("watchlist", sa.JSON(), nullable=False),
        sa.Column("account_balance", sa.Float(), nullable=False),
        sa.Column("risk_pct", sa.Float(), nullable=False),
        sa.Column("min_rr", sa.String(length=10), nullable=False),
        sa.Column("sessions", sa.JSON(), nullable=False),
        sa.Column("prophet_md", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("device_token"),
    )
    op.create_index("ix_user_profiles_device_token", "user_profiles", ["device_token"])
    op.create_index("ix_user_profiles_created_at", "user_profiles", ["created_at"])
    op.create_index("ix_user_profiles_updated_at", "user_profiles", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_user_profiles_updated_at", table_name="user_profiles")
    op.drop_index("ix_user_profiles_created_at", table_name="user_profiles")
    op.drop_index("ix_user_profiles_device_token", table_name="user_profiles")
    op.drop_table("user_profiles")
