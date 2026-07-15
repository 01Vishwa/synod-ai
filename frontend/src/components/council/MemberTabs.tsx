'use client';

/**
 * MemberTabs — Stage 1 tab view.
 * One tab per Council Member, each streaming its independent answer.
 * Keyboard navigable: [ / ] to move between tabs.
 */

import React, { useState, useEffect, useRef } from 'react';
import type { CouncilMemberConfig, MemberResponse } from '@/lib/api-client';

interface MemberTabsProps {
  members: CouncilMemberConfig[];
  responses: MemberResponse[];
  streamingMemberIds?: Set<string>;
}

// ─── Error Classification (PRD §12.6) ─────────────────────────────────────
// PRD §12.6: partial/degraded state must name the error *class*
// (timeout / auth / rate-limit), never just a raw message or bare spinner.

type ErrorClass = 'timeout' | 'auth' | 'rate-limit' | 'unknown';

function classifyError(errorStr: string): ErrorClass {
  const lower = errorStr.toLowerCase();
  if (
    lower.includes('timeout') ||
    lower.includes('timed out') ||
    lower.includes('time out') ||
    lower.includes('deadline exceeded') ||
    lower.includes('connection reset')
  ) return 'timeout';
  if (
    lower.includes('auth') ||
    lower.includes('unauthorized') ||
    lower.includes('403') ||
    lower.includes('401') ||
    lower.includes('invalid key') ||
    lower.includes('invalid api key') ||
    lower.includes('permission denied') ||
    lower.includes('forbidden')
  ) return 'auth';
  if (
    lower.includes('rate') ||
    lower.includes('429') ||
    lower.includes('quota') ||
    lower.includes('throttl') ||
    lower.includes('too many requests') ||
    lower.includes('requests per minute')
  ) return 'rate-limit';
  return 'unknown';
}

function ErrorClassBadge({ errorClass }: { errorClass: ErrorClass }) {
  return (
    <span
      className="font-mono text-xs font-bold px-2 py-px border-2 border-black rounded-sm uppercase"
      aria-label={`Error class: ${errorClass}`}
    >
      {errorClass}
    </span>
  );
}

function StatusLabel({ response }: { response?: MemberResponse }) {
  if (!response) {
    return (
      <span className="text-subtle" style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
        ○ Waiting
      </span>
    );
  }
  if (response.error) {
    return (
      <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
        ✕ Failed
      </span>
    );
  }
  return (
    <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
      ✓ Done
    </span>
  );
}

function ProviderBadge({ provider }: { provider: string }) {
  const labels: Record<string, string> = {
    openrouter: 'OR',
    nvidia_nim: 'NIM',
  };
  return (
    <span
      className="badge badge-muted"
      title={provider}
      style={{ fontSize: '10px' }}
    >
      {labels[provider] ?? provider.slice(0, 2).toUpperCase()}
    </span>
  );
}

export function MemberTabs({ members, responses, streamingMemberIds }: MemberTabsProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  const tablistRef = useRef<HTMLDivElement>(null);

  // Keyboard navigation: [ to go left, ] to go right
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.key === '[') {
        setActiveIndex((i) => Math.max(0, i - 1));
      }
      if (e.key === ']') {
        setActiveIndex((i) => Math.min(members.length - 1, i + 1));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [members.length]);

  if (members.length === 0) {
    return (
      <div style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--color-text-subtle)' }}>
        No Council Members configured.
      </div>
    );
  }

  const activeResponse = responses.find(
    (r) => r.member_id === members[activeIndex]?.member_id,
  );
  const activeMember = members[activeIndex];
  const isStreaming = activeMember && streamingMemberIds?.has(activeMember.member_id);

  return (
    <div>
      {/* Mobile Accordion View (<768px) */}
      <div className="md:hidden flex flex-col gap-2">
        {members.map((member, i) => {
          const res = responses.find((r) => r.member_id === member.member_id);
          const isActive = i === activeIndex;
          const hasError = !!res?.error;
          const isStreamingThis = streamingMemberIds?.has(member.member_id);

          return (
            <div key={member.member_id} className={`border ${hasError ? 'border-2 border-black' : 'border-border'} rounded-md overflow-hidden bg-background`}>
              <button
                onClick={() => setActiveIndex(isActive ? -1 : i)}
                className={`w-full flex items-center justify-between px-4 py-3 font-display text-sm transition-colors ${isActive ? 'bg-grey-93 font-bold text-black' : 'text-muted hover:bg-grey-93'}`}
                aria-expanded={isActive}
              >
                <div className="flex items-center gap-2">
                  <ProviderBadge provider={member.provider} />
                  <span>{member.display_label || `Seat ${i + 1}`}</span>
                  {isStreamingThis && <span className="text-[10px] font-mono animate-pulse">◌</span>}
                  {res && !isStreamingThis && !hasError && <span className="text-[10px]">✓</span>}
                  {hasError && <span className="text-[10px] font-bold">✕</span>}
                </div>
                <span className="text-xs">{isActive ? '−' : '+'}</span>
              </button>
              
              {isActive && (
                <div className="p-4 border-t border-border animate-fade-in">
                  {/* Member info bar */}
                  <div className="flex items-center justify-between mb-4 pb-3 border-b border-border">
                    <div className="flex items-center gap-3">
                      <span className="font-display font-bold text-sm">
                        {member.display_label || `Council Seat ${i + 1}`}
                      </span>
                      <span className="badge badge-muted font-mono text-[11px]">
                        {member.model_id}
                      </span>
                    </div>
                    <div className="flex items-center gap-4">
                      <StatusLabel response={res} />
                      {res && !res.error && (
                        <>
                          <span className="text-[11px] font-mono text-subtle">{res.latency_ms}ms</span>
                          <span className="text-[11px] font-mono text-subtle">{(res.tokens_in + res.tokens_out).toLocaleString()} tok</span>
                          <span className="text-[11px] font-mono text-subtle">${res.cost_usd.toFixed(5)}</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Content */}
                  {!res && !isStreamingThis && (
                    <div>
                      <div className="h-4 w-4/5 bg-grey-93 rounded animate-pulse mb-3" />
                      <div className="h-4 w-[95%] bg-grey-93 rounded animate-pulse mb-3" />
                      <div className="h-4 w-[70%] bg-grey-93 rounded animate-pulse mb-3" />
                      <p className="mt-3 text-sm text-subtle">Waiting for Council Seat {i + 1}…</p>
                    </div>
                  )}

                  {res?.error && (
                    <div role="alert" className="border-2 border-black rounded-md p-6">
                      <div className="flex items-center gap-3 mb-2">
                        <p className="font-bold">✕ Failed — excluded from ranking</p>
                        <ErrorClassBadge errorClass={classifyError(res.error)} />
                      </div>
                      <p className="font-mono text-sm text-muted">{res.error}</p>
                      <p className="text-xs text-subtle mt-3 mb-0">
                        This member will be excluded from the Stage 2 peer review and aggregate ranking.
                        The council will proceed with the remaining members.
                      </p>
                    </div>
                  )}

                  {res && !res.error && (
                    <div
                      className="prose max-w-none text-sm"
                      dangerouslySetInnerHTML={{ __html: res.content }}
                    />
                  )}

                  {isStreamingThis && !res?.content && (
                    <div className="flex items-center gap-2 text-subtle text-sm">
                      <span className="font-mono animate-pulse">◌</span>
                      Streaming response…
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Tablet/Desktop Tabs View (>=768px) */}
      <div className="hidden md:block">
        {/* Tab strip */}
        <div
          ref={tablistRef}
          role="tablist"
          aria-label="Council Member responses"
          className="flex gap-1 border-b-2 border-border overflow-x-auto p-0"
        >
          {members.map((member, i) => {
            const res = responses.find((r) => r.member_id === member.member_id);
            const isActive = i === activeIndex;
            const hasError = !!res?.error;
            const isStreamingThis = streamingMemberIds?.has(member.member_id);

            return (
              <button
                key={member.member_id}
                id={`tab-${member.member_id}`}
                role="tab"
                aria-selected={isActive}
                aria-controls={`panel-${member.member_id}`}
                onClick={() => setActiveIndex(i)}
                className={`px-4 py-2 font-display text-sm flex items-center gap-2 -mb-[2px] transition-colors whitespace-nowrap outline-none border-b-2 border-t-2
                  ${isActive ? 'font-bold border-b-black text-black border-t-transparent' : 'font-normal border-b-transparent text-muted hover:text-black hover:border-b-grey-85'}
                  ${hasError && !isActive ? 'border-t-black' : 'border-t-transparent'}`}
              >
                <ProviderBadge provider={member.provider} />
                <span>{member.display_label || `Seat ${i + 1}`}</span>
                {isStreamingThis && <span className="text-[10px] font-mono animate-pulse">◌</span>}
                {res && !isStreamingThis && !hasError && <span className="text-[10px]">✓</span>}
                {hasError && <span className="text-[10px] font-bold">✕</span>}
              </button>
            );
          })}
        </div>

        {/* Tab panel */}
        <div
          id={`panel-${activeMember?.member_id}`}
          role="tabpanel"
          aria-labelledby={`tab-${activeMember?.member_id}`}
          className="p-6 animate-fade-in"
        >
          {/* Member info bar */}
          {activeMember && (
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-border">
              <div className="flex items-center gap-3">
                <span className="font-display font-bold text-sm">
                  {activeMember.display_label || `Council Seat ${activeIndex + 1}`}
                </span>
                <span className="badge badge-muted font-mono text-[11px]">
                  {activeMember.model_id}
                </span>
              </div>
              <div className="flex items-center gap-4">
                <StatusLabel response={activeResponse} />
                {activeResponse && !activeResponse.error && (
                  <>
                    <span className="text-[11px] font-mono text-subtle">{activeResponse.latency_ms}ms</span>
                    <span className="text-[11px] font-mono text-subtle">{(activeResponse.tokens_in + activeResponse.tokens_out).toLocaleString()} tok</span>
                    <span className="text-[11px] font-mono text-subtle">${activeResponse.cost_usd.toFixed(5)}</span>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Content */}
          {!activeResponse && !isStreaming && (
            <div>
              <div className="h-4 w-4/5 bg-grey-93 rounded animate-pulse mb-3" />
              <div className="h-4 w-[95%] bg-grey-93 rounded animate-pulse mb-3" />
              <div className="h-4 w-[70%] bg-grey-93 rounded animate-pulse mb-3" />
              <p className="mt-3 text-sm text-subtle">Waiting for Council Seat {activeIndex + 1}…</p>
            </div>
          )}

          {activeResponse?.error && (
            <div role="alert" className="border-2 border-black rounded-md p-6">
              <div className="flex items-center gap-3 mb-2">
                <p className="font-bold">✕ Failed — excluded from ranking</p>
                <ErrorClassBadge errorClass={classifyError(activeResponse.error)} />
              </div>
              <p className="font-mono text-sm text-muted">{activeResponse.error}</p>
              <p className="text-xs text-subtle mt-3 mb-0">
                This member will be excluded from the Stage 2 peer review and aggregate ranking.
                The council will proceed with the remaining members.
              </p>
            </div>
          )}

          {activeResponse && !activeResponse.error && (
            <div
              className="prose max-w-none text-sm"
              dangerouslySetInnerHTML={{ __html: activeResponse.content }}
            />
          )}

          {isStreaming && !activeResponse?.content && (
            <div className="flex items-center gap-2 text-subtle text-sm">
              <span className="font-mono animate-pulse">◌</span>
              Streaming response…
            </div>
          )}
        </div>

        {/* Keyboard hint */}
        <div className="px-6 py-2 border-t border-border text-[11px] text-subtle font-mono">
          Use <kbd className="px-1 border border-border rounded-[2px]">[</kbd> / <kbd className="px-1 border border-border rounded-[2px]">]</kbd> to navigate tabs
        </div>
      </div>
    </div>
  );
}
