"""add enrichment run-state tracking columns to influencers

Phase 6 — enrichment orchestration needs to track per-creator state so the
system knows what's fresh, stale, or failed:

  - last_enriched_at: timestamp of last successful full-pipeline enrichment
  - enrichment_status: "pending" | "running" | "completed" | "partial" | "failed"
  - enrichment_error: error message / reason on last failure (NULL on success)

Revision ID: 0004_enrichment_tracking
Revises: 0003_trust_sponsorship
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_enrichment_tracking"
down_revision = "0003_trust_sponsorship"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "influencers",
        sa.Column("last_enriched_at", sa.DateTime, nullable=True),
    )
    op.add_column(
        "influencers",
        sa.Column("enrichment_status", sa.String, nullable=True),
    )
    op.add_column(
        "influencers",
        sa.Column("enrichment_error", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("influencers", "enrichment_error")
    op.drop_column("influencers", "enrichment_status")
    op.drop_column("influencers", "last_enriched_at")
