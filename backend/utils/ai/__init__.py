"""AI Campaign Intelligence services.

Each module here follows the house pattern established by utils/brand_matcher.py,
utils/trust_scorer.py and utils/sponsorship_analyzer.py:

  1. Deterministic backbone computed from real stored data.
  2. Optional Gemini augmentation (never required, never overrides numbers it
     didn't compute, always degrades gracefully when GEMINI_API_KEY is unset).
  3. Missing data renders as "Insufficient data" / None — never fabricated.

None of these modules recompute Trust Score (utils.trust_scorer) or Tier
(utils.tiering) — they consume utils.tiering.compose_creator_intelligence()
output as an input.
"""
