"""
Campaign Report assembler.

Pure composition — this module computes NOTHING new. It assembles the
13-section report from data already produced elsewhere: Campaign,
CampaignCreator actuals, CampaignMatch, creator intelligence
(utils.tiering.compose_creator_intelligence), and AIInsight rows from
utils.ai.performance_analyst. Every section that lacks underlying data says
so explicitly rather than being omitted silently or fabricated.
"""

from typing import Any, Dict, List, Optional


def build_report(
    *,
    campaign_name: str,
    campaign_status: str,
    ai_campaign_brief: Optional[Dict[str, Any]],
    shortlisted_creators: List[Dict[str, Any]],
    creator_intelligence: List[Dict[str, Any]],
    performance: Dict[str, Any],
    creator_performance: List[Dict[str, Any]],
    insights: List[Dict[str, Any]],
) -> Dict[str, Any]:
    objective = (
        (ai_campaign_brief or {}).get("objective")
        or f"No AI-parsed objective on file for '{campaign_name}'. Run POST /ai/analyze to add one."
    )

    if shortlisted_creators:
        names = ", ".join(c.get("display_name", "?") for c in shortlisted_creators[:10])
        creator_selection = f"{len(shortlisted_creators)} creator(s) shortlisted: {names}."
    else:
        creator_selection = "No creators have been shortlisted for this campaign yet."

    ranked = [c for c in creator_performance if c.get("roi_percentage") is not None]
    ranked.sort(key=lambda c: c["roi_percentage"], reverse=True)
    best = ranked[:3]
    # Only report a distinct "weakest" list when the pool is large enough that
    # it doesn't just repeat the best-performers list.
    worst = ranked[-3:] if len(ranked) > 3 else []

    if performance.get("roi_percentage") is not None:
        roi_analysis = (
            f"Blended campaign ROI is {performance['roi_percentage']:.1f}% across "
            f"{performance.get('data_completeness', 'unknown')} data coverage."
        )
    else:
        roi_analysis = "Insufficient data. No creator has both revenue and spend recorded yet."

    key_insights = [i["content"] for i in insights if i.get("insight_type") in ("why", "what_happened")]
    what_next = [i["content"] for i in insights if i.get("insight_type") == "what_next"]

    risks: List[str] = []
    for ci in creator_intelligence:
        intel = ci.get("intelligence") or {}
        readiness = intel.get("readiness") or {}
        if not readiness.get("gate_passed", True):
            risks.append(
                f"{ci.get('display_name', 'A creator')}: reliability gate failed "
                f"({readiness.get('gate_reason', 'reason unknown')})."
            )
        sr = intel.get("sponsorship_readiness") or {}
        if sr.get("label") == "saturated":
            risks.append(f"{ci.get('display_name', 'A creator')}: sponsorship-saturated audience — ad fatigue risk.")
    if not risks:
        risks = ["No elevated risk flags detected among shortlisted/analyzed creators."]

    recommendations = what_next if what_next else [
        "Run POST /ai/analyze-performance once actuals are recorded to generate grounded recommendations."
    ]

    next_strategy = (
        recommendations[0] if recommendations and "Insufficient" not in recommendations[0]
        else "Insufficient data to propose a next-campaign strategy — record actuals first."
    )

    executive_summary = (
        f"'{campaign_name}' ({campaign_status}): {creator_selection} {roi_analysis}"
    )

    return {
        "executive_summary": executive_summary,
        "campaign_objective": objective,
        "creator_selection": creator_selection,
        "creator_intelligence": creator_intelligence,
        "campaign_performance": performance,
        "creator_performance": creator_performance,
        "best_performing_creators": best,
        "weakest_performing_creators": worst,
        "roi_analysis": roi_analysis,
        "key_insights": key_insights or ["No AI insights generated yet — run POST /ai/analyze-performance."],
        "risks": risks,
        "recommendations": recommendations,
        "next_campaign_strategy": next_strategy,
    }
