import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

export const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const { login, isLoading } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React. FormEvent) => {
    e.preventDefault();
    setError('');

    try {
      await login(email, password);
      navigate('/dashboard');
    } catch (err:  any) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map((d: any) => d.msg).join(', '));
      } else {
        setError(detail || 'Login failed');
      }
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>🎯 Login</h1>
        <p style={styles.subtitle}>Welcome back to Influencer ROI Hunter</p>

        {error && <div style={styles.error}>{error}</div>}

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.formGroup}>
            <label style={styles.label}>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={styles.input}
              placeholder="Enter your email"
              required
            />
          </div>

          <div style={styles. formGroup}>
            <label style={styles.label}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={styles.input}
              placeholder="Enter your password"
              required
            />
          </div>

          <button type="submit" style={styles. button} disabled={isLoading}>
            {isLoading ? 'Logging in...' : 'Login'}
          </button>
        </form>

        <p style={styles.footer}>
          Don't have an account? <Link to="/register" style={styles.link}>Register</Link>
        </p>
      </div>
    </div>
  );
};

const styles = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    padding: '2rem',
  },
  card: {
    background: 'white',
    padding: '3rem',
    borderRadius: '15px',
    boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
    maxWidth: '450px',
    width: '100%',
  },
  title: {
    margin: '0 0 0.5rem 0',
    fontSize: '2rem',
    color: '#333',
    textAlign: 'center' as const,
  },
  subtitle: {
    margin: '0 0 2rem 0',
    color:  '#666',
    textAlign: 'center' as const,
    fontSize: '0.9rem',
  },
  error: {
    background: '#fee',
    color: '#c00',
    padding: '0.75rem',
    borderRadius: '5px',
    marginBottom: '1rem',
    fontSize: '0.9rem',
  },
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1.5rem',
  },
  formGroup: {
    display:  'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  label: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#333',
  },
  input: {
    padding:  '0.75rem',
    fontSize: '1rem',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    outline: 'none',
    transition: 'border-color 0.2s',
  },
  button: {
    padding:  '1rem',
    fontSize: '1rem',
    fontWeight: '600',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'transform 0.2s',
  },
  footer: {
    marginTop: '1. 5rem',
    textAlign: 'center' as const,
    color: '#666',
    fontSize: '0.9rem',
  },
  link: {
    color: '#667eea',
    textDecoration: 'none',
    fontWeight: '600',
  },
};