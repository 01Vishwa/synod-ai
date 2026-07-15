'use client';

/**
 * ChairmanReport — Stage 3 final report renderer.
 * Renders the Chairman's synthesized Markdown with citations,
 * agreement/disagreement strip, and de-anonymized reveal.
 */

import React, { useState } from 'react';
import type { CouncilMemberConfig, MemberResponse, RankingEntry } from '@/lib/api-client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Citation {
  url?: string;
  title?: string;
  snippet?: string;
}

interface ChairmanReportProps {
  reportMd: string;
  citations: Array<Record<string, unknown>>;
  members: CouncilMemberConfig[];
  stage1Responses: MemberResponse[];
  aggregateScores: Record<string, number>;
  chairmanMemberId: string;
  notionPageUrl?: string;
  traceId?: string;
  stage3Status?: string;
  sessionStatus?: string;
  excludedMemberIds?: string[];
}

function ChairmanBadge({ member }: { member: CouncilMemberConfig | undefined }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        border: '2px solid var(--grey-0)',
        borderRadius: 'var(--radius-sm)',
        padding: 'var(--space-1) var(--space-3)',
        marginBottom: 'var(--space-6)',
      }}
    >
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', fontWeight: 700 }}>
        CHAIRMAN
      </span>
      {member && (
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
          {member.display_label} — {member.model_id}
        </span>
      )}
    </div>
  );
}

export function ChairmanReport({
  reportMd,
  citations,
  members,
  stage1Responses,
  aggregateScores,
  chairmanMemberId,
  notionPageUrl,
  traceId,
  stage3Status,
  sessionStatus,
  excludedMemberIds = [],
}: ChairmanReportProps) {
  const [showReveal, setShowReveal] = useState(false);

  const isSkipped = stage3Status === 'skipped' || stage3Status === 'failed' || sessionStatus === 'failed';

  const chairmanMember = members.find((m) => m.member_id === chairmanMemberId);

  // Sort members by score for the reveal table
  const sortedMembers = [...members].sort((a, b) => {
    const isAE = excludedMemberIds.includes(a.member_id);
    const isBE = excludedMemberIds.includes(b.member_id);
    if (isAE && !isBE) return 1;
    if (!isAE && isBE) return -1;
    const sa = aggregateScores[a.member_id] ?? 0;
    const sb = aggregateScores[b.member_id] ?? 0;
    return sb - sa;
  });

  const maxScore = Math.max(...Object.values(aggregateScores), 0);

  return (
    <div>
      {/* Chairman identity banner */}
      {!isSkipped && <ChairmanBadge member={chairmanMember} />}

      {/* The report itself */}
      {isSkipped ? (
        <div className="border-2 border-black rounded-md p-6 bg-grey-93 mb-8">
          <p className="font-bold mb-1">Chairman synthesis skipped.</p>
          <p className="text-xs text-subtle m-0">Synthesis cannot run because no valid deliberations completed.</p>
        </div>
      ) : reportMd ? (
        <div className="prose" style={{ maxWidth: '100%', marginBottom: 'var(--space-8)' }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {reportMd}
          </ReactMarkdown>
        </div>
      ) : (
        <div>
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="skeleton"
              style={{
                height: '18px',
                width: `${70 + i * 8}%`,
                marginBottom: '14px',
              }}
            />
          ))}
          <p style={{ color: 'var(--color-text-subtle)', fontSize: 'var(--text-sm)' }}>
            ◌ Chairman is synthesizing the final report…
          </p>
        </div>
      )}

      {/* Citations */}
      {!isSkipped && citations.length > 0 && (
        <section
          aria-labelledby="citations-heading"
          style={{
            borderTop: '1px solid var(--color-border)',
            paddingTop: 'var(--space-6)',
            marginBottom: 'var(--space-6)',
          }}
        >
          <h3
            id="citations-heading"
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-sm)',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: 'var(--space-4)',
            }}
          >
            Sources
          </h3>
          <ol style={{ paddingLeft: 'var(--space-6)', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {citations.map((c, i) => {
              const cit = c as Citation;
              return (
                <li key={i} style={{ fontSize: 'var(--text-sm)' }}>
                  {cit.url ? (
                    <a
                      href={cit.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}
                    >
                      {cit.title || cit.url}
                    </a>
                  ) : (
                    <span>{cit.title ?? JSON.stringify(c)}</span>
                  )}
                  {cit.snippet && (
                    <span style={{ color: 'var(--color-text-muted)', marginLeft: 'var(--space-2)' }}>
                      — {cit.snippet}
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {/* De-anonymized reveal */}
      <section
        aria-labelledby="reveal-heading"
        style={{
          borderTop: '1px solid var(--color-border)',
          paddingTop: 'var(--space-6)',
          marginBottom: 'var(--space-6)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
          <h3
            id="reveal-heading"
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-sm)',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
            }}
          >
            Who Said What
          </h3>
          <button
            id="reveal-toggle-btn"
            className="btn-ghost btn-sm"
            onClick={() => setShowReveal((v) => !v)}
            aria-expanded={showReveal}
          >
            {showReveal ? 'Hide reveal' : 'Reveal identities'}
          </button>
        </div>

        {showReveal && (
          <div style={{ animation: 'fadeIn 200ms ease' }}>
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', marginBottom: 'var(--space-4)' }}>
              Member identities are revealed here for human review only — they were never exposed to the other models during peer review.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              {sortedMembers.map((member, i) => {
                const resp = stage1Responses.find((r) => r.member_id === member.member_id);
                const isExcluded = excludedMemberIds.includes(member.member_id);
                const score = aggregateScores[member.member_id] ?? 0;
                const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
                const isChairman = member.member_id === chairmanMemberId;

                return (
                  <div
                    key={member.member_id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '24px 1fr auto',
                      gap: 'var(--space-3)',
                      alignItems: 'center',
                      padding: 'var(--space-2) var(--space-3)',
                      border: isChairman && !isSkipped ? '2px solid var(--grey-0)' : '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-sm)',
                      background: isExcluded ? 'rgba(0,0,0,0.02)' : 'transparent',
                    }}
                  >
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 'var(--text-xs)' }}>
                      {i + 1}
                    </span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 'var(--text-sm)', color: isExcluded ? 'var(--color-text-muted)' : 'inherit' }}>
                        {member.display_label}
                        {isChairman && !isSkipped && (
                          <span style={{ marginLeft: 'var(--space-2)', fontFamily: 'var(--font-mono)', fontSize: '10px', fontWeight: 400, padding: '0 4px', border: '1px solid var(--grey-0)', borderRadius: '2px' }}>
                            CHAIRMAN
                          </span>
                        )}
                        {isExcluded && (
                          <span style={{ marginLeft: 'var(--space-2)', fontFamily: 'var(--font-mono)', fontSize: '10px', fontWeight: 700, padding: '0 4px', border: '1px solid red', color: 'red', borderRadius: '2px' }}>
                            EXCLUDED
                          </span>
                        )}
                      </div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--color-text-subtle)' }}>
                        {member.provider} / {member.model_id}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', marginBottom: '4px', color: isExcluded ? 'red' : 'inherit', fontWeight: isExcluded ? 700 : 'normal' }}>
                        {isExcluded ? 'FAILED/EXCLUDED' : score.toFixed(2)}
                      </div>
                      {!isExcluded && (
                        <div
                          style={{
                            width: '80px',
                            height: '6px',
                            background: 'var(--grey-93)',
                            borderRadius: '3px',
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: `${pct}%`,
                              height: '100%',
                              background: 'var(--grey-0)',
                            }}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* Footer links */}
      <div
        style={{
          borderTop: '1px solid var(--color-border)',
          paddingTop: 'var(--space-4)',
          display: 'flex',
          gap: 'var(--space-4)',
          flexWrap: 'wrap',
          fontSize: 'var(--text-xs)',
        }}
      >
        {notionPageUrl && (
          <a
            href={notionPageUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            ✓ Archived to Notion
          </a>
        )}
        {traceId && (
          <a
            href={`/api/v1/observability/trace/${traceId}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontFamily: 'var(--font-mono)' }}
          >
            View full Langfuse trace →
          </a>
        )}
      </div>
    </div>
  );
}
