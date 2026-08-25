import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

export const RegisterPage = () => {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const { register, isLoading } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    try {
      await register(email, username, password);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed');
    }
  };

  return (
    <div style={styles. container}>
      <div style={styles.card}>
        <h1 style={styles.title}>🎯 Register</h1>
        <p style={styles.subtitle}>Create your Influencer ROI Hunter account</p>

        {error && <div style={styles.error}>{error}</div>}

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={styles.formGroup}>
            <label style={styles.label}>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target. value)}
              style={styles. input}
              placeholder="your@email.com"
              required
            />
          </div>

          <div style={styles. formGroup}>
            <label style={styles.label}>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={styles.input}
              placeholder="Choose a username"
              required
            />
          </div>

          <div style={styles.formGroup}>
            <label style={styles.label}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={styles.input}
              placeholder="Create a strong password"
              required
            />
          </div>

          <div style={styles.formGroup}>
            <label style={styles.label}>Confirm Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              style={styles.input}
              placeholder="Confirm your password"
              required
            />
          </div>

          <button type="submit" style={styles.button} disabled={isLoading}>
            {isLoading ?  'Creating account...' : 'Register'}
          </button>
        </form>

        <p style={styles.footer}>
          Already have an account? <Link to="/login" style={styles.link}>Login</Link>
        </p>
      </div>
    </div>
  );
};

const styles = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems:  'center',
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
    color: '#666',
    textAlign: 'center' as const,
    fontSize: '0.9rem',
  },
  error: {
    background: '#fee',
    color:  '#c00',
    padding:  '0.75rem',
    borderRadius: '5px',
    marginBottom: '1rem',
    fontSize: '0.9rem',
  },
  form: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '1.5rem',
  },
  formGroup:  {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '0.5rem',
  },
  label: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#333',
  },
  input: {
    padding: '0.75rem',
    fontSize: '1rem',
    border: '2px solid #e0e0e0',
    borderRadius: '8px',
    outline: 'none',
    transition: 'border-color 0.2s',
  },
  button: {
    padding: '1rem',
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
    marginTop: '1.5rem',
    textAlign: 'center' as const,
    color: '#666',
    fontSize: '0.9rem',
  },
  link: {
    color:  '#667eea',
    textDecoration: 'none',
    fontWeight: '600',
  },
};