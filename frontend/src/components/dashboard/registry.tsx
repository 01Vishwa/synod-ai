'use client';

import React from 'react';
import type { z } from 'zod';
import type {
  MetricCardSchema,
  RankBarSchema,
  TokenTableSchema,
  SourceListSchema,
} from './catalog';

// ─── Implementations ──────────────────────────────────────────────────────

function MetricCard({ label, value, unit, description }: z.infer<typeof MetricCardSchema>) {
  return (
    <div
      style={{
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-4)',
        background: 'var(--color-bg)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', marginBottom: 'var(--space-2)' }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-2)' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xl)', fontWeight: 700 }}>
          {value}
        </span>
        {unit && (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
            {unit}
          </span>
        )}
      </div>
      {description && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: 'var(--space-2)' }}>
          {description}
        </div>
      )}
    </div>
  );
}

function RankBar({ label, score, maxScore }: z.infer<typeof RankBarSchema>) {
  const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-4)',
        marginBottom: 'var(--space-2)',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-sm)',
          fontWeight: 600,
          width: '120px',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={label}
      >
        {label}
      </div>
      <div
        style={{
          flex: 1,
          height: '8px',
          background: 'var(--grey-93)',
          borderRadius: '4px',
          overflow: 'hidden',
          border: '1px solid var(--color-border)',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: 'var(--grey-0)',
            transition: 'width 500ms ease',
            borderRadius: '4px',
          }}
        />
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', width: '40px', textAlign: 'right' }}>
        {score.toFixed(2)}
      </div>
    </div>
  );
}

function TokenTable({ members }: z.infer<typeof TokenTableSchema>) {
  return (
    <div style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
        <thead>
          <tr style={{ background: 'var(--color-bg-subtle)', borderBottom: '1px solid var(--color-border)' }}>
            <th style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'left', fontWeight: 600 }}>Member</th>
            <th style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', fontWeight: 600 }}>In</th>
            <th style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', fontWeight: 600 }}>Out</th>
            <th style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', fontWeight: 600 }}>Cost</th>
          </tr>
        </thead>
        <tbody style={{ fontFamily: 'var(--font-mono)' }}>
          {members.map((m, i) => (
            <tr key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
              <td style={{ padding: 'var(--space-2) var(--space-4)', fontFamily: 'var(--font-body)', fontWeight: 500 }}>{m.label}</td>
              <td style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', color: 'var(--color-text-muted)' }}>{m.tokensIn.toLocaleString()}</td>
              <td style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', color: 'var(--color-text-muted)' }}>{m.tokensOut.toLocaleString()}</td>
              <td style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right' }}>${m.costUsd.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourceList({ sources }: z.infer<typeof SourceListSchema>) {
  if (sources.length === 0) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      {sources.map((s, i) => (
        <div key={i} style={{ border: '1px solid var(--color-border)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)' }}>
          {s.url ? (
            <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 600, fontSize: 'var(--text-sm)', display: 'block', marginBottom: 'var(--space-1)' }}>
              {s.title}
            </a>
          ) : (
            <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', marginBottom: 'var(--space-1)' }}>{s.title}</div>
          )}
          {s.snippet && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{s.snippet}</div>}
        </div>
      ))}
    </div>
  );
}

// ─── Registry Mapping ────────────────────────────────────────────────────

export const registry: any = {
  MetricCard,
  RankBar,
  TokenTable,
  SourceList,
};
