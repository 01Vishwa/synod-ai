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
    openrouter:    'OR',
    nvidia_nim:    'NIM',
    github_models: 'GH',
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
      {/* Tab strip */}
      <div
        ref={tablistRef}
        role="tablist"
        aria-label="Council Member responses"
        style={{
          display: 'flex',
          gap: 'var(--space-1)',
          borderBottom: '2px solid var(--color-border)',
          overflowX: 'auto',
          padding: '0 0 0 0',
        }}
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
              style={{
                padding: 'var(--space-2) var(--space-4)',
                fontFamily: 'var(--font-display)',
                fontSize: 'var(--text-sm)',
                fontWeight: isActive ? 700 : 400,
                border: 'none',
                borderBottom: isActive
                  ? '2px solid var(--grey-0)'
                  : '2px solid transparent',
                borderTop: hasError && !isActive ? '2px solid var(--grey-0)' : 'none',
                background: 'transparent',
                color: isActive ? 'var(--grey-0)' : 'var(--color-text-muted)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                marginBottom: '-2px',
                transition: 'color var(--transition-fast), border-color var(--transition-fast)',
                whiteSpace: 'nowrap',
                position: 'relative',
              }}
            >
              <ProviderBadge provider={member.provider} />
              <span>{member.display_label || `Seat ${i + 1}`}</span>
              {isStreamingThis && (
                <span style={{ fontSize: '10px', fontFamily: 'var(--font-mono)' }}>◌</span>
              )}
              {res && !isStreamingThis && !hasError && (
                <span style={{ fontSize: '10px' }}>✓</span>
              )}
              {hasError && (
                <span style={{ fontSize: '10px', fontWeight: 700 }}>✕</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab panel */}
      <div
        id={`panel-${activeMember?.member_id}`}
        role="tabpanel"
        aria-labelledby={`tab-${activeMember?.member_id}`}
        style={{
          padding: 'var(--space-6)',
          animation: 'fadeIn 150ms ease',
        }}
      >
        {/* Member info bar */}
        {activeMember && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 'var(--space-4)',
              paddingBottom: 'var(--space-3)',
              borderBottom: '1px solid var(--color-border)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
              <span
                style={{
                  fontFamily: 'var(--font-display)',
                  fontWeight: 700,
                  fontSize: 'var(--text-sm)',
                }}
              >
                {activeMember.display_label || `Council Seat ${activeIndex + 1}`}
              </span>
              <span className="badge badge-muted" style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                {activeMember.model_id}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
              <StatusLabel response={activeResponse} />
              {activeResponse && !activeResponse.error && (
                <>
                  <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-text-subtle)' }}>
                    {activeResponse.latency_ms}ms
                  </span>
                  <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-text-subtle)' }}>
                    {(activeResponse.tokens_in + activeResponse.tokens_out).toLocaleString()} tok
                  </span>
                  <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--color-text-subtle)' }}>
                    ${activeResponse.cost_usd.toFixed(5)}
                  </span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Content */}
        {!activeResponse && !isStreaming && (
          <div>
            <div className="skeleton" style={{ height: '16px', width: '80%', marginBottom: '12px' }} />
            <div className="skeleton" style={{ height: '16px', width: '95%', marginBottom: '12px' }} />
            <div className="skeleton" style={{ height: '16px', width: '70%', marginBottom: '12px' }} />
            <p style={{ marginTop: 'var(--space-3)', fontSize: 'var(--text-sm)', color: 'var(--color-text-subtle)' }}>
              Waiting for Council Seat {activeIndex + 1}…
            </p>
          </div>
        )}

        {activeResponse?.error && (
          <div
            role="alert"
            style={{
              border: '2px solid var(--grey-0)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-6)',
            }}
          >
            <p style={{ fontWeight: 700, marginBottom: 'var(--space-2)' }}>
              ✕ Failed — excluded from ranking
            </p>
            <p style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
              {activeResponse.error}
            </p>
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', marginTop: 'var(--space-3)', marginBottom: 0 }}>
              This member will be excluded from the Stage 2 peer review and aggregate ranking.
              The council will proceed with the remaining members.
            </p>
          </div>
        )}

        {activeResponse && !activeResponse.error && (
          <div
            className="prose"
            style={{ maxWidth: '100%' }}
            dangerouslySetInnerHTML={{ __html: activeResponse.content }}
          />
        )}

        {isStreaming && !activeResponse?.content && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', color: 'var(--color-text-subtle)', fontSize: 'var(--text-sm)' }}>
            <span style={{ fontFamily: 'var(--font-mono)' }}>◌</span>
            Streaming response…
          </div>
        )}
      </div>

      {/* Keyboard hint */}
      <div
        style={{
          padding: 'var(--space-2) var(--space-6)',
          borderTop: '1px solid var(--color-border)',
          fontSize: '11px',
          color: 'var(--color-text-subtle)',
          fontFamily: 'var(--font-mono)',
        }}
      >
        Use <kbd style={{ padding: '0 3px', border: '1px solid var(--color-border)', borderRadius: '2px' }}>[</kbd>{' '}
        / <kbd style={{ padding: '0 3px', border: '1px solid var(--color-border)', borderRadius: '2px' }}>]</kbd>{' '}
        to navigate tabs
      </div>
    </div>
  );
}
