import React from 'react';

interface InlineFieldErrorProps {
  id?: string;
  error?: string | null;
}

export function InlineFieldError({ id, error }: InlineFieldErrorProps) {
  if (!error) return null;

  return (
    <div
      id={id}
      role="alert"
      aria-live="polite"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        color: 'var(--color-text)',
        fontSize: 'var(--text-sm)',
        fontWeight: 500,
        marginTop: 'var(--space-2)',
      }}
    >
      <span aria-hidden="true" style={{ fontSize: '1.1em', display: 'flex', alignItems: 'center' }}>✕</span>
      <span>{error}</span>
    </div>
  );
}
