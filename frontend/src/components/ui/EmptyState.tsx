import React from 'react';

interface EmptyStateProps {
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div 
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-12) var(--space-6)',
        textAlign: 'center',
        background: 'var(--color-bg-subtle)',
        border: '1px dashed var(--color-border)',
        borderRadius: 'var(--radius-md)',
        minHeight: '200px'
      }}
    >
      <div 
        style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          width: '48px',
          height: '48px',
          borderRadius: '50%',
          background: 'var(--color-bg)',
          border: '1px solid var(--color-border)',
          marginBottom: 'var(--space-4)',
          fontSize: '1.5em',
          color: 'var(--color-text-muted)'
        }}
        aria-hidden="true"
      >
        ∅
      </div>
      <h3 style={{ marginBottom: 'var(--space-2)' }}>{title}</h3>
      {description && (
        <div style={{ color: 'var(--color-text-subtle)', marginBottom: action ? 'var(--space-6)' : 0, maxWidth: '400px' }}>
          {description}
        </div>
      )}
      {action && <div>{action}</div>}
    </div>
  );
}
