'use client';

import React from 'react';
import { useCouncilSession } from '@/hooks/useCouncilSession';
import { useDashboardSpec } from '@/hooks/useDashboardSpec';
import { MemberTabs } from '@/components/council/MemberTabs';
import { RankingTable } from '@/components/council/RankingTable';
import { ChairmanReport } from '@/components/council/ChairmanReport';
import { DashboardRenderer } from '@/components/dashboard/DashboardRenderer';
import { CostMeter } from '@/components/council/CostMeter';
import type { Stage } from '@/lib/api-client';

function StageStrip({ currentStage }: { currentStage: Stage | null }) {
  const steps = [
    { id: 'stage_1', label: '① First Opinions' },
    { id: 'stage_2', label: '② Peer Review' },
    { id: 'stage_3', label: '③ Chairman Report' },
  ];

  const currentIndex = steps.findIndex((s) => s.id === currentStage);
  const activeIndex =
    currentStage === 'done' || currentStage === 'archiving' ? 2 : Math.max(0, currentIndex);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        marginBottom: 'var(--space-8)',
        overflowX: 'auto',
        paddingBottom: 'var(--space-2)',
      }}
    >
      {steps.map((step, i) => {
        const isPast = i < activeIndex;
        const isActive = i === activeIndex;
        const isFuture = i > activeIndex;

        return (
          <React.Fragment key={step.id}>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                fontWeight: isActive ? 700 : 400,
                color: isFuture ? 'var(--color-text-subtle)' : 'var(--color-text)',
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                whiteSpace: 'nowrap',
              }}
            >
              {step.label}
              {isActive && currentStage !== 'done' && currentStage !== 'error' && (
                <span style={{ fontSize: '10px' }}>◌</span>
              )}
            </div>
            {i < steps.length - 1 && (
              <span style={{ color: 'var(--color-text-subtle)' }}>→</span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

export default function SessionPage({ params }: { params: { sessionId: string } }) {
  const { state, status, stage, error, totalCostUsd, totalTokens, refetch } = useCouncilSession(params.sessionId);
  const dashboardSpec = useDashboardSpec(state);

  if (status === 'loading' && !state) {
    return (
      <div style={{ maxWidth: 'var(--content-max)', margin: '0 auto', padding: 'var(--space-8) var(--content-gutter)' }}>
        <div className="skeleton" style={{ height: '32px', width: '60%', marginBottom: 'var(--space-8)' }} />
        <div className="skeleton" style={{ height: '16px', width: '40%', marginBottom: 'var(--space-8)' }} />
        <div className="skeleton" style={{ height: '300px' }} />
      </div>
    );
  }

  if (status === 'error' && !state) {
    return (
      <div style={{ maxWidth: 'var(--content-max)', margin: '0 auto', padding: 'var(--space-8) var(--content-gutter)' }}>
        <div className="card" style={{ borderColor: 'var(--grey-0)' }}>
          <h2 style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-2)' }}>Failed to load session</h2>
          <p style={{ color: 'var(--color-text-muted)' }}>{error}</p>
          <button className="btn-primary" onClick={refetch} style={{ marginTop: 'var(--space-4)' }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!state) return null;

  // Determine streaming members for Stage 1 tab loading indicators
  const streamingMemberIds = new Set<string>();
  if (stage === 'stage_1') {
    state.members.forEach((m) => {
      const hasResponse = state.stage_1_responses.some((r) => r.member_id === m.member_id);
      if (!hasResponse) streamingMemberIds.add(m.member_id);
    });
  }

  return (
    <div style={{ maxWidth: 'var(--content-max)', margin: '0 auto', padding: 'var(--space-8) var(--content-gutter)' }}>
      {/* Session Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-6)' }}>
        <div style={{ flex: 1, paddingRight: 'var(--space-6)' }}>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-2xl)',
              fontWeight: 700,
              lineHeight: 1.3,
              marginBottom: 'var(--space-2)',
            }}
          >
            {state.user_query}
          </h1>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)' }}>
            Session ID: {state.session_id} • {new Date(state.created_at).toLocaleString()}
          </div>
        </div>
        <div>
          <CostMeter totalCostUsd={totalCostUsd} totalTokens={totalTokens} stage={stage} />
        </div>
      </div>

      <StageStrip currentStage={stage} />

      {/* Global Error Banner */}
      {status === 'error' && state.stage === 'error' && (
        <div
          role="alert"
          style={{
            border: '2px solid var(--grey-0)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-6)',
            marginBottom: 'var(--space-8)',
          }}
        >
          <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-2)' }}>Session Halted</h3>
          <p style={{ color: 'var(--color-text-muted)', marginBottom: 0 }}>
            {error || 'All Council Members failed during execution.'}
          </p>
        </div>
      )}

      {/* Main Content Area based on Stage */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-12)' }}>
        {/* Stage 1 is always visible once it has started */}
        <section aria-labelledby="stage1-heading">
          <h2 id="stage1-heading" className="sr-only">First Opinions</h2>
          <MemberTabs
            members={state.members}
            responses={state.stage_1_responses}
            streamingMemberIds={streamingMemberIds}
          />
        </section>

        {/* Stage 2 & 3 become visible as they are reached */}
        {(stage === 'stage_2' || stage === 'stage_3' || stage === 'archiving' || stage === 'done' || (stage === 'error' && state.stage_2_responses.length > 0)) && (
          <section aria-labelledby="stage2-heading">
            <RankingTable
              rankings={state.rankings}
              aggregateScores={state.aggregate_scores}
              members={state.members}
              anonymizationMap={state.anonymization_map}
            />
          </section>
        )}

        {(stage === 'stage_3' || stage === 'archiving' || stage === 'done') && (
          <section aria-labelledby="stage3-heading">
            <ChairmanReport
              reportMd={state.final_report_md ?? ''}
              citations={state.citations}
              members={state.members}
              stage1Responses={state.stage_1_responses}
              aggregateScores={state.aggregate_scores}
              chairmanMemberId={state.chairman_member_id}
              notionPageUrl={state.notion_page_url}
              traceId={state.trace_id}
            />
          </section>
        )}

        {/* Dashboard Region (rendered if backend emits a spec) */}
        {dashboardSpec && (
          <section
            aria-labelledby="dashboard-heading"
            style={{
              borderTop: '1px solid var(--color-border)',
              paddingTop: 'var(--space-8)',
            }}
          >
            <h2 id="dashboard-heading" className="sr-only">Session Metrics</h2>
            <DashboardRenderer spec={dashboardSpec} />
          </section>
        )}
      </div>
    </div>
  );
}
