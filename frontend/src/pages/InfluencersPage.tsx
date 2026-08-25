import { useEffect, useState } from 'react';
import { influencersAPI } from '../lib/api';
import { InfluencerCard } from '../components/InfluencerCard';
import type { Influencer } from '../lib/types';

export const InfluencersPage = () => {
  const [influencers, setInfluencers] = useState<Influencer[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [youtubeChannelId, setYoutubeChannelId] = useState('');
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchInfluencers();
  }, []);

  const fetchInfluencers = async () => {
    try {
      const data = await influencersAPI. list();
      setInfluencers(data);
    } catch (error) {
      console.error('Failed to fetch influencers:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleFetchYouTube = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setFetching(true);

    try {
      await influencersAPI.fetchYouTube(youtubeChannelId);
      setShowAddModal(false);
      setYoutubeChannelId('');
      await fetchInfluencers();
    } catch (err:  any) {
      setError(err.response?.data?.detail || 'Failed to fetch YouTube channel');
    } finally {
      setFetching(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>👥 Influencers</h1>
          <p style={styles.subtitle}>Manage your influencer network</p>
        </div>
        <button onClick={() => setShowAddModal(true)} style={styles.addButton}>
          + Add YouTube Channel
        </button>
      </div>

      {loading ?  (
        <div style={styles.loading}>Loading influencers... </div>
      ) : influencers.length === 0 ? (
        <div style={styles.empty}>
          <p>No influencers found</p>
          <button onClick={() => setShowAddModal(true)} style={styles.emptyButton}>
            Add your first influencer
          </button>
        </div>
      ) : (
        <div style={styles.grid}>
          {influencers.map((influencer) => (
            <InfluencerCard key={influencer. id} influencer={influencer} />
          ))}
        </div>
      )}

      {showAddModal && (
        <div style={styles.modalOverlay} onClick={() => setShowAddModal(false)}>
          <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h2 style={styles.modalTitle}>Add YouTube Channel</h2>
            <p style={styles.modalSubtitle}>
              Enter a YouTube channel ID to fetch and analyze
            </p>

            {error && <div style={styles.error}>{error}</div>}

            <form onSubmit={handleFetchYouTube} style={styles.form}>
              <div style={styles.formGroup}>
                <label style={styles.label}>YouTube Channel ID</label>
                <input
                  type="text"
                  value={youtubeChannelId}
                  onChange={(e) => setYoutubeChannelId(e.target.value)}
                  style={styles.input}
                  placeholder="UC..."
                  required
                />
                <small style={styles.hint}>
                  Find it in the channel URL or About page
                </small>
              </div>

              <div style={styles.modalActions}>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  style={styles.cancelButton}
                >
                  Cancel
                </button>
                <button type="submit" style={styles.submitButton} disabled={fetching}>
                  {fetching ? 'Fetching...' : 'Fetch & Add'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

const styles = {
  container:  {
    maxWidth: '1200px',
    margin: '0 auto',
    padding:  '2rem',
  },
  header: {
    display:  'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '2rem',
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
  addButton:  {
    padding: '0.75rem 1.5rem',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius:  '8px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'transform 0.2s',
  },
  loading: {
    textAlign: 'center' as const,
    padding: '4rem',
    color: '#666',
  },
  empty: {
    textAlign: 'center' as const,
    padding: '4rem',
    background: 'white',
    borderRadius: '10px',
  },
  emptyButton: {
    marginTop: '1rem',
    padding: '0.75rem 1.5rem',
    background: '#667eea',
    color:  'white',
    border:  'none',
    borderRadius:  '8px',
    fontWeight: '600',
    cursor:  'pointer',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
    gap: '1.5rem',
  },
  modalOverlay: {
    position: 'fixed' as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(0,0,0,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
  modal:  {
    background: 'white',
    padding: '2rem',
    borderRadius: '15px',
    maxWidth: '500px',
    width: '90%',
    boxShadow: '0 10px 40px rgba(0,0,0,0.3)',
  },
  modalTitle: {
    margin: '0 0 0.5rem 0',
    fontSize: '1.5rem',
    color: '#333',
  },
  modalSubtitle: {
    margin: '0 0 1.5rem 0',
    color: '#666',
    fontSize:  '0.9rem',
  },
  error: {
    background: '#fee',
    color: '#c00',
    padding: '0.75rem',
    borderRadius:  '5px',
    marginBottom: '1rem',
    fontSize: '0.9rem',
  },
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1.5rem',
  },
  formGroup: {
    display:  'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  label: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#333',
  },
  input: {
    padding:  '0.75rem',
    fontSize: '1rem',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    outline: 'none',
  },
  hint: {
    fontSize: '0.8rem',
    color: '#999',
  },
  modalActions: {
    display: 'flex',
    gap: '1rem',
    justifyContent: 'flex-end',
  },
  cancelButton: {
    padding:  '0.75rem 1.5rem',
    background: '#e0e0e0',
    border: 'none',
    borderRadius: '8px',
    fontWeight: '600',
    cursor: 'pointer',
  },
  submitButton: {
    padding: '0.75rem 1.5rem',
    background: '#667eea',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontWeight: '600',
    cursor: 'pointer',
  },
};