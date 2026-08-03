import React from 'react';

interface ErrorPanelProps {
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
}

export function ErrorPanel({ title, description, children }: ErrorPanelProps) {
  return (
    <div
      role="alert"
      style={{
        border: '2px solid var(--color-border-strong)',
        background: 'var(--color-surface)',
        color: 'var(--color-text)',
        padding: 'var(--space-6)',
        borderRadius: 'var(--radius-md)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)',
        marginBottom: 'var(--space-6)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <span aria-hidden="true" style={{ fontSize: '1.5em', fontWeight: 'bold' }}>✕</span>
        <strong 
          style={{ 
            fontSize: 'var(--text-lg)', 
            textTransform: 'uppercase', 
            letterSpacing: '0.05em' 
          }}
        >
          {title}
        </strong>
      </div>
      {(description || children) && (
        <div style={{ fontSize: 'var(--text-base)', opacity: 0.9 }}>
          {description}
          {children && <div style={{ marginTop: 'var(--space-4)' }}>{children}</div>}
        </div>
      )}
    </div>
  );
}
