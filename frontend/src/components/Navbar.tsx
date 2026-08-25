import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

export const Navbar = () => {
  const { user, isAuthenticated, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <nav style={styles.nav}>
      <div style={styles.container}>
        <Link to="/" style={styles.logo}>
          🎯 Influencer ROI Hunter
        </Link>

        <div style={styles.menu}>
          {isAuthenticated ? (
            <>
              <Link to="/dashboard" style={styles.link}>Dashboard</Link>
              <Link to="/roster" style={styles.link}>🧠 Roster</Link>
              <Link to="/influencers" style={styles.link}>Influencers</Link>
              <Link to="/campaigns" style={styles.link}>Campaigns</Link>
              <Link to="/analytics" style={styles.link}>Analytics</Link>
              <Link to="/brands" style={styles.link}>🎯 Brand Discovery</Link>
              <Link to="/content-studio" style={styles.link}>🎬 Content Studio</Link>
              <Link to="/assistant" style={styles.link}>💬 Assistant</Link>

              <div style={styles.userSection}>
                <span style={styles.username}>👤 {user?.username}</span>
                <button onClick={handleLogout} style={styles.logoutBtn}>
                  Logout
                </button>
              </div>
            </>
          ) : (
            <>
              <Link to="/login" style={styles.link}>Login</Link>
              <Link to="/register" style={styles.link}>Register</Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
};

const styles = {
  nav: {
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    padding: '1rem 0',
    boxShadow:  '0 2px 10px rgba(0,0,0,0.1)',
  },
  container: {
    maxWidth: '1200px',
    margin: '0 auto',
    padding: '0 2rem',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  logo: {
    fontSize: '1.5rem',
    fontWeight: 'bold',
    color: 'white',
    textDecoration: 'none',
  },
  menu: {
    display: 'flex',
    gap: '2rem',
    alignItems: 'center',
  },
  link: {
    color: 'white',
    textDecoration: 'none',
    fontSize: '1rem',
    transition: 'opacity 0.2s',
  },
  userSection: {
    display: 'flex',
    gap: '1rem',
    alignItems: 'center',
  },
  username: {
    color: 'white',
    fontSize: '0.9rem',
  },
  logoutBtn: {
    padding: '0.5rem 1rem',
    background: 'rgba(255,255,255,0.2)',
    border: '1px solid white',
    borderRadius: '5px',
    color: 'white',
    cursor: 'pointer',
    transition: 'background 0.2s',
  },
};