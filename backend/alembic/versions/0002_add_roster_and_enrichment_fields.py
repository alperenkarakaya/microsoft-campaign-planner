"""add roster and enrichment fields to influencers

Extends the influencers table with columns for roster ingestion (Phase 0)
and deterministic enrichment signals (Phase 1):
  - source_handle: the @handle from the curated roster spreadsheet
  - business_email: contact email from the roster
  - talent_agency: YES/NO flag from the roster (nullable bool)
  - enrichment_signals: JSON blob of deterministic signals from utils/signals.py

Revision ID: 0002_roster_enrichment
Revises: 0001_initial_schema
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_roster_enrichment"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("influencers", sa.Column("source_handle", sa.String, nullable=True, index=True))
    op.add_column("influencers", sa.Column("business_email", sa.String, nullable=True))
    op.add_column("influencers", sa.Column("talent_agency", sa.Boolean, nullable=True))
    op.add_column("influencers", sa.Column("enrichment_signals", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("influencers", "enrichment_signals")
    op.drop_column("influencers", "talent_agency")
    op.drop_column("influencers", "business_email")
    op.drop_column("influencers", "source_handle")
