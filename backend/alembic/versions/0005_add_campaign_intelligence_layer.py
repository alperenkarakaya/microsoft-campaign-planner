"""add AI campaign intelligence layer (additive only)

Adds the multi-creator AI campaign matching / brief / content / execution /
insight tables described in CLAUDE.md's Intelligence Pipeline extension.
Entirely additive: Campaign.influencer_id (the legacy single-creator field)
and every existing column/table are untouched.

Revision ID: 0005_campaign_intelligence
Revises: 0004_enrichment_tracking
Create Date: 2026-08-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_campaign_intelligence"
down_revision = "0004_enrichment_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("ai_campaign_brief", sa.JSON, nullable=True))

    op.create_table(
        "campaign_creators",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False, index=True),
        sa.Column("influencer_id", sa.Integer, sa.ForeignKey("influencers.id"), nullable=False, index=True),
        sa.Column("status", sa.String, nullable=False, server_default="matched"),
        sa.Column("recommended_role", sa.String, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("views", sa.Integer, nullable=True),
        sa.Column("engagement", sa.Integer, nullable=True),
        sa.Column("clicks", sa.Integer, nullable=True),
        sa.Column("conversions", sa.Integer, nullable=True),
        sa.Column("revenue", sa.Float, nullable=True),
        sa.Column("spend", sa.Float, nullable=True),
        sa.Column("added_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("campaign_id", "influencer_id", name="uq_campaign_creator"),
    )

    op.create_table(
        "campaign_matches",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False, index=True),
        sa.Column("influencer_id", sa.Integer, sa.ForeignKey("influencers.id"), nullable=False, index=True),
        sa.Column("match_score", sa.Float, nullable=True),
        sa.Column("audience_fit", sa.Float, nullable=True),
        sa.Column("brand_fit", sa.Float, nullable=True),
        sa.Column("category_fit", sa.Float, nullable=True),
        sa.Column("geographic_fit", sa.Float, nullable=True),
        sa.Column("budget_fit", sa.Float, nullable=True),
        sa.Column("trust_component", sa.Float, nullable=True),
        sa.Column("sponsorship_component", sa.Float, nullable=True),
        sa.Column("risk_level", sa.String, nullable=True),
        sa.Column("reasons", sa.JSON, nullable=True),
        sa.Column("recommended_role", sa.String, nullable=True),
        sa.Column("confidence", sa.String, nullable=True),
        sa.Column("estimated_reach", sa.Integer, nullable=True),
        sa.Column("estimated_cost_low", sa.Float, nullable=True),
        sa.Column("estimated_cost_high", sa.Float, nullable=True),
        sa.Column("source", sa.String, nullable=True),
        sa.Column("computed_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("campaign_id", "influencer_id", name="uq_campaign_match"),
    )

    op.create_table(
        "campaign_briefs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False, index=True),
        sa.Column("influencer_id", sa.Integer, sa.ForeignKey("influencers.id"), nullable=False, index=True),
        sa.Column("objective", sa.Text, nullable=True),
        sa.Column("key_message", sa.Text, nullable=True),
        sa.Column("content_format", sa.String, nullable=True),
        sa.Column("creative_direction", sa.Text, nullable=True),
        sa.Column("hook", sa.Text, nullable=True),
        sa.Column("talking_points", sa.JSON, nullable=True),
        sa.Column("cta", sa.Text, nullable=True),
        sa.Column("dos", sa.JSON, nullable=True),
        sa.Column("donts", sa.JSON, nullable=True),
        sa.Column("required_disclosures", sa.Text, nullable=True),
        sa.Column("deadline", sa.DateTime, nullable=True),
        sa.Column("deliverables", sa.JSON, nullable=True),
        sa.Column("source", sa.String, nullable=True),
        sa.Column("generated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("campaign_id", "influencer_id", name="uq_campaign_brief"),
    )

    op.create_table(
        "creator_content",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("influencer_id", sa.Integer, sa.ForeignKey("influencers.id"), nullable=False, index=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=True, index=True),
        sa.Column("content_type", sa.String, nullable=False),
        sa.Column("caption", sa.Text, nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("hook", sa.Text, nullable=True),
        sa.Column("video_concept", sa.Text, nullable=True),
        sa.Column("script_outline", sa.Text, nullable=True),
        sa.Column("cta", sa.Text, nullable=True),
        sa.Column("hashtags", sa.JSON, nullable=True),
        sa.Column("talking_points", sa.JSON, nullable=True),
        sa.Column("source", sa.String, nullable=True),
        sa.Column("generated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "campaign_tasks",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("campaign_creator_id", sa.Integer, sa.ForeignKey("campaign_creators.id"), nullable=False, index=True),
        sa.Column("task_type", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("deadline", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "ai_insights",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False, index=True),
        sa.Column("insight_type", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("data_snapshot", sa.JSON, nullable=True),
        sa.Column("generated_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ai_insights")
    op.drop_table("campaign_tasks")
    op.drop_table("creator_content")
    op.drop_table("campaign_briefs")
    op.drop_table("campaign_matches")
    op.drop_table("campaign_creators")
    op.drop_column("campaigns", "ai_campaign_brief")
