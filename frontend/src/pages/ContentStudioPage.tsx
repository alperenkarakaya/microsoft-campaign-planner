import { useEffect, useState } from 'react';
import { rosterAPI, campaignIntelligenceAPI } from '../lib/api';
import type { RosterCreator, CreatorContent, ContentType } from '../lib/types';

const CONTENT_TYPES: ContentType[] = [
  'caption', 'youtube_title', 'youtube_description', 'short_hook',
  'video_concept', 'script_outline', 'cta', 'hashtags', 'talking_points',
];

export const ContentStudioPage = () => {
  const [creators, setCreators] = useState<RosterCreator[]>([]);
  const [influencerId, setInfluencerId] = useState<number | null>(null);
  const [contentType, setContentType] = useState<ContentType>('caption');
  const [extra, setExtra] = useState('');
  const [result, setResult] = useState<CreatorContent | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    rosterAPI.intelligence({ limit: 200 }).then((r) => {
      setCreators(r.creators);
      if (r.creators.length > 0) setInfluencerId(r.creators[0].influencer_id);
    }).catch(() => {});
  }, []);

  const generate = async () => {
    if (!influencerId) return;
    setBusy(true);
    setError(null);
    try {
      const r = await campaignIntelligenceAPI.generateContent({
        influencer_id: influencerId, content_type: contentType,
        extra_instructions: extra || undefined,
      });
      setResult(r);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Content generation failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={s.container}>
      <h1 style={s.title}>{'🎬'} Content Studio</h1>
      <p style={s.subtitle}>
        Generate captions, titles, hooks, scripts, and more — tailored to each creator's
        existing category and content tone.
      </p>

      <div style={s.card}>
        <div style={s.formRow}>
          <select value={influencerId ?? ''} onChange={(e) => setInfluencerId(Number(e.target.value))} style={s.select}>
            {creators.map((c) => <option key={c.influencer_id} value={c.influencer_id}>{c.display_name}</option>)}
          </select>
          <select value={contentType} onChange={(e) => setContentType(e.target.value as ContentType)} style={s.select}>
            {CONTENT_TYPES.map((ct) => <option key={ct} value={ct}>{ct.replace('_', ' ')}</option>)}
          </select>
        </div>
        <textarea
          placeholder="Extra instructions (optional)"
          value={extra}
          onChange={(e) => setExtra(e.target.value)}
          style={s.textarea}
        />
        <button onClick={generate} disabled={busy || !influencerId} style={s.primaryBtn}>
          {busy ? 'Generating…' : '✨ Generate'}
        </button>
        {error && <p style={s.errorText}>{error}</p>}

        {result && (
          <div style={s.resultBox}>
            {Object.entries(result)
              .filter(([k, v]) => v && !['id', 'influencer_id', 'campaign_id', 'content_type', 'source', 'generated_at'].includes(k))
              .map(([k, v]) => (
                <p key={k}><strong>{k.replace('_', ' ')}:</strong> {Array.isArray(v) ? v.join(' · ') : String(v)}</p>
              ))}
            <p style={s.mutedSmall}>Source: {result.source}</p>
          </div>
        )}
      </div>
    </div>
  );
};

const s: Record<string, React.CSSProperties> = {
  container: { maxWidth: '800px', margin: '0 auto', padding: '2rem' },
  title: { margin: '0 0 0.25rem 0', fontSize: '2rem', color: '#333' },
  subtitle: { margin: '0 0 1.5rem 0', color: '#666' },
  card: { background: 'white', borderRadius: '12px', padding: '1.5rem', boxShadow: '0 2px 8px rgba(0,0,0,0.08)' },
  formRow: { display: 'flex', gap: '0.6rem', marginBottom: '0.75rem', flexWrap: 'wrap' as const },
  select: { padding: '0.55rem 0.75rem', border: '1.5px solid #e0e0e0', borderRadius: '8px', fontSize: '0.9rem', flex: '1 1 200px' },
  textarea: { width: '100%', minHeight: '70px', padding: '0.6rem', border: '1.5px solid #e0e0e0', borderRadius: '8px', fontSize: '0.9rem', marginBottom: '0.75rem', boxSizing: 'border-box' as const, resize: 'vertical' as const },
  primaryBtn: {
    padding: '0.65rem 1.25rem', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', fontSize: '0.9rem',
  },
  errorText: { color: '#ef4444', fontSize: '0.85rem', marginTop: '0.5rem' },
  resultBox: { marginTop: '1.25rem', paddingTop: '1.25rem', borderTop: '1px solid #eee', fontSize: '0.92rem', color: '#444', lineHeight: 1.7 },
  mutedSmall: { color: '#888', fontSize: '0.78rem' },
};
