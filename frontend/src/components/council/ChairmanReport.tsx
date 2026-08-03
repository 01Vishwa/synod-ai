'use client';

import React, { useState, useEffect } from 'react';
import type { CouncilMemberConfig, MemberResponse } from '@/lib/api-client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ProviderBadge } from '@/components/ui/ProviderBadge';

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
  chairmanStreamingContent: string;
  isStreaming: boolean;
}

function ChairmanBadge({ member }: { member: CouncilMemberConfig | undefined }) {
  return (
    <div className="inline-flex items-center gap-3 border border-primary/30 bg-primary/5 rounded-xl px-4 py-2 mb-8 shadow-sm">
      <span className="font-mono text-[10px] font-bold tracking-widest text-primary uppercase flex items-center gap-1.5">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
        </svg>
        Chairman
      </span>
      {member && (
        <>
          <div className="w-px h-4 bg-primary/20" />
          <span className="text-sm font-semibold text-foreground">
            {member.display_label}
          </span>
          <span className="font-mono text-xs text-muted">
            {member.model_id}
          </span>
        </>
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
  chairmanStreamingContent,
  isStreaming,
}: ChairmanReportProps) {
  const [showReveal, setShowReveal] = useState(false);
  const [cursorVisible, setCursorVisible] = useState(true);

  useEffect(() => {
    if (!isStreaming) return;
    const id = setInterval(() => setCursorVisible((v) => !v), 530);
    return () => clearInterval(id);
  }, [isStreaming]);

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
    <div className="flex flex-col">
      {/* Chairman identity banner */}
      {!isSkipped && <ChairmanBadge member={chairmanMember} />}

      {/* The report itself */}
      {isSkipped ? (
        <div className="border-l-4 border-black rounded-xl p-6 bg-white text-black flex items-start gap-4 mb-8 shadow-sm">
          <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <h4 className="font-bold text-lg mb-1">Chairman synthesis skipped</h4>
            <p className="text-sm opacity-80 m-0">Synthesis cannot run because no valid deliberations completed.</p>
          </div>
        </div>
      ) : reportMd && !isStreaming ? (
        // State 4 — Complete: render markdown
        <div className="prose prose-sm md:prose-base max-w-[65ch] text-foreground leading-relaxed marker:text-muted mb-12">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {reportMd}
          </ReactMarkdown>
        </div>
      ) : isStreaming && chairmanStreamingContent !== '' ? (
        // State 3 — Streaming with content: plain text + blinking cursor
        <div className="max-w-[65ch] font-mono text-sm text-foreground leading-relaxed whitespace-pre-wrap mb-12">
          {chairmanStreamingContent}
          <span
            aria-hidden="true"
            className="inline-block w-px h-[1em] bg-foreground align-middle ml-0.5"
            style={{ opacity: cursorVisible ? 1 : 0 }}
          />
        </div>
      ) : isStreaming && chairmanStreamingContent === '' ? (
        // State 2 — Streaming, waiting for first token
        <div className="p-8 text-center text-muted border border-border rounded-xl bg-surface mb-12 max-w-[65ch]">
          Chairman is preparing synthesis...
        </div>
      ) : (
        // State 1 — Not started
        <div className="p-8 text-center text-muted border border-border rounded-xl bg-surface mb-12 max-w-[65ch]">
          Chairman synthesis will begin after Peer Review completes.
        </div>
      )}

      {/* Citations */}
      {!isSkipped && citations.length > 0 && (
        <section
          aria-labelledby="citations-heading"
          className="border-t border-border pt-8 mb-12"
        >
          <h3
            id="citations-heading"
            className="text-xs font-bold uppercase tracking-widest text-muted mb-6 flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
            </svg>
            Sources & Citations
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {citations.map((c, i) => {
              const cit = c as Citation;
              return (
                <div key={i} className="flex flex-col gap-2 p-4 bg-surface border border-border rounded-xl shadow-sm hover:border-border-strong transition-colors">
                  <div className="flex items-start gap-3">
                    <span className="font-mono text-[10px] font-bold bg-bgSubtle px-1.5 py-0.5 rounded border border-border mt-0.5 shrink-0">
                      [{i + 1}]
                    </span>
                    <a
                      href={cit.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm font-medium text-foreground hover:text-primary transition-colors line-clamp-2"
                    >
                      {cit.title || cit.url}
                    </a>
                  </div>
                  {cit.snippet && (
                    <p className="text-xs text-muted leading-relaxed line-clamp-3 ml-8 mt-1">
                      &quot;{cit.snippet}&quot;
                    </p>
                  )}
                  {cit.url && (
                    <span className="text-[10px] font-mono text-subtle truncate ml-8">
                      {cit.url}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* De-anonymized reveal */}
      <section
        aria-labelledby="reveal-heading"
        className="border-t border-border pt-8 mb-12"
      >
        <div className="flex items-center justify-between mb-6">
          <h3
            id="reveal-heading"
            className="text-xs font-bold uppercase tracking-widest text-muted flex items-center gap-2 m-0"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            Who Said What
          </h3>
          <button
            id="reveal-toggle-btn"
            className="text-xs font-bold text-foreground bg-surface border border-border px-4 py-2 rounded-lg hover:bg-surface-hover transition-colors shadow-sm"
            onClick={() => setShowReveal((v) => !v)}
            aria-expanded={showReveal}
          >
            {showReveal ? 'Hide Identities' : 'Reveal Identities'}
          </button>
        </div>

        {showReveal && (
          <div className="animate-in fade-in slide-in-from-top-4 duration-300">
            <p className="text-sm text-subtle mb-6 max-w-[65ch]">
              Member identities are revealed here for human review only — they were never exposed to the other models during peer review.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {sortedMembers.map((member, i) => {
                const isExcluded = excludedMemberIds.includes(member.member_id);
                const score = aggregateScores[member.member_id] ?? 0;
                const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
                const isChairman = member.member_id === chairmanMemberId;

                return (
                  <div
                    key={member.member_id}
                    className={`flex flex-col p-4 rounded-xl shadow-sm border transition-colors
                      ${isChairman && !isSkipped ? 'border-primary/50 bg-primary/5' : 'border-border bg-surface'}
                      ${isExcluded ? 'opacity-70 bg-bgSubtle border-dashed' : ''}
                    `}
                  >
                    <div className="flex justify-between items-start mb-4">
                      <div className="flex items-center gap-3">
                        <span className={`w-6 h-6 inline-flex items-center justify-center rounded-md font-mono text-xs font-bold shrink-0
                          ${isExcluded ? 'bg-white border border-black text-black font-bold' : i === 0 ? 'bg-foreground text-background' : 'bg-bgSubtle text-muted border border-border'}`}>
                          {isExcluded ? '✕' : i + 1}
                        </span>
                        <div>
                          <div className="font-bold text-sm text-foreground flex items-center gap-2">
                            {member.display_label}
                            {isChairman && !isSkipped && (
                              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 bg-primary/20 text-primary rounded uppercase">Chairman</span>
                            )}
                            {isExcluded && (
                              <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 bg-white border border-black text-black rounded uppercase">Excluded</span>
                            )}
                          </div>
                          <div className="font-mono text-[10px] text-muted flex items-center gap-2 mt-1">
                            <ProviderBadge provider={member.provider} />
                            {member.model_id}
                          </div>
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex flex-col gap-2 mt-auto pt-4 border-t border-border/50">
                      <div className="flex justify-between items-center text-[10px] font-bold uppercase tracking-wider">
                        <span className="text-subtle">Borda Score</span>
                        <span className={`font-mono text-xs ${isExcluded ? 'text-gray-700' : 'text-foreground'}`}>
                          {isExcluded ? '0.00' : score.toFixed(2)}
                        </span>
                      </div>
                      {!isExcluded && (
                        <div className="h-1.5 bg-bgSubtle rounded-full overflow-hidden border border-border/50">
                          <div className="h-full bg-foreground rounded-full" style={{ width: `${pct}%` }} />
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
      <div className="flex flex-wrap gap-4 border-t border-border pt-6 pb-12">
        {notionPageUrl && (
          <a
            href={notionPageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-sm font-semibold bg-[#F1F1F0] dark:bg-[#2F2F2F] text-[#37352F] dark:text-[#E0E0E0] px-4 py-2 rounded-lg border border-[#E9E9E7] dark:border-[#3F3F3F] hover:bg-[#E9E9E7] dark:hover:bg-[#3F3F3F] transition-colors shadow-sm"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M4.117 3.84h15.688v16.142H4.117z" fillOpacity=".01" />
              <path d="M21.573 23H2.35v-1.121h2.247V2.122H2.35V1h19.222v1.121h-2.246v19.757h2.246V23zM6.843 3.243v16.514h10.237V3.243H6.843zm4.629 11.233V8.04l4.201 6.845h.582V7.126h-1.393v6.331l-4.144-6.741h-.638v7.76h1.392z" />
            </svg>
            Archived to Notion
          </a>
        )}
      </div>
    </div>
  );
}
