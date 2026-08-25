import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useCampaignStore } from '../store/campaignStore';
import { campaignsAPI } from '../lib/api';

export const CampaignDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { selectedCampaign, fetchCampaign, updateCampaign, deleteCampaign, isLoading } = useCampaignStore();
  const [isEditing, setIsEditing] = useState(false);
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvFormat, setCsvFormat] = useState<'youtube_studio' | 'shopify_orders' | 'stripe_payouts'>('youtube_studio');
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvMsg, setCsvMsg] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    views: 0,
    likes: 0,
    comments: 0,
    shares: 0,
    clicks: 0,
    conversions: 0,
    revenue: 0,
    status: 'planning',
  });

  useEffect(() => {
    if (id) {
      fetchCampaign(parseInt(id));
    }
  }, [id, fetchCampaign]);

  useEffect(() => {
    if (selectedCampaign) {
      setFormData({
        views: selectedCampaign.views,
        likes: selectedCampaign.likes,
        comments: selectedCampaign.comments,
        shares: selectedCampaign.shares,
        clicks: selectedCampaign.clicks,
        conversions: selectedCampaign.conversions,
        revenue: selectedCampaign.revenue,
        status: selectedCampaign.status,
      });
    }
  }, [selectedCampaign]);

  const handleUpdate = async () => {
    if (!id) return;
    try {
      await updateCampaign(parseInt(id), formData);
      setIsEditing(false);
      await fetchCampaign(parseInt(id));
    } catch (error) {
      console.error('Failed to update campaign:', error);
    }
  };

  const handleCsvImport = async () => {
    if (!id || !csvFile) return;
    setCsvBusy(true);
    setCsvMsg(null);
    try {
      await campaignsAPI.importCsv(parseInt(id), csvFile, csvFormat);
      await fetchCampaign(parseInt(id));
      setCsvMsg('Import successful — metrics and ROI updated from CSV.');
      setCsvFile(null);
    } catch (err: any) {
      setCsvMsg(err.response?.data?.detail || 'Import failed');
    } finally {
      setCsvBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!id) return;
    if (window.confirm('Are you sure you want to delete this campaign?')) {
      try {
        await deleteCampaign(parseInt(id));
        navigate('/campaigns');
      } catch (error) {
        console.error('Failed to delete campaign:', error);
      }
    }
  };

  if (isLoading || !selectedCampaign) {
    return <div style={styles.loading}>Loading campaign...</div>;
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return '#10b981';
      case 'completed': return '#3b82f6';
      case 'planning': return '#f59e0b';
      case 'cancelled': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const getRoiColor = (roi: number) => {
    if (roi > 50) return '#10b981';
    if (roi > 0) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <Link to="/campaigns" style={styles.backLink}>← Back to Campaigns</Link>
          <h1 style={styles.title}>{selectedCampaign.name}</h1>
        </div>
        <div style={styles.actions}>
          <Link to={`/campaigns/${id}/intelligence`} style={styles.aiButton}>
            🤖 AI Campaign Intelligence
          </Link>
          <button onClick={() => setIsEditing(!isEditing)} style={styles.editButton}>
            {isEditing ? 'Cancel' : '✏️ Edit'}
          </button>
          <button onClick={handleDelete} style={styles.deleteButton}>
            🗑️ Delete
          </button>
        </div>
      </div>

      <div style={styles.content}>
        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Campaign Info</h2>
          <div style={styles.infoGrid}>
            <div style={styles.infoItem}>
              <span style={styles.infoLabel}>Status</span>
              {isEditing ? (
                <select
                  value={formData.status}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                  style={styles.select}
                >
                  <option value="planning">Planning</option>
                  <option value="active">Active</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              ) : (
                <span style={{ ...styles.statusBadge, background: getStatusColor(selectedCampaign.status) }}>
                  {selectedCampaign.status}
                </span>
              )}
            </div>
            <div style={styles.infoItem}>
              <span style={styles.infoLabel}>Budget</span>
              <span style={styles.infoValue}>${selectedCampaign.budget.toLocaleString()}</span>
            </div>
            <div style={styles.infoItem}>
              <span style={styles.infoLabel}>Start Date</span>
              <span style={styles.infoValue}>
                {new Date(selectedCampaign.start_date).toLocaleDateString()}
              </span>
            </div>
            {selectedCampaign.description && (
              <div style={styles.infoItem}>
                <span style={styles.infoLabel}>Description</span>
                <span style={styles.infoValue}>{selectedCampaign.description}</span>
              </div>
            )}
          </div>
        </div>

        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Performance Metrics</h2>
          <div style={styles.metricsGrid}>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>Views</span>
              {isEditing ? (
                <input
                  type="number"
                  value={formData.views}
                  onChange={(e) => setFormData({ ...formData, views: parseInt(e.target.value) || 0 })}
                  style={styles.input}
                />
              ) : (
                <span style={styles.metricValue}>{selectedCampaign.views.toLocaleString()}</span>
              )}
            </div>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>Likes</span>
              {isEditing ? (
                <input
                  type="number"
                  value={formData.likes}
                  onChange={(e) => setFormData({ ...formData, likes: parseInt(e.target.value) || 0 })}
                  style={styles.input}
                />
              ) : (
                <span style={styles.metricValue}>{selectedCampaign.likes.toLocaleString()}</span>
              )}
            </div>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>Comments</span>
              {isEditing ? (
                <input
                  type="number"
                  value={formData.comments}
                  onChange={(e) => setFormData({ ...formData, comments: parseInt(e.target.value) || 0 })}
                  style={styles.input}
                />
              ) : (
                <span style={styles.metricValue}>{selectedCampaign.comments.toLocaleString()}</span>
              )}
            </div>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>Shares</span>
              {isEditing ? (
                <input
                  type="number"
                  value={formData.shares}
                  onChange={(e) => setFormData({ ...formData, shares: parseInt(e.target.value) || 0 })}
                  style={styles.input}
                />
              ) : (
                <span style={styles.metricValue}>{selectedCampaign.shares.toLocaleString()}</span>
              )}
            </div>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>Clicks</span>
              {isEditing ? (
                <input
                  type="number"
                  value={formData.clicks}
                  onChange={(e) => setFormData({ ...formData, clicks: parseInt(e.target.value) || 0 })}
                  style={styles.input}
                />
              ) : (
                <span style={styles.metricValue}>{selectedCampaign.clicks.toLocaleString()}</span>
              )}
            </div>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>Conversions</span>
              {isEditing ? (
                <input
                  type="number"
                  value={formData.conversions}
                  onChange={(e) => setFormData({ ...formData, conversions: parseInt(e.target.value) || 0 })}
                  style={styles.input}
                />
              ) : (
                <span style={styles.metricValue}>{selectedCampaign.conversions.toLocaleString()}</span>
              )}
            </div>
          </div>
        </div>

        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Financial Performance</h2>
          <div style={styles.financialGrid}>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>Revenue</span>
              {isEditing ? (
                <input
                  type="number"
                  value={formData.revenue}
                  onChange={(e) => setFormData({ ...formData, revenue: parseFloat(e.target.value) || 0 })}
                  style={styles.input}
                  step="0.01"
                />
              ) : (
                <span style={styles.metricValue}>${selectedCampaign.revenue.toLocaleString()}</span>
              )}
            </div>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>ROI</span>
              <span style={{ ...styles.metricValue, color: getRoiColor(selectedCampaign.roi_percentage) }}>
                {selectedCampaign.roi_percentage.toFixed(2)}%
              </span>
            </div>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>CPM</span>
              <span style={styles.metricValue}>${selectedCampaign.cpm.toFixed(2)}</span>
            </div>
            <div style={styles.metricCard}>
              <span style={styles.metricLabel}>CPC</span>
              <span style={styles.metricValue}>${selectedCampaign.cpc.toFixed(2)}</span>
            </div>
            {selectedCampaign.cpa && (
              <div style={styles.metricCard}>
                <span style={styles.metricLabel}>CPA</span>
                <span style={styles.metricValue}>${selectedCampaign.cpa.toFixed(2)}</span>
              </div>
            )}
          </div>
        </div>

        {isEditing && (
          <button onClick={handleUpdate} style={styles.saveButton} disabled={isLoading}>
            {isLoading ? 'Saving...' : '💾 Save Changes'}
          </button>
        )}

        <div style={styles.section}>
          <h2 style={styles.sectionTitle}>Import Actuals from CSV</h2>
          <p style={{ color: '#666', fontSize: '14px', marginTop: 0 }}>
            Upload a vendor export to overwrite this campaign's measured metrics. Recomputes ROI/CPM/CPC/CPA.
          </p>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              value={csvFormat}
              onChange={(e) => setCsvFormat(e.target.value as any)}
              style={styles.select}
              disabled={csvBusy}
            >
              <option value="youtube_studio">YouTube Studio (views/likes/comments)</option>
              <option value="shopify_orders">Shopify Orders (revenue/conversions)</option>
              <option value="stripe_payouts">Stripe Payouts (revenue)</option>
            </select>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
              disabled={csvBusy}
            />
            <button
              onClick={handleCsvImport}
              disabled={!csvFile || csvBusy}
              style={styles.editButton}
            >
              {csvBusy ? 'Importing...' : '📥 Import'}
            </button>
          </div>
          {csvMsg && <div style={{ marginTop: '12px', color: csvMsg.includes('success') ? '#10b981' : '#ef4444' }}>{csvMsg}</div>}
        </div>
      </div>
    </div>
  );
};

const styles = {
  container: {
    maxWidth: '1200px',
    margin: '0 auto',
    padding: '24px',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: '32px',
  },
  backLink: {
    color: '#667eea',
    textDecoration: 'none',
    fontSize: '14px',
    marginBottom: '8px',
    display: 'inline-block',
  },
  title: {
    fontSize: '32px',
    fontWeight: '700',
    color: '#1a1a2e',
    margin: 0,
  },
  actions: {
    display: 'flex',
    gap: '12px',
  },
  editButton: {
    padding: '10px 20px',
    background: '#667eea',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
  } as React.CSSProperties,
  aiButton: {
    padding: '10px 20px',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
    textDecoration: 'none',
    display: 'inline-flex',
    alignItems: 'center',
  } as React.CSSProperties,
  deleteButton: {
    padding: '10px 20px',
    background: '#ef4444',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: '600',
    cursor: 'pointer',
  } as React.CSSProperties,
  loading: {
    textAlign: 'center',
    padding: '60px',
    fontSize: '18px',
    color: '#666',
  } as React.CSSProperties,
  content: {
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
  } as React.CSSProperties,
  section: {
    background: 'white',
    borderRadius: '12px',
    padding: '24px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
  sectionTitle: {
    fontSize: '20px',
    fontWeight: '600',
    color: '#1a1a2e',
    marginBottom: '20px',
  },
  infoGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '16px',
  },
  infoItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  } as React.CSSProperties,
  infoLabel: {
    fontSize: '12px',
    color: '#666',
    fontWeight: '500',
  },
  infoValue: {
    fontSize: '16px',
    color: '#1a1a2e',
    fontWeight: '600',
  },
  statusBadge: {
    display: 'inline-block',
    padding: '4px 12px',
    borderRadius: '12px',
    color: 'white',
    fontSize: '12px',
    fontWeight: '600',
    textTransform: 'capitalize',
    width: 'fit-content',
  } as React.CSSProperties,
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
    gap: '16px',
  },
  financialGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '16px',
  },
  metricCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    padding: '16px',
    background: '#f8f9fa',
    borderRadius: '8px',
  } as React.CSSProperties,
  metricLabel: {
    fontSize: '12px',
    color: '#666',
    fontWeight: '500',
  },
  metricValue: {
    fontSize: '24px',
    color: '#1a1a2e',
    fontWeight: '700',
  },
  input: {
    padding: '8px',
    border: '1px solid #ddd',
    borderRadius: '6px',
    fontSize: '16px',
    fontWeight: '600',
  },
  select: {
    padding: '8px',
    border: '1px solid #ddd',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: '600',
    width: 'fit-content',
    textTransform: 'capitalize',
  } as React.CSSProperties,
  saveButton: {
    padding: '12px 32px',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '16px',
    fontWeight: '600',
    cursor: 'pointer',
    alignSelf: 'flex-end',
  } as React.CSSProperties,
};
