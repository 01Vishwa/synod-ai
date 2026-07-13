import React from 'react';

interface InlineFieldSuccessProps {
  id?: string;
  message?: string | null;
}

export function InlineFieldSuccess({ id, message }: InlineFieldSuccessProps) {
  if (!message) return null;

  return (
    <div
      id={id}
      role="status"
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
      <span aria-hidden="true" style={{ fontSize: '1.1em', display: 'flex', alignItems: 'center' }}>✓</span>
      <span>{message}</span>
    </div>
  );
}
