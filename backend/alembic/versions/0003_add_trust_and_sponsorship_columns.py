"""add trust_breakdown and sponsorship_profile to influencer_analysis

Phase 2 (Community Trust Depth + Authority) and Phase 3 (Sponsorship
Authenticity) store their scoring outputs as JSON blobs on
InfluencerAnalysis, mirroring the existing predicted_outcome column.

  - trust_breakdown: JSON from utils/trust_scorer.py
  - sponsorship_profile: JSON from utils/sponsorship_analyzer.py

Revision ID: 0003_trust_sponsorship
Revises: 0002_roster_enrichment
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_trust_sponsorship"
down_revision = "0002_roster_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "influencer_analysis",
        sa.Column("trust_breakdown", sa.JSON, nullable=True),
    )
    op.add_column(
        "influencer_analysis",
        sa.Column("sponsorship_profile", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("influencer_analysis", "sponsorship_profile")
    op.drop_column("influencer_analysis", "trust_breakdown")
