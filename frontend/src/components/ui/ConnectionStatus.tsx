import React from 'react';

type ConnectionState = 'connected' | 'reconnecting' | 'failed';

interface ConnectionStatusProps {
  status: ConnectionState;
  onRefresh?: () => void;
}

export function ConnectionStatus({ status, onRefresh }: ConnectionStatusProps) {
  if (status === 'connected') return null;

  if (status === 'reconnecting') {
    return (
      <div 
        role="status" 
        aria-live="polite"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: 'var(--space-1) var(--space-3)',
          background: 'var(--grey-93)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-mono)'
        }}
      >
        <span aria-hidden="true" style={{ animation: 'skeleton-pulse 1.5s ease-in-out infinite' }}>◌</span>
        Live updates interrupted. Reconnecting…
      </div>
    );
  }

  return (
    <div 
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 'var(--space-4)',
        padding: 'var(--space-3) var(--space-4)',
        background: 'var(--grey-0)',
        color: 'var(--grey-100)',
        borderRadius: 'var(--radius-sm)',
        marginBottom: 'var(--space-4)'
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
        <strong style={{ fontSize: 'var(--text-sm)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Live Updates Unavailable
        </strong>
        <span style={{ fontSize: 'var(--text-sm)', opacity: 0.9 }}>
          The council may still be running. Refresh the execution status.
        </span>
      </div>
      {onRefresh && (
        <button 
          onClick={onRefresh}
          style={{
            background: 'var(--grey-100)',
            color: 'var(--grey-0)',
            border: 'none',
            padding: 'var(--space-2) var(--space-4)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
            cursor: 'pointer',
            whiteSpace: 'nowrap'
          }}
        >
          Refresh status
        </button>
      )}
    </div>
  );
}
