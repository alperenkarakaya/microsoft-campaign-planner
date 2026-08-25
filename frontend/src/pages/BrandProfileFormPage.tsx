import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { brandsAPI } from '../lib/api';

export const BrandProfileFormPage = () => {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    name: '',
    aggressive_score: 5,
    creative_score: 5,
    humorous_score: 5,
    professional_score: 5,
    edgy_score: 5,
    target_age_min: 18,
    target_age_max: 45,
    target_gender: 'all',
    target_countries: ['US'],
    min_followers: 10000,
    max_followers: 1000000,
    preferred_categories: [] as string[],
    budget_range_min: 0,
    budget_range_max: 0,
    target_aov: 0,
  });
  const [categoryInput, setCategoryInput] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSliderChange = (field: string, value: number) => {
    setFormData({ ...formData, [field]: value });
  };

  const addCategory = () => {
    if (categoryInput.trim() && !formData.preferred_categories.includes(categoryInput.trim())) {
      setFormData({
        ...formData,
        preferred_categories: [...formData. preferred_categories, categoryInput.trim()],
      });
      setCategoryInput('');
    }
  };

  const removeCategory = (category: string) => {
    setFormData({
      ...formData,
      preferred_categories: formData.preferred_categories.filter((c) => c !== category),
    });
  };

  const handleSubmit = async (e:  React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    if (!formData.name) {
      setError('Brand name is required');
      setLoading(false);
      return;
    }

    try {
      await brandsAPI.createProfile(formData);
      navigate('/brands');
    } catch (err: any) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;
      if (err.code === 'ECONNABORTED' || /timeout/i.test(err.message || '')) {
        setError('Request timed out. The backend is slow or offline — please retry.');
      } else if (status === 503) {
        setError(detail || 'Service is temporarily unavailable. Please try again in a moment.');
      } else if (status >= 500) {
        setError(detail || 'Server error. Please retry; if it persists check the backend logs.');
      } else {
        setError(detail || 'Failed to create brand profile');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles. container}>
      <div style={styles.header}>
        <h1 style={styles. title}>🎯 Create Brand Profile</h1>
        <button onClick={() => navigate('/brands')} style={styles.backButton}>
          ← Back
        </button>
      </div>

      <form onSubmit={handleSubmit} style={styles.form}>
        {error && <div style={styles.error}>{error}</div>}

        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Basic Information</h2>
          
          <div style={styles.field}>
            <label style={styles.label}>Brand Name *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              style={styles.input}
              placeholder="e.g., RedBull, Nike, Netflix"
              required
            />
          </div>
        </div>

        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Brand Personality (0-10)</h2>
          <p style={styles.sectionSubtitle}>
            Adjust sliders to define your brand's personality traits
          </p>

          {[
            { key: 'aggressive_score', label: '🔥 Aggressive', color: '#ef4444', desc: 'Bold, assertive, intense' },
            { key: 'creative_score', label: '✨ Creative', color: '#8b5cf6', desc:  'Innovative, artistic, unique' },
            { key: 'humorous_score', label:  '😂 Humorous', color: '#f59e0b', desc: 'Funny, entertaining, lighthearted' },
            { key: 'professional_score', label: '💼 Professional', color: '#3b82f6', desc: 'Serious, corporate, polished' },
            { key:  'edgy_score', label: '⚡ Edgy', color: '#ec4899', desc: 'Provocative, controversial, cutting-edge' },
          ].map(({ key, label, color, desc }) => (
            <div key={key} style={styles.sliderField}>
              <div style={styles.sliderHeader}>
                <label style={styles.sliderLabel}>{label}</label>
                <span style={{ ... styles.sliderValue, color }}>{formData[key as keyof typeof formData]}/10</span>
              </div>
              <p style={styles.sliderDesc}>{desc}</p>
              <input
                type="range"
                min="0"
                max="10"
                step="0.5"
                value={formData[key as keyof typeof formData]}
                onChange={(e) => handleSliderChange(key, parseFloat(e.target.value))}
                style={{ ...styles.slider, background: `linear-gradient(to right, ${color} 0%, ${color} ${(formData[key as keyof typeof formData] as number) * 10}%, #e0e0e0 ${(formData[key as keyof typeof formData] as number) * 10}%, #e0e0e0 100%)` }}
              />
            </div>
          ))}
        </div>

        <div style={styles.section}>
          <h2 style={styles. sectionTitle}>Target Audience</h2>
          
          <div style={styles.row}>
            <div style={styles.field}>
              <label style={styles.label}>Age Range</label>
              <div style={styles.row}>
                <input
                  type="number"
                  value={formData.target_age_min}
                  onChange={(e) => setFormData({ ...formData, target_age_min: parseInt(e.target.value) })}
                  style={{ ... styles.input, width: '100px' }}
                  min="13"
                  max="100"
                />
                <span style={styles. separator}>to</span>
                <input
                  type="number"
                  value={formData.target_age_max}
                  onChange={(e) => setFormData({ ...formData, target_age_max: parseInt(e.target. value) })}
                  style={{ ...styles.input, width: '100px' }}
                  min="13"
                  max="100"
                />
              </div>
            </div>

            <div style={styles.field}>
              <label style={styles.label}>Gender</label>
              <select
                value={formData.target_gender}
                onChange={(e) => setFormData({ ...formData, target_gender: e.target.value })}
                style={styles.input}
              >
                <option value="all">All</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
            </div>
          </div>
        </div>

        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Influencer Criteria</h2>
          
          <div style={styles.field}>
            <label style={styles.label}>Follower Range</label>
            <div style={styles.row}>
              <input
                type="number"
                value={formData.min_followers}
                onChange={(e) => setFormData({ ...formData, min_followers: parseInt(e.target.value) })}
                style={styles.input}
                placeholder="Min"
              />
              <span style={styles.separator}>to</span>
              <input
                type="number"
                value={formData.max_followers}
                onChange={(e) => setFormData({ ...formData, max_followers: parseInt(e.target.value) })}
                style={styles.input}
                placeholder="Max"
              />
            </div>
          </div>

          <div style={styles.field}>
            <label style={styles.label}>Average Order Value (USD)</label>
            <input
              type="number"
              step="0.01"
              value={formData.target_aov}
              onChange={(e) => setFormData({ ...formData, target_aov: parseFloat(e.target.value) || 0 })}
              style={styles.input}
              placeholder="e.g., 49.99"
            />
            <small style={{ display: 'block', marginTop: '0.5rem', fontSize: '0.85rem', color: '#666' }}>
              Powers revenue and ROI predictions. Without it, only reach and cost ranges are shown.
            </small>
          </div>

          <div style={styles. field}>
            <label style={styles.label}>Preferred Categories</label>
            <div style={styles.categoryInput}>
              <input
                type="text"
                value={categoryInput}
                onChange={(e) => setCategoryInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addCategory())}
                style={{ ...styles.input, marginBottom: 0 }}
                placeholder="e.g., Gaming, Tech, Comedy"
              />
              <button type="button" onClick={addCategory} style={styles.addButton}>
                + Add
              </button>
            </div>
            <div style={styles.categoryList}>
              {formData.preferred_categories.map((cat) => (
                <span key={cat} style={styles. categoryTag}>
                  {cat}
                  <button type="button" onClick={() => removeCategory(cat)} style={styles.removeTag}>
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
        </div>

        <button
          type="submit"
          style={{
            ...styles.submitButton,
            ...(loading ? { opacity: 0.6, cursor: 'not-allowed' } : {}),
          }}
          disabled={loading}
        >
          {loading ? '⏳ Creating...' : '✨ Create Brand Profile'}
        </button>
      </form>
    </div>
  );
};

const styles = {
  container: {
    maxWidth: '800px',
    margin: '0 auto',
    padding: '2rem',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '2rem',
  },
  title: {
    margin: 0,
    fontSize: '2rem',
    color: '#333',
  },
  backButton:  {
    padding: '0.5rem 1rem',
    background: '#e0e0e0',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    fontWeight: '500',
  },
  form: {
    background: 'white',
    padding: '2rem',
    borderRadius: '15px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
  },
  error: {
    background: '#fee',
    color: '#c00',
    padding: '1rem',
    borderRadius: '8px',
    marginBottom: '1.5rem',
  },
  section: {
    marginBottom:  '2.5rem',
  },
  sectionTitle: {
    margin: '0 0 0.5rem 0',
    fontSize: '1.25rem',
    color: '#333',
  },
  sectionSubtitle: {
    margin: '0 0 1.5rem 0',
    fontSize: '0.9rem',
    color: '#666',
  },
  field: {
    marginBottom: '1.5rem',
  },
  label: {
    display: 'block',
    marginBottom:  '0.5rem',
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#333',
  },
  input: {
    width: '100%',
    padding: '0.75rem',
    fontSize: '1rem',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    outline: 'none',
  },
  row: {
    display: 'flex',
    gap: '1rem',
    alignItems: 'center',
  },
  separator: {
    color: '#999',
    fontWeight: '500',
  },
  sliderField: {
    marginBottom: '2rem',
  },
  sliderHeader: {
    display:  'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '0.25rem',
  },
  sliderLabel: {
    fontSize:  '1rem',
    fontWeight: '600',
    color: '#333',
  },
  sliderValue: {
    fontSize: '1.1rem',
    fontWeight: 'bold',
  },
  sliderDesc: {
    margin: '0 0 0.75rem 0',
    fontSize: '0.85rem',
    color: '#999',
  },
  slider:  {
    width: '100%',
    height: '8px',
    borderRadius: '4px',
    outline: 'none',
    appearance: 'none' as const,
    cursor: 'pointer',
  },
  categoryInput: {
    display: 'flex',
    gap: '0.5rem',
    marginBottom: '1rem',
  },
  addButton: {
    padding: '0.75rem 1.5rem',
    background: '#667eea',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    fontWeight: '600',
    whiteSpace: 'nowrap' as const,
  },
  categoryList: {
    display:  'flex',
    flexWrap: 'wrap' as const,
    gap: '0.5rem',
  },
  categoryTag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '0.5rem',
    padding: '0.5rem 1rem',
    background: '#f0f0f0',
    borderRadius: '20px',
    fontSize: '0.9rem',
    color: '#333',
  },
  removeTag: {
    background: 'none',
    border: 'none',
    fontSize: '1. 25rem',
    color: '#999',
    cursor: 'pointer',
    padding: 0,
    lineHeight: 1,
  },
  submitButton: {
    width: '100%',
    padding: '1rem',
    fontSize: '1.1rem',
    fontWeight: '600',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'transform 0.2s',
  },
};