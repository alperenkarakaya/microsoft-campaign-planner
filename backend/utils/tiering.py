"""
Reliability/Readiness gate + Intrinsic Tiering (Phase 4).

Composes outputs from Phase 1 (enrichment_signals), Phase 2
(trust_breakdown), and Phase 3 (sponsorship_profile) into:

  1. **Reliability/Readiness flags** — a QUALIFICATION GATE, not a ranker.
     Flags: active/dormant, reachable, agency_managed, view_stable.
     Used to gate or annotate creators; never to drive ranking.

  2. **Intrinsic tier (S / A / B)** — determined by AUDIENCE TRUST ONLY,
     with Reliability as a gate.  Sponsorship maturity is surfaced as a
     visible label and secondary sort signal but NEVER gates the tier.
     Follower count is NOT the spine.

  3. **Sponsorship readiness** — a separate qualification label that
     answers "How ready is this creator for brand partnerships?"
     Independent of tier assignment.

Output shape:
  {
    "tier": "S" | "A" | "B" | null,
    "tier_label": str,
    "tier_explanation": str,
    "confidence": "high" | "medium" | "low",
    "readiness": {
      "is_active": bool | null,
      "is_reachable": bool | null,
      "is_agency_managed": bool | null,
      "view_stability": "stable" | "moderate" | "volatile" | null,
      "flags": [str],
      "gate_passed": bool,
      "gate_reason": str | null,
    },
    "trust_score": float | null,
    "sponsorship_score": float | null,
    "sponsorship_readiness": {
      "label": str | null,
      "score": float | null,
      "explanation": str,
      "outreach_implication": str,
    },
    "override_reason": str | null,
  }

Rules (non-negotiable):
  - Trust determines tier. Sponsorship readiness is a SEPARATE label.
  - Missing layers => lower confidence / "untiered" with reason. Never fabricate.
  - Follower count never drives tier.
  - Mirrors cap/override_reason discipline from brand_matcher.py.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reliability / Readiness gate
# ---------------------------------------------------------------------------

# Upload cadence thresholds (in days since last upload)
_DORMANT_DAYS = 90       # No upload in 90+ days => dormant
_INACTIVE_DAYS = 180     # No upload in 180+ days => inactive

# View consistency CV thresholds
_VIEW_STABLE_CV = 0.40   # CV <= 0.40 => stable views
_VIEW_VOLATILE_CV = 0.80  # CV > 0.80 => volatile (algorithm-driven)


def compute_readiness(
    enrichment_signals: Optional[Dict[str, Any]],
    influencer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute reliability/readiness flags from Phase-1 signals + roster data.

    This is a QUALIFICATION GATE — it flags partnership readiness, it does
    NOT rank creators.

    Args:
        enrichment_signals: Influencer.enrichment_signals JSON blob.
        influencer: Dict with optional keys: business_email, talent_agency.

    Returns:
        Readiness dict with flags and gate_passed bool.
    """
    flags: List[str] = []
    reasons: List[str] = []
    inf = influencer or {}

    # --- Activity / Recency ---
    is_active: Optional[bool] = None
    if enrichment_signals:
        cadence = enrichment_signals.get("upload_cadence") or {}
        last_upload_days = cadence.get("last_upload_days_ago")
        if last_upload_days is not None:
            if last_upload_days <= _DORMANT_DAYS:
                is_active = True
                flags.append("active")
            elif last_upload_days <= _INACTIVE_DAYS:
                is_active = False
                flags.append("dormant")
                reasons.append(
                    f"last upload {last_upload_days:.0f} days ago (dormant)"
                )
            else:
                is_active = False
                flags.append("inactive")
                reasons.append(
                    f"last upload {last_upload_days:.0f} days ago (inactive)"
                )
        else:
            flags.append("activity_unknown")
    else:
        flags.append("no_enrichment_signals")

    # --- Contactability (business email present) ---
    is_reachable: Optional[bool] = None
    business_email = inf.get("business_email")
    if business_email:
        is_reachable = True
        flags.append("reachable")
    else:
        is_reachable = False
        flags.append("not_reachable")

    # --- Agency status ---
    is_agency_managed: Optional[bool] = None
    talent_agency = inf.get("talent_agency")
    if talent_agency is True:
        is_agency_managed = True
        flags.append("agency_managed")
    elif talent_agency is False:
        is_agency_managed = False
        flags.append("independent")
    else:
        is_agency_managed = None
        flags.append("agency_unknown")

    # --- View stability ---
    view_stability: Optional[str] = None
    if enrichment_signals:
        vc = enrichment_signals.get("view_consistency") or {}
        cv = vc.get("recent_view_cv")
        if cv is not None:
            if cv <= _VIEW_STABLE_CV:
                view_stability = "stable"
                flags.append("view_stable")
            elif cv <= _VIEW_VOLATILE_CV:
                view_stability = "moderate"
                flags.append("view_moderate")
            else:
                view_stability = "volatile"
                flags.append("view_volatile")
                reasons.append(f"view CV={cv:.2f} (volatile/algorithm-driven)")
        else:
            view_stability = None

    # --- Gate decision ---
    # Gate passes if the creator is active (or activity unknown) AND at least
    # one of reachable or agency_managed. If we have no enrichment signals at
    # all, gate fails (cannot qualify without data).
    gate_passed = True
    gate_reason = None

    if is_active is False:
        gate_passed = False
        gate_reason = "creator is dormant or inactive"
    elif enrichment_signals is None:
        gate_passed = False
        gate_reason = "no enrichment signals — cannot assess readiness"

    return {
        "is_active": is_active,
        "is_reachable": is_reachable,
        "is_agency_managed": is_agency_managed,
        "view_stability": view_stability,
        "flags": flags,
        "gate_passed": gate_passed,
        "gate_reason": "; ".join(reasons) if reasons else gate_reason,
    }


# ---------------------------------------------------------------------------
# Intrinsic Tier (S / A / B)
# ---------------------------------------------------------------------------

# Trust score boundaries (0-100 scale from trust_scorer.py)
# Trust is the SOLE driver of tier assignment (Model C).
_TRUST_HIGH = 58.0   # >= 58 = strong community trust
_TRUST_LOW = 38.0    # < 38 = shallow community

# Sponsorship readiness outreach implications (by maturity label)
_OUTREACH_IMPLICATIONS = {
    "mature": "Experienced with brand deals. Send a professional proposal.",
    "emerging": "Early sponsorship experience. Position as a growth partnership.",
    "unproven": "No sponsorship history detected. Pitch as a discovery/test opportunity.",
    "saturated": "High ad density. Differentiate your offer from existing sponsors.",
    "unknown": "Sponsorship history could not be assessed.",
}


def _build_sponsorship_readiness(
    sponsorship_profile: Optional[Dict[str, Any]],
    sponsorship_score: Optional[float],
) -> Dict[str, Any]:
    """Build the sponsorship readiness label from the sponsorship profile.

    This is INDEPENDENT of tier assignment — it answers "How ready is this
    creator for brand partnerships?" without affecting their quality tier.
    """
    if sponsorship_profile is None or sponsorship_profile.get("status") == "unanalyzed":
        return {
            "label": None,
            "score": sponsorship_score,
            "explanation": "Sponsorship history could not be assessed.",
            "outreach_implication": _OUTREACH_IMPLICATIONS["unknown"],
        }

    maturity = sponsorship_profile.get("maturity") or {}
    label = maturity.get("label")
    sponsored_ratio = maturity.get("sponsored_ratio")
    quality = sponsorship_profile.get("quality") or {}
    repeat_sponsors = quality.get("repeat_sponsors", [])

    # Build explanation from maturity data
    if label == "mature":
        ratio_pct = f"{sponsored_ratio * 100:.0f}%" if sponsored_ratio is not None else "N/A"
        repeat_part = " with repeat sponsors detected" if repeat_sponsors else ""
        explanation = (
            f"Mature: {ratio_pct} of recent videos contain sponsorship "
            f"signals{repeat_part}."
        )
    elif label == "emerging":
        ratio_pct = f"{sponsored_ratio * 100:.0f}%" if sponsored_ratio is not None else "a few"
        explanation = (
            f"Emerging: {ratio_pct} of recent videos show early sponsorship "
            f"activity."
        )
    elif label == "unproven":
        explanation = "Unproven: no sponsorship signals detected in recent videos."
    elif label == "saturated":
        ratio_pct = f"{sponsored_ratio * 100:.0f}%" if sponsored_ratio is not None else "most"
        explanation = (
            f"Saturated: {ratio_pct} of recent videos contain sponsorship "
            f"signals — ad fatigue risk."
        )
    else:
        label = label or "unknown"
        explanation = "Sponsorship history could not be assessed."

    outreach = _OUTREACH_IMPLICATIONS.get(label, _OUTREACH_IMPLICATIONS["unknown"])

    return {
        "label": label,
        "score": sponsorship_score,
        "explanation": explanation,
        "outreach_implication": outreach,
    }


def compute_intrinsic_tier(
    trust_breakdown: Optional[Dict[str, Any]],
    sponsorship_profile: Optional[Dict[str, Any]],
    readiness: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute intrinsic agency tier (S / A / B) from stored analysis layers.

    Model C: Trust determines tier, sponsorship is a visible label only.

      - Trust (Phase 2) is the SOLE driver of tier assignment.
      - Sponsorship (Phase 3) is surfaced as a separate readiness label and
        secondary sort signal — it NEVER gates or affects the tier.
      - Reliability (computed above) is a GATE: if it fails, tier is capped
        at B regardless of trust score.
      - Follower count is NEVER used.

    Tier definitions (trust-only):
      S — high audience trust + reachable + reliably active.
      A — high-potential (high trust but not reachable/active, or moderate trust).
      B — commodity/nurture (low audience trust, or reliability gate failure).

    Missing trust layer => untiered with reason, never fabricated.
    """
    override_reasons: List[str] = []

    # Extract composite scores
    trust_score: Optional[float] = None
    sponsorship_score: Optional[float] = None
    trust_confidence: Optional[str] = None
    sponsorship_confidence: Optional[str] = None

    if trust_breakdown and trust_breakdown.get("status") != "unanalyzed":
        trust_score = trust_breakdown.get("composite_trust_score")
        trust_confidence = trust_breakdown.get("confidence")
    else:
        override_reasons.append("trust layer missing or unanalyzed")

    if sponsorship_profile and sponsorship_profile.get("status") != "unanalyzed":
        sponsorship_score = sponsorship_profile.get("composite_sponsorship_score")
        sponsorship_confidence = sponsorship_profile.get("confidence")
    else:
        override_reasons.append("sponsorship layer missing or unanalyzed")

    # --- Build sponsorship readiness (independent of tier) ---
    sponsorship_readiness = _build_sponsorship_readiness(
        sponsorship_profile, sponsorship_score,
    )

    # --- If trust layer is missing, return untiered ---
    if trust_score is None:
        return {
            "tier": None,
            "tier_label": "Untiered",
            "tier_explanation": (
                "Cannot compute tier: trust layer is missing or unanalyzed. "
                "Tier is based on audience trust only."
            ),
            "confidence": "low",
            "readiness": readiness,
            "trust_score": None,
            "sponsorship_score": sponsorship_score,
            "sponsorship_readiness": sponsorship_readiness,
            "override_reason": "; ".join(override_reasons) if override_reasons else None,
        }

    # --- Reliability gate: if gate fails, cap at B ---
    gate_capped = False
    if not readiness.get("gate_passed", False):
        gate_capped = True
        override_reasons.append(
            f"reliability gate failed: {readiness.get('gate_reason', 'unknown')} "
            f"— tier capped at B"
        )

    # --- Compute raw tier from TRUST ONLY ---
    trust_high = trust_score >= _TRUST_HIGH
    trust_mid = _TRUST_LOW <= trust_score < _TRUST_HIGH

    # Reachability and activity for S-tier qualification
    is_reachable = readiness.get("is_reachable", False)
    is_active = readiness.get("is_active")  # None = unknown

    # --- Tier assignment (trust-only) ---
    tier: Optional[str] = None
    explanation_parts: List[str] = []

    if trust_high and is_reachable and is_active is not False:
        # S-tier: high audience trust + reachable + active (or activity unknown)
        tier = "S"
        explanation_parts.append(
            f"High audience trust ({trust_score:.1f}) — tier based on "
            f"community engagement and authority, independent of "
            f"sponsorship history"
        )
        if is_active is True:
            explanation_parts.append("reliably active and reachable")
        else:
            explanation_parts.append("reachable (activity status unknown)")

    elif trust_high:
        # A-tier: high trust but not reachable or activity is False
        tier = "A"
        explanation_parts.append(
            f"High audience trust ({trust_score:.1f}) but limited "
            f"reachability or activity — tier based on community "
            f"engagement and authority only"
        )

    elif trust_mid:
        # A-tier: moderate audience trust
        tier = "A"
        explanation_parts.append(
            f"Moderate audience trust ({trust_score:.1f}) — "
            f"high-potential with room for growth. Tier based on "
            f"community engagement and authority only"
        )

    else:
        # B-tier: low audience trust
        tier = "B"
        explanation_parts.append(
            f"Low audience trust ({trust_score:.1f}) — tier based on "
            f"community engagement and authority only"
        )

    # --- Apply reliability gate cap ---
    if gate_capped and tier in ("S", "A"):
        explanation_parts.append(
            f"tier capped from {tier} to B due to reliability gate failure"
        )
        tier = "B"

    # --- Determine confidence ---
    has_trust = trust_score is not None
    has_sponsorship = sponsorship_score is not None
    both_confident = (
        trust_confidence in ("high", "medium")
        and sponsorship_confidence in ("high", "medium")
    )

    if has_trust and has_sponsorship and both_confident and readiness.get("gate_passed"):
        confidence = "high"
    elif has_trust and has_sponsorship:
        confidence = "medium"
    elif has_trust or has_sponsorship:
        confidence = "low"
    else:
        confidence = "low"

    tier_labels = {
        "S": "Priority Partner",
        "A": "High-Potential",
        "B": "Commodity / Nurture",
    }

    return {
        "tier": tier,
        "tier_label": tier_labels.get(tier, "Untiered"),
        "tier_explanation": "; ".join(explanation_parts),
        "confidence": confidence,
        "readiness": readiness,
        "trust_score": trust_score,
        "sponsorship_score": sponsorship_score,
        "sponsorship_readiness": sponsorship_readiness,
        "override_reason": "; ".join(override_reasons) if override_reasons else None,
    }


# ---------------------------------------------------------------------------
# Public composition function
# ---------------------------------------------------------------------------

def compose_creator_intelligence(
    enrichment_signals: Optional[Dict[str, Any]],
    trust_breakdown: Optional[Dict[str, Any]],
    sponsorship_profile: Optional[Dict[str, Any]],
    influencer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compose the full creator-intelligence view from stored layers.

    This is a pure computation over stored data — it does NOT trigger any
    live YouTube/Gemini enrichment.

    Args:
        enrichment_signals: Influencer.enrichment_signals JSON blob (Phase 1).
        trust_breakdown: InfluencerAnalysis.trust_breakdown JSON blob (Phase 2).
        sponsorship_profile: InfluencerAnalysis.sponsorship_profile JSON blob (Phase 3).
        influencer: Dict with optional keys: business_email, talent_agency.

    Returns:
        Creator intelligence dict with tier + readiness + scores.
    """
    readiness = compute_readiness(enrichment_signals, influencer)
    tiering = compute_intrinsic_tier(trust_breakdown, sponsorship_profile, readiness)
    return tiering
