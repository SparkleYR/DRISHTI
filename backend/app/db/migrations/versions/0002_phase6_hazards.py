"""Add local Phase 6 hazard workflow tables.

Revision ID: 0002_phase6_hazards
Revises: 0001_phase0_baseline
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_phase6_hazards"
down_revision = "0001_phase0_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hazards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("category", sa.String(length=96), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("map_id", sa.String(length=96), nullable=True),
        sa.Column("map_version", sa.String(length=64), nullable=True),
        sa.Column("map_x", sa.Float(), nullable=True),
        sa.Column("map_y", sa.Float(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confirmation_count", sa.Integer(), nullable=False),
        sa.Column("temporary", sa.Boolean(), nullable=False),
        sa.Column("assigned_to", sa.String(length=96), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("evidence_path", sa.Text(), nullable=True),
        sa.Column("merged_into_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["merged_into_id"], ["hazards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hazards_category", "hazards", ["category"])
    op.create_index("ix_hazards_status", "hazards", ["status"])
    op.create_table(
        "hazard_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hazard_id", sa.String(length=36), nullable=False),
        sa.Column("source_hazard_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["hazard_id"], ["hazards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hazard_observations_hazard_id",
        "hazard_observations",
        ["hazard_id"],
    )
    op.create_table(
        "hazard_status_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("hazard_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=False),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_alias", sa.String(length=96), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["hazard_id"], ["hazards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hazard_status_history_hazard_id",
        "hazard_status_history",
        ["hazard_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hazard_status_history_hazard_id",
        table_name="hazard_status_history",
    )
    op.drop_table("hazard_status_history")
    op.drop_index(
        "ix_hazard_observations_hazard_id",
        table_name="hazard_observations",
    )
    op.drop_table("hazard_observations")
    op.drop_index("ix_hazards_status", table_name="hazards")
    op.drop_index("ix_hazards_category", table_name="hazards")
    op.drop_table("hazards")
