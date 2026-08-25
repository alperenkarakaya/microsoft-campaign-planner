"""initial schema

Captures the full v2.1 schema in one baseline revision: users, influencers,
campaigns, brand_profiles, influencer_analysis, influencer_recommendations.
Replaces the previous alembic_manuel_migration.py one-off helper.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("email", sa.String, unique=True, index=True),
        sa.Column("username", sa.String, unique=True, index=True),
        sa.Column("hashed_password", sa.String),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "influencers",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("platform", sa.String, index=True),
        sa.Column("platform_id", sa.String, unique=True, index=True),
        sa.Column("username", sa.String, index=True),
        sa.Column("display_name", sa.String),
        sa.Column("followers_count", sa.Integer),
        sa.Column("engagement_rate", sa.Float),
        sa.Column("category", sa.String),
        sa.Column("country", sa.String),
        sa.Column("avatar_url", sa.String, nullable=True),
        sa.Column("bio", sa.String, nullable=True),
        sa.Column("verified", sa.Boolean, default=False),
        sa.Column("fake_follower_percentage", sa.Float, default=0.0),
        sa.Column("last_updated", sa.DateTime, server_default=sa.func.now()),
        sa.Column("platform_metadata", sa.JSON, nullable=True),
    )

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String, index=True),
        sa.Column("description", sa.String, nullable=True),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("influencer_id", sa.Integer, sa.ForeignKey("influencers.id")),
        sa.Column("budget", sa.Float),
        sa.Column("start_date", sa.DateTime),
        sa.Column("end_date", sa.DateTime, nullable=True),
        sa.Column("status", sa.String, default="planning"),
        sa.Column("views", sa.Integer, default=0),
        sa.Column("likes", sa.Integer, default=0),
        sa.Column("comments", sa.Integer, default=0),
        sa.Column("shares", sa.Integer, default=0),
        sa.Column("clicks", sa.Integer, default=0),
        sa.Column("conversions", sa.Integer, default=0),
        sa.Column("revenue", sa.Float, default=0.0),
        sa.Column("roi_percentage", sa.Float, default=0.0),
        sa.Column("cpm", sa.Float, default=0.0),
        sa.Column("cpc", sa.Float, default=0.0),
        sa.Column("cpa", sa.Float, default=0.0),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "brand_profiles",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("name", sa.String, index=True),
        sa.Column("aggressive_score", sa.Float, default=5.0),
        sa.Column("creative_score", sa.Float, default=5.0),
        sa.Column("humorous_score", sa.Float, default=5.0),
        sa.Column("professional_score", sa.Float, default=5.0),
        sa.Column("edgy_score", sa.Float, default=5.0),
        sa.Column("target_age_min", sa.Integer, default=18),
        sa.Column("target_age_max", sa.Integer, default=45),
        sa.Column("target_gender", sa.String, default="all"),
        sa.Column("target_countries", sa.JSON),
        sa.Column("min_followers", sa.Integer, default=10000),
        sa.Column("max_followers", sa.Integer, default=10000000),
        sa.Column("preferred_categories", sa.JSON),
        sa.Column("budget_range_min", sa.Float, nullable=True),
        sa.Column("budget_range_max", sa.Float, nullable=True),
        sa.Column("target_aov", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "influencer_analysis",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("influencer_id", sa.Integer, sa.ForeignKey("influencers.id")),
        sa.Column("brand_profile_id", sa.Integer, sa.ForeignKey("brand_profiles.id")),
        sa.Column("content_style_match_score", sa.Float),
        sa.Column("audience_match_score", sa.Float),
        sa.Column("engagement_quality_score", sa.Float),
        sa.Column("brand_safety_score", sa.Float),
        sa.Column("overall_match_score", sa.Float),
        sa.Column("original_match_score", sa.Float, nullable=True),
        sa.Column("override_reason", sa.Text, nullable=True),
        sa.Column("ai_analysis_summary", sa.Text),
        sa.Column("top_video_themes", sa.JSON),
        sa.Column("audience_demographics", sa.JSON),
        sa.Column("content_tone", sa.String),
        sa.Column("quality_flags", sa.JSON, nullable=True),
        sa.Column("predicted_outcome", sa.JSON, nullable=True),
        sa.Column("cpm_benchmark_low", sa.Float, nullable=True),
        sa.Column("cpm_benchmark_high", sa.Float, nullable=True),
        sa.Column("analyzed_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "influencer_recommendations",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("brand_profile_id", sa.Integer, sa.ForeignKey("brand_profiles.id")),
        sa.Column("micro_influencers", sa.JSON),
        sa.Column("macro_influencers", sa.JSON),
        sa.Column("mega_influencers", sa.JSON),
        sa.Column("recommended_budget_low", sa.Float),
        sa.Column("recommended_budget_high", sa.Float),
        sa.Column("projected_total_reach_low", sa.Integer),
        sa.Column("projected_total_reach_high", sa.Integer),
        sa.Column("predicted_total_revenue_low", sa.Float, nullable=True),
        sa.Column("predicted_total_revenue_high", sa.Float, nullable=True),
        sa.Column("predicted_total_roi_low", sa.Float, nullable=True),
        sa.Column("predicted_total_roi_high", sa.Float, nullable=True),
        sa.Column("campaign_strategy", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("influencer_recommendations")
    op.drop_table("influencer_analysis")
    op.drop_table("brand_profiles")
    op.drop_table("campaigns")
    op.drop_table("influencers")
    op.drop_table("users")
