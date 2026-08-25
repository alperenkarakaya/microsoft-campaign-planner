import { useEffect, useState, useMemo } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { rosterAPI, campaignIntelligenceAPI } from '../lib/api';
import type { RosterCreator, RosterIntelligenceResponse, CampaignMatchResult } from '../lib/types';

// ---------------------------------------------------------------------------
// Module-level cache so navigating from roster table doesn't re-fetch
// ---------------------------------------------------------------------------
let _cachedData: RosterIntelligenceResponse | null = null;
let _cacheTime = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

export function setRosterCache(data: RosterIntelligenceResponse) {
  _cachedData = data;
  _cacheTime = Date.now();
}

// ---------------------------------------------------------------------------
// Helpers (duplicated from RosterPage for independence — same derivation)
// ---------------------------------------------------------------------------

function formatSubs(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

type RecommendationLabel = 'Strong Buy' | 'Buy' | 'Watchlist' | 'Avoid';

interface RiskFlag {
  emoji: string;
  key: string;
  description: string;
}

const RISK_DESCRIPTIONS: Record<string, string> = {
  volatile: 'View consistency CV > 0.8 -- views are algorithm-driven, not from a loyal base',
  dormant: 'No uploads in 60+ days',
  ad_fatigue: 'Saturated with sponsorships',
  weak_community: 'Trust score below 40',
  low_view_ratio: 'Less than 5% of subscribers watch',
};

function deriveRiskFlags(creator: RosterCreator): RiskFlag[] {
  const flags: RiskFlag[] = [];
  const tb = creator.trust_breakdown;

  if (tb) {
    const ctd = tb.community_trust_depth;
    if (ctd?.components?.view_consistency?.cv != null && ctd.components.view_consistency.cv > 0.8) {
      flags.push({ emoji: '⚡', key: 'volatile', description: RISK_DESCRIPTIONS.volatile });
    }
  }

  if (creator.intelligence.readiness.is_active === false) {
    flags.push({ emoji: '💤', key: 'dormant', description: RISK_DESCRIPTIONS.dormant });
  }

  const srLabel = creator.sponsorship_readiness?.label
    ?? creator.intelligence.sponsorship_readiness?.label;
  if (srLabel === 'saturated') {
    flags.push({ emoji: '📢', key: 'ad_fatigue', description: RISK_DESCRIPTIONS.ad_fatigue });
  }

  if (creator.intelligence.trust_score != null && creator.intelligence.trust_score < 40) {
    flags.push({ emoji: '👥', key: 'weak_community', description: RISK_DESCRIPTIONS.weak_community });
  }

  if (tb) {
    const vc = tb.community_trust_depth?.components?.view_consistency;
    const medianViews = vc?.recent_view_median;
    if (medianViews != null && creator.followers_count > 0) {
      const ratio = (medianViews / creator.followers_count) * 100;
      if (ratio < 5) {
        flags.push({ emoji: '📉', key: 'low_view_ratio', description: RISK_DESCRIPTIONS.low_view_ratio });
      }
    }
  }

  return flags;
}

function deriveRecommendation(creator: RosterCreator): RecommendationLabel {
  const trust = creator.intelligence.trust_score;
  if (trust == null) return 'Avoid';

  const maturityLabel = creator.sponsorship_readiness?.label
    ?? creator.intelligence.sponsorship_readiness?.label
    ?? null;
  const risks = deriveRiskFlags(creator);
  const hasRisks = risks.length > 0;

  const matureOrEmerging = maturityLabel === 'mature' || maturityLabel === 'emerging';

  if (trust >= 65 && matureOrEmerging && !hasRisks) return 'Strong Buy';
  if (trust >= 65 && maturityLabel === 'unproven') return 'Buy';
  if (trust >= 65 && hasRisks) return 'Buy';
  if (trust >= 58 && matureOrEmerging) return 'Buy';
  if (trust >= 58) return 'Buy';
  if (trust >= 38) return 'Watchlist';
  return 'Avoid';
}

const RECOMMENDATION_COLORS: Record<RecommendationLabel, string> = {
  'Strong Buy': '#10b981',
  'Buy': '#3b82f6',
  'Watchlist': '#f59e0b',
  'Avoid': '#ef4444',
};

function getMaturityLabel(creator: RosterCreator): string | null {
  return creator.sponsorship_readiness?.label
    ?? creator.intelligence.sponsorship_readiness?.label
    ?? null;
}

function getOutreachStrategy(maturity: string | null): string {
  switch (maturity) {
    case 'mature': return 'Send professional proposal';
    case 'emerging': return 'Position as growth partnership';
    case 'unproven': return 'Pitch as discovery opportunity';
    case 'saturated': return 'Differentiate from existing sponsors';
    default: return 'Assess further before outreach';
  }
}

function getTopSignals(creator: RosterCreator): Array<{ name: string; score: number }> {
  const tb = creator.trust_breakdown;
  if (!tb) return [];
  const signals: Array<{ name: string; score: number }> = [];

  if (tb.community_trust_depth?.score != null) {
    signals.push({ name: 'Community Trust', score: tb.community_trust_depth.score });
  }
  if (tb.authority?.score != null) {
    signals.push({ name: 'Authority', score: tb.authority.score });
  }
  if (tb.audience_loyalty?.score != null) {
    signals.push({ name: 'Audience Loyalty', score: tb.audience_loyalty.score });
  }
  if (tb.growth_trajectory?.score != null) {
    signals.push({ name: 'Growth Trajectory', score: tb.growth_trajectory.score });
  }
  if (tb.content_consistency?.score != null) {
    signals.push({ name: 'Content Consistency', score: tb.content_consistency.score });
  }

  signals.sort((a, b) => b.score - a.score);
  return signals.slice(0, 3);
}

function extractCommunityScore(creator: RosterCreator): number | null {
  return creator.trust_breakdown?.community_trust_depth?.score ?? null;
}

function extractAuthorityScore(creator: RosterCreator): number | null {
  return creator.trust_breakdown?.authority?.score ?? null;
}

// ---------------------------------------------------------------------------
// Small reusable sub-components
// ---------------------------------------------------------------------------

function ScoreBar({ value, max = 100, color }: { value: number; max?: number; color: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div style={ds.barBg}>
      <div style={{ ...ds.barFill, width: `${pct}%`, background: color }} />
    </div>
  );
}

function ComponentRow({ label, value, points, maxPoints = 25 }: {
  label: string;
  value: string;
  points: number | null;
  maxPoints?: number;
}) {
  const p = points ?? 0;
  const color = p >= maxPoints * 0.7 ? '#10b981' : p >= maxPoints * 0.4 ? '#f59e0b' : '#ef4444';
  return (
    <div style={ds.componentRow}>
      <div style={ds.componentLabel}>{label}</div>
      <div style={ds.componentValue}>{value}</div>
      <div style={ds.componentPoints}>{p.toFixed(1)} pts</div>
      <div style={{ width: '60px' }}>
        <ScoreBar value={p} max={maxPoints} color={color} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export const CreatorDetailPage = () => {
  const { creatorId } = useParams<{ creatorId: string }>();
  const [searchParams] = useSearchParams();
  const campaignId = searchParams.get('campaign_id');
  const [allCreators, setAllCreators] = useState<RosterCreator[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [campaignMatch, setCampaignMatch] = useState<CampaignMatchResult | null>(null);

  useEffect(() => {
    if (!campaignId || !creatorId) return;
    const cid = parseInt(campaignId, 10);
    const iid = parseInt(creatorId, 10);
    campaignIntelligenceAPI.listMatches(cid).then((r) => {
      const match = r.matches.find((m: CampaignMatchResult) => m.influencer_id === iid);
      setCampaignMatch(match ?? null);
    }).catch(() => setCampaignMatch(null));
  }, [campaignId, creatorId]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);

      // Use cache if fresh
      if (_cachedData && Date.now() - _cacheTime < CACHE_TTL) {
        if (!cancelled) {
          setAllCreators(_cachedData.creators);
          setLoading(false);
        }
        return;
      }

      try {
        const result = await rosterAPI.intelligence({ limit: 200 });
        setRosterCache(result);
        if (!cancelled) {
          setAllCreators(result.creators);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.response?.data?.detail || 'Failed to load creator data.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  const creator = useMemo(() => {
    if (!creatorId) return null;
    const id = parseInt(creatorId, 10);
    return allCreators.find((c) => c.influencer_id === id) ?? null;
  }, [allCreators, creatorId]);

  // Find similar creators
  const similarCreators = useMemo(() => {
    if (!creator) return [];
    const trust = creator.intelligence.trust_score ?? 0;
    const community = extractCommunityScore(creator) ?? 0;
    const authority = extractAuthorityScore(creator) ?? 0;

    return allCreators
      .filter((c) => c.influencer_id !== creator.influencer_id)
      .map((c) => {
        const ct = c.intelligence.trust_score ?? 0;
        const cc = extractCommunityScore(c) ?? 0;
        const ca = extractAuthorityScore(c) ?? 0;
        const dist = Math.abs(trust - ct) + Math.abs(community - cc) + Math.abs(authority - ca);
        return { creator: c, distance: dist };
      })
      .sort((a, b) => a.distance - b.distance)
      .slice(0, 5);
  }, [allCreators, creator]);

  // Loading
  if (loading) {
    return (
      <div style={ds.container}>
        <div style={ds.loadingContainer}>
          <div style={ds.loadingSpinner} />
          <p style={ds.loadingText}>Loading creator profile...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={ds.container}>
        <div style={ds.errorBox}>
          <p style={ds.errorText}>{error}</p>
          <Link to="/roster" style={ds.backLink}>{'←'} Back to Roster</Link>
        </div>
      </div>
    );
  }

  if (!creator) {
    return (
      <div style={ds.container}>
        <div style={ds.errorBox}>
          <p style={ds.errorText}>Creator not found.</p>
          <Link to="/roster" style={ds.backLink}>{'←'} Back to Roster</Link>
        </div>
      </div>
    );
  }

  const rec = deriveRecommendation(creator);
  const risks = deriveRiskFlags(creator);
  const maturity = getMaturityLabel(creator);
  const trustScore = creator.intelligence.trust_score;
  const communityScore = extractCommunityScore(creator);
  const authorityScore = extractAuthorityScore(creator);
  const tb = creator.trust_breakdown;
  const ctd = tb?.community_trust_depth;
  const auth = tb?.authority;
  const sp = creator.sponsorship_profile;
  const topSignals = getTopSignals(creator);
  const outreachStrategy = creator.sponsorship_readiness?.outreach_implication
    ?? creator.intelligence.sponsorship_readiness?.outreach_implication
    ?? getOutreachStrategy(maturity);

  const trustColor = trustScore != null
    ? trustScore >= 65 ? '#10b981' : trustScore >= 50 ? '#f59e0b' : '#ef4444'
    : '#9ca3af';

  return (
    <div style={ds.container}>
      {/* Back link */}
      <Link to="/roster" style={ds.backLink}>{'←'} Back to Roster</Link>

      {/* ================================================================
          SECTION 1: Identity + Decision Banner
          ================================================================ */}
      <div style={ds.banner}>
        <div style={ds.bannerLeft}>
          <div style={ds.avatarLarge}>
            {creator.display_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h1 style={ds.bannerName}>{creator.display_name}</h1>
            <div style={ds.bannerMeta}>
              <span style={ds.bannerUsername}>@{creator.username}</span>
              <span style={ds.platformBadge}>
                {creator.platform === 'youtube' ? '📺' : '🌐'} {creator.platform}
              </span>
              <span style={ds.subCount}>{formatSubs(creator.followers_count)} subscribers</span>
            </div>
          </div>
        </div>
        <div style={ds.bannerRight}>
          {/* Tier */}
          <span style={{
            ...ds.tierPillLg,
            background: creator.intelligence.tier === 'S' ? '#f59e0b'
              : creator.intelligence.tier === 'A' ? '#3b82f6'
              : creator.intelligence.tier === 'B' ? '#9ca3af'
              : '#e5e7eb',
            color: creator.intelligence.tier ? '#fff' : '#999',
          }}>
            {creator.intelligence.tier ?? '-'} Tier
          </span>

          {/* Recommendation */}
          <span style={{
            ...ds.recPillLg,
            background: RECOMMENDATION_COLORS[rec] + '18',
            color: RECOMMENDATION_COLORS[rec],
            borderColor: RECOMMENDATION_COLORS[rec],
          }}>
            {rec}
          </span>

          {/* Maturity */}
          {maturity && (
            <span style={{
              ...ds.maturityPillLg,
              background: maturity === 'mature' ? '#d1fae5'
                : maturity === 'emerging' ? '#dbeafe'
                : maturity === 'saturated' ? '#ffedd5'
                : '#f3f4f6',
              color: maturity === 'mature' ? '#065f46'
                : maturity === 'emerging' ? '#1e40af'
                : maturity === 'saturated' ? '#9a3412'
                : '#6b7280',
            }}>
              {maturity}
            </span>
          )}

          {/* Confidence */}
          <span style={{
            ...ds.confidencePill,
            background: creator.intelligence.confidence === 'high' ? '#d1fae5'
              : creator.intelligence.confidence === 'medium' ? '#fef3c7'
              : '#fee2e2',
            color: creator.intelligence.confidence === 'high' ? '#065f46'
              : creator.intelligence.confidence === 'medium' ? '#92400e'
              : '#991b1b',
          }}>
            {creator.intelligence.confidence.toUpperCase()} confidence
          </span>
        </div>
      </div>

      {/* ================================================================
          SECTION 2: Intelligence Breakdown (two-column grid)
          ================================================================ */}
      <div style={ds.intelGrid}>
        {/* ---- LEFT COLUMN: Audience Trust ---- */}
        <div style={ds.column}>
          <h2 style={ds.columnTitle}>{'📊'} Audience Trust</h2>

          {/* Composite trust score */}
          <div style={ds.card}>
            <h3 style={ds.cardTitle}>Composite Trust Score</h3>
            <div style={ds.trustScoreRow}>
              <span style={{ ...ds.trustScoreBig, color: trustColor }}>
                {trustScore != null ? trustScore.toFixed(1) : 'N/A'}
              </span>
              <span style={ds.trustScoreMax}>/ 100</span>
            </div>
            {trustScore != null && (
              <div style={ds.trustBarLgBg}>
                <div style={{
                  ...ds.trustBarLgFill,
                  width: `${Math.min(trustScore, 100)}%`,
                  background: trustColor,
                }} />
              </div>
            )}
          </div>

          {/* Why this tier? */}
          <div style={ds.card}>
            <h3 style={ds.cardTitle}>Why this tier?</h3>
            <p style={ds.cardText}>
              {creator.intelligence.tier_explanation || 'No tier explanation available.'}
            </p>
          </div>

          {/* Community Trust Depth */}
          <div style={ds.card}>
            <h3 style={ds.cardTitle}>Community Trust Depth</h3>
            <div style={ds.scoreHeader}>
              <span style={ds.scoreLabel}>Score</span>
              <span style={ds.scoreValue}>
                {communityScore != null ? communityScore.toFixed(1) : 'N/A'}
              </span>
            </div>
            {ctd?.components && (
              <div style={ds.componentList}>
                <ComponentRow
                  label="Like/View ratio"
                  value={ctd.components.like_view_ratio?.ratio != null
                    ? `${(ctd.components.like_view_ratio.ratio * 100).toFixed(2)}%`
                    : '-'}
                  points={ctd.components.like_view_ratio?.points ?? null}
                />
                <ComponentRow
                  label="Comment/View ratio"
                  value={ctd.components.comment_view_ratio?.ratio != null
                    ? `${(ctd.components.comment_view_ratio.ratio * 100).toFixed(3)}%`
                    : '-'}
                  points={ctd.components.comment_view_ratio?.points ?? null}
                />
                <ComponentRow
                  label="View consistency CV"
                  value={ctd.components.view_consistency?.cv != null
                    ? ctd.components.view_consistency.cv.toFixed(2)
                    : '-'}
                  points={ctd.components.view_consistency?.points ?? null}
                />
                <ComponentRow
                  label="Sample size"
                  value={ctd.components.sample_size?.video_count != null
                    ? `${ctd.components.sample_size.video_count} videos`
                    : '-'}
                  points={ctd.components.sample_size?.points ?? null}
                />
              </div>
            )}
          </div>

          {/* Authority */}
          <div style={ds.card}>
            <h3 style={ds.cardTitle}>Authority</h3>
            <div style={ds.scoreHeader}>
              <span style={ds.scoreLabel}>Score</span>
              <span style={ds.scoreValue}>
                {authorityScore != null ? authorityScore.toFixed(1) : 'N/A'}
              </span>
            </div>
            {auth?.components && (
              <div style={ds.componentList}>
                <ComponentRow
                  label="Reply rate"
                  value={auth.components.reply_rate?.rate != null
                    ? `${(auth.components.reply_rate.rate * 100).toFixed(1)}%`
                    : '-'}
                  points={auth.components.reply_rate?.points ?? null}
                />
                <ComponentRow
                  label="Reply sample size"
                  value={auth.components.reply_sample_size?.count != null
                    ? `${auth.components.reply_sample_size.count} replies`
                    : '-'}
                  points={auth.components.reply_sample_size?.points ?? null}
                />
                <ComponentRow
                  label="Comment depth"
                  value={auth.components.comment_depth?.avg_length != null
                    ? `${auth.components.comment_depth.avg_length.toFixed(0)} chars`
                    : '-'}
                  points={auth.components.comment_depth?.points ?? null}
                />
                <ComponentRow
                  label="View ratio"
                  value={auth.components.view_ratio?.ratio != null
                    ? `${(auth.components.view_ratio.ratio * 100).toFixed(1)}%`
                    : '-'}
                  points={auth.components.view_ratio?.points ?? null}
                />
              </div>
            )}
          </div>
        </div>

        {/* ---- RIGHT COLUMN: Partnership Readiness ---- */}
        <div style={ds.column}>
          <h2 style={ds.columnTitle}>{'🤝'} Partnership Readiness</h2>

          {/* Sponsorship Maturity */}
          <div style={ds.card}>
            <h3 style={ds.cardTitle}>Sponsorship Maturity</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
              {maturity && (
                <span style={{
                  ...ds.maturityPillSm,
                  background: maturity === 'mature' ? '#d1fae5'
                    : maturity === 'emerging' ? '#dbeafe'
                    : maturity === 'saturated' ? '#ffedd5'
                    : '#f3f4f6',
                  color: maturity === 'mature' ? '#065f46'
                    : maturity === 'emerging' ? '#1e40af'
                    : maturity === 'saturated' ? '#9a3412'
                    : '#6b7280',
                }}>
                  {maturity}
                </span>
              )}
            </div>
            <p style={ds.cardText}>
              {creator.sponsorship_readiness?.explanation
                ?? creator.intelligence.sponsorship_readiness?.explanation
                ?? 'Not assessed'}
            </p>
          </div>

          {/* Outreach Strategy */}
          <div style={ds.card}>
            <h3 style={ds.cardTitle}>Outreach Strategy</h3>
            <div style={ds.outreachBox}>
              <p style={ds.outreachText}>{outreachStrategy}</p>
            </div>
          </div>

          {/* Readiness Flags */}
          <div style={ds.card}>
            <h3 style={ds.cardTitle}>Readiness Flags</h3>
            <div style={ds.flagList}>
              <div style={ds.flagRow}>
                <span style={ds.flagIcon}>
                  {creator.intelligence.readiness.is_active === true ? '✅'
                    : creator.intelligence.readiness.is_active === false ? '💤'
                    : '❓'}
                </span>
                <span style={ds.flagLabel}>
                  {creator.intelligence.readiness.is_active === true ? 'Active'
                    : creator.intelligence.readiness.is_active === false ? 'Dormant'
                    : 'Unknown activity'}
                </span>
              </div>
              <div style={ds.flagRow}>
                <span style={ds.flagIcon}>
                  {creator.intelligence.readiness.is_reachable ? '✅' : '❌'}
                </span>
                <span style={ds.flagLabel}>
                  {creator.intelligence.readiness.is_reachable ? 'Reachable' : 'Not reachable'}
                </span>
              </div>
              <div style={ds.flagRow}>
                <span style={ds.flagIcon}>
                  {creator.intelligence.readiness.is_agency_managed ? '🏢' : '👤'}
                </span>
                <span style={ds.flagLabel}>
                  {creator.intelligence.readiness.is_agency_managed ? 'Agency managed' : 'Independent'}
                </span>
              </div>
              <div style={ds.flagRow}>
                <span style={ds.flagIcon}>{'📊'}</span>
                <span style={ds.flagLabel}>
                  View stability: {creator.intelligence.readiness.view_stability ?? 'unknown'}
                </span>
              </div>
            </div>
          </div>

          {/* Risk Assessment */}
          <div style={ds.card}>
            <h3 style={ds.cardTitle}>Risk Assessment</h3>
            {risks.length === 0 ? (
              <p style={{ ...ds.cardText, color: '#10b981', fontWeight: 600 }}>
                {'✅'} No risk flags detected
              </p>
            ) : (
              <div style={ds.riskList}>
                {risks.map((r) => (
                  <div key={r.key} style={ds.riskItem}>
                    <span style={ds.riskEmoji}>{r.emoji}</span>
                    <div>
                      <span style={ds.riskKey}>{r.key.replace(/_/g, ' ')}</span>
                      <span style={ds.riskDesc}> -- {r.description}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Sponsorship Profile */}
          {sp && (
            <div style={ds.card}>
              <h3 style={ds.cardTitle}>Sponsorship Profile</h3>
              <div style={ds.spGrid}>
                {sp.maturity_score != null && (
                  <div style={ds.spItem}>
                    <span style={ds.spLabel}>Maturity Score</span>
                    <span style={ds.spValue}>{sp.maturity_score.toFixed(1)}</span>
                  </div>
                )}
                {sp.maturity_label && (
                  <div style={ds.spItem}>
                    <span style={ds.spLabel}>Label</span>
                    <span style={ds.spValue}>{sp.maturity_label}</span>
                  </div>
                )}
                {sp.quality_score != null && (
                  <div style={ds.spItem}>
                    <span style={ds.spLabel}>Quality Score</span>
                    <span style={ds.spValue}>{sp.quality_score.toFixed(1)}</span>
                  </div>
                )}
                {sp.repeat_sponsors && sp.repeat_sponsors.length > 0 && (
                  <div style={{ ...ds.spItem, gridColumn: '1 / -1' }}>
                    <span style={ds.spLabel}>Repeat Sponsors</span>
                    <span style={ds.spValue}>{sp.repeat_sponsors.join(', ')}</span>
                  </div>
                )}
                {sp.integration_style && (
                  <div style={ds.spItem}>
                    <span style={ds.spLabel}>Integration Style</span>
                    <span style={ds.spValue}>{sp.integration_style}</span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ================================================================
          SECTION 3: Decision Summary
          ================================================================ */}
      <div style={ds.decisionCard}>
        <h2 style={ds.decisionTitle}>{'🎯'} Decision Summary</h2>
        <div style={ds.decisionGrid}>
          {/* Recommendation */}
          <div style={ds.decisionBlock}>
            <h4 style={ds.decisionLabel}>Recommendation</h4>
            <span style={{
              ...ds.recPillLg,
              background: RECOMMENDATION_COLORS[rec] + '18',
              color: RECOMMENDATION_COLORS[rec],
              borderColor: RECOMMENDATION_COLORS[rec],
              fontSize: '1rem',
            }}>
              {rec}
            </span>
            <p style={ds.decisionText}>
              Trust score of {trustScore != null ? trustScore.toFixed(1) : 'N/A'} with{' '}
              {maturity ?? 'unknown'} sponsorship maturity and {risks.length} risk flag{risks.length !== 1 ? 's' : ''}.
            </p>
          </div>

          {/* Strongest positive signals */}
          <div style={ds.decisionBlock}>
            <h4 style={ds.decisionLabel}>Strongest Positive Signals</h4>
            {topSignals.length > 0 ? (
              <div style={ds.signalList}>
                {topSignals.map((sig) => (
                  <div key={sig.name} style={ds.signalItem}>
                    <span style={ds.signalName}>{sig.name}</span>
                    <span style={ds.signalScore}>{sig.score.toFixed(1)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p style={ds.decisionText}>No signal data available.</p>
            )}
          </div>

          {/* Concerns */}
          <div style={ds.decisionBlock}>
            <h4 style={ds.decisionLabel}>Concerns</h4>
            {risks.length > 0 ? (
              <div>
                {risks.map((r) => (
                  <p key={r.key} style={ds.decisionText}>
                    {r.emoji} {r.key.replace(/_/g, ' ')}
                  </p>
                ))}
              </div>
            ) : (
              <p style={{ ...ds.decisionText, color: '#10b981' }}>No concerns identified.</p>
            )}
            {/* Also flag low sub-scores */}
            {communityScore != null && communityScore < 40 && (
              <p style={ds.decisionText}>{'💡'} Community score is low ({communityScore.toFixed(1)})</p>
            )}
            {authorityScore != null && authorityScore < 30 && (
              <p style={ds.decisionText}>{'💡'} Authority score is low ({authorityScore.toFixed(1)})</p>
            )}
          </div>

          {/* Suggested action */}
          <div style={ds.decisionBlock}>
            <h4 style={ds.decisionLabel}>Suggested Action</h4>
            <p style={{ ...ds.decisionText, fontWeight: 600, color: '#667eea' }}>
              {outreachStrategy}
            </p>
          </div>
        </div>
      </div>

      {/* ================================================================
          Similar Creators
          ================================================================ */}
      {similarCreators.length > 0 && (
        <div style={ds.similarCard}>
          <h2 style={ds.decisionTitle}>{'🔍'} Similar Creators in Roster</h2>
          <div style={ds.similarList}>
            {similarCreators.map(({ creator: sc }) => (
              <Link
                key={sc.influencer_id}
                to={`/roster/${sc.influencer_id}`}
                style={ds.similarItem}
              >
                <div style={ds.similarAvatar}>
                  {sc.display_name.charAt(0).toUpperCase()}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={ds.similarName}>{sc.display_name}</div>
                  <div style={ds.similarMeta}>
                    @{sc.username} {'·'} {formatSubs(sc.followers_count)}
                  </div>
                </div>
                <span style={{
                  ...ds.tierPillSm,
                  background: sc.intelligence.tier === 'S' ? '#f59e0b'
                    : sc.intelligence.tier === 'A' ? '#3b82f6'
                    : sc.intelligence.tier === 'B' ? '#9ca3af'
                    : '#e5e7eb',
                  color: sc.intelligence.tier ? '#fff' : '#999',
                }}>
                  {sc.intelligence.tier ?? '-'}
                </span>
                <span style={ds.similarTrust}>
                  {sc.intelligence.trust_score != null ? sc.intelligence.trust_score.toFixed(1) : '-'}
                </span>
                <span style={{
                  ...ds.maturityPillSm,
                  background: getMaturityLabel(sc) === 'mature' ? '#d1fae5'
                    : getMaturityLabel(sc) === 'emerging' ? '#dbeafe'
                    : '#f3f4f6',
                  color: getMaturityLabel(sc) === 'mature' ? '#065f46'
                    : getMaturityLabel(sc) === 'emerging' ? '#1e40af'
                    : '#6b7280',
                }}>
                  {getMaturityLabel(sc) ?? '-'}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ================================================================
          SECTION: Campaign Intelligence (SEPARATE from Creator Intelligence
          above — this creator's fit for ONE specific campaign, not their
          intrinsic quality). Only shown when navigated with ?campaign_id=.
          ================================================================ */}
      {campaignId && (
        <div style={ds.card}>
          <h3 style={ds.cardTitle}>🎯 Campaign Intelligence</h3>
          {campaignMatch ? (
            <>
              <p style={ds.cardText}>
                Intrinsic quality vs. this campaign's fit are tracked separately —
                a creator can be excellent overall but only a moderate fit here, or vice versa.
              </p>
              <div style={ds.campaignScoreRow}>
                <div style={ds.campaignScoreBox}>
                  <div style={ds.campaignScoreLabel}>Trust Score (intrinsic)</div>
                  <div style={ds.campaignScoreValue}>
                    {campaignMatch.trust_score != null ? campaignMatch.trust_score.toFixed(1) : '—'}
                  </div>
                </div>
                <div style={ds.campaignScoreBox}>
                  <div style={ds.campaignScoreLabel}>Campaign Match</div>
                  <div style={{ ...ds.campaignScoreValue, color: '#667eea' }}>
                    {campaignMatch.match_score != null ? campaignMatch.match_score.toFixed(1) : '—'}
                  </div>
                </div>
                <div style={ds.campaignScoreBox}>
                  <div style={ds.campaignScoreLabel}>Audience Fit</div>
                  <div style={ds.campaignScoreValue}>
                    {campaignMatch.audience_fit != null ? campaignMatch.audience_fit.toFixed(0) : '—'}
                  </div>
                </div>
                <div style={ds.campaignScoreBox}>
                  <div style={ds.campaignScoreLabel}>Brand Fit</div>
                  <div style={ds.campaignScoreValue}>
                    {campaignMatch.brand_fit != null ? campaignMatch.brand_fit.toFixed(0) : '—'}
                  </div>
                </div>
              </div>
              {campaignMatch.recommended_role && (
                <p style={ds.cardText}><strong>Recommended role:</strong> {campaignMatch.recommended_role}</p>
              )}
              <p style={ds.cardText}>{campaignMatch.why}</p>
              <Link to={`/campaigns/${campaignId}/intelligence`} style={{ ...ds.backLink, marginBottom: 0 }}>
                Open full Campaign Intelligence →
              </Link>
            </>
          ) : (
            <p style={ds.cardText}>
              No Campaign Match computed yet for this creator on this campaign.{' '}
              <Link to={`/campaigns/${campaignId}/intelligence`} style={{ ...ds.backLink, marginBottom: 0 }}>Run AI matching →</Link>
            </p>
          )}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const ds: Record<string, React.CSSProperties> = {
  container: {
    maxWidth: '1200px',
    margin: '0 auto',
    padding: '2rem',
  },

  // Back link
  backLink: {
    display: 'inline-block',
    marginBottom: '1.5rem',
    color: '#667eea',
    textDecoration: 'none',
    fontWeight: 600,
    fontSize: '0.95rem',
  },

  // Banner
  banner: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexWrap: 'wrap' as const,
    gap: '1.5rem',
    background: 'white',
    padding: '2rem',
    borderRadius: '12px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
    marginBottom: '2rem',
  },
  bannerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '1.25rem',
  },
  avatarLarge: {
    width: '64px',
    height: '64px',
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 700,
    fontSize: '1.5rem',
    flexShrink: 0,
  },
  bannerName: {
    margin: 0,
    fontSize: '1.75rem',
    color: '#333',
    fontWeight: 700,
  },
  bannerMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    marginTop: '0.25rem',
    flexWrap: 'wrap' as const,
  },
  bannerUsername: {
    color: '#888',
    fontSize: '0.95rem',
  },
  platformBadge: {
    background: '#f3f4f6',
    padding: '0.2rem 0.6rem',
    borderRadius: '8px',
    fontSize: '0.8rem',
    color: '#555',
    fontWeight: 600,
    textTransform: 'capitalize' as const,
  },
  subCount: {
    color: '#555',
    fontSize: '0.9rem',
    fontWeight: 500,
  },
  bannerRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    flexWrap: 'wrap' as const,
  },
  tierPillLg: {
    display: 'inline-block',
    padding: '0.35rem 1rem',
    borderRadius: '14px',
    fontWeight: 800,
    fontSize: '0.9rem',
    letterSpacing: '0.5px',
  },
  recPillLg: {
    display: 'inline-block',
    padding: '0.35rem 1rem',
    borderRadius: '14px',
    fontWeight: 700,
    fontSize: '0.85rem',
    border: '1.5px solid',
    whiteSpace: 'nowrap' as const,
  },
  maturityPillLg: {
    display: 'inline-block',
    padding: '0.35rem 0.85rem',
    borderRadius: '12px',
    fontWeight: 600,
    fontSize: '0.82rem',
    textTransform: 'capitalize' as const,
  },
  confidencePill: {
    display: 'inline-block',
    padding: '0.3rem 0.75rem',
    borderRadius: '12px',
    fontWeight: 700,
    fontSize: '0.75rem',
    letterSpacing: '0.3px',
  },

  // Intel grid
  intelGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '2rem',
    marginBottom: '2rem',
  },
  column: {},
  columnTitle: {
    margin: '0 0 1rem 0',
    fontSize: '1.2rem',
    color: '#333',
    fontWeight: 700,
  },

  // Card
  card: {
    background: 'white',
    padding: '1.25rem 1.5rem',
    borderRadius: '10px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
    marginBottom: '1rem',
  },
  cardTitle: {
    margin: '0 0 0.75rem 0',
    fontSize: '0.85rem',
    fontWeight: 700,
    color: '#667eea',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.3px',
  },
  cardText: {
    margin: '0 0 0.35rem 0',
    fontSize: '0.9rem',
    color: '#444',
    lineHeight: 1.6,
  },

  // Campaign Intelligence scores (separate from intrinsic Trust Score above)
  campaignScoreRow: {
    display: 'flex',
    gap: '0.75rem',
    flexWrap: 'wrap' as const,
    margin: '0.75rem 0',
  },
  campaignScoreBox: {
    flex: '1 1 110px',
    background: '#f8f9ff',
    borderRadius: '8px',
    padding: '0.6rem 0.85rem',
    textAlign: 'center' as const,
  },
  campaignScoreLabel: {
    fontSize: '0.68rem',
    color: '#888',
    textTransform: 'uppercase' as const,
    marginBottom: '0.25rem',
    letterSpacing: '0.3px',
  },
  campaignScoreValue: {
    fontSize: '1.3rem',
    fontWeight: 800,
    color: '#333',
  },

  // Trust score big
  trustScoreRow: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '0.35rem',
    marginBottom: '0.5rem',
  },
  trustScoreBig: {
    fontSize: '2.5rem',
    fontWeight: 800,
  },
  trustScoreMax: {
    fontSize: '1rem',
    color: '#bbb',
    fontWeight: 500,
  },
  trustBarLgBg: {
    width: '100%',
    height: '10px',
    borderRadius: '5px',
    background: '#eee',
    overflow: 'hidden',
  },
  trustBarLgFill: {
    height: '100%',
    borderRadius: '5px',
    transition: 'width 0.3s ease',
  },

  // Score header
  scoreHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '0.75rem',
    padding: '0.5rem 0.75rem',
    background: '#f8f9ff',
    borderRadius: '8px',
  },
  scoreLabel: {
    fontSize: '0.85rem',
    color: '#888',
    fontWeight: 500,
  },
  scoreValue: {
    fontSize: '1.25rem',
    fontWeight: 700,
    color: '#667eea',
  },

  // Component breakdown rows
  componentList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.4rem',
  },
  componentRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    padding: '0.35rem 0.5rem',
    background: '#fafbff',
    borderRadius: '6px',
    fontSize: '0.82rem',
  },
  componentLabel: {
    flex: '1 1 0',
    color: '#555',
    fontWeight: 500,
  },
  componentValue: {
    width: '80px',
    textAlign: 'right' as const,
    color: '#888',
    fontSize: '0.8rem',
  },
  componentPoints: {
    width: '55px',
    textAlign: 'right' as const,
    fontWeight: 600,
    color: '#333',
    fontSize: '0.8rem',
  },

  // Score bars
  barBg: {
    width: '100%',
    height: '5px',
    borderRadius: '3px',
    background: '#eee',
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: '3px',
    transition: 'width 0.3s ease',
  },

  // Outreach box
  outreachBox: {
    background: 'linear-gradient(135deg, #667eea15 0%, #764ba215 100%)',
    border: '1px solid #667eea30',
    borderRadius: '8px',
    padding: '1rem',
  },
  outreachText: {
    margin: 0,
    fontSize: '0.95rem',
    color: '#667eea',
    fontWeight: 600,
    fontStyle: 'italic' as const,
  },

  // Readiness flags
  flagList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  flagRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.6rem',
    padding: '0.35rem 0.5rem',
    background: '#fafbff',
    borderRadius: '6px',
  },
  flagIcon: {
    fontSize: '1.1rem',
  },
  flagLabel: {
    fontSize: '0.88rem',
    color: '#444',
    fontWeight: 500,
  },

  // Risk assessment
  riskList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  riskItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0.5rem',
    padding: '0.5rem',
    background: '#fff5f5',
    borderRadius: '6px',
    border: '1px solid #fee2e2',
  },
  riskEmoji: {
    fontSize: '1.1rem',
    flexShrink: 0,
  },
  riskKey: {
    fontWeight: 600,
    color: '#991b1b',
    textTransform: 'capitalize' as const,
    fontSize: '0.85rem',
  },
  riskDesc: {
    fontSize: '0.83rem',
    color: '#666',
  },

  // Sponsorship profile
  spGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '0.5rem',
  },
  spItem: {
    padding: '0.5rem',
    background: '#fafbff',
    borderRadius: '6px',
  },
  spLabel: {
    display: 'block',
    fontSize: '0.75rem',
    color: '#888',
    fontWeight: 600,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.3px',
    marginBottom: '0.2rem',
  },
  spValue: {
    fontSize: '0.9rem',
    color: '#333',
    fontWeight: 600,
  },

  // Maturity pill (small)
  maturityPillSm: {
    display: 'inline-block',
    padding: '0.2rem 0.6rem',
    borderRadius: '10px',
    fontWeight: 600,
    fontSize: '0.78rem',
    textTransform: 'capitalize' as const,
  },

  // Decision summary
  decisionCard: {
    background: 'white',
    padding: '2rem',
    borderRadius: '12px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
    marginBottom: '2rem',
    borderTop: '4px solid #667eea',
  },
  decisionTitle: {
    margin: '0 0 1.25rem 0',
    fontSize: '1.3rem',
    color: '#333',
    fontWeight: 700,
  },
  decisionGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '1.5rem',
  },
  decisionBlock: {},
  decisionLabel: {
    margin: '0 0 0.5rem 0',
    fontSize: '0.82rem',
    fontWeight: 700,
    color: '#667eea',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.3px',
  },
  decisionText: {
    margin: '0 0 0.25rem 0',
    fontSize: '0.88rem',
    color: '#555',
    lineHeight: 1.5,
  },

  // Signals
  signalList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.3rem',
  },
  signalItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0.3rem 0.5rem',
    background: '#f0f2ff',
    borderRadius: '6px',
    fontSize: '0.85rem',
  },
  signalName: {
    color: '#555',
    fontWeight: 500,
  },
  signalScore: {
    fontWeight: 700,
    color: '#667eea',
  },

  // Similar creators
  similarCard: {
    background: 'white',
    padding: '2rem',
    borderRadius: '12px',
    boxShadow: '0 2px 12px rgba(0,0,0,0.08)',
    marginBottom: '2rem',
  },
  similarList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  similarItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.75rem 1rem',
    background: '#fafbff',
    borderRadius: '8px',
    textDecoration: 'none',
    transition: 'background 0.15s',
    cursor: 'pointer',
  },
  similarAvatar: {
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 700,
    fontSize: '0.85rem',
    flexShrink: 0,
  },
  similarName: {
    fontWeight: 600,
    color: '#333',
    fontSize: '0.88rem',
  },
  similarMeta: {
    fontSize: '0.78rem',
    color: '#888',
  },
  tierPillSm: {
    display: 'inline-block',
    padding: '0.15rem 0.5rem',
    borderRadius: '10px',
    fontWeight: 800,
    fontSize: '0.75rem',
    letterSpacing: '0.5px',
  },
  similarTrust: {
    fontWeight: 600,
    fontSize: '0.88rem',
    color: '#667eea',
    minWidth: '32px',
    textAlign: 'right' as const,
  },

  // Loading / Error
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    padding: '6rem 2rem',
  },
  loadingSpinner: {
    width: '40px',
    height: '40px',
    border: '4px solid #e0e0e0',
    borderTopColor: '#667eea',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
    marginBottom: '1rem',
  },
  loadingText: {
    color: '#666',
    fontSize: '1rem',
  },
  errorBox: {
    textAlign: 'center' as const,
    padding: '4rem 2rem',
    background: '#fee2e2',
    borderRadius: '10px',
    margin: '2rem 0',
  },
  errorText: {
    color: '#991b1b',
    fontSize: '1rem',
    marginBottom: '1rem',
  },
};
