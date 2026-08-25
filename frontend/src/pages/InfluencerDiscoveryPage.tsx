import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { brandsAPI } from '../lib/api';
import type { BrandProfile, DiscoveryResult, InfluencerMatch } from '../lib/types';

const fmtRange = (range: [number, number], suffix = '', digits = 0) => {
  const [low, high] = range;
  const fmt = (n: number) =>
    digits > 0 ? n.toFixed(digits) : Math.round(n).toLocaleString();
  return low === high ? `${fmt(low)}${suffix}` : `${fmt(low)}–${fmt(high)}${suffix}`;
};

const fmtMoneyRange = (range: [number, number]) => {
  const [low, high] = range;
  const fmt = (n: number) => `$${Math.round(n).toLocaleString()}`;
  return low === high ? fmt(low) : `${fmt(low)}–${fmt(high)}`;
};

export const InfluencerDiscoveryPage = () => {
  const { brandId } = useParams<{ brandId: string }>();
  const navigate = useNavigate();
  const [brandProfile, setBrandProfile] = useState<BrandProfile | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [maxResults, setMaxResults] = useState(20);
  const [minSubscribers, setMinSubscribers] = useState<number>(10000);
  const [maxSubscribers, setMaxSubscribers] = useState<number>(1000000);
  const [minViewRatio, setMinViewRatio] = useState<number | undefined>(undefined);
  const [numPosts, setNumPosts] = useState(1);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [result, setResult] = useState<DiscoveryResult | null>(null);
  const [error, setError] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<'all' | 'micro' | 'macro' | 'mega'>('all');

  useEffect(() => {
    if (brandId) fetchBrandProfile();
  }, [brandId]);

  const fetchBrandProfile = async () => {
    try {
      const data = await brandsAPI.getProfile(parseInt(brandId!));
      setBrandProfile(data);
    } catch {
      setError('Failed to load brand profile');
    }
  };

  const handleDiscover = async () => {
    if (!brandId) return;
    setDiscovering(true);
    setError('');
    setResult(null);
    try {
      const data = await brandsAPI.discoverInfluencers({
        brand_profile_id: parseInt(brandId),
        search_query: searchQuery || undefined,
        max_results: maxResults,
        min_subscribers: minSubscribers,
        max_subscribers: maxSubscribers,
        min_view_ratio: minViewRatio,
        num_posts: numPosts,
      });
      if (data.recommended_influencers.length === 0) {
        setError('No influencers found. Try different keywords or relax filters.');
      } else {
        setResult(data);
      }
    } catch (err: any) {
      const status = err.response?.status;
      const detail: string = err.response?.data?.detail || '';
      if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')) {
        setError('Request timed out. Gemini or YouTube took too long — try again with fewer results.');
      } else if (status === 503) {
        setError(detail || 'YouTube or AI service is temporarily unavailable. Please retry shortly.');
      } else if (detail.includes('quota')) {
        setError('YouTube API quota reached. Try again in 24 hours.');
      } else if (detail.includes('No influencers found') || status === 404) {
        setError('No influencers found. Try broader keywords (e.g., "tech", "gaming") or relax filters.');
      } else if (status >= 500) {
        setError(detail || 'Server error. Please retry; if it persists check the backend logs.');
      } else {
        setError(detail || 'Discovery failed.');
      }
    } finally {
      setDiscovering(false);
    }
  };

  const getFilteredInfluencers = () => {
    if (!result) return [];
    if (selectedCategory === 'all') return result.recommended_influencers;
    return result.recommended_influencers.filter((inf) => inf.category === selectedCategory);
  };

  const getScoreColor = (score: number) => {
    if (score >= 80) return '#10b981';
    if (score >= 60) return '#f59e0b';
    return '#ef4444';
  };

  const confidenceLabel: Record<string, { color: string; label: string }> = {
    high: { color: '#10b981', label: 'high confidence' },
    medium: { color: '#f59e0b', label: 'medium confidence' },
    low: { color: '#ef4444', label: 'low confidence' },
  };

  const getToneEmoji = (tone: string) => {
    const tones: Record<string, string> = {
      aggressive: '🔥', friendly: '😊', professional: '💼',
      humorous: '😂', edgy: '⚡', unknown: '❓',
    };
    return tones[tone] || '📝';
  };

  if (!brandProfile) return <div style={styles.loading}>Loading brand profile...</div>;

  const aovMissing = !brandProfile.target_aov || brandProfile.target_aov <= 0;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <button onClick={() => navigate('/brands')} style={styles.backButton}>← Back to Brands</button>
        <h1 style={styles.title}>🔍 Discover Influencers</h1>
        <p style={styles.subtitle}>Brand: <strong>{brandProfile.name}</strong></p>
      </div>

      {aovMissing && (
        <div style={styles.warning}>
          <strong>Heads up:</strong> this brand has no <code>target_aov</code> (average order value).
          Without it, revenue and ROI predictions can't be computed and only reach / cost ranges will show.
          Set it in the brand profile to unlock the full forecast.
        </div>
      )}

      <div style={styles.searchPanel}>
        <h2 style={styles.panelTitle}>Search Configuration</h2>

        <div style={styles.field}>
          <label style={styles.label}>Search Query (optional)</label>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={styles.input}
            placeholder="e.g., gaming tech review, comedy vlog"
            disabled={discovering}
          />
          <small style={styles.hint}>
            Leave empty to use brand's preferred categories: {brandProfile.preferred_categories.join(', ') || 'None'}
          </small>
        </div>

        <div style={styles.row}>
          <div style={styles.field}>
            <label style={styles.label}>Max Results</label>
            <input
              type="number"
              value={maxResults}
              onChange={(e) => { const v = parseInt(e.target.value); if (!isNaN(v)) setMaxResults(v); }}
              style={styles.input}
              min={5} max={50}
              disabled={discovering}
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Posts per Influencer</label>
            <input
              type="number"
              value={numPosts}
              onChange={(e) => { const v = parseInt(e.target.value); if (!isNaN(v) && v >= 1) setNumPosts(v); }}
              style={styles.input}
              min={1} max={10}
              disabled={discovering}
            />
            <small style={styles.hint}>Used to scale predicted reach × posts</small>
          </div>
        </div>

        <div style={styles.advancedToggle}>
          <button type="button" onClick={() => setShowAdvanced(!showAdvanced)} style={styles.toggleButton}>
            {showAdvanced ? '▼' : '▶'} Advanced Filters
          </button>
        </div>

        {showAdvanced && (
          <div style={styles.advancedSection}>
            <div style={styles.row}>
              <div style={styles.field}>
                <label style={styles.label}>Min Subscribers</label>
                <input
                  type="number"
                  value={minSubscribers}
                  onChange={(e) => setMinSubscribers(parseInt(e.target.value) || 0)}
                  style={styles.input}
                  disabled={discovering}
                />
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Max Subscribers</label>
                <input
                  type="number"
                  value={maxSubscribers}
                  onChange={(e) => setMaxSubscribers(parseInt(e.target.value) || 0)}
                  style={styles.input}
                  disabled={discovering}
                />
              </div>
            </div>
            <div style={styles.field}>
              <label style={styles.label}>Min View/Sub Ratio (%) — optional</label>
              <input
                type="number"
                step="0.1"
                value={minViewRatio ?? ''}
                onChange={(e) => setMinViewRatio(e.target.value ? parseFloat(e.target.value) : undefined)}
                style={styles.input}
                placeholder="e.g., 3.0"
                disabled={discovering}
              />
              <small style={styles.hint}>Higher = healthier channel</small>
            </div>
          </div>
        )}

        {error && <div style={styles.error}>{error}</div>}

        <button
          onClick={handleDiscover}
          disabled={discovering}
          style={{
            ...styles.discoverButton,
            ...(discovering ? { opacity: 0.6, cursor: 'not-allowed' } : {}),
          }}
        >
          {discovering ? '🔄 Analyzing with AI…' : '✨ Start Discovery'}
        </button>

        {discovering && (
          <div style={styles.progressInfo}>
            <p>This may take 30-60 seconds. Gemini is scoring fit; YouTube data is fetched in parallel.</p>
          </div>
        )}
      </div>

      {result && result.recommended_influencers.length > 0 && (
        <>
          <div style={styles.resultsHeader}>
            <h2 style={styles.resultsTitle}>📊 Discovery Results</h2>
            <div style={styles.disclaimer}>{result.disclaimer}</div>

            <div style={styles.stats}>
              <div style={styles.statItem}>
                <span style={styles.statLabel}>Found</span>
                <span style={styles.statValue}>{result.recommended_influencers.length}</span>
              </div>
              <div style={styles.statItem}>
                <span style={styles.statLabel}>Recommended Budget</span>
                <span style={styles.statValue}>{fmtMoneyRange(result.recommended_budget)}</span>
              </div>
              <div style={styles.statItem}>
                <span style={styles.statLabel}>Projected Reach</span>
                <span style={styles.statValue}>{fmtRange(result.projected_total_reach)}</span>
              </div>
              {result.predicted_total_revenue && (
                <div style={styles.statItem}>
                  <span style={styles.statLabel}>Predicted Revenue</span>
                  <span style={styles.statValue}>{fmtMoneyRange(result.predicted_total_revenue)}</span>
                </div>
              )}
              {result.predicted_total_roi_percentage && (
                <div style={styles.statItem}>
                  <span style={styles.statLabel}>Predicted ROI</span>
                  <span style={{
                    ...styles.statValue,
                    color: getScoreColor((result.predicted_total_roi_percentage[0] + result.predicted_total_roi_percentage[1]) / 2),
                  }}>
                    {fmtRange(result.predicted_total_roi_percentage, '%', 1)}
                  </span>
                </div>
              )}
            </div>
          </div>

          <div style={styles.strategyPanel}>
            <h3 style={styles.strategyTitle}>🎯 AI Campaign Strategy</h3>
            <div style={styles.strategyContent}>
              {result.campaign_strategy.split('\n').map((line, i) => (
                <p key={i} style={styles.strategyLine}>{line}</p>
              ))}
            </div>
          </div>

          <div style={styles.filterButtons}>
            <button
              onClick={() => setSelectedCategory('all')}
              style={{ ...styles.filterButton, ...(selectedCategory === 'all' ? styles.filterActive : {}) }}
            >
              All ({result.recommended_influencers.length})
            </button>
            <button
              onClick={() => setSelectedCategory('micro')}
              style={{ ...styles.filterButton, ...(selectedCategory === 'micro' ? styles.filterActive : {}) }}
            >
              Micro ({result.breakdown.micro_count})
            </button>
            <button
              onClick={() => setSelectedCategory('macro')}
              style={{ ...styles.filterButton, ...(selectedCategory === 'macro' ? styles.filterActive : {}) }}
            >
              Macro ({result.breakdown.macro_count})
            </button>
            <button
              onClick={() => setSelectedCategory('mega')}
              style={{ ...styles.filterButton, ...(selectedCategory === 'mega' ? styles.filterActive : {}) }}
            >
              Mega ({result.breakdown.mega_count})
            </button>
          </div>

          <div style={styles.influencerGrid}>
            {getFilteredInfluencers().map((inf: InfluencerMatch, idx) => {
              const conf = inf.predicted_outcome
                ? confidenceLabel[inf.predicted_outcome.confidence]
                : null;
              return (
                <div key={inf.influencer_id} style={styles.influencerCard}>
                  <div style={styles.cardHeader}>
                    <div style={styles.rank}>#{idx + 1}</div>
                    <div style={styles.categoryBadge}>{inf.category.toUpperCase()}</div>
                  </div>

                  <h3 style={styles.influencerName}>{inf.display_name}</h3>
                  <p style={styles.influencerUsername}>@{inf.username}</p>

                  <div style={styles.mainScore}>
                    <div style={{
                      fontSize: '2.5rem',
                      fontWeight: 'bold',
                      color: getScoreColor(inf.overall_match_score),
                    }}>
                      {inf.overall_match_score.toFixed(0)}
                    </div>
                    <div style={styles.scoreLabel}>Match Score / 100</div>
                  </div>

                  <div style={styles.metrics}>
                    <div style={styles.metricItem}>
                      <span style={styles.metricLabel}>👥 Followers</span>
                      <span style={styles.metricValue}>{inf.followers_count.toLocaleString()}</span>
                    </div>
                    <div style={styles.metricItem}>
                      <span style={styles.metricLabel}>🔥 Engagement</span>
                      <span style={styles.metricValue}>{inf.engagement_rate.toFixed(2)}%</span>
                    </div>
                    {inf.median_recent_views !== undefined && (
                      <div style={styles.metricItem}>
                        <span style={styles.metricLabel}>📺 Median Views (recent)</span>
                        <span style={styles.metricValue}>{inf.median_recent_views.toLocaleString()}</span>
                      </div>
                    )}
                    {inf.fake_follower_percentage !== undefined && inf.fake_follower_percentage !== null && (
                      <div style={styles.metricItem}>
                        <span style={styles.metricLabel}>🤖 Fake Follower %</span>
                        <span style={{
                          ...styles.metricValue,
                          color: inf.fake_follower_percentage > 30 ? '#ef4444' : '#333',
                        }}>
                          {inf.fake_follower_percentage.toFixed(1)}%
                        </span>
                      </div>
                    )}
                    <div style={styles.metricItem}>
                      <span style={styles.metricLabel}>💰 CPM (benchmark)</span>
                      <span style={styles.metricValue}>{fmtMoneyRange(inf.cpm_benchmark)}</span>
                    </div>
                  </div>

                  {inf.predicted_outcome && (
                    <div style={styles.predictionBlock}>
                      <div style={styles.predictionHeader}>
                        <strong>Predicted outcome</strong>
                        {conf && (
                          <span style={{ ...styles.confChip, background: conf.color }}>{conf.label}</span>
                        )}
                      </div>
                      <div style={styles.predictionGrid}>
                        <div>
                          <div style={styles.predLabel}>Reach</div>
                          <div style={styles.predValue}>{fmtRange(inf.predicted_outcome.predicted_reach)}</div>
                        </div>
                        <div>
                          <div style={styles.predLabel}>Clicks</div>
                          <div style={styles.predValue}>{fmtRange(inf.predicted_outcome.predicted_clicks)}</div>
                        </div>
                        <div>
                          <div style={styles.predLabel}>Cost</div>
                          <div style={styles.predValue}>{fmtMoneyRange(inf.predicted_outcome.predicted_cost)}</div>
                        </div>
                        <div>
                          <div style={styles.predLabel}>Conversions</div>
                          <div style={styles.predValue}>{fmtRange(inf.predicted_outcome.predicted_conversions, '', 1)}</div>
                        </div>
                        <div>
                          <div style={styles.predLabel}>Revenue</div>
                          <div style={styles.predValue}>
                            {inf.predicted_outcome.predicted_revenue[1] > 0
                              ? fmtMoneyRange(inf.predicted_outcome.predicted_revenue)
                              : '— (set AOV)'}
                          </div>
                        </div>
                        <div>
                          <div style={styles.predLabel}>ROI %</div>
                          <div style={{
                            ...styles.predValue,
                            color: inf.predicted_outcome.predicted_roi_percentage[1] !== 0
                              ? getScoreColor((inf.predicted_outcome.predicted_roi_percentage[0] + inf.predicted_outcome.predicted_roi_percentage[1]) / 2)
                              : '#999',
                          }}>
                            {inf.predicted_outcome.predicted_roi_percentage[1] !== 0
                              ? fmtRange(inf.predicted_outcome.predicted_roi_percentage, '%', 1)
                              : '— (set AOV)'}
                          </div>
                        </div>
                      </div>
                      <div style={styles.predSource}>Source: {inf.predicted_outcome.source}</div>
                    </div>
                  )}

                  <div style={styles.subScores}>
                    {([
                      ['Content Style', inf.content_style_match],
                      ['Audience Match', inf.audience_match],
                      ['Engagement Quality', inf.engagement_quality],
                      ['Brand Safety', inf.brand_safety],
                    ] as const).map(([label, val]) => (
                      <div style={styles.subScore} key={label}>
                        <div style={styles.subScoreBar}>
                          <div style={{ ...styles.subScoreFill, width: `${val}%`, background: getScoreColor(val) }} />
                        </div>
                        <span style={styles.subScoreLabel}>{label}</span>
                        <span style={styles.subScoreValue}>{val.toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>

                  <div style={styles.tone}>
                    <span style={styles.toneEmoji}>{getToneEmoji(inf.content_tone)}</span>
                    <span style={styles.toneText}>{inf.content_tone}</span>
                    {inf.quality_flags?.length > 0 && (
                      <span style={styles.flags}>{inf.quality_flags.join(', ')}</span>
                    )}
                  </div>

                  <div style={styles.aiSummary}>
                    <strong>🤖 AI Analysis:</strong>
                    <p style={styles.summaryText}>{inf.ai_summary}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: { maxWidth: '1400px', margin: '0 auto', padding: '2rem' },
  loading: { textAlign: 'center', padding: '4rem', fontSize: '1.2rem', color: '#666' },
  header: { marginBottom: '2rem' },
  backButton: { padding: '0.5rem 1rem', background: '#e0e0e0', border: 'none', borderRadius: '8px', cursor: 'pointer', marginBottom: '1rem', fontWeight: 500 },
  title: { margin: '0 0 0.5rem 0', fontSize: '2.5rem', color: '#333' },
  subtitle: { margin: 0, fontSize: '1rem', color: '#666' },
  warning: { background: '#fff7ed', border: '1px solid #fb923c', color: '#9a3412', padding: '1rem', borderRadius: '8px', marginBottom: '1.5rem' },
  searchPanel: { background: 'white', padding: '2rem', borderRadius: '15px', boxShadow: '0 4px 12px rgba(0,0,0,0.1)', marginBottom: '2rem' },
  panelTitle: { margin: '0 0 1.5rem 0', fontSize: '1.5rem', color: '#333' },
  field: { marginBottom: '1.5rem' },
  label: { display: 'block', marginBottom: '0.5rem', fontSize: '0.9rem', fontWeight: 600, color: '#333' },
  input: { width: '100%', padding: '0.75rem', fontSize: '1rem', border: '2px solid #e0e0e0', borderRadius: '8px', outline: 'none' },
  hint: { display: 'block', marginTop: '0.5rem', fontSize: '0.85rem', color: '#999' },
  error: { background: '#fee', color: '#c00', padding: '1rem', borderRadius: '8px', marginBottom: '1rem' },
  discoverButton: { width: '100%', padding: '1rem', fontSize: '1.1rem', fontWeight: 600, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer' },
  progressInfo: { marginTop: '1rem', padding: '1rem', background: '#f0f9ff', borderRadius: '8px', textAlign: 'center' },
  resultsHeader: { background: 'white', padding: '2rem', borderRadius: '15px', boxShadow: '0 4px 12px rgba(0,0,0,0.1)', marginBottom: '1.5rem' },
  resultsTitle: { margin: '0 0 0.5rem 0', fontSize: '1.75rem', color: '#333' },
  disclaimer: { fontSize: '0.85rem', color: '#666', marginBottom: '1.5rem', fontStyle: 'italic' },
  stats: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1.5rem' },
  statItem: { textAlign: 'center' },
  statLabel: { display: 'block', fontSize: '0.85rem', color: '#666', marginBottom: '0.5rem' },
  statValue: { display: 'block', fontSize: '1.5rem', fontWeight: 'bold', color: '#333' },
  strategyPanel: { background: 'linear-gradient(135deg, #667eea15 0%, #764ba215 100%)', padding: '2rem', borderRadius: '15px', marginBottom: '2rem', border: '2px solid #667eea30' },
  strategyTitle: { margin: '0 0 1rem 0', fontSize: '1.25rem', color: '#333' },
  strategyContent: { fontSize: '1rem', lineHeight: '1.8', color: '#444' },
  strategyLine: { margin: '0.5rem 0' },
  filterButtons: { display: 'flex', gap: '1rem', marginBottom: '2rem' },
  filterButton: { padding: '0.75rem 1.5rem', background: 'white', border: '2px solid #e0e0e0', borderRadius: '8px', cursor: 'pointer', fontWeight: 600 },
  filterActive: { background: '#667eea', color: 'white', borderColor: '#667eea' },
  influencerGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))', gap: '2rem' },
  influencerCard: { background: 'white', padding: '2rem', borderRadius: '15px', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' },
  rank: { fontSize: '1.5rem', fontWeight: 'bold', color: '#667eea' },
  categoryBadge: { padding: '0.25rem 0.75rem', background: '#f0f0f0', borderRadius: '20px', fontSize: '0.75rem', fontWeight: 700, color: '#666' },
  influencerName: { margin: '0 0 0.25rem 0', fontSize: '1.25rem', color: '#333' },
  influencerUsername: { margin: '0 0 1.5rem 0', fontSize: '0.9rem', color: '#999' },
  mainScore: { display: 'flex', flexDirection: 'column', alignItems: 'center', marginBottom: '1.5rem' },
  scoreLabel: { fontSize: '0.85rem', color: '#666', fontWeight: 600 },
  metrics: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem', padding: '1rem', background: '#f9f9f9', borderRadius: '10px' },
  metricItem: { display: 'flex', flexDirection: 'column', gap: '0.25rem' },
  metricLabel: { fontSize: '0.8rem', color: '#666' },
  metricValue: { fontSize: '1rem', fontWeight: 'bold', color: '#333' },
  predictionBlock: { padding: '1rem', background: '#f0f9ff', borderRadius: '10px', marginBottom: '1.5rem', border: '1px solid #cfe7ff' },
  predictionHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' },
  confChip: { color: 'white', fontSize: '0.7rem', padding: '0.2rem 0.6rem', borderRadius: '12px', textTransform: 'uppercase', fontWeight: 700 },
  predictionGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' },
  predLabel: { fontSize: '0.75rem', color: '#666' },
  predValue: { fontSize: '0.95rem', fontWeight: 600, color: '#0c4a6e' },
  predSource: { marginTop: '0.75rem', fontSize: '0.7rem', color: '#888', fontStyle: 'italic' },
  subScores: { display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' },
  subScore: { display: 'grid', gridTemplateColumns: '1fr auto auto', alignItems: 'center', gap: '0.5rem' },
  subScoreBar: { height: '6px', background: '#e0e0e0', borderRadius: '3px', overflow: 'hidden' },
  subScoreFill: { height: '100%', transition: 'width 0.3s ease' },
  subScoreLabel: { fontSize: '0.8rem', color: '#666' },
  subScoreValue: { fontSize: '0.85rem', fontWeight: 'bold', color: '#333', width: '40px', textAlign: 'right' },
  tone: { display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', background: '#f0f0f0', borderRadius: '8px', marginBottom: '1rem' },
  toneEmoji: { fontSize: '1.5rem' },
  toneText: { fontSize: '0.9rem', fontWeight: 600, color: '#333', textTransform: 'capitalize' },
  flags: { marginLeft: 'auto', fontSize: '0.75rem', color: '#9a3412', fontStyle: 'italic' },
  aiSummary: { padding: '1rem', background: '#f0f9ff', borderRadius: '8px', fontSize: '0.9rem', lineHeight: '1.6', color: '#333' },
  summaryText: { margin: '0.5rem 0 0 0' },
  advancedToggle: { marginBottom: '1rem' },
  toggleButton: { padding: '0.5rem 1rem', background: '#f0f0f0', border: '1px solid #ddd', borderRadius: '6px', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 600, color: '#555' },
  advancedSection: { background: '#f9f9f9', padding: '1.5rem', borderRadius: '10px', marginBottom: '1.5rem', border: '1px solid #e0e0e0' },
  row: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' },
};
