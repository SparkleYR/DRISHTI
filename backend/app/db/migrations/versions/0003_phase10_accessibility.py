"""Add Phase 10 versioned indoor accessibility routes.

Revision ID: 0003_phase10_accessibility
Revises: 0002_phase6_hazards
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_phase10_accessibility"
down_revision = "0002_phase6_hazards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accessibility_routes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("route_key", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("map_id", sa.String(length=96), nullable=False),
        sa.Column("map_version", sa.String(length=64), nullable=False),
        sa.Column("specification_version", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_key", "specification_version", name="uq_route_version"),
    )
    op.create_index("ix_accessibility_routes_route_key", "accessibility_routes", ["route_key"])
    op.create_table(
        "accessibility_segments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("route_id", sa.String(length=64), nullable=False),
        sa.Column("segment_key", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("start_x", sa.Float(), nullable=False),
        sa.Column("start_y", sa.Float(), nullable=False),
        sa.Column("end_x", sa.Float(), nullable=False),
        sa.Column("end_y", sa.Float(), nullable=False),
        sa.Column("corridor_radius", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["accessibility_routes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("route_id", "segment_key", name="uq_route_segment"),
    )
    op.create_index("ix_accessibility_segments_route_id", "accessibility_segments", ["route_id"])

    route_table = sa.table(
        "accessibility_routes",
        sa.column("id", sa.String), sa.column("route_key", sa.String),
        sa.column("name", sa.String), sa.column("description", sa.Text),
        sa.column("map_id", sa.String), sa.column("map_version", sa.String),
        sa.column("specification_version", sa.String), sa.column("active", sa.Boolean),
    )
    segment_table = sa.table(
        "accessibility_segments",
        sa.column("id", sa.String), sa.column("route_id", sa.String),
        sa.column("segment_key", sa.String), sa.column("name", sa.String),
        sa.column("sequence", sa.Integer), sa.column("start_x", sa.Float),
        sa.column("start_y", sa.Float), sa.column("end_x", sa.Float),
        sa.column("end_y", sa.Float), sa.column("corridor_radius", sa.Float),
    )
    op.bulk_insert(route_table, [{
        "id": "hall-obstacle-course-v1",
        "route_key": "hall-obstacle-course",
        "name": "Hall Obstacle Course",
        "description": "Versioned normalized reference route for the indoor judging demonstration.",
        "map_id": "hackathon-demo-hall",
        "map_version": "1",
        "specification_version": "1.0.0",
        "active": True,
    }])
    op.bulk_insert(segment_table, [
        {"id": "hall-v1-entrance", "route_id": "hall-obstacle-course-v1", "segment_key": "entrance", "name": "Entrance approach", "sequence": 1, "start_x": 0.5, "start_y": 0.95, "end_x": 0.5, "end_y": 0.67, "corridor_radius": 0.13},
        {"id": "hall-v1-main-aisle", "route_id": "hall-obstacle-course-v1", "segment_key": "main-aisle", "name": "Main hall aisle", "sequence": 2, "start_x": 0.5, "start_y": 0.67, "end_x": 0.5, "end_y": 0.34, "corridor_radius": 0.13},
        {"id": "hall-v1-judge-approach", "route_id": "hall-obstacle-course-v1", "segment_key": "judge-approach", "name": "Judge table approach", "sequence": 3, "start_x": 0.5, "start_y": 0.34, "end_x": 0.5, "end_y": 0.08, "corridor_radius": 0.13},
    ])


def downgrade() -> None:
    op.drop_index("ix_accessibility_segments_route_id", table_name="accessibility_segments")
    op.drop_table("accessibility_segments")
    op.drop_index("ix_accessibility_routes_route_key", table_name="accessibility_routes")
    op.drop_table("accessibility_routes")
