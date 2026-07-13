import React from 'react';

interface RetryPanelProps {
  message: React.ReactNode;
  onRetry?: () => void;
  isRetrying?: boolean;
  retryText?: string;
  retryingText?: string;
}

export function RetryPanel({ 
  message, 
  onRetry, 
  isRetrying = false, 
  retryText = 'Try again',
  retryingText = 'Retrying…' 
}: RetryPanelProps) {
  return (
    <div
      role="alert"
      style={{
        border: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        padding: 'var(--space-4)',
        borderRadius: 'var(--radius-sm)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 'var(--space-4)',
        marginBottom: 'var(--space-4)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
        <span aria-hidden="true" style={{ fontSize: '1.2em' }}>↻</span>
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
          {isRetrying ? retryingText : message}
        </span>
      </div>
      {onRetry && (
        <button 
          onClick={onRetry} 
          disabled={isRetrying}
          className="btn-secondary btn-sm"
          style={{ whiteSpace: 'nowrap' }}
        >
          {isRetrying ? 'Please wait' : retryText}
        </button>
      )}
    </div>
  );
}
