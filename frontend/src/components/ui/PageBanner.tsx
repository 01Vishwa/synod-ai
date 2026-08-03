import React from 'react';

interface PageBannerProps {
  title?: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
}

export function PageBanner({ title, description, children }: PageBannerProps) {
  return (
    <div
      role="alert"
      style={{
        border: '1px solid var(--color-border-strong)',
        borderLeft: '4px solid var(--color-border-strong)',
        background: 'var(--color-surface)',
        color: 'var(--color-text)',
        padding: 'var(--space-4)',
        borderRadius: 'var(--radius-sm)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
        marginBottom: 'var(--space-4)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
        <span aria-hidden="true" style={{ fontSize: '1.2em', fontWeight: 'bold' }}>⚠</span>
        {title && <strong style={{ fontSize: 'var(--text-sm)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{title}</strong>}
      </div>
      {(description || children) && (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
          {description}
          {children}
        </div>
      )}
    </div>
  );
}
