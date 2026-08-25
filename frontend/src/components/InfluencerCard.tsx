import type { Influencer } from '../lib/types';

interface InfluencerCardProps {
  influencer: Influencer;
  onSelect?:  () => void;
}

export const InfluencerCard = ({ influencer, onSelect }:  InfluencerCardProps) => {
  const getPlatformIcon = (platform: string) => {
    switch (platform) {
      case 'youtube': return '▶️';
      case 'instagram': return '📷';
      case 'tiktok': return '🎵';
      default: return '👤';
    }
  };

  const getFakeFollowerColor = (percentage: number) => {
    if (percentage < 10) return '#10b981';
    if (percentage < 30) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div style={styles.card} onClick={onSelect}>
      <div style={styles.header}>
        {influencer.avatar_url ?  (
          <img src={influencer.avatar_url} alt={influencer.display_name} style={styles.avatar} />
        ) : (
          <div style={styles.avatarPlaceholder}>{getPlatformIcon(influencer. platform)}</div>
        )}
        
        <div style={styles.info}>
          <div style={styles.nameSection}>
            <h3 style={styles.name}>{influencer.display_name}</h3>
            {influencer.verified && <span style={styles.verified}>✓</span>}
          </div>
          <p style={styles.username}>@{influencer.username}</p>
        </div>
      </div>

      <div style={styles.stats}>
        <div style={styles.stat}>
          <span style={styles.statLabel}>Followers</span>
          <span style={styles.statValue}>
            {influencer.followers_count.toLocaleString()}
          </span>
        </div>
        <div style={styles.stat}>
          <span style={styles.statLabel}>Engagement</span>
          <span style={styles.statValue}>{influencer.engagement_rate. toFixed(2)}%</span>
        </div>
      </div>

      <div style={styles.footer}>
        <span style={styles.platform}>
          {getPlatformIcon(influencer.platform)} {influencer.platform}
        </span>
        <span style={{ ...styles.fakeScore, color: getFakeFollowerColor(influencer.fake_follower_percentage) }}>
          Fake:  {influencer.fake_follower_percentage.toFixed(1)}%
        </span>
      </div>
    </div>
  );
};

const styles = {
  card: {
    background: 'white',
    padding: '1.5rem',
    borderRadius: '10px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    cursor: 'pointer',
    transition: 'transform 0.2s, box-shadow 0.2s',
  },
  header: {
    display: 'flex',
    gap: '1rem',
    marginBottom: '1rem',
  },
  avatar: {
    width: '60px',
    height: '60px',
    borderRadius: '50%',
    objectFit: 'cover' as const,
  },
  avatarPlaceholder: {
    width: '60px',
    height: '60px',
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '2rem',
  },
  info: {
    flex: 1,
  },
  nameSection: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  name: {
    margin: 0,
    fontSize:  '1.1rem',
    color: '#333',
  },
  verified: {
    background: '#3b82f6',
    color: 'white',
    borderRadius: '50%',
    width: '20px',
    height: '20px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '0.75rem',
  },
  username: {
    margin: '0.25rem 0 0 0',
    color: '#666',
    fontSize: '0.9rem',
  },
  stats: {
    display: 'grid',
    gridTemplateColumns:  '1fr 1fr',
    gap: '1rem',
    padding: '1rem 0',
    borderTop: '1px solid #eee',
    borderBottom: '1px solid #eee',
    marginBottom: '1rem',
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
    fontSize: '1.1rem',
    fontWeight: 'bold',
    color: '#333',
  },
  footer: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  platform: {
    fontSize: '0.85rem',
    color: '#666',
    textTransform: 'capitalize' as const,
  },
  fakeScore: {
    fontSize: '0.85rem',
    fontWeight: '600',
  },
};