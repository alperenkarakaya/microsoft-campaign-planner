"""utils.ai.report_generator — pure composition, no new computation."""

from utils.ai.report_generator import build_report


def test_empty_campaign_reports_missing_data_honestly():
    report = build_report(
        campaign_name="New Campaign", campaign_status="planning",
        ai_campaign_brief=None, shortlisted_creators=[], creator_intelligence=[],
        performance={"roi_percentage": None, "data_completeness": "none"},
        creator_performance=[], insights=[],
    )
    assert "No creators have been shortlisted" in report["creator_selection"]
    assert "Insufficient data" in report["roi_analysis"]
    assert "No AI insights generated yet" in report["key_insights"][0]


def test_report_surfaces_best_and_risk_flags():
    creator_intelligence = [{
        "influencer_id": 1, "display_name": "Risky Creator",
        "intelligence": {
            "readiness": {"gate_passed": False, "gate_reason": "dormant"},
            "sponsorship_readiness": {"label": "saturated"},
        },
    }]
    creator_performance = [
        {"display_name": "A", "roi_percentage": 200.0},
        {"display_name": "B", "roi_percentage": 50.0},
        {"display_name": "C", "roi_percentage": 10.0},
        {"display_name": "D", "roi_percentage": -20.0},
    ]
    report = build_report(
        campaign_name="Live Campaign", campaign_status="active",
        ai_campaign_brief={"objective": "Drive sales"},
        shortlisted_creators=[{"display_name": "A"}],
        creator_intelligence=creator_intelligence,
        performance={"roi_percentage": 60.0, "data_completeness": "full"},
        creator_performance=creator_performance,
        insights=[{"insight_type": "what_next", "content": "Scale A."}],
    )
    assert report["campaign_objective"] == "Drive sales"
    assert report["best_performing_creators"][0]["display_name"] == "A"
    assert report["weakest_performing_creators"][-1]["display_name"] == "D"
    assert any("Risky Creator" in r for r in report["risks"])
    assert report["recommendations"] == ["Scale A."]
