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

// ─── Stage Progress Bar ────────────────────────────────────────────────────

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
    <div className="flex items-center gap-2 mb-8 overflow-x-auto pb-2">
      {steps.map((step, i) => {
        const isPast = i < activeIndex;
        const isActive = i === activeIndex;
        const isFuture = i > activeIndex;

        return (
          <React.Fragment key={step.id}>
            <div
              className={`font-mono text-xs flex items-center gap-2 whitespace-nowrap transition-colors
                ${isFuture ? 'text-subtle' : 'text-foreground'}
                ${isActive ? 'font-bold' : 'font-normal'}
                ${isPast ? 'text-muted' : ''}`}
            >
              {step.label}
              {isActive && currentStage !== 'done' && currentStage !== 'error' && (
                <span className="text-[10px] animate-pulse">◌</span>
              )}
              {isPast && <span className="text-[10px]">✓</span>}
            </div>
            {i < steps.length - 1 && (
              <span className="text-subtle">→</span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ─── Loading Skeleton ──────────────────────────────────────────────────────

function SessionSkeleton() {
  return (
    <div className="max-w-[960px] mx-auto px-6 py-8">
      <div className="h-8 w-3/5 bg-grey-93 rounded animate-pulse mb-8" />
      <div className="h-4 w-2/5 bg-grey-93 rounded animate-pulse mb-8" />
      <div className="h-[300px] bg-grey-93 rounded animate-pulse" />
    </div>
  );
}

// ─── Error State ───────────────────────────────────────────────────────────

function SessionError({ error, refetch }: { error: string; refetch: () => void }) {
  return (
    <div className="max-w-[960px] mx-auto px-6 py-8">
      <div className="bg-background border-2 border-black rounded-md p-6">
        <h2 className="text-xl font-display font-bold mb-2">Failed to load session</h2>
        <p className="text-muted mb-4">{error}</p>
        <button
          className="bg-black text-white px-6 py-3 border-2 border-black font-semibold text-sm rounded hover:bg-grey-10 transition-colors"
          onClick={refetch}
        >
          Retry
        </button>
      </div>
    </div>
  );
}

// ─── Page Component ────────────────────────────────────────────────────────

export default function SessionPage({ params }: { params: { sessionId: string } }) {
  const { state, status, stage, error, totalCostUsd, totalTokens, refetch } =
    useCouncilSession(params.sessionId);
  const dashboardSpec = useDashboardSpec(state);

  if (status === 'loading' && !state) {
    return <SessionSkeleton />;
  }

  if (status === 'error' && !state) {
    return <SessionError error={error ?? 'Unknown error'} refetch={refetch} />;
  }

  if (!state) return null;

  // Determine which members are still waiting on Stage 1 responses
  const streamingMemberIds = new Set<string>();
  if (stage === 'stage_1') {
    state.members.forEach((m) => {
      const hasResponse = state.stage_1_responses.some((r) => r.member_id === m.member_id);
      if (!hasResponse) streamingMemberIds.add(m.member_id);
    });
  }

  const isActive = stage !== 'done' && stage !== 'error';

  return (
    <div className="max-w-[960px] mx-auto px-6 py-8">
      {/* Session Header */}
      <div className="flex justify-between items-start mb-6">
        <div className="flex-1 pr-6">
          <h1 className="font-display text-2xl sm:text-3xl font-bold leading-snug mb-2">
            {state.user_query}
          </h1>
          <div className="font-mono text-xs text-subtle">
            Session ID: {state.session_id} • {new Date(state.created_at).toLocaleString()}
            {isActive && (
              <span className="ml-3 inline-flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-black animate-pulse" />
                Live
              </span>
            )}
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
          className="border-2 border-black rounded-md p-6 mb-8"
        >
          <h3 className="text-xl font-display font-bold mb-2">Session Halted</h3>
          <p className="text-muted m-0">
            {error || 'All Council Members failed during execution.'}
          </p>
        </div>
      )}

      {/* Research Digest (shown if present) */}
      {state.research_digest && (
        <section aria-labelledby="research-heading" className="mb-8">
          <h2 id="research-heading" className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
            Research Context
          </h2>
          <div className="bg-grey-93 border border-border rounded-md p-4">
            <p className="text-sm text-foreground mb-3 font-medium">
              {state.research_digest.summary}
            </p>
            <div className="flex flex-col gap-1">
              {state.research_digest.sources.slice(0, 5).map((src, i) => (
                <a
                  key={i}
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-muted underline hover:text-foreground transition-colors font-mono truncate"
                >
                  [{i + 1}] {src.title || src.url}
                </a>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Main Content Area — stages reveal as they complete */}
      <div className="flex flex-col gap-12">
        {/* Stage 1 — always visible once started */}
        <section aria-labelledby="stage1-heading">
          <h2 id="stage1-heading" className="sr-only">First Opinions</h2>
          <MemberTabs
            members={state.members}
            responses={state.stage_1_responses}
            streamingMemberIds={streamingMemberIds}
          />
        </section>

        {/* Stage 2 — peer reviews */}
        {(stage === 'stage_2' ||
          stage === 'stage_3' ||
          stage === 'archiving' ||
          stage === 'done' ||
          (stage === 'error' && state.stage_2_responses.length > 0)) && (
          <section aria-labelledby="stage2-heading">
            <RankingTable
              rankings={state.rankings}
              aggregateScores={state.aggregate_scores}
              members={state.members}
              anonymizationMap={state.anonymization_map}
            />
          </section>
        )}

        {/* Stage 3 — chairman synthesis */}
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

        {/* Dashboard Region */}
        {dashboardSpec && (
          <section
            aria-labelledby="dashboard-heading"
            className="border-t border-border pt-8"
          >
            <h2 id="dashboard-heading" className="sr-only">Session Metrics</h2>
            <DashboardRenderer spec={dashboardSpec} />
          </section>
        )}
      </div>
    </div>
  );
}
