import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { campaignsAPI, campaignIntelligenceAPI, brandsAPI } from '../lib/api';
import type {
  Campaign, BrandProfile, CampaignMatchResult, CampaignCreator, CampaignTask,
  CampaignBrief, CreatorContent, CampaignPerformance, PerformanceAnalysis,
  CampaignReport, ContentType,
} from '../lib/types';
import { CAMPAIGN_CREATOR_STATUSES, CAMPAIGN_TASK_TYPES } from '../lib/types';

type Tab = 'matches' | 'creators' | 'briefs' | 'content' | 'performance' | 'report';

const TIER_COLOR: Record<string, string> = { S: '#f59e0b', A: '#3b82f6', B: '#9ca3af' };
const RISK_COLOR: Record<string, string> = { low: '#10b981', medium: '#f59e0b', high: '#ef4444', unknown: '#9ca3af' };

function fmtNum(n: number | null | undefined): string {
  if (n == null) return '—';
  return n.toLocaleString();
}
function fmtScore(n: number | null | undefined): string {
  return n == null ? '—' : n.toFixed(1);
}
function fmtMoney(n: number | null | undefined): string {
  return n == null ? '—' : `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export const CampaignIntelligencePage = () => {
  const { id } = useParams<{ id: string }>();
  const campaignId = id ? parseInt(id, 10) : null;

  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [tab, setTab] = useState<Tab>('matches');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!campaignId) return;
    campaignsAPI.get(campaignId).then(setCampaign).catch((e) => setError(e.response?.data?.detail || 'Failed to load campaign'));
  }, [campaignId]);

  if (!campaignId) return <div style={s.container}>Invalid campaign.</div>;

  return (
    <div style={s.container}>
      <Link to={`/campaigns/${campaignId}`} style={s.backLink}>{'←'} Back to Campaign</Link>
      <div style={s.header}>
        <h1 style={s.title}>{'🤖'} AI Campaign Intelligence</h1>
        <p style={s.subtitle}>{campaign ? campaign.name : `Campaign #${campaignId}`}</p>
      </div>

      {error && <div style={s.errorBanner}>{error}</div>}

      <div style={s.tabs}>
        {(['matches', 'creators', 'briefs', 'content', 'performance', 'report'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{ ...s.tabBtn, ...(tab === t ? s.tabBtnActive : {}) }}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {tab === 'matches' && <MatchesTab campaignId={campaignId} />}
      {tab === 'creators' && <CreatorsTab campaignId={campaignId} />}
      {tab === 'briefs' && <BriefsTab campaignId={campaignId} />}
      {tab === 'content' && <ContentTab campaignId={campaignId} />}
      {tab === 'performance' && <PerformanceTab campaignId={campaignId} />}
      {tab === 'report' && <ReportTab campaignId={campaignId} />}
    </div>
  );
};

const TAB_LABELS: Record<Tab, string> = {
  matches: 'AI Matches',
  creators: 'Shortlist',
  briefs: 'Briefs',
  content: 'Content Studio',
  performance: 'Performance',
  report: 'Report',
};

// ---------------------------------------------------------------------------
// AI Matches tab
// ---------------------------------------------------------------------------

function MatchesTab({ campaignId }: { campaignId: number }) {
  const [brandProfiles, setBrandProfiles] = useState<BrandProfile[]>([]);
  const [brandProfileId, setBrandProfileId] = useState<number | null>(null);
  const [objective, setObjective] = useState('');
  const [budget, setBudget] = useState<string>('');
  const [matches, setMatches] = useState<CampaignMatchResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tierFilter, setTierFilter] = useState('all');
  const [shortlisting, setShortlisting] = useState<Set<number>>(new Set());

  useEffect(() => {
    brandsAPI.listProfiles().then((profiles: BrandProfile[]) => {
      setBrandProfiles(profiles);
      if (profiles.length > 0) setBrandProfileId(profiles[0].id);
    }).catch(() => {});
    campaignIntelligenceAPI.listMatches(campaignId).then((r) => setMatches(r.matches)).catch(() => {});
  }, [campaignId]);

  const runMatching = async () => {
    if (!brandProfileId) { setError('Select a brand profile first.'); return; }
    setBusy(true);
    setError(null);
    try {
      if (objective || budget) {
        await campaignIntelligenceAPI.analyze(campaignId, {
          objective: objective || undefined,
          budget: budget ? parseFloat(budget) : undefined,
        });
      }
      const result = await campaignIntelligenceAPI.matchCreators(campaignId, { brand_profile_id: brandProfileId });
      setMatches(result.matches);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'AI matching failed.');
    } finally {
      setBusy(false);
    }
  };

  const shortlist = async (influencerId: number) => {
    setShortlisting((prev) => new Set(prev).add(influencerId));
    try {
      await campaignIntelligenceAPI.shortlist(campaignId, [influencerId]);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Shortlist failed.');
    }
  };

  const filtered = tierFilter === 'all' ? matches : matches.filter((m) => m.tier === tierFilter);

  return (
    <div>
      <div style={s.card}>
        <h3 style={s.cardTitle}>Run AI Creator Matching</h3>
        <p style={s.cardHint}>
          Consumes each creator's existing Trust Score / Sponsorship Maturity — never recomputes them.
          Produces a separate, per-campaign Campaign Match Score.
        </p>
        <div style={s.formRow}>
          <select value={brandProfileId ?? ''} onChange={(e) => setBrandProfileId(Number(e.target.value))} style={s.select}>
            <option value="" disabled>Select brand profile…</option>
            {brandProfiles.map((bp) => <option key={bp.id} value={bp.id}>{bp.name}</option>)}
          </select>
          <input
            placeholder="Campaign objective (optional)"
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            style={s.input}
          />
          <input
            placeholder="Budget (optional)"
            type="number"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            style={{ ...s.input, maxWidth: '140px' }}
          />
          <button onClick={runMatching} disabled={busy || brandProfiles.length === 0} style={s.primaryBtn}>
            {busy ? 'Matching…' : '🤖 Run AI Matching'}
          </button>
        </div>
        {brandProfiles.length === 0 && (
          <p style={s.warnText}>No brand profiles yet — <Link to="/brands/new">create one</Link> first.</p>
        )}
        {error && <p style={s.errorText}>{error}</p>}
      </div>

      {matches.length > 0 && (
        <>
          <div style={s.filterRow}>
            <select value={tierFilter} onChange={(e) => setTierFilter(e.target.value)} style={s.select}>
              <option value="all">All tiers</option>
              <option value="S">S — Priority Partner</option>
              <option value="A">A — High-Potential</option>
              <option value="B">B — Commodity</option>
            </select>
            <span style={s.hintText}>{filtered.length} of {matches.length} creators</span>
          </div>

          <div style={s.matchGrid}>
            {filtered.map((m) => (
              <div key={m.influencer_id} style={s.matchCard}>
                <div style={s.matchCardHeader}>
                  <div>
                    <Link to={`/roster/${m.influencer_id}?campaign_id=${campaignId}`} style={s.creatorLink}>{m.display_name}</Link>
                    <div style={s.mutedSmall}>@{m.username} · {fmtNum(m.followers_count)} followers</div>
                  </div>
                  {m.tier && (
                    <span style={{ ...s.pill, background: TIER_COLOR[m.tier], color: '#fff' }}>{m.tier}</span>
                  )}
                </div>

                <div style={s.scoreRow}>
                  <div style={s.scoreBox}>
                    <div style={s.scoreLabel}>Trust Score</div>
                    <div style={s.scoreValue}>{fmtScore(m.trust_score)}</div>
                  </div>
                  <div style={s.scoreBox}>
                    <div style={s.scoreLabel}>Campaign Match</div>
                    <div style={{ ...s.scoreValue, color: '#667eea' }}>{fmtScore(m.match_score)}</div>
                  </div>
                  <div style={s.scoreBox}>
                    <div style={s.scoreLabel}>Risk</div>
                    <div style={{ ...s.scoreValue, color: RISK_COLOR[m.risk_level ?? 'unknown'], fontSize: '0.9rem', textTransform: 'capitalize' }}>
                      {m.risk_level ?? 'unknown'}
                    </div>
                  </div>
                </div>

                {m.sponsorship_maturity && (
                  <div style={s.mutedSmall}>Sponsorship: <strong>{m.sponsorship_maturity}</strong></div>
                )}
                <div style={s.mutedSmall}>
                  Est. reach {fmtNum(m.estimated_reach)} · Est. cost {m.estimated_cost ? `${fmtMoney(m.estimated_cost[0])}–${fmtMoney(m.estimated_cost[1])}` : '—'}
                </div>

                <p style={s.whyText}>{m.why}</p>

                <button onClick={() => shortlist(m.influencer_id)} style={s.secondaryBtn} disabled={shortlisting.has(m.influencer_id)}>
                  {shortlisting.has(m.influencer_id) ? '✓ Shortlisted' : '+ Shortlist'}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shortlist / Creators tab
// ---------------------------------------------------------------------------

function CreatorsTab({ campaignId }: { campaignId: number }) {
  const [creators, setCreators] = useState<CampaignCreator[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = useCallback(() => {
    campaignIntelligenceAPI.listCreators(campaignId).then(setCreators).catch((e) => setError(e.response?.data?.detail));
  }, [campaignId]);

  useEffect(() => { load(); }, [load]);

  const updateStatus = async (influencerId: number, status: string) => {
    try {
      await campaignIntelligenceAPI.updateCreator(campaignId, influencerId, { status });
      load();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Update failed.');
    }
  };

  if (creators.length === 0) {
    return <div style={s.card}><p style={s.cardHint}>No creators shortlisted yet — shortlist from the AI Matches tab.</p></div>;
  }

  return (
    <div>
      {error && <p style={s.errorText}>{error}</p>}
      {creators.map((c) => (
        <div key={c.id} style={s.card}>
          <div style={s.matchCardHeader}>
            <div>
              <Link to={`/roster/${c.influencer_id}?campaign_id=${campaignId}`} style={s.creatorLink}>{c.display_name}</Link>
              <div style={s.mutedSmall}>
                Match {fmtScore(c.match_score)} · Trust {fmtScore(c.trust_score)}
                {c.recommended_role ? ` · ${c.recommended_role}` : ''}
              </div>
            </div>
            <select value={c.status} onChange={(e) => updateStatus(c.influencer_id, e.target.value)} style={s.select}>
              {CAMPAIGN_CREATOR_STATUSES.map((st) => <option key={st} value={st}>{st.replace('_', ' ')}</option>)}
            </select>
          </div>

          <button onClick={() => setExpanded((prev) => (prev === c.id ? null : c.id))} style={s.linkBtn}>
            {expanded === c.id ? 'Hide actuals & tasks ▲' : 'Actuals & tasks ▼'}
          </button>

          {expanded === c.id && (
            <CreatorDetailPanel campaignId={campaignId} creator={c} onChanged={load} />
          )}
        </div>
      ))}
    </div>
  );
}

function CreatorDetailPanel({ campaignId, creator, onChanged }: { campaignId: number; creator: CampaignCreator; onChanged: () => void }) {
  const [actuals, setActuals] = useState({
    views: creator.views ?? '', clicks: creator.clicks ?? '', conversions: creator.conversions ?? '',
    revenue: creator.revenue ?? '', spend: creator.spend ?? '',
  });
  const [tasks, setTasks] = useState<CampaignTask[]>([]);
  const [taskType, setTaskType] = useState<string>(CAMPAIGN_TASK_TYPES[0]);
  const [deadline, setDeadline] = useState('');
  const [busy, setBusy] = useState(false);

  const loadTasks = useCallback(() => {
    campaignIntelligenceAPI.listTasks(campaignId, creator.influencer_id).then(setTasks).catch(() => {});
  }, [campaignId, creator.influencer_id]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const saveActuals = async () => {
    setBusy(true);
    try {
      const payload: Record<string, number> = {};
      for (const [k, v] of Object.entries(actuals)) {
        if (v !== '') payload[k] = Number(v);
      }
      await campaignIntelligenceAPI.updateCreator(campaignId, creator.influencer_id, payload);
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const addTask = async () => {
    await campaignIntelligenceAPI.createTask(campaignId, creator.influencer_id, {
      task_type: taskType,
      deadline: deadline ? new Date(deadline).toISOString() : undefined,
    });
    setDeadline('');
    loadTasks();
  };

  return (
    <div style={s.subPanel}>
      <h4 style={s.detailTitle}>Actuals</h4>
      <div style={s.formRow}>
        {(['views', 'clicks', 'conversions', 'revenue', 'spend'] as const).map((field) => (
          <input
            key={field}
            type="number"
            placeholder={field}
            value={actuals[field]}
            onChange={(e) => setActuals((prev) => ({ ...prev, [field]: e.target.value }))}
            style={{ ...s.input, maxWidth: '110px' }}
          />
        ))}
        <button onClick={saveActuals} disabled={busy} style={s.secondaryBtn}>Save</button>
      </div>

      <h4 style={s.detailTitle}>Tasks</h4>
      {tasks.length === 0 && <p style={s.mutedSmall}>No tasks yet.</p>}
      {tasks.map((t) => (
        <div key={t.id} style={s.taskRow}>
          <span>{t.task_type.replace('_', ' ')}</span>
          <span style={{ color: t.is_overdue ? '#ef4444' : '#888' }}>
            {t.deadline ? new Date(t.deadline).toLocaleDateString() : 'no deadline'}
            {t.is_overdue ? ' · OVERDUE' : ''}
          </span>
          <span>{t.status}</span>
        </div>
      ))}
      <div style={s.formRow}>
        <select value={taskType} onChange={(e) => setTaskType(e.target.value)} style={s.select}>
          {CAMPAIGN_TASK_TYPES.map((tt) => <option key={tt} value={tt}>{tt.replace('_', ' ')}</option>)}
        </select>
        <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} style={s.input} />
        <button onClick={addTask} style={s.secondaryBtn}>+ Add task</button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Briefs tab
// ---------------------------------------------------------------------------

function BriefsTab({ campaignId }: { campaignId: number }) {
  const [creators, setCreators] = useState<CampaignCreator[]>([]);
  const [briefs, setBriefs] = useState<Record<number, CampaignBrief>>({});
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    campaignIntelligenceAPI.listCreators(campaignId).then(setCreators).catch(() => {});
  }, [campaignId]);

  const generate = async (influencerId: number) => {
    setBusy(influencerId);
    try {
      const result = await campaignIntelligenceAPI.generateBriefs(campaignId, [influencerId]);
      setBriefs((prev) => ({ ...prev, [influencerId]: result[0] }));
    } finally {
      setBusy(null);
    }
  };

  if (creators.length === 0) {
    return <div style={s.card}><p style={s.cardHint}>Shortlist creators first, then generate personalized briefs here.</p></div>;
  }

  return (
    <div>
      {creators.map((c) => {
        const brief = briefs[c.influencer_id];
        return (
          <div key={c.id} style={s.card}>
            <div style={s.matchCardHeader}>
              <span style={s.creatorLink}>{c.display_name}</span>
              <button onClick={() => generate(c.influencer_id)} disabled={busy === c.influencer_id} style={s.primaryBtn}>
                {busy === c.influencer_id ? 'Generating…' : brief ? '↻ Regenerate' : '✍️ Generate Brief'}
              </button>
            </div>
            {brief && (
              <div style={s.briefBody}>
                <p><strong>Objective:</strong> {brief.objective}</p>
                <p><strong>Key message:</strong> {brief.key_message}</p>
                <p><strong>Format:</strong> {brief.content_format}</p>
                <p><strong>Hook:</strong> {brief.hook}</p>
                <p><strong>Talking points:</strong> {brief.talking_points.join(' · ')}</p>
                <p><strong>CTA:</strong> {brief.cta}</p>
                <p><strong>Do's:</strong> {brief.dos.join(' · ')}</p>
                <p><strong>Don'ts:</strong> {brief.donts.join(' · ')}</p>
                <p><strong>Disclosures:</strong> {brief.required_disclosures}</p>
                <p style={s.mutedSmall}>Source: {brief.source}</p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Content Studio tab
// ---------------------------------------------------------------------------

const CONTENT_TYPES: ContentType[] = [
  'caption', 'youtube_title', 'youtube_description', 'short_hook',
  'video_concept', 'script_outline', 'cta', 'hashtags', 'talking_points',
];

function ContentTab({ campaignId }: { campaignId: number }) {
  const [creators, setCreators] = useState<CampaignCreator[]>([]);
  const [influencerId, setInfluencerId] = useState<number | null>(null);
  const [contentType, setContentType] = useState<ContentType>('caption');
  const [result, setResult] = useState<CreatorContent | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    campaignIntelligenceAPI.listCreators(campaignId).then((list) => {
      setCreators(list);
      if (list.length > 0) setInfluencerId(list[0].influencer_id);
    }).catch(() => {});
  }, [campaignId]);

  const generate = async () => {
    if (!influencerId) return;
    setBusy(true);
    try {
      const r = await campaignIntelligenceAPI.generateContent({ influencer_id: influencerId, campaign_id: campaignId, content_type: contentType });
      setResult(r);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={s.card}>
      <div style={s.formRow}>
        <select value={influencerId ?? ''} onChange={(e) => setInfluencerId(Number(e.target.value))} style={s.select}>
          {creators.map((c) => <option key={c.influencer_id} value={c.influencer_id}>{c.display_name}</option>)}
        </select>
        <select value={contentType} onChange={(e) => setContentType(e.target.value as ContentType)} style={s.select}>
          {CONTENT_TYPES.map((ct) => <option key={ct} value={ct}>{ct.replace('_', ' ')}</option>)}
        </select>
        <button onClick={generate} disabled={busy || !influencerId} style={s.primaryBtn}>
          {busy ? 'Generating…' : '✨ Generate'}
        </button>
      </div>
      {creators.length === 0 && <p style={s.cardHint}>Shortlist creators first to generate content for them.</p>}
      {result && (
        <div style={s.briefBody}>
          {Object.entries(result).filter(([k, v]) => v && !['id', 'influencer_id', 'campaign_id', 'content_type', 'source', 'generated_at'].includes(k)).map(([k, v]) => (
            <p key={k}><strong>{k.replace('_', ' ')}:</strong> {Array.isArray(v) ? v.join(' · ') : String(v)}</p>
          ))}
          <p style={s.mutedSmall}>Source: {result.source}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Performance tab
// ---------------------------------------------------------------------------

function PerformanceTab({ campaignId }: { campaignId: number }) {
  const [perf, setPerf] = useState<CampaignPerformance | null>(null);
  const [analysis, setAnalysis] = useState<PerformanceAnalysis | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    campaignIntelligenceAPI.performance(campaignId).then(setPerf).catch(() => {});
  }, [campaignId]);

  useEffect(() => { load(); }, [load]);

  const runAnalysis = async () => {
    setBusy(true);
    try {
      const r = await campaignIntelligenceAPI.analyzePerformance(campaignId);
      setAnalysis(r);
    } finally {
      setBusy(false);
    }
  };

  if (!perf) return null;

  return (
    <div>
      <div style={s.card}>
        <h3 style={s.cardTitle}>Campaign Performance ({perf.data_completeness} data)</h3>
        <div style={s.scoreRow}>
          <Metric label="Views" value={fmtNum(perf.views)} />
          <Metric label="Clicks" value={fmtNum(perf.clicks)} />
          <Metric label="CTR" value={perf.ctr != null ? `${perf.ctr}%` : '—'} />
          <Metric label="Conversions" value={fmtNum(perf.conversions)} />
          <Metric label="Revenue" value={fmtMoney(perf.revenue)} />
          <Metric label="Spend" value={fmtMoney(perf.spend)} />
          <Metric label="ROI" value={perf.roi_percentage != null ? `${perf.roi_percentage}%` : '—'} />
          <Metric label="CPM" value={fmtMoney(perf.cpm)} />
        </div>
        {perf.note && <p style={s.warnText}>{perf.note}</p>}
      </div>

      {perf.per_creator.length > 0 && (
        <div style={s.card}>
          <h4 style={s.detailTitle}>Per-creator</h4>
          {perf.per_creator.map((cp) => (
            <div key={cp.influencer_id} style={s.taskRow}>
              <span>{cp.display_name}</span>
              <span>{fmtNum(cp.views)} views</span>
              <span>{fmtMoney(cp.revenue)} rev</span>
              <span>{cp.roi_percentage != null ? `${cp.roi_percentage}% ROI` : 'no ROI yet'}</span>
            </div>
          ))}
        </div>
      )}

      <div style={s.card}>
        <button onClick={runAnalysis} disabled={busy} style={s.primaryBtn}>
          {busy ? 'Analyzing…' : '🧠 Run AI Performance Analysis'}
        </button>
        {analysis && (
          <div style={s.briefBody}>
            <p><strong>What happened:</strong> {analysis.what_happened}</p>
            <p><strong>Why:</strong> {analysis.why}</p>
            <p><strong>What next:</strong> {analysis.what_next}</p>
            <p style={s.mutedSmall}>Source: {analysis.source}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={s.scoreBox}>
      <div style={s.scoreLabel}>{label}</div>
      <div style={s.scoreValue}>{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Report tab
// ---------------------------------------------------------------------------

function ReportTab({ campaignId }: { campaignId: number }) {
  const [report, setReport] = useState<CampaignReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    campaignIntelligenceAPI.report(campaignId).then(setReport).catch((e) => setError(e.response?.data?.detail));
  }, [campaignId]);

  if (error) return <p style={s.errorText}>{error}</p>;
  if (!report) return null;

  return (
    <div style={s.card}>
      <h3 style={s.cardTitle}>Campaign Report</h3>
      <Section title="Executive Summary" text={report.executive_summary} />
      <Section title="Objective" text={report.campaign_objective} />
      <Section title="Creator Selection" text={report.creator_selection} />
      <Section title="ROI Analysis" text={report.roi_analysis} />
      <ListSection title="Key Insights" items={report.key_insights} />
      <ListSection title="Risks" items={report.risks} />
      <ListSection title="Recommendations" items={report.recommendations} />
      <Section title="Next Campaign Strategy" text={report.next_campaign_strategy} />
    </div>
  );
}

function Section({ title, text }: { title: string; text: string }) {
  return (
    <div style={{ marginBottom: '1rem' }}>
      <h4 style={s.detailTitle}>{title}</h4>
      <p style={s.mutedText}>{text}</p>
    </div>
  );
}

function ListSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div style={{ marginBottom: '1rem' }}>
      <h4 style={s.detailTitle}>{title}</h4>
      <ul>
        {items.map((it, idx) => <li key={idx} style={s.mutedText}>{it}</li>)}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles — matches the project's established purple gradient / card system
// ---------------------------------------------------------------------------

const s: Record<string, React.CSSProperties> = {
  container: { maxWidth: '1200px', margin: '0 auto', padding: '2rem' },
  backLink: { color: '#667eea', textDecoration: 'none', fontSize: '0.9rem' },
  header: { margin: '0.75rem 0 1.5rem 0' },
  title: { margin: '0 0 0.25rem 0', fontSize: '2rem', color: '#333' },
  subtitle: { margin: 0, color: '#666' },
  errorBanner: { background: '#fee2e2', color: '#991b1b', padding: '0.75rem 1rem', borderRadius: '8px', marginBottom: '1rem' },
  tabs: { display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' as const },
  tabBtn: {
    padding: '0.55rem 1.1rem', borderRadius: '8px', border: '1.5px solid #e0e0e0',
    background: 'white', color: '#555', fontWeight: 600, cursor: 'pointer', fontSize: '0.88rem',
  },
  tabBtnActive: { background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white', border: 'none' },
  card: { background: 'white', borderRadius: '12px', padding: '1.5rem', marginBottom: '1.25rem', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' },
  cardTitle: { margin: '0 0 0.5rem 0', fontSize: '1.15rem', color: '#333' },
  cardHint: { color: '#777', fontSize: '0.9rem', margin: '0 0 1rem 0' },
  formRow: { display: 'flex', gap: '0.6rem', flexWrap: 'wrap' as const, alignItems: 'center' },
  filterRow: { display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '1rem' },
  select: { padding: '0.55rem 0.75rem', border: '1.5px solid #e0e0e0', borderRadius: '8px', fontSize: '0.88rem', background: 'white' },
  input: { padding: '0.55rem 0.75rem', border: '1.5px solid #e0e0e0', borderRadius: '8px', fontSize: '0.88rem', flex: '1 1 160px' },
  primaryBtn: {
    padding: '0.6rem 1.1rem', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.88rem',
  },
  secondaryBtn: {
    padding: '0.5rem 0.9rem', background: 'white', color: '#667eea', border: '1.5px solid #667eea',
    borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.85rem',
  },
  linkBtn: { background: 'none', border: 'none', color: '#667eea', cursor: 'pointer', fontSize: '0.85rem', padding: '0.5rem 0', fontWeight: 600 },
  warnText: { color: '#b45309', fontSize: '0.85rem' },
  errorText: { color: '#ef4444', fontSize: '0.85rem' },
  hintText: { color: '#888', fontSize: '0.85rem' },
  matchGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' },
  matchCard: { background: 'white', borderRadius: '12px', padding: '1.25rem', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' },
  matchCardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' },
  creatorLink: { fontWeight: 700, color: '#333', textDecoration: 'none', fontSize: '1rem' },
  mutedSmall: { color: '#888', fontSize: '0.78rem', marginTop: '0.15rem' },
  mutedText: { color: '#444', fontSize: '0.9rem', lineHeight: 1.6 },
  pill: { padding: '0.2rem 0.65rem', borderRadius: '12px', fontWeight: 800, fontSize: '0.8rem' },
  scoreRow: { display: 'flex', gap: '0.75rem', margin: '0.75rem 0', flexWrap: 'wrap' as const },
  scoreBox: { flex: '1 1 90px', background: '#f8f9fa', borderRadius: '8px', padding: '0.5rem 0.75rem', textAlign: 'center' as const },
  scoreLabel: { fontSize: '0.7rem', color: '#888', textTransform: 'uppercase' as const, marginBottom: '0.2rem' },
  scoreValue: { fontSize: '1.1rem', fontWeight: 700, color: '#333' },
  whyText: { fontSize: '0.85rem', color: '#555', lineHeight: 1.5, margin: '0.5rem 0' },
  subPanel: { marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid #eee' },
  detailTitle: { fontSize: '0.85rem', fontWeight: 700, color: '#667eea', textTransform: 'uppercase' as const, margin: '0.5rem 0' },
  taskRow: { display: 'flex', justifyContent: 'space-between', padding: '0.4rem 0', borderBottom: '1px solid #f0f0f0', fontSize: '0.85rem' },
  briefBody: { marginTop: '0.75rem', fontSize: '0.9rem', color: '#444', lineHeight: 1.7 },
};
