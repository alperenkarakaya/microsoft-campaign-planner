import { useEffect, useState } from 'react';
import { analyticsAPI } from '../lib/api';
import type { CampaignPerformance, InfluencerRanking } from '../lib/types';

export const AnalyticsPage = () => {
  const [performance, setPerformance] = useState<CampaignPerformance | null>(null);
  const [ranking, setRanking] = useState<InfluencerRanking[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAnalytics = async () => {
      try {
        const [perfData, rankData] = await Promise.all([
          analyticsAPI.campaignPerformance(),
          analyticsAPI.influencerRanking(),
        ]);
        setPerformance(perfData);
        setRanking(rankData);
      } catch (error) {
        console.error('Failed to fetch analytics:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAnalytics();
  }, []);

  if (loading) {
    return <div style={styles.loading}>Loading analytics...</div>;
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>📊 Analytics</h1>
        <p style={styles. subtitle}>Deep dive into your campaign performance</p>
      </div>

      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>🏆 Top Performing Campaigns</h2>
        {performance?. top_performers && performance.top_performers.length > 0 ? (
          <div style={styles.table}>
            {performance.top_performers.map((campaign, index) => (
              <div key={campaign.id} style={styles.tableRow}>
                <span style={styles.rank}>#{index + 1}</span>
                <span style={styles. campaignName}>{campaign.name}</span>
                <span style={styles.metric}>
                  Budget: ${campaign.budget.toLocaleString()}
                </span>
                <span style={styles. metric}>
                  Revenue: ${campaign.revenue.toLocaleString()}
                </span>
                <span style={{ ...styles.roi, color: campaign.roi > 0 ? '#10b981' : '#ef4444' }}>
                  ROI: {campaign.roi.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p style={styles.noData}>No campaign data available</p>
        )}
      </div>

      <div style={styles.section}>
        <h2 style={styles. sectionTitle}>📉 Needs Improvement</h2>
        {performance?.worst_performers && performance.worst_performers.length > 0 ? (
          <div style={styles. table}>
            {performance.worst_performers.map((campaign, index) => (
              <div key={campaign.id} style={styles.tableRow}>
                <span style={styles.rank}>#{index + 1}</span>
                <span style={styles.campaignName}>{campaign.name}</span>
                <span style={styles.metric}>
                  Budget: ${campaign.budget.toLocaleString()}
                </span>
                <span style={styles.metric}>
                  Revenue: ${campaign.revenue.toLocaleString()}
                </span>
                <span style={{ ...styles.roi, color: '#ef4444' }}>
                  ROI: {campaign.roi.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p style={styles.noData}>No data available</p>
        )}
      </div>

      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>👥 Influencer Performance Ranking</h2>
        {ranking.length > 0 ?  (
          <div style={styles.influencerGrid}>
            {ranking.map((inf, index) => (
              <div key={inf.influencer_id} style={styles.influencerCard}>
                <div style={styles.influencerHeader}>
                  <span style={styles.influencerRank}>#{index + 1}</span>
                  <div>
                    <h3 style={styles.influencerName}>{inf.display_name}</h3>
                    <p style={styles.influencerUsername}>@{inf.username}</p>
                  </div>
                </div>
                <div style={styles.influencerStats}>
                  <div style={styles.stat}>
                    <span style={styles.statLabel}>Avg ROI</span>
                    <span style={{ ...styles.statValue, color: inf.avg_roi > 0 ? '#10b981' : '#ef4444' }}>
                      {inf.avg_roi.toFixed(1)}%
                    </span>
                  </div>
                  <div style={styles.stat}>
                    <span style={styles.statLabel}>Campaigns</span>
                    <span style={styles.statValue}>{inf. campaign_count}</span>
                  </div>
                  <div style={styles.stat}>
                    <span style={styles.statLabel}>Followers</span>
                    <span style={styles.statValue}>{inf.followers. toLocaleString()}</span>
                  </div>
                  <div style={styles.stat}>
                    <span style={styles.statLabel}>Engagement</span>
                    <span style={styles.statValue}>{inf. engagement_rate.toFixed(2)}%</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p style={styles.noData}>No influencer data available</p>
        )}
      </div>
    </div>
  );
};

const styles = {
  container: {
    maxWidth: '1200px',
    margin:  '0 auto',
    padding: '2rem',
  },
  loading: {
    textAlign: 'center' as const,
    padding: '4rem',
    color: '#666',
  },
  header: {
    marginBottom: '3rem',
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
  section: {
    marginBottom: '3rem',
  },
  sectionTitle: {
    margin: '0 0 1.5rem 0',
    fontSize: '1.5rem',
    color: '#333',
  },
  table:  {
    background: 'white',
    borderRadius: '10px',
    overflow: 'hidden',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
  tableRow: {
    display: 'grid',
    gridTemplateColumns: '50px 1fr auto auto auto',
    gap: '1rem',
    padding: '1rem 1.5rem',
    borderBottom: '1px solid #eee',
    alignItems: 'center',
  },
  rank: {
    fontWeight: 'bold',
    color: '#667eea',
    fontSize: '1.1rem',
  },
  campaignName: {
    fontWeight: '600',
    color: '#333',
  },
  metric: {
    fontSize: '0.9rem',
    color: '#666',
  },
  roi: {
    fontWeight: 'bold',
    fontSize: '1rem',
  },
  noData: {
    textAlign: 'center' as const,
    padding: '2rem',
    background: 'white',
    borderRadius: '10px',
    color: '#999',
  },
  influencerGrid: {
    display:  'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
    gap: '1.5rem',
  },
  influencerCard: {
    background: 'white',
    padding: '1.5rem',
    borderRadius: '10px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
  influencerHeader:  {
    display: 'flex',
    gap: '1rem',
    marginBottom: '1rem',
    alignItems: 'center',
  },
  influencerRank: {
    fontSize: '1.5rem',
    fontWeight: 'bold',
    color: '#667eea',
  },
  influencerName: {
    margin: 0,
    fontSize:  '1.1rem',
    color: '#333',
  },
  influencerUsername: {
    margin: '0.25rem 0 0 0',
    fontSize: '0.85rem',
    color: '#666',
  },
  influencerStats: {
    display: 'grid',
    gridTemplateColumns:  '1fr 1fr',
    gap: '1rem',
    paddingTop: '1rem',
    borderTop: '1px solid #eee',
  },
  stat: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.25rem',
  },
  statLabel: {
    fontSize: '0.75rem',
    color: '#999',
    textTransform: 'uppercase' as const,
  },
  statValue: {
    fontSize:  '1rem',
    fontWeight: 'bold',
    color: '#333',
  },
};