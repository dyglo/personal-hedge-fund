"""initial schema"""

from alembic import op
import sqlalchemy as sa


revision = "20260308_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pairs_scanned", sa.JSON(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("ai_provider_used", sa.String(length=50), nullable=True),
        sa.Column("ai_output", sa.JSON(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_metadata", sa.JSON(), nullable=True),
    )
    op.create_index("ix_scan_runs_timestamp", "scan_runs", ["timestamp"])

    op.create_table(
        "detected_setups",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("scan_run_id", sa.Integer(), sa.ForeignKey("scan_runs.id"), nullable=False),
        sa.Column("pair", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.String(length=10), nullable=False),
        sa.Column("bias", sa.String(length=20), nullable=False),
        sa.Column("structure", sa.String(length=20), nullable=False),
        sa.Column("key_level", sa.Float(), nullable=False),
        sa.Column("key_level_type", sa.String(length=20), nullable=False),
        sa.Column("fvg_detected", sa.Boolean(), nullable=False),
        sa.Column("fvg_range", sa.JSON(), nullable=True),
        sa.Column("fib_zone_hit", sa.Boolean(), nullable=False),
        sa.Column("fib_level", sa.Float(), nullable=True),
        sa.Column("liquidity_sweep", sa.Boolean(), nullable=False),
        sa.Column("sweep_level", sa.Float(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("surfaced", sa.Boolean(), nullable=False),
        sa.Column("signals_summary", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
    )
    op.create_index("ix_detected_setups_scan_run_id", "detected_setups", ["scan_run_id"])
    op.create_index("ix_detected_setups_pair", "detected_setups", ["pair"])
    op.create_index("ix_detected_setups_score", "detected_setups", ["score"])


def downgrade() -> None:
    op.drop_index("ix_detected_setups_score", table_name="detected_setups")
    op.drop_index("ix_detected_setups_pair", table_name="detected_setups")
    op.drop_index("ix_detected_setups_scan_run_id", table_name="detected_setups")
    op.drop_table("detected_setups")
    op.drop_index("ix_scan_runs_timestamp", table_name="scan_runs")
    op.drop_table("scan_runs")
