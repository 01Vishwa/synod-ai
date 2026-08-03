'use client';

import React, { useState, useEffect, useRef } from 'react';
import type { CouncilMemberConfig, MemberResponse, MemberLifecycle } from '@/lib/api-client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ProviderBadge } from '@/components/ui/ProviderBadge';
import { StatusBadge, type StatusType } from '@/components/ui/StatusBadge';

export interface MemberTabsProps {
  members: CouncilMemberConfig[];
  responses: MemberResponse[];
  memberLifecycles?: Record<string, MemberLifecycle>;
  streamingContents?: Record<string, string>;
  memberExecutionStates?: Record<string, { tokens_generated: number }>;
  streamingMemberIds?: Set<string>;
}

export interface MemberCardProps {
  member: CouncilMemberConfig;
  response?: MemberResponse;
  lifecycle: MemberLifecycle;
  streamingContent: string;
  tokensGenerated: number;
}

function MemberCard({ member, response, lifecycle, streamingContent, tokensGenerated }: MemberCardProps) {
  const [elapsedMs, setElapsedMs] = useState(0);
  
  useEffect(() => {
    if (lifecycle === 'completed' || lifecycle === 'failed') return;
    const id = setInterval(() => setElapsedMs(e => e + 100), 100);
    return () => clearInterval(id);
  }, [lifecycle]);

  const statusLabel: Record<MemberLifecycle, string> = {
    queued:              'In Queue',
    initializing:        'Initializing...',
    connecting:          'Connecting to provider...',
    waiting_first_token: 'Waiting for response...',
    streaming:           'Generating...',
    completed:           '',
    failed:              'Failed',
    timeout:             'Timed out',
  };

  const isSlowFreeModel =
    elapsedMs > 15000 &&
    tokensGenerated === 0 &&
    member.model_id?.endsWith(':free');

  if (lifecycle === 'queued' || lifecycle === 'initializing' || lifecycle === 'connecting' || lifecycle === 'waiting_first_token') {
    return (
      <div className="flex flex-col items-center justify-center p-8 border border-dashed border-gray-400 rounded-xl min-h-[150px]">
        <span className="text-muted font-medium">{statusLabel[lifecycle]}</span>
        {isSlowFreeModel && (
          <p className="text-sm text-gray-500 mt-2 text-center">
            Free-tier model — queue can take up to 90 seconds.
            Still waiting for first token...
          </p>
        )}
      </div>
    );
  }

  if (lifecycle === 'streaming') {
    return (
      <div className="p-5 border rounded-xl border-border">
        <div className="font-mono text-sm whitespace-pre-wrap text-foreground">
          {streamingContent}<span className="animate-pulse">|</span>
        </div>
        {isSlowFreeModel && (
          <p className="text-sm text-gray-500 mt-2">
            Free-tier model — queue can take up to 90 seconds.
            Still waiting for first token...
          </p>
        )}
        <div className="mt-4 pt-4 border-t border-border flex gap-4 text-xs font-mono text-muted">
          <span>{elapsedMs}ms</span>
          <span>{tokensGenerated} tok</span>
        </div>
      </div>
    );
  }

  if (lifecycle === 'completed' && response) {
    return (
      <div className="p-0">
        <div className="prose prose-sm md:prose-base max-w-none text-foreground leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {response.content}
          </ReactMarkdown>
        </div>
      </div>
    );
  }

  if (lifecycle === 'failed' || lifecycle === 'timeout') {
    return (
      <div className="p-6 border-2 border-black rounded-xl bg-white">
        <h4 className="font-bold text-black font-medium mb-2">Excluded from ranking: {statusLabel[lifecycle]}</h4>
        <div className="font-mono text-sm text-black whitespace-pre-wrap">
          {response?.error || 'Execution failed.'}
        </div>
      </div>
    );
  }

  return null;
}

function getMemberStatus(res?: MemberResponse, isStreaming?: boolean, lifecycle?: MemberLifecycle): StatusType {
  if (lifecycle && lifecycle !== 'queued' && lifecycle !== 'completed' && lifecycle !== 'failed' && lifecycle !== 'timeout') return 'running';
  if (isStreaming) return 'running';
  if (!res) return 'waiting';
  if (res.error) {
    if (res.error.toLowerCase().includes('auth') || res.error.toLowerCase().includes('unauthorized') || res.error.toLowerCase().includes('401') || res.error.toLowerCase().includes('403')) return 'excluded';
    return 'failed';
  }
  return 'completed';
}

export function MemberTabs({ members, responses, memberLifecycles, streamingContents, memberExecutionStates, streamingMemberIds }: MemberTabsProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const tablistRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.key === '[') setActiveIndex((i) => Math.max(0, i - 1));
      if (e.key === ']') setActiveIndex((i) => Math.min(members.length - 1, i + 1));
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [members.length]);

  if (members.length === 0) {
    return (
      <div className="p-12 text-center border-2 border-dashed border-border rounded-xl">
        <div className="w-12 h-12 bg-bgSubtle rounded-full flex items-center justify-center mx-auto mb-4 text-muted">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
        </div>
        <h3 className="text-lg font-bold text-foreground mb-1">No Council Members</h3>
        <p className="text-sm text-subtle">There are no council members configured for this session.</p>
      </div>
    );
  }

  const activeResponse = responses.find((r) => r.member_id === members[activeIndex]?.member_id);
  const activeMember = members[activeIndex];
  const isStreaming = activeMember && streamingMemberIds?.has(activeMember.member_id);
  
  const getLifecycle = (m: CouncilMemberConfig, r?: MemberResponse) => {
    return memberLifecycles?.[m.member_id] || (r ? (r.error ? 'failed' : 'completed') : (streamingMemberIds?.has(m.member_id) ? 'streaming' : 'queued'));
  };

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Mobile Accordion View (<768px) */}
      <div className="md:hidden flex flex-col gap-2">
        {members.map((member, i) => {
          const res = responses.find((r) => r.member_id === member.member_id);
          const isActive = i === activeIndex;
          const isStreamingThis = streamingMemberIds?.has(member.member_id);
          const lifecycle = getLifecycle(member, res);
          const status = getMemberStatus(res, isStreamingThis, lifecycle);

          return (
            <div key={member.member_id} className={`border rounded-xl overflow-hidden bg-background shadow-sm transition-colors ${status === 'failed' || status === 'excluded' ? 'border-black' : isActive ? 'border-border-strong' : 'border-border'}`}>
              <button
                onClick={() => setActiveIndex(isActive ? -1 : i)}
                className={`w-full flex items-center justify-between px-4 py-4 font-display text-sm transition-colors outline-none
                  ${isActive ? 'bg-surface-hover' : 'hover:bg-surface-hover'}`}
                aria-expanded={isActive}
              >
                <div className="flex items-center gap-3">
                  <ProviderBadge provider={member.provider} />
                  <span className={`font-semibold ${isActive ? 'text-foreground' : 'text-muted'}`}>{member.display_label || `Seat ${i + 1}`}</span>
                  <StatusBadge status={status} className="ml-1" />
                </div>
                <span className="text-subtle">
                  <svg className={`w-4 h-4 transition-transform ${isActive ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                  </svg>
                </span>
              </button>
              
              {isActive && (
                <div className="p-5 border-t border-border animate-in slide-in-from-top-2 duration-200">
                  <div className="flex flex-col gap-4 mb-6 pb-4 border-b border-border">
                    <div>
                      <h4 className="font-display font-bold text-base text-foreground mb-1">
                        {member.display_label || `Council Seat ${i + 1}`}
                      </h4>
                      <p className="font-mono text-[11px] text-muted">{member.model_id}</p>
                    </div>
                    {res && !res.error && (
                      <div className="flex flex-wrap gap-2 text-[11px] font-mono">
                        <span className="px-2 py-1 rounded bg-bgSubtle border border-border text-muted flex items-center gap-1.5"><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>{res.latency_ms}ms</span>
                        <span className="px-2 py-1 rounded bg-bgSubtle border border-border text-muted flex items-center gap-1.5"><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>{(res.tokens_in + res.tokens_out).toLocaleString()}</span>
                        <span className="px-2 py-1 rounded bg-bgSubtle border border-border text-muted flex items-center gap-1.5"><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>${res.cost_usd.toFixed(4)}</span>
                      </div>
                    )}
                  </div>

                  <MemberCard
                    member={member}
                    response={res}
                    lifecycle={lifecycle}
                    streamingContent={streamingContents?.[member.member_id] || ''}
                    tokensGenerated={memberExecutionStates?.[member.member_id]?.tokens_generated || 0}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Tablet/Desktop Tabs View (>=768px) */}
      <div className="hidden md:flex flex-col h-full bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
        <div
          ref={tablistRef}
          role="tablist"
          aria-label="Council Member responses"
          className="flex flex-nowrap overflow-x-auto bg-bgSubtle border-b border-border hide-scrollbar"
        >
          {members.map((member, i) => {
            const res = responses.find((r) => r.member_id === member.member_id);
            const isActive = i === activeIndex;
            const isStreamingThis = streamingMemberIds?.has(member.member_id);
            const lifecycle = getLifecycle(member, res);
            const status = getMemberStatus(res, isStreamingThis, lifecycle);
            const hasError = status === 'failed' || status === 'excluded';

            return (
              <button
                key={member.member_id}
                id={`tab-${member.member_id}`}
                role="tab"
                aria-selected={isActive}
                aria-controls={`panel-${member.member_id}`}
                onClick={() => setActiveIndex(i)}
                className={`px-5 py-4 font-display text-sm flex items-center gap-3 transition-colors outline-none border-b-2 shrink-0
                  ${isActive 
                    ? `bg-surface border-b-primary text-foreground font-bold shadow-[0_-2px_0_0_transparent_inset]` 
                    : `border-b-transparent text-muted hover:bg-surface-hover hover:text-foreground`
                  }
                  ${hasError && !isActive ? 'border-b-red-500/50' : ''}`}
              >
                <ProviderBadge provider={member.provider} />
                <span className="truncate max-w-[150px] lg:max-w-[200px] text-left">{member.display_label || `Seat ${i + 1}`}</span>
                <StatusBadge status={status} />
              </button>
            );
          })}
        </div>

        <div
          id={`panel-${activeMember?.member_id}`}
          role="tabpanel"
          aria-labelledby={`tab-${activeMember?.member_id}`}
          className="flex-1 p-6 lg:p-8 animate-in fade-in duration-300 overflow-y-auto"
        >
          {activeMember && (
            <div className="flex flex-wrap items-center justify-between gap-4 mb-8 pb-4 border-b border-border">
              <div className="flex flex-col gap-1">
                <h3 className="font-display font-bold text-lg text-foreground">
                  {activeMember.display_label || `Council Seat ${activeIndex + 1}`}
                </h3>
                <p className="font-mono text-xs text-muted">
                  {activeMember.model_id}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {activeResponse && !activeResponse.error && (
                  <div className="flex items-center gap-2 mr-4">
                    <span className="px-2 py-1 rounded-md bg-bgSubtle border border-border text-xs font-mono text-muted flex items-center gap-1.5"><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>{activeResponse.latency_ms}ms</span>
                    <span className="px-2 py-1 rounded-md bg-bgSubtle border border-border text-xs font-mono text-muted flex items-center gap-1.5"><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>{(activeResponse.tokens_in + activeResponse.tokens_out).toLocaleString()} tok</span>
                    <span className="px-2 py-1 rounded-md bg-bgSubtle border border-border text-xs font-mono text-muted flex items-center gap-1.5"><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>${activeResponse.cost_usd.toFixed(4)}</span>
                  </div>
                )}
                <StatusBadge status={getMemberStatus(activeResponse, isStreaming, getLifecycle(activeMember, activeResponse))} />
              </div>
            </div>
          )}

          {activeMember && (
            <MemberCard
              member={activeMember}
              response={activeResponse}
              lifecycle={getLifecycle(activeMember, activeResponse)}
              streamingContent={streamingContents?.[activeMember.member_id] || ''}
              tokensGenerated={memberExecutionStates?.[activeMember.member_id]?.tokens_generated || 0}
            />
          )}
        </div>

        <div className="px-6 py-3 border-t border-border bg-bgSubtle text-[11px] text-muted flex items-center justify-between mt-auto">
          <span className="flex items-center gap-2">
            Use 
            <kbd className="px-1.5 py-0.5 border border-border shadow-sm rounded bg-surface font-mono font-bold text-foreground">[</kbd> 
            <kbd className="px-1.5 py-0.5 border border-border shadow-sm rounded bg-surface font-mono font-bold text-foreground">]</kbd> 
            to navigate members
          </span>
        </div>
      </div>
    </div>
  );
}
