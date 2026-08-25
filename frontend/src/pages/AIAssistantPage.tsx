import { useState } from 'react';
import { assistantAPI } from '../lib/api';
import type { AssistantQueryResponse } from '../lib/types';

interface Turn {
  query: string;
  response: AssistantQueryResponse | null;
  error: string | null;
}

const SUGGESTIONS = [
  'Who are the best gaming creators in the roster?',
  'Which creators performed best last campaign?',
  'What should we change for the next campaign?',
];

export const AIAssistantPage = () => {
  const [query, setQuery] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  const ask = async (q: string) => {
    if (!q.trim()) return;
    setBusy(true);
    setQuery('');
    try {
      const response = await assistantAPI.query(q);
      setTurns((prev) => [...prev, { query: q, response, error: null }]);
    } catch (e: any) {
      setTurns((prev) => [...prev, { query: q, response: null, error: e.response?.data?.detail || 'Assistant failed to respond.' }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={s.container}>
      <h1 style={s.title}>{'💬'} AI Partnership Assistant</h1>
      <p style={s.subtitle}>
        Ask about creators, campaigns, or performance. Answers are grounded only in data
        stored in this workspace — never fabricated.
      </p>

      {turns.length === 0 && (
        <div style={s.suggestions}>
          {SUGGESTIONS.map((sg) => (
            <button key={sg} onClick={() => ask(sg)} style={s.suggestionBtn}>{sg}</button>
          ))}
        </div>
      )}

      <div style={s.thread}>
        {turns.map((t, idx) => (
          <div key={idx} style={s.turn}>
            <div style={s.queryBubble}>{t.query}</div>
            {t.error && <div style={s.errorBubble}>{t.error}</div>}
            {t.response && (
              <div style={s.answerBubble}>
                <p style={{ margin: 0 }}>{t.response.answer}</p>
                <p style={s.sourceTag}>Source: {t.response.source === 'gemini' ? 'AI' : 'grounded data (no AI configured)'}</p>
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={s.inputRow}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') ask(query); }}
          placeholder="Ask about your creators or campaigns…"
          style={s.input}
          disabled={busy}
        />
        <button onClick={() => ask(query)} disabled={busy || !query.trim()} style={s.sendBtn}>
          {busy ? '…' : 'Send'}
        </button>
      </div>
    </div>
  );
};

const s: Record<string, React.CSSProperties> = {
  container: { maxWidth: '700px', margin: '0 auto', padding: '2rem', display: 'flex', flexDirection: 'column' as const, minHeight: '70vh' },
  title: { margin: '0 0 0.25rem 0', fontSize: '2rem', color: '#333' },
  subtitle: { margin: '0 0 1.5rem 0', color: '#666' },
  suggestions: { display: 'flex', flexDirection: 'column' as const, gap: '0.5rem', marginBottom: '1.5rem' },
  suggestionBtn: {
    textAlign: 'left' as const, padding: '0.75rem 1rem', background: 'white', border: '1.5px solid #e0e0e0',
    borderRadius: '10px', cursor: 'pointer', fontSize: '0.9rem', color: '#555',
  },
  thread: { flex: 1, display: 'flex', flexDirection: 'column' as const, gap: '1rem', marginBottom: '1.5rem' },
  turn: { display: 'flex', flexDirection: 'column' as const, gap: '0.5rem' },
  queryBubble: {
    alignSelf: 'flex-end', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white', padding: '0.65rem 1rem', borderRadius: '14px 14px 2px 14px', maxWidth: '80%', fontSize: '0.9rem',
  },
  answerBubble: {
    alignSelf: 'flex-start', background: 'white', boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    padding: '0.75rem 1rem', borderRadius: '14px 14px 14px 2px', maxWidth: '85%', fontSize: '0.9rem', color: '#333',
  },
  errorBubble: {
    alignSelf: 'flex-start', background: '#fee2e2', color: '#991b1b',
    padding: '0.65rem 1rem', borderRadius: '14px 14px 14px 2px', maxWidth: '85%', fontSize: '0.9rem',
  },
  sourceTag: { margin: '0.4rem 0 0 0', fontSize: '0.72rem', color: '#999' },
  inputRow: { display: 'flex', gap: '0.6rem' },
  input: { flex: 1, padding: '0.75rem 1rem', border: '1.5px solid #e0e0e0', borderRadius: '10px', fontSize: '0.9rem' },
  sendBtn: {
    padding: '0.75rem 1.5rem', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white', border: 'none', borderRadius: '10px', fontWeight: 600, cursor: 'pointer',
  },
};
