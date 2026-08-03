'use client';

import React, { useState } from 'react';
import type { RankingEntry, CouncilMemberConfig } from '@/lib/api-client';

interface RankingTableProps {
  rankings: RankingEntry[];
  aggregateScores: Record<string, number>;
  members: CouncilMemberConfig[];
  anonymizationMap: Record<string, string>;
  stage2Status?: string;
  sessionStatus?: string;
  totalMembers: number;
  reviewsCompleted: number;
}

function ScoreBar({ score, max }: { score: number; max: number }) {
  const pct = max > 0 ? (score / max) * 100 : 0;
  return (
    <div
      className="h-2.5 bg-bgSubtle rounded-full overflow-hidden border border-border/50 shadow-inner w-full"
      role="img"
      aria-label={`Score: ${score.toFixed(2)} out of ${max.toFixed(2)}`}
    >
      <div
        className="h-full bg-primary transition-all duration-700 ease-out rounded-full"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function RankBadge({ rank }: { rank: number }) {
  const isFirst = rank === 1;
  return (
    <span
      className={`font-mono font-bold text-sm w-7 h-7 inline-flex items-center justify-center rounded-lg shadow-sm shrink-0
        ${isFirst ? 'border-2 border-primary bg-primary/10 text-primary' : 'border border-border bg-surface text-foreground'}`}
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
  totalMembers,
  reviewsCompleted,
}: RankingTableProps) {
  const [expandedMemberId, setExpandedMemberId] = useState<string | null>(null);

  const isSkipped = stage2Status === 'skipped' || stage2Status === 'failed' || sessionStatus === 'failed';

  if (isSkipped) {
    return (
      <div className="border border-amber-500/30 rounded-xl p-6 bg-amber-500/5 text-amber-600 flex items-start gap-4 shadow-sm">
        <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <div>
          <h4 className="font-bold text-lg mb-1">Peer review skipped</h4>
          <p className="text-sm opacity-80 m-0">At least two successful opinions are required for blind peer review.</p>
        </div>
      </div>
    );
  }

  if (stage2Status === 'pending') {
    return (
      <div className="p-12 text-center text-muted border-2 border-dashed border-border rounded-xl">
        Peer Review will begin after all First Opinions complete.
      </div>
    );
  }

  if (stage2Status === 'running' && rankings.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 bg-bgSubtle border border-border rounded-xl animate-pulse" />
        ))}
        <div className="text-center text-primary font-medium text-sm mt-4 animate-pulse">
          Collecting peer reviews...
        </div>
      </div>
    );
  }

  if (members.length === 0) {
    return (
      <div className="p-12 text-center text-muted border-2 border-dashed border-border rounded-xl">
        Peer review not available yet.
      </div>
    );
  }

  // Only include members who successfully made it to Stage 2
  const eligibleMembers = members.filter(m => m.member_id in anonymizationMap);

  // Build sorted member list by aggregate score (descending)
  const sortedMembers = [...eligibleMembers].sort((a, b) => {
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
    <div className="flex flex-col gap-10">
      {stage2Status === 'running' && rankings.length > 0 && (
        <div className="bg-surface border border-border rounded-xl p-4 shadow-sm flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
            </span>
            <span className="font-medium text-sm text-foreground">Collecting peer reviews...</span>
          </div>
          <span className="font-mono text-sm font-bold text-primary bg-primary/10 px-3 py-1 rounded-md border border-primary/20">
            {reviewsCompleted} of {totalMembers} reviews collected
          </span>
        </div>
      )}

      {/* Aggregate scores summary */}
      <section className="bg-surface border border-border rounded-xl shadow-sm p-6 lg:p-8">
        <h3 className="text-xs font-bold uppercase tracking-widest text-muted mb-6 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          Aggregate Rankings (Borda Count)
        </h3>

        <div className="flex flex-col gap-4">
          {sortedMembers.map((member, i) => {
            const label = anonymizationMap[member.member_id] ?? `Member ${String.fromCharCode(65 + i)}`;
            const score = aggregateScores[member.member_id] ?? 0;
            return (
              <div
                key={member.member_id}
                className="grid grid-cols-[auto_minmax(100px,180px)_1fr_auto] items-center gap-4 bg-background border border-border p-3 rounded-lg hover:border-border-strong transition-colors"
              >
                <RankBadge rank={i + 1} />
                <span className="font-mono text-sm font-semibold truncate" title={label}>
                  {label}
                </span>
                <div className="w-full">
                  <ScoreBar score={score} max={maxScore} />
                </div>
                <span className="font-mono text-xs font-bold text-foreground bg-bgSubtle px-2 py-1 rounded-md min-w-[3rem] text-center border border-border">
                  {score.toFixed(2)}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* Per-reviewer justifications */}
      <section>
        <h3 className="text-xs font-bold uppercase tracking-widest text-muted mb-6 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          Peer Justifications
        </h3>

        <div className="flex flex-col gap-3">
          {eligibleMembers.map((member, i) => {
              const entry = rankingByReviewer[member.member_id];
              const reviewerLabel = anonymizationMap[member.member_id] ?? `Member ${String.fromCharCode(65 + i)}`;
              const isExpanded = expandedMemberId === member.member_id;

              return (
                <div
                  key={member.member_id}
                  className={`bg-surface border rounded-xl overflow-hidden shadow-sm transition-colors ${isExpanded ? 'border-border-strong' : 'border-border'}`}
                >
                  <button
                    id={`justify-toggle-${member.member_id}`}
                    onClick={() => setExpandedMemberId(isExpanded ? null : member.member_id)}
                    aria-expanded={isExpanded}
                    className="w-full flex items-center justify-between p-4 outline-none hover:bg-surface-hover transition-colors"
                  >
                    <div className="flex flex-wrap items-center gap-4">
                      <span className="font-mono font-bold text-sm text-foreground">
                        {reviewerLabel}
                      </span>
                      
                      {entry ? (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-muted uppercase tracking-wider font-semibold">Ranked:</span>
                          <span className="text-xs font-mono bg-bgSubtle border border-border px-2 py-0.5 rounded text-foreground font-semibold">
                            {entry.ranking_order.join(' → ')}
                          </span>
                        </div>
                      ) : stage2Status === 'running' ? (
                        <span className="text-xs font-medium text-primary flex items-center gap-1.5 animate-pulse">
                          <span className="font-mono">◌</span> Reviewing…
                        </span>
                      ) : (!stage2Status || stage2Status === 'pending') ? (
                        <span className="text-xs font-medium text-muted flex items-center gap-1.5">
                          <span className="w-3 h-3 rounded-full border-2 border-dashed border-muted shrink-0" />
                          Waiting…
                        </span>
                      ) : (
                        <span className="text-xs font-medium text-red-600 flex items-center gap-1.5">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
                          Review failed
                        </span>
                      )}
                    </div>
                    <span className="text-muted shrink-0 ml-4">
                      <svg className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                      </svg>
                    </span>
                  </button>

                  {isExpanded && entry && (
                    <div className="px-6 py-5 border-t border-border bg-background">
                      <h4 className="text-[10px] font-bold text-subtle uppercase tracking-wider mb-3">Justification</h4>
                      <p className="text-sm leading-relaxed text-foreground m-0 animate-in fade-in slide-in-from-top-2">
                        {entry.justification}
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      </section>
    </div>
  );
}
