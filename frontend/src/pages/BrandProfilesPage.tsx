import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { brandsAPI } from '../lib/api';
import type { BrandProfile } from '../lib/types';

export const BrandProfilesPage = () => {
  const [profiles, setProfiles] = useState<BrandProfile[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProfiles();
  }, []);

  const fetchProfiles = async () => {
    try {
      const data = await brandsAPI.listProfiles();
      setProfiles(data);
    } catch (error) {
      console.error('Failed to fetch brand profiles:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>🎯 Brand Profiles</h1>
          <p style={styles.subtitle}>Create brand profiles to discover matching influencers</p>
        </div>
        <Link to="/brands/new" style={styles.createButton}>
          + New Brand Profile
        </Link>
      </div>

      {loading ? (
        <div style={styles.loading}>Loading profiles...</div>
      ) : profiles.length === 0 ? (
        <div style={styles. empty}>
          <p>No brand profiles yet</p>
          <Link to="/brands/new" style={styles. emptyLink}>
            Create your first brand profile
          </Link>
        </div>
      ) : (
        <div style={styles.grid}>
          {profiles.map((profile) => (
            <div key={profile. id} style={styles.card}>
              <h3 style={styles.cardTitle}>{profile.name}</h3>
              
              <div style={styles.scores}>
                <div style={styles.scoreItem}>
                  <span style={styles.scoreLabel}>🔥 Aggressive</span>
                  <div style={styles.scoreBar}>
                    <div style={{ ... styles.scoreBarFill, width: `${profile.aggressive_score * 10}%`, background: '#ef4444' }} />
                  </div>
                  <span style={styles.scoreValue}>{profile.aggressive_score}/10</span>
                </div>
                
                <div style={styles.scoreItem}>
                  <span style={styles.scoreLabel}>✨ Creative</span>
                  <div style={styles.scoreBar}>
                    <div style={{ ...styles.scoreBarFill, width: `${profile.creative_score * 10}%`, background: '#8b5cf6' }} />
                  </div>
                  <span style={styles.scoreValue}>{profile.creative_score}/10</span>
                </div>
                
                <div style={styles.scoreItem}>
                  <span style={styles.scoreLabel}>😂 Humorous</span>
                  <div style={styles. scoreBar}>
                    <div style={{ ...styles.scoreBarFill, width: `${profile.humorous_score * 10}%`, background: '#f59e0b' }} />
                  </div>
                  <span style={styles.scoreValue}>{profile.humorous_score}/10</span>
                </div>
                
                <div style={styles.scoreItem}>
                  <span style={styles. scoreLabel}>💼 Professional</span>
                  <div style={styles.scoreBar}>
                    <div style={{ ...styles.scoreBarFill, width: `${profile.professional_score * 10}%`, background: '#3b82f6' }} />
                  </div>
                  <span style={styles.scoreValue}>{profile.professional_score}/10</span>
                </div>
                
                <div style={styles. scoreItem}>
                  <span style={styles.scoreLabel}>⚡ Edgy</span>
                  <div style={styles.scoreBar}>
                    <div style={{ ...styles.scoreBarFill, width: `${profile.edgy_score * 10}%`, background: '#ec4899' }} />
                  </div>
                  <span style={styles.scoreValue}>{profile.edgy_score}/10</span>
                </div>
              </div>

              <div style={styles.info}>
                <p style={styles.infoItem}>
                  👥 Target:  {profile.target_age_min}-{profile.target_age_max} years
                </p>
                <p style={styles.infoItem}>
                  📊 Followers: {profile.min_followers. toLocaleString()} - {profile.max_followers.toLocaleString()}
                </p>
                {profile.preferred_categories.length > 0 && (
                  <p style={styles.infoItem}>
                    🏷️ Categories: {profile.preferred_categories.join(', ')}
                  </p>
                )}
              </div>

              <Link to={`/brands/${profile.id}/discover`} style={styles.discoverButton}>
                🔍 Discover Influencers
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const styles = {
  container: {
    maxWidth:  '1200px',
    margin: '0 auto',
    padding: '2rem',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom:  '2rem',
  },
  title: {
    margin: '0 0 0.5rem 0',
    fontSize: '2.5rem',
    color: '#333',
  },
  subtitle:  {
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
    color:  '#667eea',
    textDecoration: 'none',
    fontWeight: '600',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))',
    gap: '2rem',
  },
  card: {
    background: 'white',
    padding: '2rem',
    borderRadius: '15px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
  },
  cardTitle: {
    margin: '0 0 1.5rem 0',
    fontSize: '1.5rem',
    color: '#333',
  },
  scores: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1rem',
    marginBottom: '1. 5rem',
  },
  scoreItem: {
    display:  'flex',
    alignItems: 'center',
    gap: '0.75rem',
  },
  scoreLabel: {
    width: '130px',
    fontSize: '0.85rem',
    fontWeight: '500',
    color: '#666',
  },
  scoreBar: {
    flex: 1,
    height:  '8px',
    background: '#e0e0e0',
    borderRadius: '4px',
    overflow: 'hidden',
  },
  scoreBarFill:  {
    height: '100%',
    transition: 'width 0.3s ease',
  },
  scoreValue: {
    width: '40px',
    textAlign: 'right' as const,
    fontSize: '0.85rem',
    fontWeight: '600',
    color: '#333',
  },
  info: {
    padding: '1rem 0',
    borderTop: '1px solid #eee',
    borderBottom: '1px solid #eee',
    marginBottom: '1.5rem',
  },
  infoItem:  {
    margin: '0.5rem 0',
    fontSize: '0.9rem',
    color: '#666',
  },
  discoverButton: {
    display: 'block',
    textAlign: 'center' as const,
    padding: '0.75rem',
    background: '#667eea',
    color: 'white',
    textDecoration: 'none',
    borderRadius: '8px',
    fontWeight: '600',
    transition: 'background 0.2s',
  },
};