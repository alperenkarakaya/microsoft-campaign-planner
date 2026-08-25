import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useCampaignStore } from '../store/campaignStore';
import { CampaignCard } from '../components/CampaignCard';

export const CampaignsPage = () => {
  const { campaigns, fetchCampaigns, isLoading } = useCampaignStore();
  const [filter, setFilter] = useState<string>('');

  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  const filteredCampaigns = filter
    ? campaigns.filter((c) => c.status === filter)
    : campaigns;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>📋 Campaigns</h1>
          <p style={styles.subtitle}>Manage your influencer campaigns</p>
        </div>
        <Link to="/campaigns/new" style={styles.createButton}>
          + New Campaign
        </Link>
      </div>

      <div style={styles.filters}>
        <button
          onClick={() => setFilter('')}
          style={{... styles.filterButton, ...(filter === '' ?  styles.filterActive : {})}}
        >
          All
        </button>
        <button
          onClick={() => setFilter('planning')}
          style={{...styles.filterButton, ...(filter === 'planning' ? styles.filterActive : {})}}
        >
          Planning
        </button>
        <button
          onClick={() => setFilter('active')}
          style={{...styles.filterButton, ...(filter === 'active' ? styles.filterActive : {})}}
        >
          Active
        </button>
        <button
          onClick={() => setFilter('completed')}
          style={{...styles.filterButton, ...(filter === 'completed' ? styles.filterActive : {})}}
        >
          Completed
        </button>
      </div>

      {isLoading ? (
        <div style={styles.loading}>Loading campaigns...</div>
      ) : filteredCampaigns.length === 0 ? (
        <div style={styles.empty}>
          <p>No campaigns found</p>
          <Link to="/campaigns/new" style={styles. emptyLink}>
            Create your first campaign
          </Link>
        </div>
      ) : (
        <div style={styles.grid}>
          {filteredCampaigns.map((campaign) => (
            <CampaignCard key={campaign.id} campaign={campaign} />
          ))}
        </div>
      )}
    </div>
  );
};

const styles = {
  container: {
    maxWidth: '1200px',
    margin:  '0 auto',
    padding: '2rem',
  },
  header: {
    display: 'flex',
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
  createButton: {
    padding: '0.75rem 1.5rem',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    textDecoration: 'none',
    borderRadius: '8px',
    fontWeight: '600',
    transition: 'transform 0.2s',
  },
  filters: {
    display: 'flex',
    gap: '1rem',
    marginBottom: '2rem',
  },
  filterButton: {
    padding: '0.5rem 1rem',
    background: 'white',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'all 0.2s',
    fontWeight: '500',
  },
  filterActive: {
    background: '#667eea',
    color: 'white',
    borderColor: '#667eea',
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
  emptyLink: {
    display: 'inline-block',
    marginTop:  '1rem',
    color: '#667eea',
    textDecoration: 'none',
    fontWeight: '600',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
    gap: '1.5rem',
  },
};