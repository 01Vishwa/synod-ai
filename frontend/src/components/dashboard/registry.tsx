'use client';

import React from 'react';
import type { z } from 'zod';
import type {
  MetricCardSchema,
  RankBarSchema,
  LatencyChartSchema,
  CostGaugeSchema,
  TokenTableSchema,
  SourceListSchema,
} from './catalog';

// ─── Implementations ──────────────────────────────────────────────────────

function MetricCard({ label, value, unit, description }: z.infer<typeof MetricCardSchema>) {
  return (
    <div
      role="region"
      aria-label={`${label} Metric`}
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
        role="meter"
        aria-label={`${label} Score`}
        aria-valuemin={0}
        aria-valuemax={maxScore}
        aria-valuenow={score}
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
      <table role="table" aria-label="Token Usage and Cost" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)' }}>
        <thead role="rowgroup">
          <tr role="row" style={{ background: 'var(--color-bg-subtle)', borderBottom: '1px solid var(--color-border)' }}>
            <th role="columnheader" style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'left', fontWeight: 600 }}>Member</th>
            <th role="columnheader" style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', fontWeight: 600 }}>In</th>
            <th role="columnheader" style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', fontWeight: 600 }}>Out</th>
            <th role="columnheader" style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', fontWeight: 600 }}>Cost</th>
          </tr>
        </thead>
        <tbody role="rowgroup" style={{ fontFamily: 'var(--font-mono)' }}>
          {members.map((m, i) => (
            <tr role="row" key={i} style={{ borderBottom: '1px solid var(--color-border)' }}>
              <td role="cell" style={{ padding: 'var(--space-2) var(--space-4)', fontFamily: 'var(--font-body)', fontWeight: 500 }}>{m.label}</td>
              <td role="cell" style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', color: 'var(--color-text-muted)' }}>{m.tokensIn.toLocaleString()}</td>
              <td role="cell" style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right', color: 'var(--color-text-muted)' }}>{m.tokensOut.toLocaleString()}</td>
              <td role="cell" style={{ padding: 'var(--space-2) var(--space-4)', textAlign: 'right' }}>${m.costUsd.toFixed(4)}</td>
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
    <div role="list" aria-label="Research Sources" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      {sources.map((s, i) => (
        <div role="listitem" key={i} style={{ border: '1px solid var(--color-border)', padding: 'var(--space-3)', borderRadius: 'var(--radius-sm)' }}>
          {s.url ? (
            <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 600, fontSize: 'var(--text-sm)', display: 'block', marginBottom: 'var(--space-1)' }}>
              {s.title}
            </a>
          ) : (
            <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', marginBottom: 'var(--space-1)' }}>{s.title}</div>
          )}
          {s.snippet && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)' }}>{s.snippet}</div>}
        </div>
      ))}
    </div>
  );
}

// ─── LatencyChart ─────────────────────────────────────────────────────────────
// PRD §11.3: per-member latency horizontal bar chart, greyscale only.

function LatencyChart({ members, unit = 'ms' }: z.infer<typeof LatencyChartSchema>) {
  if (!members || members.length === 0) return null;
  const maxLatency = Math.max(...members.map((m) => m.latencyMs), 1);
  const sorted = [...members].sort((a, b) => a.latencyMs - b.latencyMs);

  return (
    <div
      role="region"
      aria-label="Member Latency Chart"
      style={{
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-4)',
        background: 'var(--color-bg)',
      }}
    >
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', marginBottom: 'var(--space-3)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        Response Latency
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        {sorted.map((m, i) => {
          const pct = maxLatency > 0 ? (m.latencyMs / maxLatency) * 100 : 0;
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
              <div
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  fontWeight: 600,
                  width: '100px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                }}
                title={m.label}
              >
                {m.label}
              </div>
              <div
                role="meter"
                aria-label={`${m.label} latency`}
                aria-valuenow={m.latencyMs}
                aria-valuemin={0}
                aria-valuemax={maxLatency}
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
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', width: '60px', textAlign: 'right', flexShrink: 0 }}>
                {m.latencyMs.toLocaleString()}{unit}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── CostGauge ────────────────────────────────────────────────────────────────
// PRD §11.3: session-total cost gauge with optional budget ceiling bar.
// PRD §12.8: threshold is communicated via border weight, never color.

function CostGauge({ label, costUsd, budgetUsd, description }: z.infer<typeof CostGaugeSchema>) {
  const hasBudget = budgetUsd != null && budgetUsd > 0;
  const pct = hasBudget ? Math.min((costUsd / budgetUsd!) * 100, 100) : 0;
  // Near-budget (>90%) communicated via bold border, not color (PRD §12.8)
  const nearBudget = hasBudget && pct >= 90;

  return (
    <div
      role="region"
      aria-label={label}
      style={{
        border: nearBudget ? '2px solid var(--grey-0)' : '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-4)',
        background: 'var(--color-bg)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
      }}
    >
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', fontWeight: 700 }}>
        {label}
        {nearBudget && (
          <span style={{ marginLeft: 'var(--space-2)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}
                aria-label="Near budget limit">
            ⚠ Near limit
          </span>
        )}
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xl)', fontWeight: 700 }}>
        ${costUsd.toFixed(4)}
      </div>
      {hasBudget && (
        <div
          role="meter"
          aria-label={`Cost: $${costUsd.toFixed(4)} of $${budgetUsd!.toFixed(2)} budget`}
          aria-valuenow={costUsd}
          aria-valuemin={0}
          aria-valuemax={budgetUsd!}
          style={{
            height: '6px',
            background: 'var(--grey-93)',
            borderRadius: '3px',
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
              borderRadius: '3px',
            }}
          />
        </div>
      )}
      {description && (
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)' }}>
          {description}
        </div>
      )}
      {hasBudget && (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)' }}>
          Budget: ${budgetUsd!.toFixed(2)} ({pct.toFixed(0)}% used)
        </div>
      )}
    </div>
  );
}

// ─── Registry Mapping ────────────────────────────────────────────────────

export const registry: any = {
  MetricCard,
  RankBar,
  LatencyChart,
  CostGauge,
  TokenTable,
  SourceList,
};
