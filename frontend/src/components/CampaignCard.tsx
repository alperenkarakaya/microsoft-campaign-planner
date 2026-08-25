import { Link } from 'react-router-dom';
import type { Campaign } from '../lib/types';

interface CampaignCardProps {
  campaign: Campaign;
}

export const CampaignCard = ({ campaign }: CampaignCardProps) => {
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
    <div style={styles.card}>
      <div style={styles.header}>
        <h3 style={styles.title}>{campaign.name}</h3>
        <span style={{ ...styles.status, background: getStatusColor(campaign.status) }}>
          {campaign. status}
        </span>
      </div>

      {campaign.description && (
        <p style={styles.description}>{campaign.description}</p>
      )}

      <div style={styles.metrics}>
        <div style={styles.metric}>
          <span style={styles.metricLabel}>Budget</span>
          <span style={styles.metricValue}>${campaign.budget.toLocaleString()}</span>
        </div>
        <div style={styles.metric}>
          <span style={styles.metricLabel}>Revenue</span>
          <span style={styles.metricValue}>${campaign.revenue.toLocaleString()}</span>
        </div>
        <div style={styles.metric}>
          <span style={styles.metricLabel}>ROI</span>
          <span style={{ ...styles.metricValue, color: getRoiColor(campaign. roi_percentage) }}>
            {campaign.roi_percentage. toFixed(1)}%
          </span>
        </div>
      </div>

      <div style={styles.stats}>
        <div style={styles.stat}>
          <span>👁️ {campaign.views. toLocaleString()}</span>
        </div>
        <div style={styles.stat}>
          <span>👆 {campaign.clicks.toLocaleString()}</span>
        </div>
        <div style={styles.stat}>
          <span>✅ {campaign.conversions. toLocaleString()}</span>
        </div>
      </div>

      <Link to={`/campaigns/${campaign.id}`} style={styles.link}>
        View Details →
      </Link>
    </div>
  );
};

const styles = {
  card:  {
    background: 'white',
    padding: '1.5rem',
    borderRadius:  '10px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    transition: 'transform 0.2s, box-shadow 0.2s',
  },
  header:  {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '1rem',
  },
  title: {
    margin: 0,
    fontSize: '1.25rem',
    color: '#333',
  },
  status: {
    padding: '0.25rem 0.75rem',
    borderRadius: '20px',
    color: 'white',
    fontSize: '0.75rem',
    fontWeight: '600',
    textTransform: 'uppercase' as const,
  },
  description: {
    color: '#666',
    fontSize: '0.9rem',
    marginBottom: '1rem',
  },
  metrics: {
    display: 'grid',
    gridTemplateColumns:  'repeat(3, 1fr)',
    gap: '1rem',
    marginBottom: '1rem',
    padding: '1rem 0',
    borderTop: '1px solid #eee',
    borderBottom: '1px solid #eee',
  },
  metric: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.25rem',
  },
  metricLabel: {
    fontSize:  '0.75rem',
    color: '#999',
    textTransform: 'uppercase' as const,
  },
  metricValue: {
    fontSize:  '1.25rem',
    fontWeight: 'bold',
    color: '#333',
  },
  stats: {
    display: 'flex',
    gap: '1rem',
    marginBottom: '1rem',
  },
  stat: {
    fontSize: '0.9rem',
    color: '#666',
  },
  link: {
    display: 'inline-block',
    color: '#667eea',
    textDecoration: 'none',
    fontWeight: '600',
    fontSize: '0.9rem',
  },
};