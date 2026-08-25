import { useEffect, useState, useMemo, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { rosterAPI } from '../lib/api';
import type { RosterCreator, RosterIntelligenceResponse } from '../lib/types';
import { setRosterCache } from './CreatorDetailPage';

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function formatSubs(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

function formatDaysAgo(d: number | null | undefined): string {
  if (d == null) return '-';
  return `${Math.round(d)}d ago`;
}

// ---------------------------------------------------------------------------
// Data derivation helpers
// ---------------------------------------------------------------------------

type RecommendationLabel = 'Strong Buy' | 'Buy' | 'Watchlist' | 'Avoid';

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

interface RiskFlag {
  emoji: string;
  key: string;
}

function deriveRiskFlags(creator: RosterCreator): RiskFlag[] {
  const flags: RiskFlag[] = [];

  // volatile audience: view_consistency CV > 0.8
  const tb = creator.trust_breakdown;
  if (tb) {
    const ctd = tb.community_trust_depth;
    if (ctd?.components?.view_consistency?.cv != null && ctd.components.view_consistency.cv > 0.8) {
      flags.push({ emoji: '⚡', key: 'volatile' });
    }
  }

  // dormant: is_active === false
  if (creator.intelligence.readiness.is_active === false) {
    flags.push({ emoji: '💤', key: 'dormant' });
  }

  // ad_fatigue: sponsorship label === 'saturated'
  const srLabel = creator.sponsorship_readiness?.label
    ?? creator.intelligence.sponsorship_readiness?.label;
  if (srLabel === 'saturated') {
    flags.push({ emoji: '📢', key: 'ad_fatigue' });
  }

  // weak_community: trust_score < 40
  if (creator.intelligence.trust_score != null && creator.intelligence.trust_score < 40) {
    flags.push({ emoji: '👥', key: 'weak_community' });
  }

  // low_view_ratio: median_views / followers * 100 < 5
  if (tb) {
    const vc = tb.community_trust_depth?.components?.view_consistency;
    const medianViews = vc?.recent_view_median;
    if (medianViews != null && creator.followers_count > 0) {
      const ratio = (medianViews / creator.followers_count) * 100;
      if (ratio < 5) {
        flags.push({ emoji: '📉', key: 'low_view_ratio' });
      }
    }
  }

  return flags;
}

function extractCommunityScore(creator: RosterCreator): number | null {
  const tb = creator.trust_breakdown;
  if (!tb) return null;
  return tb.community_trust_depth?.score ?? null;
}

function extractAuthorityScore(creator: RosterCreator): number | null {
  const tb = creator.trust_breakdown;
  if (!tb) return null;
  return tb.authority?.score ?? null;
}

function extractLastUploadDays(_creator: RosterCreator): number | null {
  // Not directly in the API response; use readiness flag as proxy
  return null;
}

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

const RISK_DETAILS: Record<string, string> = {
  volatile: 'View counts fluctuate heavily (CV > 0.80) -- audience may be algorithm-driven rather than loyal.',
  dormant: 'Creator has not uploaded recently -- may be inactive or on hiatus.',
  ad_fatigue: 'Sponsorship saturation detected -- audience may tune out branded content.',
  weak_community: 'Trust score is below 40 -- shallow community engagement.',
  low_view_ratio: 'Median views are below 5% of subscriber count -- low organic reach.',
};

// ---------------------------------------------------------------------------
// Sort logic
// ---------------------------------------------------------------------------

type SortKey =
  | 'tier'
  | 'trust'
  | 'community'
  | 'authority'
  | 'sponsorship'
  | 'recommendation'
  | 'subs'
  | 'contact';

type SortDir = 'asc' | 'desc';

const TIER_RANK: Record<string, number> = { S: 3, A: 2, B: 1 };
const REC_RANK: Record<RecommendationLabel, number> = {
  'Strong Buy': 4,
  'Buy': 3,
  'Watchlist': 2,
  'Avoid': 1,
};

function compareFn(a: RosterCreator, b: RosterCreator, key: SortKey, dir: SortDir): number {
  let av: number;
  let bv: number;

  switch (key) {
    case 'tier':
      av = TIER_RANK[a.intelligence.tier ?? ''] ?? 0;
      bv = TIER_RANK[b.intelligence.tier ?? ''] ?? 0;
      break;
    case 'trust':
      av = a.intelligence.trust_score ?? -1;
      bv = b.intelligence.trust_score ?? -1;
      break;
    case 'community':
      av = extractCommunityScore(a) ?? -1;
      bv = extractCommunityScore(b) ?? -1;
      break;
    case 'authority':
      av = extractAuthorityScore(a) ?? -1;
      bv = extractAuthorityScore(b) ?? -1;
      break;
    case 'sponsorship': {
      const MATURITY_RANK: Record<string, number> = { mature: 4, emerging: 3, unproven: 2, saturated: 1 };
      av = MATURITY_RANK[getMaturityLabel(a) ?? ''] ?? 0;
      bv = MATURITY_RANK[getMaturityLabel(b) ?? ''] ?? 0;
      break;
    }
    case 'recommendation':
      av = REC_RANK[deriveRecommendation(a)];
      bv = REC_RANK[deriveRecommendation(b)];
      break;
    case 'subs':
      av = a.followers_count;
      bv = b.followers_count;
      break;
    case 'contact':
      av = a.intelligence.readiness.is_reachable ? 1 : 0;
      bv = b.intelligence.readiness.is_reachable ? 1 : 0;
      break;
    default:
      av = 0;
      bv = 0;
  }

  const cmp = av - bv;
  return dir === 'desc' ? -cmp : cmp;
}

// ---------------------------------------------------------------------------
// Bookmark helpers
// ---------------------------------------------------------------------------

const BOOKMARKS_KEY = 'roster_bookmarks';

function loadBookmarks(): Set<number> {
  try {
    const raw = localStorage.getItem(BOOKMARKS_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as number[]);
  } catch {
    return new Set();
  }
}

function saveBookmarks(ids: Set<number>) {
  localStorage.setItem(BOOKMARKS_KEY, JSON.stringify([...ids]));
}

// ---------------------------------------------------------------------------
// CSV Export helper
// ---------------------------------------------------------------------------

function exportCreatorsCSV(creators: RosterCreator[], filename: string) {
  const headers = [
    'Creator',
    'Username',
    'Tier',
    'Trust',
    'Community',
    'Authority',
    'Sponsorship Maturity',
    'Recommendation',
    'Risk Flags',
    'Subscribers',
    'Contact Available',
  ];

  const rows = creators.map((c) => {
    const risks = deriveRiskFlags(c);
    return [
      `"${c.display_name.replace(/"/g, '""')}"`,
      `"@${c.username}"`,
      c.intelligence.tier ?? '-',
      c.intelligence.trust_score != null ? c.intelligence.trust_score.toFixed(1) : '-',
      extractCommunityScore(c)?.toFixed(1) ?? '-',
      extractAuthorityScore(c)?.toFixed(1) ?? '-',
      getMaturityLabel(c) ?? '-',
      deriveRecommendation(c),
      risks.length > 0 ? `"${risks.map((r) => r.key).join(', ')}"` : 'None',
      String(c.followers_count),
      c.intelligence.readiness.is_reachable ? 'Yes' : 'No',
    ].join(',');
  });

  const csv = [headers.join(','), ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  window.URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Find Similar helper
// ---------------------------------------------------------------------------

function findSimilarCreators(
  target: RosterCreator,
  allCreators: RosterCreator[],
  count: number = 5
): RosterCreator[] {
  const trust = target.intelligence.trust_score ?? 0;
  const community = extractCommunityScore(target) ?? 0;
  const authority = extractAuthorityScore(target) ?? 0;

  return allCreators
    .filter((c) => c.influencer_id !== target.influencer_id)
    .map((c) => {
      const ct = c.intelligence.trust_score ?? 0;
      const cc = extractCommunityScore(c) ?? 0;
      const ca = extractAuthorityScore(c) ?? 0;
      const dist = Math.abs(trust - ct) + Math.abs(community - cc) + Math.abs(authority - ca);
      return { creator: c, distance: dist };
    })
    .sort((a, b) => a.distance - b.distance)
    .slice(0, count)
    .map((item) => item.creator);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50;

export const RosterPage = () => {
  // Data state
  const [data, setData] = useState<RosterIntelligenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pagination
  const [page, setPage] = useState(0);

  // Filters
  const [search, setSearch] = useState('');
  const [tierFilter, setTierFilter] = useState<string>('all');
  const [maturityFilter, setMaturityFilter] = useState<string>('all');

  // Sort
  const [sortKey, setSortKey] = useState<SortKey>('tier');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Expansion
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // Bulk selection
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Bookmarks
  const [bookmarks, setBookmarks] = useState<Set<number>>(loadBookmarks);

  // Find Similar
  const [similarTargetId, setSimilarTargetId] = useState<number | null>(null);

  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await rosterAPI.intelligence({ skip: page * PAGE_SIZE, limit: PAGE_SIZE });
      setData(result);
      // Populate cache for detail page
      setRosterCache(result);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load roster data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Filtered + sorted creators
  const creators = useMemo(() => {
    if (!data) return [];
    let list = [...data.creators];

    // Search filter
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (c) =>
          c.display_name.toLowerCase().includes(q) ||
          c.username.toLowerCase().includes(q)
      );
    }

    // Tier filter
    if (tierFilter === 'bookmarked') {
      list = list.filter((c) => bookmarks.has(c.influencer_id));
    } else if (tierFilter !== 'all') {
      list = list.filter((c) => (c.intelligence.tier ?? 'none') === tierFilter);
    }

    // Maturity filter
    if (maturityFilter !== 'all') {
      list = list.filter((c) => getMaturityLabel(c) === maturityFilter);
    }

    // Sort
    list.sort((a, b) => compareFn(a, b, sortKey, sortDir));

    return list;
  }, [data, search, tierFilter, maturityFilter, sortKey, sortDir, bookmarks]);

  // Tier distribution
  const tierCounts = useMemo(() => {
    if (!data) return { S: 0, A: 0, B: 0, none: 0 };
    const counts = { S: 0, A: 0, B: 0, none: 0 };
    for (const c of data.creators) {
      const t = c.intelligence.tier;
      if (t === 'S') counts.S++;
      else if (t === 'A') counts.A++;
      else if (t === 'B') counts.B++;
      else counts.none++;
    }
    return counts;
  }, [data]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const sortArrow = (key: SortKey) => {
    if (sortKey !== key) return ' ';
    return sortDir === 'desc' ? ' ▼' : ' ▲';
  };

  const toggleExpand = (id: number) => {
    setExpandedId((prev) => (prev === id ? null : id));
    setSimilarTargetId(null);
  };

  // Bulk selection handlers
  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === creators.length && creators.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(creators.map((c) => c.influencer_id)));
    }
  };

  const clearSelection = () => setSelectedIds(new Set());

  // Bookmark handlers
  const toggleBookmark = (id: number) => {
    setBookmarks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      saveBookmarks(next);
      return next;
    });
  };

  // Export handlers
  const handleExportAll = () => {
    exportCreatorsCSV(creators, 'roster_export.csv');
  };

  const handleExportSelected = () => {
    const selected = creators.filter((c) => selectedIds.has(c.influencer_id));
    exportCreatorsCSV(selected, 'roster_selected_export.csv');
  };

  // Similar creators for expanded panel
  const similarCreators = useMemo(() => {
    if (!similarTargetId || !data) return [];
    const target = data.creators.find((c) => c.influencer_id === similarTargetId);
    if (!target) return [];
    return findSimilarCreators(target, data.creators, 5);
  }, [similarTargetId, data]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div style={s.container}>
        <div style={s.loadingContainer}>
          <div style={s.loadingSpinner} />
          <p style={s.loadingText}>Loading roster intelligence...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={s.container}>
        <div style={s.errorBox}>
          <p style={s.errorText}>{error}</p>
          <button onClick={fetchData} style={s.retryBtn}>Retry</button>
        </div>
      </div>
    );
  }

  const allSelected = creators.length > 0 && selectedIds.size === creators.length;

  return (
    <div style={s.container}>
      {/* ---- Header ---- */}
      <div style={s.header}>
        <div>
          <h1 style={s.title}>{'🧠'} Creator Intelligence</h1>
          <p style={s.subtitle}>
            Roster ranked by intrinsic audience trust — not follower count
          </p>
        </div>
        <button onClick={handleExportAll} style={s.exportBtn}>
          {'📥'} Export CSV
        </button>
      </div>

      {/* ---- Controls bar ---- */}
      <div style={s.controlsBar}>
        {/* Tier badges */}
        <div style={s.badgeRow}>
          <span style={{ ...s.tierBadge, background: '#f59e0b', color: '#fff' }}>
            S: {tierCounts.S}
          </span>
          <span style={{ ...s.tierBadge, background: '#3b82f6', color: '#fff' }}>
            A: {tierCounts.A}
          </span>
          <span style={{ ...s.tierBadge, background: '#9ca3af', color: '#fff' }}>
            B: {tierCounts.B}
          </span>
          {tierCounts.none > 0 && (
            <span style={{ ...s.tierBadge, background: '#d1d5db', color: '#666' }}>
              Untiered: {tierCounts.none}
            </span>
          )}
        </div>

        {/* Search */}
        <input
          type="text"
          placeholder="Search by creator name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={s.searchInput}
        />

        {/* Tier filter */}
        <select
          value={tierFilter}
          onChange={(e) => setTierFilter(e.target.value)}
          style={s.filterSelect}
        >
          <option value="all">All Tiers</option>
          <option value="S">S - Priority</option>
          <option value="A">A - High-Potential</option>
          <option value="B">B - Commodity</option>
          <option value="none">Untiered</option>
          <option value="bookmarked">{'⭐'} Bookmarked</option>
        </select>

        {/* Maturity filter */}
        <select
          value={maturityFilter}
          onChange={(e) => setMaturityFilter(e.target.value)}
          style={s.filterSelect}
        >
          <option value="all">All Maturity</option>
          <option value="mature">Mature</option>
          <option value="emerging">Emerging</option>
          <option value="unproven">Unproven</option>
          <option value="saturated">Saturated</option>
        </select>
      </div>

      {/* ---- Table ---- */}
      {creators.length === 0 ? (
        <div style={s.emptyState}>
          No creators match your filters. Try adjusting your search.
        </div>
      ) : (
        <div style={s.tableWrapper}>
          {/* Table header */}
          <div style={s.tableHeader}>
            {/* Checkbox column */}
            <div style={{ ...s.thCell, flex: '0 0 36px', cursor: 'pointer' }} onClick={toggleSelectAll}>
              <span style={{ fontSize: '0.85rem' }}>{allSelected ? '☑' : '☐'}</span>
            </div>
            {/* Bookmark column */}
            <div style={{ ...s.thCell, flex: '0 0 32px' }}>{'⭐'}</div>
            <div style={{ ...s.thCell, flex: '2 1 0' }}>Creator</div>
            <div style={{ ...s.thCell, flex: '0.6 1 0', cursor: 'pointer' }} onClick={() => handleSort('tier')}>
              Tier{sortArrow('tier')}
            </div>
            <div style={{ ...s.thCell, flex: '1 1 0', cursor: 'pointer' }} onClick={() => handleSort('trust')}>
              Trust{sortArrow('trust')}
            </div>
            <div style={{ ...s.thCell, flex: '0.8 1 0', cursor: 'pointer' }} onClick={() => handleSort('community')}>
              Community{sortArrow('community')}
            </div>
            <div style={{ ...s.thCell, flex: '0.8 1 0', cursor: 'pointer' }} onClick={() => handleSort('authority')}>
              Authority{sortArrow('authority')}
            </div>
            <div style={{ ...s.thCell, flex: '1 1 0', cursor: 'pointer' }} onClick={() => handleSort('sponsorship')}>
              Sponsorship{sortArrow('sponsorship')}
            </div>
            <div style={{ ...s.thCell, flex: '1 1 0', cursor: 'pointer' }} onClick={() => handleSort('recommendation')}>
              Rec{sortArrow('recommendation')}
            </div>
            <div style={{ ...s.thCell, flex: '0.6 1 0' }}>Risk</div>
            <div style={{ ...s.thCell, flex: '0.7 1 0', cursor: 'pointer' }} onClick={() => handleSort('subs')}>
              Subs{sortArrow('subs')}
            </div>
            <div style={{ ...s.thCell, flex: '0.7 1 0' }}>Last Upload</div>
            <div style={{ ...s.thCell, flex: '0.5 1 0', cursor: 'pointer' }} onClick={() => handleSort('contact')}>
              Contact{sortArrow('contact')}
            </div>
          </div>

          {/* Table rows */}
          {creators.map((c) => {
            const rec = deriveRecommendation(c);
            const risks = deriveRiskFlags(c);
            const community = extractCommunityScore(c);
            const authority = extractAuthorityScore(c);
            const maturity = getMaturityLabel(c);
            const lastUpload = extractLastUploadDays(c);
            const isExpanded = expandedId === c.influencer_id;
            const isSelected = selectedIds.has(c.influencer_id);
            const isBookmarked = bookmarks.has(c.influencer_id);

            return (
              <div key={c.influencer_id}>
                {/* Row */}
                <div
                  style={{
                    ...s.tableRow,
                    ...(isExpanded ? s.tableRowExpanded : {}),
                    ...(isSelected ? { background: '#f0f2ff' } : {}),
                  }}
                >
                  {/* Checkbox */}
                  <div
                    style={{ ...s.tdCell, flex: '0 0 36px', cursor: 'pointer', fontSize: '1rem' }}
                    onClick={(e) => { e.stopPropagation(); toggleSelect(c.influencer_id); }}
                  >
                    {isSelected ? '☑' : '☐'}
                  </div>

                  {/* Bookmark */}
                  <div
                    style={{ ...s.tdCell, flex: '0 0 32px', cursor: 'pointer', fontSize: '1.1rem' }}
                    onClick={(e) => { e.stopPropagation(); toggleBookmark(c.influencer_id); }}
                  >
                    {isBookmarked ? '⭐' : '☆'}
                  </div>

                  {/* Creator - clickable name links to detail, row click toggles expand */}
                  <div
                    style={{ ...s.tdCell, flex: '2 1 0', cursor: 'pointer' }}
                    onClick={() => toggleExpand(c.influencer_id)}
                  >
                    <div style={s.creatorAvatar}>
                      {c.display_name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <Link
                        to={`/roster/${c.influencer_id}`}
                        style={s.creatorNameLink}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {c.display_name}
                      </Link>
                      <div style={s.creatorUsername}>@{c.username}</div>
                    </div>
                  </div>

                  {/* Tier */}
                  <div style={{ ...s.tdCell, flex: '0.6 1 0' }} onClick={() => toggleExpand(c.influencer_id)}>
                    <span style={{
                      ...s.tierPill,
                      background: c.intelligence.tier === 'S' ? '#f59e0b'
                        : c.intelligence.tier === 'A' ? '#3b82f6'
                        : c.intelligence.tier === 'B' ? '#9ca3af'
                        : '#e5e7eb',
                      color: c.intelligence.tier ? '#fff' : '#999',
                    }}>
                      {c.intelligence.tier ?? '-'}
                    </span>
                  </div>

                  {/* Trust */}
                  <div style={{ ...s.tdCell, flex: '1 1 0' }} onClick={() => toggleExpand(c.influencer_id)}>
                    <div style={s.trustContainer}>
                      <span style={s.trustValue}>
                        {c.intelligence.trust_score != null
                          ? c.intelligence.trust_score.toFixed(1)
                          : '-'}
                      </span>
                      {c.intelligence.trust_score != null && (
                        <div style={s.trustBarBg}>
                          <div
                            style={{
                              ...s.trustBarFill,
                              width: `${Math.min(c.intelligence.trust_score, 100)}%`,
                              background:
                                c.intelligence.trust_score >= 65 ? '#10b981'
                                : c.intelligence.trust_score >= 50 ? '#f59e0b'
                                : '#ef4444',
                            }}
                          />
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Community */}
                  <div style={{ ...s.tdCell, flex: '0.8 1 0', color: '#555' }} onClick={() => toggleExpand(c.influencer_id)}>
                    {community != null ? community.toFixed(1) : '-'}
                  </div>

                  {/* Authority */}
                  <div style={{ ...s.tdCell, flex: '0.8 1 0', color: '#555' }} onClick={() => toggleExpand(c.influencer_id)}>
                    {authority != null ? authority.toFixed(1) : '-'}
                  </div>

                  {/* Sponsorship maturity */}
                  <div style={{ ...s.tdCell, flex: '1 1 0' }} onClick={() => toggleExpand(c.influencer_id)}>
                    {maturity ? (
                      <span style={{
                        ...s.maturityPill,
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
                    ) : (
                      <span style={{ color: '#bbb' }}>-</span>
                    )}
                  </div>

                  {/* Recommendation */}
                  <div style={{ ...s.tdCell, flex: '1 1 0' }} onClick={() => toggleExpand(c.influencer_id)}>
                    <span style={{
                      ...s.recPill,
                      background: RECOMMENDATION_COLORS[rec] + '18',
                      color: RECOMMENDATION_COLORS[rec],
                      borderColor: RECOMMENDATION_COLORS[rec],
                    }}>
                      {rec}
                    </span>
                  </div>

                  {/* Risk flags */}
                  <div style={{ ...s.tdCell, flex: '0.6 1 0', fontSize: '1.1rem', letterSpacing: '2px' }} onClick={() => toggleExpand(c.influencer_id)}>
                    {risks.length > 0 ? risks.map((r) => r.emoji).join('') : ''}
                  </div>

                  {/* Subs */}
                  <div style={{ ...s.tdCell, flex: '0.7 1 0', fontWeight: 500, color: '#555' }} onClick={() => toggleExpand(c.influencer_id)}>
                    {formatSubs(c.followers_count)}
                  </div>

                  {/* Last upload */}
                  <div style={{ ...s.tdCell, flex: '0.7 1 0', color: '#888' }} onClick={() => toggleExpand(c.influencer_id)}>
                    {c.intelligence.readiness.is_active === true
                      ? '✅ Active'
                      : c.intelligence.readiness.is_active === false
                      ? '⚠️ Dormant'
                      : formatDaysAgo(lastUpload)}
                  </div>

                  {/* Contact */}
                  <div style={{ ...s.tdCell, flex: '0.5 1 0', fontSize: '1.1rem' }} onClick={() => toggleExpand(c.influencer_id)}>
                    {c.intelligence.readiness.is_reachable ? '✅' : '❌'}
                  </div>
                </div>

                {/* Expanded detail panel */}
                {isExpanded && (
                  <div style={s.expandedPanel}>
                    <div style={s.detailGrid}>
                      {/* Why this tier? */}
                      <div style={s.detailSection}>
                        <h4 style={s.detailTitle}>Why this tier?</h4>
                        <p style={s.detailText}>
                          {c.intelligence.tier_explanation || 'No tier explanation available.'}
                        </p>
                      </div>

                      {/* Sponsorship readiness */}
                      <div style={s.detailSection}>
                        <h4 style={s.detailTitle}>Sponsorship Readiness</h4>
                        <p style={s.detailText}>
                          {c.sponsorship_readiness?.explanation
                            ?? c.intelligence.sponsorship_readiness?.explanation
                            ?? 'Not assessed'}
                        </p>
                        {(c.sponsorship_readiness?.outreach_implication
                          ?? c.intelligence.sponsorship_readiness?.outreach_implication) && (
                          <p style={{ ...s.detailText, fontStyle: 'italic', color: '#667eea' }}>
                            {c.sponsorship_readiness?.outreach_implication
                              ?? c.intelligence.sponsorship_readiness?.outreach_implication}
                          </p>
                        )}
                      </div>

                      {/* Confidence */}
                      <div style={s.detailSection}>
                        <h4 style={s.detailTitle}>Confidence</h4>
                        <span style={{
                          ...s.confidenceBadge,
                          background: c.intelligence.confidence === 'high' ? '#d1fae5'
                            : c.intelligence.confidence === 'medium' ? '#fef3c7'
                            : '#fee2e2',
                          color: c.intelligence.confidence === 'high' ? '#065f46'
                            : c.intelligence.confidence === 'medium' ? '#92400e'
                            : '#991b1b',
                        }}>
                          {c.intelligence.confidence.toUpperCase()}
                        </span>
                      </div>

                      {/* Outreach strategy */}
                      <div style={s.detailSection}>
                        <h4 style={s.detailTitle}>Outreach Strategy</h4>
                        <p style={s.detailText}>
                          {getOutreachStrategy(maturity)}
                        </p>
                      </div>

                      {/* Strongest signals */}
                      {(() => {
                        const topSignals = getTopSignals(c);
                        if (topSignals.length === 0) return null;
                        return (
                          <div style={s.detailSection}>
                            <h4 style={s.detailTitle}>Strongest Signals</h4>
                            <div style={s.signalList}>
                              {topSignals.map((sig) => (
                                <div key={sig.name} style={s.signalItem}>
                                  <span style={s.signalName}>{sig.name}</span>
                                  <span style={s.signalScore}>{sig.score.toFixed(1)}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })()}

                      {/* Risk details */}
                      {risks.length > 0 && (
                        <div style={s.detailSection}>
                          <h4 style={s.detailTitle}>Risk Details</h4>
                          {risks.map((r) => (
                            <p key={r.key} style={s.detailText}>
                              {r.emoji} <strong style={{ textTransform: 'capitalize' }}>{r.key.replace('_', ' ')}</strong>
                              {' -- '}
                              {RISK_DETAILS[r.key] ?? 'Unknown risk flag.'}
                            </p>
                          ))}
                        </div>
                      )}

                      {/* Override reason */}
                      {c.intelligence.override_reason && (
                        <div style={s.detailSection}>
                          <h4 style={s.detailTitle}>Override Note</h4>
                          <p style={{ ...s.detailText, color: '#b45309' }}>
                            {c.intelligence.override_reason}
                          </p>
                        </div>
                      )}
                    </div>

                    {/* Find Similar + View Detail buttons */}
                    <div style={s.expandedActions}>
                      <Link
                        to={`/roster/${c.influencer_id}`}
                        style={s.viewDetailBtn}
                      >
                        View Full Profile {'→'}
                      </Link>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSimilarTargetId((prev) =>
                            prev === c.influencer_id ? null : c.influencer_id
                          );
                        }}
                        style={s.findSimilarBtn}
                      >
                        {'🔍'} {similarTargetId === c.influencer_id ? 'Hide Similar' : 'Find Similar'}
                      </button>
                    </div>

                    {/* Similar creators panel */}
                    {similarTargetId === c.influencer_id && similarCreators.length > 0 && (
                      <div style={s.similarPanel}>
                        <h4 style={s.detailTitle}>Similar Creators</h4>
                        <div style={s.similarList}>
                          {similarCreators.map((sc) => (
                            <Link
                              key={sc.influencer_id}
                              to={`/roster/${sc.influencer_id}`}
                              style={s.similarRow}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <span style={s.similarAvatar}>
                                {sc.display_name.charAt(0).toUpperCase()}
                              </span>
                              <span style={s.similarName}>{sc.display_name}</span>
                              <span style={{
                                ...s.tierPill,
                                background: sc.intelligence.tier === 'S' ? '#f59e0b'
                                  : sc.intelligence.tier === 'A' ? '#3b82f6'
                                  : sc.intelligence.tier === 'B' ? '#9ca3af'
                                  : '#e5e7eb',
                                color: sc.intelligence.tier ? '#fff' : '#999',
                                fontSize: '0.7rem',
                                padding: '0.1rem 0.5rem',
                              }}>
                                {sc.intelligence.tier ?? '-'}
                              </span>
                              <span style={s.similarTrust}>
                                {sc.intelligence.trust_score != null
                                  ? sc.intelligence.trust_score.toFixed(1)
                                  : '-'}
                              </span>
                              <span style={{
                                ...s.maturityPill,
                                fontSize: '0.7rem',
                                padding: '0.1rem 0.5rem',
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
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ---- Pagination ---- */}
      {data && (
        <div style={s.pagination}>
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            style={{
              ...s.pageBtn,
              opacity: page === 0 ? 0.4 : 1,
              cursor: page === 0 ? 'default' : 'pointer',
            }}
          >
            Previous
          </button>
          <span style={s.pageInfo}>
            Page {page + 1} &middot; Showing {creators.length} of {data.total} creators
          </span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={data.total <= (page + 1) * PAGE_SIZE}
            style={{
              ...s.pageBtn,
              opacity: data.total <= (page + 1) * PAGE_SIZE ? 0.4 : 1,
              cursor: data.total <= (page + 1) * PAGE_SIZE ? 'default' : 'pointer',
            }}
          >
            Next
          </button>
        </div>
      )}

      {/* ---- Floating selection bar ---- */}
      {selectedIds.size > 0 && (
        <div style={s.floatingBar}>
          <span style={s.floatingCount}>{selectedIds.size} selected</span>
          <button onClick={handleExportSelected} style={s.floatingBtn}>
            {'📥'} Export Selected
          </button>
          <button onClick={clearSelection} style={s.floatingBtnClear}>
            Clear Selection
          </button>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Inline styles — matches the project's established pattern
// ---------------------------------------------------------------------------

const s: Record<string, React.CSSProperties> = {
  container: {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: '2rem',
  },

  // Header
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: '1.5rem',
  },
  title: {
    margin: '0 0 0.5rem 0',
    fontSize: '2.5rem',
    color: '#333',
  },
  subtitle: {
    margin: 0,
    color: '#666',
    fontSize: '1rem',
  },
  exportBtn: {
    padding: '0.6rem 1.25rem',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontWeight: 600,
    fontSize: '0.9rem',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },

  // Controls bar
  controlsBar: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: '1rem',
    alignItems: 'center',
    marginBottom: '1.5rem',
    background: 'white',
    padding: '1rem 1.5rem',
    borderRadius: '10px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
  },
  badgeRow: {
    display: 'flex',
    gap: '0.5rem',
    marginRight: '0.5rem',
  },
  tierBadge: {
    padding: '0.25rem 0.75rem',
    borderRadius: '20px',
    fontSize: '0.8rem',
    fontWeight: 700,
    letterSpacing: '0.5px',
  },
  searchInput: {
    flex: '1 1 200px',
    padding: '0.6rem 1rem',
    fontSize: '0.95rem',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    outline: 'none',
    minWidth: '180px',
  },
  filterSelect: {
    padding: '0.6rem 1rem',
    fontSize: '0.95rem',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    outline: 'none',
    background: 'white',
    cursor: 'pointer',
  },

  // Table
  tableWrapper: {
    background: 'white',
    borderRadius: '10px',
    overflow: 'hidden',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
  tableHeader: {
    display: 'flex',
    alignItems: 'center',
    padding: '0.85rem 1.25rem',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#fff',
    fontSize: '0.78rem',
    fontWeight: 700,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
    userSelect: 'none' as const,
  },
  thCell: {
    padding: '0 0.35rem',
  },
  tableRow: {
    display: 'flex',
    alignItems: 'center',
    padding: '0.85rem 1.25rem',
    borderBottom: '1px solid #f0f0f0',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  tableRowExpanded: {
    background: '#f8f9ff',
    borderBottom: 'none',
  },
  tdCell: {
    padding: '0 0.35rem',
    fontSize: '0.9rem',
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },

  // Creator cell
  creatorAvatar: {
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
  creatorNameLink: {
    fontWeight: 600,
    color: '#667eea',
    fontSize: '0.9rem',
    lineHeight: 1.3,
    textDecoration: 'none',
    cursor: 'pointer',
  },
  creatorUsername: {
    fontSize: '0.78rem',
    color: '#888',
  },

  // Tier pill
  tierPill: {
    display: 'inline-block',
    padding: '0.2rem 0.65rem',
    borderRadius: '12px',
    fontWeight: 800,
    fontSize: '0.8rem',
    letterSpacing: '0.5px',
    textAlign: 'center' as const,
    minWidth: '28px',
  },

  // Trust bar
  trustContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    width: '100%',
  },
  trustValue: {
    fontWeight: 600,
    fontSize: '0.88rem',
    minWidth: '32px',
    color: '#333',
  },
  trustBarBg: {
    flex: 1,
    height: '6px',
    borderRadius: '3px',
    background: '#eee',
    overflow: 'hidden',
  },
  trustBarFill: {
    height: '100%',
    borderRadius: '3px',
    transition: 'width 0.3s ease',
  },

  // Maturity pill
  maturityPill: {
    display: 'inline-block',
    padding: '0.2rem 0.6rem',
    borderRadius: '10px',
    fontWeight: 600,
    fontSize: '0.78rem',
    textTransform: 'capitalize' as const,
  },

  // Recommendation pill
  recPill: {
    display: 'inline-block',
    padding: '0.2rem 0.6rem',
    borderRadius: '10px',
    fontWeight: 700,
    fontSize: '0.75rem',
    border: '1px solid',
    whiteSpace: 'nowrap' as const,
  },

  // Expanded panel
  expandedPanel: {
    background: '#f8f9ff',
    padding: '1.25rem 1.5rem 1.25rem 3.5rem',
    borderBottom: '2px solid #667eea20',
  },
  detailGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '1.25rem 2rem',
  },
  detailSection: {
    minWidth: 0,
  },
  detailTitle: {
    margin: '0 0 0.4rem 0',
    fontSize: '0.82rem',
    fontWeight: 700,
    color: '#667eea',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.3px',
  },
  detailText: {
    margin: '0 0 0.35rem 0',
    fontSize: '0.88rem',
    color: '#444',
    lineHeight: 1.55,
  },
  confidenceBadge: {
    display: 'inline-block',
    padding: '0.2rem 0.75rem',
    borderRadius: '12px',
    fontWeight: 700,
    fontSize: '0.75rem',
    letterSpacing: '0.5px',
  },
  signalList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.3rem',
  },
  signalItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0.25rem 0.5rem',
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

  // Expanded action buttons
  expandedActions: {
    display: 'flex',
    gap: '0.75rem',
    marginTop: '1.25rem',
    paddingTop: '1rem',
    borderTop: '1px solid #e5e7eb',
  },
  viewDetailBtn: {
    padding: '0.5rem 1rem',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontWeight: 600,
    fontSize: '0.82rem',
    cursor: 'pointer',
    textDecoration: 'none',
  },
  findSimilarBtn: {
    padding: '0.5rem 1rem',
    background: 'white',
    color: '#667eea',
    border: '1.5px solid #667eea',
    borderRadius: '6px',
    fontWeight: 600,
    fontSize: '0.82rem',
    cursor: 'pointer',
  },

  // Similar creators panel
  similarPanel: {
    marginTop: '1rem',
    padding: '1rem',
    background: 'white',
    borderRadius: '8px',
    border: '1px solid #e5e7eb',
  },
  similarList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.4rem',
  },
  similarRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.6rem',
    padding: '0.5rem 0.75rem',
    background: '#fafbff',
    borderRadius: '6px',
    textDecoration: 'none',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  similarAvatar: {
    width: '28px',
    height: '28px',
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: '#fff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 700,
    fontSize: '0.7rem',
    flexShrink: 0,
  },
  similarName: {
    flex: 1,
    fontWeight: 600,
    fontSize: '0.82rem',
    color: '#333',
  },
  similarTrust: {
    fontWeight: 600,
    fontSize: '0.82rem',
    color: '#667eea',
    minWidth: '28px',
    textAlign: 'right' as const,
  },

  // Pagination
  pagination: {
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    gap: '1.5rem',
    marginTop: '1.5rem',
    padding: '1rem',
  },
  pageBtn: {
    padding: '0.6rem 1.5rem',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontWeight: 600,
    fontSize: '0.9rem',
    transition: 'opacity 0.2s',
  },
  pageInfo: {
    fontSize: '0.9rem',
    color: '#666',
  },

  // Floating selection bar
  floatingBar: {
    position: 'fixed' as const,
    bottom: '2rem',
    left: '50%',
    transform: 'translateX(-50%)',
    display: 'flex',
    alignItems: 'center',
    gap: '1rem',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    padding: '0.85rem 2rem',
    borderRadius: '14px',
    boxShadow: '0 8px 30px rgba(102, 126, 234, 0.4)',
    zIndex: 1000,
  },
  floatingCount: {
    color: 'white',
    fontWeight: 700,
    fontSize: '0.9rem',
    whiteSpace: 'nowrap' as const,
  },
  floatingBtn: {
    padding: '0.5rem 1rem',
    background: 'rgba(255,255,255,0.2)',
    color: 'white',
    border: '1px solid rgba(255,255,255,0.4)',
    borderRadius: '8px',
    fontWeight: 600,
    fontSize: '0.82rem',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },
  floatingBtnClear: {
    padding: '0.5rem 1rem',
    background: 'transparent',
    color: 'rgba(255,255,255,0.8)',
    border: '1px solid rgba(255,255,255,0.3)',
    borderRadius: '8px',
    fontWeight: 500,
    fontSize: '0.82rem',
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },

  // States
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
  retryBtn: {
    padding: '0.6rem 1.5rem',
    background: '#667eea',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  emptyState: {
    textAlign: 'center' as const,
    padding: '4rem 2rem',
    background: 'white',
    borderRadius: '10px',
    color: '#999',
    fontSize: '1rem',
    boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
  },
};
