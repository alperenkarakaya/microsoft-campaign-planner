import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCampaignStore } from '../store/campaignStore';
import { api } from '../lib/api';
import type { Influencer } from '../lib/types';

export const CampaignFormPage = () => {
  const navigate = useNavigate();
  const { createCampaign, isLoading } = useCampaignStore();
  const [influencers, setInfluencers] = useState<Influencer[]>([]);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    influencer_id: '',
    budget: '',
    start_date: '',
  });
  const [error, setError] = useState('');

  useEffect(() => {
    // Influencer listesini yükle
    const fetchInfluencers = async () => {
      try {
        const response = await api.get('/influencers/');
        setInfluencers(response.data);
      } catch (err) {
        console.error('Failed to fetch influencers:', err);
      }
    };
    fetchInfluencers();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!formData.name || !formData.influencer_id || !formData.budget || !formData.start_date) {
      setError('Please fill in all required fields');
      return;
    }

    try {
      await createCampaign({
        name: formData.name,
        description: formData.description || undefined,
        influencer_id: parseInt(formData.influencer_id),
        budget: parseFloat(formData.budget),
        start_date: new Date(formData.start_date).toISOString(),
      });
      navigate('/campaigns');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create campaign');
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>🎯 Create New Campaign</h1>
        <button onClick={() => navigate('/campaigns')} style={styles.backButton}>
          ← Back to Campaigns
        </button>
      </div>

      <form onSubmit={handleSubmit} style={styles.form}>
        {error && <div style={styles.error}>{error}</div>}

        <div style={styles.field}>
          <label style={styles.label}>Campaign Name *</label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            style={styles.input}
            placeholder="Summer 2026 Campaign"
            required
          />
        </div>

        <div style={styles.field}>
          <label style={styles.label}>Description</label>
          <textarea
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            style={{ ...styles.input, ...styles.textarea }}
            placeholder="Campaign details and objectives..."
            rows={4}
          />
        </div>

        <div style={styles.field}>
          <label style={styles.label}>Influencer *</label>
          <select
            value={formData.influencer_id}
            onChange={(e) => setFormData({ ...formData, influencer_id: e.target.value })}
            style={styles.input}
            required
          >
            <option value="">Select an influencer</option>
            {influencers.map((influencer) => (
              <option key={influencer.id} value={influencer.id}>
                {influencer.display_name} (@{influencer.username}) - {influencer.platform}
              </option>
            ))}
          </select>
        </div>

        <div style={styles.row}>
          <div style={styles.field}>
            <label style={styles.label}>Budget ($) *</label>
            <input
              type="number"
              value={formData.budget}
              onChange={(e) => setFormData({ ...formData, budget: e.target.value })}
              style={styles.input}
              placeholder="5000"
              min="0"
              step="0.01"
              required
            />
          </div>

          <div style={styles.field}>
            <label style={styles.label}>Start Date *</label>
            <input
              type="date"
              value={formData.start_date}
              onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
              style={styles.input}
              required
            />
          </div>
        </div>

        <div style={styles.actions}>
          <button
            type="button"
            onClick={() => navigate('/campaigns')}
            style={styles.cancelButton}
          >
            Cancel
          </button>
          <button type="submit" style={styles.submitButton} disabled={isLoading}>
            {isLoading ? 'Creating...' : 'Create Campaign'}
          </button>
        </div>
      </form>
    </div>
  );
};

const styles = {
  container: {
    maxWidth: '800px',
    margin: '0 auto',
    padding: '24px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '32px',
  },
  title: {
    fontSize: '32px',
    fontWeight: '700',
    color: '#1a1a2e',
    margin: 0,
  },
  backButton: {
    padding: '10px 20px',
    background: '#e0e0e0',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '500',
    cursor: 'pointer',
    transition: 'all 0.3s',
  } as React.CSSProperties,
  form: {
    background: 'white',
    borderRadius: '12px',
    padding: '32px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
  error: {
    background: '#fee',
    color: '#c33',
    padding: '12px',
    borderRadius: '8px',
    marginBottom: '20px',
    fontSize: '14px',
  },
  field: {
    marginBottom: '24px',
  },
  label: {
    display: 'block',
    marginBottom: '8px',
    fontSize: '14px',
    fontWeight: '600',
    color: '#333',
  },
  input: {
    width: '100%',
    padding: '12px',
    border: '1px solid #ddd',
    borderRadius: '8px',
    fontSize: '14px',
    fontFamily: 'inherit',
    boxSizing: 'border-box',
  } as React.CSSProperties,
  textarea: {
    resize: 'vertical' as const,
    minHeight: '100px',
  },
  row: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '16px',
  },
  actions: {
    display: 'flex',
    gap: '12px',
    justifyContent: 'flex-end',
    marginTop: '32px',
  },
  cancelButton: {
    padding: '12px 24px',
    background: '#e0e0e0',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.3s',
  } as React.CSSProperties,
  submitButton: {
    padding: '12px 24px',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    transition: 'all 0.3s',
  } as React.CSSProperties,
};
