'use client';

/**
 * RankingTable — Stage 2 anonymized peer-review table.
 * Shows each member's ranking and justification in a structured grid.
 */

import React, { useState } from 'react';
import type { RankingEntry, CouncilMemberConfig } from '@/lib/api-client';

interface RankingTableProps {
  rankings: RankingEntry[];
  aggregateScores: Record<string, number>;
  members: CouncilMemberConfig[];
  // server-side anonymization map (member_id -> label)
  anonymizationMap: Record<string, string>;
  stage2Status?: string;
  sessionStatus?: string;
}

function ScoreBar({ score, max }: { score: number; max: number }) {
  const pct = max > 0 ? (score / max) * 100 : 0;
  return (
    <div
      style={{
        height: '8px',
        background: 'var(--grey-93)',
        borderRadius: '4px',
        overflow: 'hidden',
        border: '1px solid var(--color-border)',
      }}
      role="img"
      aria-label={`Score: ${score.toFixed(2)} out of ${max.toFixed(2)}`}
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
  );
}

function RankBadge({ rank }: { rank: number }) {
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontWeight: 700,
        fontSize: 'var(--text-sm)',
        width: '28px',
        height: '28px',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: rank === 1 ? '2px solid var(--grey-0)' : '1px solid var(--color-border)',
        borderRadius: 'var(--radius-sm)',
        background: rank === 1 ? 'var(--grey-0)' : 'transparent',
        color: rank === 1 ? 'var(--grey-100)' : 'var(--color-text)',
      }}
    >
      {rank}
    </span>
  );
}

export function RankingTable({
  rankings,
  aggregateScores,
  members,
  anonymizationMap,
  stage2Status,
  sessionStatus,
}: RankingTableProps) {
  const [expandedMemberId, setExpandedMemberId] = useState<string | null>(null);

  const isSkipped = stage2Status === 'skipped' || stage2Status === 'failed' || sessionStatus === 'failed';

  if (isSkipped) {
    return (
      <div className="border-2 border-black rounded-md p-6 bg-grey-93">
        <p className="font-bold mb-1">Peer review skipped — no successful Stage 1 responses.</p>
        <p className="text-xs text-subtle m-0">At least two successful opinions are required for blind peer review.</p>
      </div>
    );
  }

  if (members.length === 0) {
    return (
      <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-text-subtle)' }}>
        Peer review not available yet.
      </div>
    );
  }

  // Build sorted member list by aggregate score (descending)
  const sortedMembers = [...members].sort((a, b) => {
    const sa = aggregateScores[a.member_id] ?? 0;
    const sb = aggregateScores[b.member_id] ?? 0;
    return sb - sa;
  });

  const maxScore = Math.max(...Object.values(aggregateScores), 0);

  // Build a lookup: reviewer member_id → ranking entry
  const rankingByReviewer = Object.fromEntries(
    rankings.map((r) => [r.ranked_by_member_id, r]),
  );

  return (
    <div>
      {/* Aggregate scores summary */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <p
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            color: 'var(--color-text-subtle)',
            marginBottom: 'var(--space-4)',
          }}
        >
          Aggregate Rankings (Borda Count)
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {sortedMembers.map((member, i) => {
            const label = anonymizationMap[member.member_id] ?? `Member ${String.fromCharCode(65 + i)}`;
            const score = aggregateScores[member.member_id] ?? 0;
            return (
              <div
                key={member.member_id}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '36px 120px 1fr 80px',
                  alignItems: 'center',
                  gap: 'var(--space-3)',
                }}
              >
                <RankBadge rank={i + 1} />
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-sm)',
                    fontWeight: 600,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {label}
                </span>
                <ScoreBar score={score} max={maxScore} />
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-xs)',
                    textAlign: 'right',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  {score.toFixed(2)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ height: '1px', background: 'var(--color-border)', margin: 'var(--space-6) 0' }} />

      {/* Per-reviewer justifications */}
      <div>
        <p
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.1em',
            color: 'var(--color-text-subtle)',
            marginBottom: 'var(--space-4)',
          }}
        >
          Peer Justifications
        </p>

        {rankings.length === 0 ? (
          <div>
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="skeleton"
                style={{ height: '72px', marginBottom: 'var(--space-3)', borderRadius: 'var(--radius-sm)' }}
              />
            ))}
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-subtle)' }}>
              Waiting for peer reviews to complete…
            </p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {members.map((member, i) => {
              const entry = rankingByReviewer[member.member_id];
              const reviewerLabel = anonymizationMap[member.member_id] ?? `Member ${String.fromCharCode(65 + i)}`;
              const isExpanded = expandedMemberId === member.member_id;

              return (
                <div
                  key={member.member_id}
                  style={{
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-md)',
                    overflow: 'hidden',
                  }}
                >
                  <button
                    id={`justify-toggle-${member.member_id}`}
                    onClick={() => setExpandedMemberId(isExpanded ? null : member.member_id)}
                    aria-expanded={isExpanded}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: 'var(--space-3) var(--space-4)',
                      background: 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 600,
                          fontSize: 'var(--text-sm)',
                        }}
                      >
                        {reviewerLabel}
                      </span>
                      {entry && (
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)' }}>
                          ranked: {entry.ranking_order.join(' → ')}
                        </span>
                      )}
                      {!entry && (
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)' }}>
                          ◌ Reviewing…
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)' }}>
                      {isExpanded ? '▲' : '▼'}
                    </span>
                  </button>

                  {isExpanded && entry && (
                    <div
                      style={{
                        padding: 'var(--space-3) var(--space-4) var(--space-4)',
                        borderTop: '1px solid var(--color-border)',
                        fontSize: 'var(--text-sm)',
                        lineHeight: 1.6,
                        color: 'var(--color-text-muted)',
                        animation: 'fadeIn 150ms ease',
                      }}
                    >
                      {entry.justification}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
