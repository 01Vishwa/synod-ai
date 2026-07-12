'use client';

/**
 * CostMeter — always-visible cost meter for active sessions.
 * Displays running token spend in the user's provider currency.
 */

import React from 'react';

interface CostMeterProps {
  totalCostUsd: number;
  totalTokens: number;
  stage?: string | null;
}

function formatCost(usd: number): string {
  if (usd === 0) return '$0.0000';
  if (usd < 0.001) return `$${usd.toFixed(6)}`;
  if (usd < 0.01)  return `$${usd.toFixed(5)}`;
  return `$${usd.toFixed(4)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

export function CostMeter({ totalCostUsd, totalTokens, stage }: CostMeterProps) {
  return (
    <div
      role="status"
      aria-label={`Session cost: ${formatCost(totalCostUsd)}, tokens used: ${formatTokens(totalTokens)}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-4)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-sm)',
        padding: 'var(--space-1) var(--space-3)',
        fontFamily: 'var(--font-mono)',
        fontSize: 'var(--text-xs)',
        background: 'var(--color-bg-subtle)',
      }}
    >
      {stage && stage !== 'done' && stage !== 'error' && (
        <span
          style={{ color: 'var(--color-text-subtle)' }}
          aria-live="polite"
        >
          ◌
        </span>
      )}
      <span title="Estimated cost this session">
        <span style={{ color: 'var(--color-text-subtle)' }}>Cost </span>
        <strong style={{ color: 'var(--color-text)' }}>{formatCost(totalCostUsd)}</strong>
      </span>
      <span
        style={{
          width: '1px',
          height: '12px',
          background: 'var(--color-border)',
          display: 'inline-block',
        }}
      />
      <span title="Total tokens used">
        <span style={{ color: 'var(--color-text-subtle)' }}>Tokens </span>
        <strong style={{ color: 'var(--color-text)' }}>{formatTokens(totalTokens)}</strong>
      </span>
    </div>
  );
}
