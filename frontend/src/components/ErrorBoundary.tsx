import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message?: string;
}

/**
 * Catches render-time errors anywhere in the tree and shows a recoverable
 * fallback instead of a blank white screen. Without this, one unhandled
 * exception in any page unmounts the whole app.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface for debugging; replace with a real logger/Sentry in production.
    console.error('Unhandled UI error:', error, info.componentStack);
  }

  handleReset = () => {
    this.setState({ hasError: false, message: undefined });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={styles.container}>
          <div style={styles.card}>
            <h1 style={styles.title}>Bir şeyler ters gitti</h1>
            <p style={styles.text}>
              Beklenmeyen bir hata oluştu. Sayfayı yenileyebilir veya tekrar
              deneyebilirsiniz.
            </p>
            {this.state.message && <pre style={styles.detail}>{this.state.message}</pre>}
            <div style={styles.actions}>
              <button style={styles.button} onClick={this.handleReset}>Tekrar dene</button>
              <button
                style={{ ...styles.button, ...styles.secondary }}
                onClick={() => window.location.assign('/dashboard')}
              >
                Dashboard'a dön
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: 'calc(100vh - 70px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '2rem',
  },
  card: {
    background: 'white',
    padding: '2.5rem',
    borderRadius: '12px',
    boxShadow: '0 8px 30px rgba(0,0,0,0.12)',
    maxWidth: '520px',
    width: '100%',
    textAlign: 'center',
  },
  title: { margin: '0 0 0.75rem', color: '#333' },
  text: { color: '#666', marginBottom: '1rem' },
  detail: {
    background: '#f7f7f9',
    padding: '0.75rem',
    borderRadius: '6px',
    color: '#c0392b',
    fontSize: '0.8rem',
    overflowX: 'auto',
    textAlign: 'left',
  },
  actions: { display: 'flex', gap: '0.75rem', justifyContent: 'center', marginTop: '1.5rem' },
  button: {
    padding: '0.7rem 1.2rem',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    fontWeight: 600,
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    color: 'white',
  },
  secondary: { background: '#e0e0e0', color: '#333' },
};
