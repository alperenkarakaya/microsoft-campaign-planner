import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { analyticsAPI, rosterAPI } from '../lib/api';
import { StatsCard } from '../components/StatsCard';
import type { DashboardStats, RosterCreator } from '../lib/types';

export const DashboardPage = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [opportunities, setOpportunities] = useState<RosterCreator[]>([]);
  const [avgTrust, setAvgTrust] = useState<number | null>(null);
  const [sTierCount, setSTierCount] = useState(0);
  const [totalCreators, setTotalCreators] = useState(0);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const data = await analyticsAPI.dashboard();
        setStats(data);
      } catch (error) {
        console.error('Failed to fetch dashboard stats:', error);
      } finally {
        setLoading(false);
      }
    };

    const fetchOpportunities = async () => {
      try {
        const roster = await rosterAPI.intelligence({ limit: 200 });
        const creators: RosterCreator[] = roster.creators;
        setTotalCreators(creators.length);
        setSTierCount(creators.filter((c) => c.intelligence.tier === 'S').length);
        const trustScores = creators
          .map((c) => c.intelligence.trust_score)
          .filter((t): t is number => t != null);
        setAvgTrust(trustScores.length > 0 ? trustScores.reduce((a, b) => a + b, 0) / trustScores.length : null);

        // High-trust, reachable, not-yet-flagged-risky creators worth prioritizing.
        const prioritized = creators
          .filter((c) => (c.intelligence.trust_score ?? 0) >= 58 && c.intelligence.readiness.is_reachable)
          .sort((a, b) => (b.intelligence.trust_score ?? 0) - (a.intelligence.trust_score ?? 0))
          .slice(0, 5);
        setOpportunities(prioritized);
      } catch (error) {
        console.error('Failed to fetch roster intelligence:', error);
      }
    };

    fetchStats();
    fetchOpportunities();
  }, []);

  if (loading) {
    return <div style={styles.loading}>Loading dashboard...</div>;
  }

  if (!stats) {
    return <div style={styles.error}>Failed to load dashboard</div>;
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>📊 Dashboard</h1>
        <p style={styles.subtitle}>Overview of your influencer campaigns</p>
      </div>

      <div style={styles. statsGrid}>
        <StatsCard
          title="Total Campaigns"
          value={stats.total_campaigns}
          icon="📋"
          color="#667eea"
          subtitle={`${stats.active_campaigns} active`}
        />
        <StatsCard
          title="Total Budget"
          value={`$${stats.total_budget. toLocaleString()}`}
          icon="💰"
          color="#f59e0b"
        />
        <StatsCard
          title="Total Revenue"
          value={`$${stats.total_revenue.toLocaleString()}`}
          icon="💵"
          color="#10b981"
        />
        <StatsCard
          title="Average ROI"
          value={`${stats.avg_roi_percentage.toFixed(1)}%`}
          icon="📈"
          color={stats.avg_roi_percentage > 0 ? '#10b981' : '#ef4444'}
        />
      </div>

      <div style={styles.metricsGrid}>
        <div style={styles.metricCard}>
          <h3 style={styles.metricTitle}>Performance Metrics</h3>
          <div style={styles.metricList}>
            <div style={styles.metricItem}>
              <span style={styles.metricLabel}>👁️ Total Views</span>
              <span style={styles.metricValue}>{stats.total_views. toLocaleString()}</span>
            </div>
            <div style={styles.metricItem}>
              <span style={styles.metricLabel}>👆 Total Clicks</span>
              <span style={styles.metricValue}>{stats.total_clicks.toLocaleString()}</span>
            </div>
            <div style={styles.metricItem}>
              <span style={styles.metricLabel}>✅ Total Conversions</span>
              <span style={styles.metricValue}>{stats.total_conversions.toLocaleString()}</span>
            </div>
          </div>
        </div>

        <div style={styles.metricCard}>
          <h3 style={styles.metricTitle}>Campaign Status</h3>
          <div style={styles.metricList}>
            <div style={styles. metricItem}>
              <span style={styles.metricLabel}>🟢 Active</span>
              <span style={styles.metricValue}>{stats.active_campaigns}</span>
            </div>
            <div style={styles. metricItem}>
              <span style={styles.metricLabel}>✅ Completed</span>
              <span style={styles.metricValue}>{stats.completed_campaigns}</span>
            </div>
            <div style={styles.metricItem}>
              <span style={styles.metricLabel}>💰 Net Profit</span>
              <span style={{ ...styles.metricValue, color: stats.net_profit > 0 ? '#10b981' : '#ef4444' }}>
                ${stats.net_profit.toLocaleString()}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* AI Opportunities — additive section on top of Creator Intelligence */}
      <div style={styles.aiSection}>
        <h2 style={styles.aiTitle}>🧠 AI Opportunities</h2>
        <div style={styles.statsGrid}>
          <StatsCard title="Total Creators" value={totalCreators} icon="👥" color="#667eea" />
          <StatsCard title="S-Tier Creators" value={sTierCount} icon="🏆" color="#f59e0b" />
          <StatsCard
            title="Average Trust Score"
            value={avgTrust != null ? avgTrust.toFixed(1) : '—'}
            icon="🛡️"
            color="#10b981"
          />
        </div>

        <div style={styles.metricCard}>
          <h3 style={styles.metricTitle}>Top creators to prioritize outreach</h3>
          {opportunities.length === 0 ? (
            <p style={{ color: '#888', margin: 0 }}>
              No high-trust, reachable creators found yet — run enrichment on your roster.
            </p>
          ) : (
            <div style={styles.metricList}>
              {opportunities.map((c) => (
                <Link key={c.influencer_id} to={`/roster/${c.influencer_id}`} style={styles.oppRow}>
                  <span style={styles.metricLabel}>
                    {c.intelligence.tier ?? '-'} · {c.display_name}
                  </span>
                  <span style={styles.metricValue}>
                    {c.intelligence.trust_score != null ? c.intelligence.trust_score.toFixed(1) : '-'}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const styles = {
  container: {
    maxWidth: '1200px',
    margin: '0 auto',
    padding: '2rem',
  },
  loading: {
    textAlign: 'center' as const,
    padding: '4rem',
    fontSize: '1.2rem',
    color: '#666',
  },
  error:  {
    textAlign: 'center' as const,
    padding: '4rem',
    fontSize: '1.2rem',
    color: '#ef4444',
  },
  header: {
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
    fontSize:  '1rem',
  },
  statsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
    gap: '1.5rem',
    marginBottom: '2rem',
  },
  metricsGrid:  {
    display: 'grid',
    gridTemplateColumns:  'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '1.5rem',
  },
  metricCard: {
    background: 'white',
    padding: '1.5rem',
    borderRadius: '10px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  },
  metricTitle: {
    margin: '0 0 1rem 0',
    fontSize:  '1.1rem',
    color: '#333',
  },
  metricList: {
    display: 'flex',
    flexDirection:  'column' as const,
    gap: '1rem',
  },
  metricItem: {
    display:  'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0.75rem',
    background: '#f9fafb',
    borderRadius:  '8px',
  },
  metricLabel: {
    color: '#666',
    fontSize: '0.9rem',
  },
  metricValue: {
    fontWeight: 'bold',
    fontSize: '1.1rem',
    color: '#333',
  },
  aiSection: {
    marginTop: '2rem',
  },
  aiTitle: {
    margin: '0 0 1rem 0',
    fontSize: '1.5rem',
    color: '#333',
  },
  oppRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '0.75rem',
    background: '#f9fafb',
    borderRadius: '8px',
    textDecoration: 'none',
    cursor: 'pointer',
  },
};