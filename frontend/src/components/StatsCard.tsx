interface StatsCardProps {
  title: string;
  value: string | number;
  icon: string;
  color?:  string;
  subtitle?: string;
}

export const StatsCard = ({ title, value, icon, color = '#667eea', subtitle }: StatsCardProps) => {
  return (
    <div style={{ ... styles.card, borderLeft: `4px solid ${color}` }}>
      <div style={styles.header}>
        <span style={styles.icon}>{icon}</span>
        <h3 style={styles.title}>{title}</h3>
      </div>
      <div style={styles.value}>{value}</div>
      {subtitle && <div style={styles.subtitle}>{subtitle}</div>}
    </div>
  );
};

const styles = {
  card: {
    background: 'white',
    padding: '1.5rem',
    borderRadius: '10px',
    boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
    transition: 'transform 0.2s',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    marginBottom: '1rem',
  },
  icon: {
    fontSize: '1.5rem',
  },
  title: {
    margin: 0,
    fontSize:  '0.9rem',
    color: '#666',
    fontWeight: '500',
  },
  value: {
    fontSize: '2rem',
    fontWeight: 'bold',
    color: '#333',
    marginBottom: '0.5rem',
  },
  subtitle:  {
    fontSize: '0.85rem',
    color: '#999',
  },
};