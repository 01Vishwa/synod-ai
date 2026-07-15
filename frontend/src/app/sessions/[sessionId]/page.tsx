'use client';

import React from 'react';
import Link from 'next/link';
import { useCouncilSession } from '@/hooks/useCouncilSession';
import { useDashboardSpec } from '@/hooks/useDashboardSpec';
import { MemberTabs } from '@/components/council/MemberTabs';
import { RankingTable } from '@/components/council/RankingTable';
import { ChairmanReport } from '@/components/council/ChairmanReport';
import { DashboardRenderer } from '@/components/dashboard/DashboardRenderer';
import { CostMeter } from '@/components/council/CostMeter';
import type { Stage } from '@/lib/api-client';

// ─── Stage Progress Bar ────────────────────────────────────────────────────

function StageStrip({ currentStage, viewStage, onViewChange }: { currentStage: Stage | null, viewStage: Stage | null, onViewChange: (s: Stage) => void }) {
  const steps: {id: Stage, label: string}[] = [
    { id: 'stage_1', label: '① First Opinions' },
    { id: 'stage_2', label: '② Peer Review' },
    { id: 'stage_3', label: '③ Chairman Report' },
  ];

  const getStageIndex = (s: Stage | null) => {
    if (s === 'done' || s === 'archiving') return 2;
    if (s === 'error') return -1;
    return steps.findIndex((step) => step.id === s);
  };

  const activeIndex = Math.max(0, getStageIndex(currentStage));
  const viewIndex = Math.max(0, getStageIndex(viewStage || currentStage));

  return (
    <div className="flex items-center gap-2 mb-8 overflow-x-auto pb-2 col-span-12" role="tablist">
      {steps.map((step, i) => {
        const isPastOrCurrent = i <= activeIndex;
        const isSelected = i === viewIndex;
        const isFuture = i > activeIndex;

        return (
          <React.Fragment key={step.id}>
            <button
              role="tab"
              aria-selected={isSelected}
              aria-disabled={isFuture}
              disabled={isFuture}
              onClick={() => isPastOrCurrent && onViewChange(step.id)}
              className={`font-mono text-xs flex items-center gap-2 whitespace-nowrap transition-colors outline-none
                ${isFuture ? 'text-subtle cursor-not-allowed' : 'text-foreground cursor-pointer hover:bg-grey-93 rounded px-2 py-1 -ml-2'}
                ${isSelected ? 'font-bold' : 'font-normal'}
                ${isPastOrCurrent && !isSelected ? 'text-muted' : ''}`}
            >
              {step.label}
              {i === activeIndex && currentStage !== 'done' && currentStage !== 'error' && (
                <span className="text-[10px] animate-pulse">◌</span>
              )}
              {i < activeIndex && <span className="text-[10px]">✓</span>}
            </button>
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
  
  const [viewStage, setViewStage] = React.useState<Stage | null>(null);

  // Auto-advance view stage when real stage progresses
  const previousStageRef = React.useRef<Stage | null>(null);
  React.useEffect(() => {
    if (stage && stage !== previousStageRef.current) {
       setViewStage(stage === 'done' || stage === 'archiving' ? 'stage_3' : stage);
       previousStageRef.current = stage;
    }
  }, [stage]);

  if (status === 'loading' && !state) {
    return <SessionSkeleton />;
  }

  if (status === 'error' && !state) {
    return <SessionError error={error ?? 'Unknown error'} refetch={refetch} />;
  }

  if (!state) return null;

  // Determine which members are still waiting on Stage 1 responses.
  // Guard against members being undefined: this can happen transiently if the
  // background graph crashes before the initial state is fully persisted.
  const members = state.members ?? [];
  const streamingMemberIds = new Set<string>();
  // Only mark members as streaming when the session is actively running stage_1.
  // On terminal error/timeout, clear all streaming indicators immediately.
  if (stage === 'stage_1' && status === 'streaming') {
    members.forEach((m) => {
      const hasResponse = (state.stage_1_responses ?? []).some((r) => r.member_id === m.member_id);
      if (!hasResponse) streamingMemberIds.add(m.member_id);
    });
  }

  const isActive = stage !== 'done' && stage !== 'error';
  
  const currentView = viewStage || (stage === 'done' || stage === 'archiving' ? 'stage_3' : stage);

  return (
    <div className="max-w-[960px] mx-auto px-6 py-8 grid grid-cols-12 gap-x-6">
      {/* Session Header */}
      <div className="col-span-12 flex justify-between items-start mb-6">
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

      <StageStrip currentStage={stage} viewStage={viewStage} onViewChange={setViewStage} />

      {/* Structural Error Banner — shown when the backend graph crashed before
          populating members (i.e. the state blob arrived incomplete). */}
      {!state.members && (
        <div
          role="alert"
          className="col-span-12 border-2 border-black rounded-md p-6 mb-8"
        >
          <h3 className="text-xl font-display font-bold mb-2">Session failed to start</h3>
          <p className="text-muted m-0">
            The council session could not be initialised. The server encountered
            an error before any members were assigned. Please create a new session.
          </p>
        </div>
      )}

      {/* Global Error Banner */}
      {state.session_status === 'failed' && state.terminal_error?.code === 'NO_VALID_STAGE_1_RESPONSES' ? (
        <div
          role="alert"
          className="col-span-12 border-2 border-black rounded-md p-6 mb-8 bg-grey-93"
        >
          <h3 className="text-xl font-display font-bold mb-2">Council stopped</h3>
          <p className="text-muted mb-4">
            All Council members failed because the OpenRouter credential was rejected. Update and validate your OpenRouter API key in Settings, then start a new Council session.
          </p>
          <Link
            href="/settings"
            className="inline-block bg-black text-white font-semibold px-4 py-2 rounded text-sm hover:bg-grey-10 transition-colors"
          >
            Go to Settings
          </Link>
        </div>
      ) : (status === 'error' || state.session_status === 'failed' || state.stage === 'error') && (
        <div
          role="alert"
          className="col-span-12 border-2 border-black rounded-md p-6 mb-8"
        >
          <h3 className="text-xl font-display font-bold mb-2">Session Halted</h3>
          <p className="text-muted m-0">
            {state.terminal_error?.message || error || 'All Council Members failed during execution.'}
          </p>
        </div>
      )}

      {/* Research Digest (shown if present) */}
      {state.research_digest && (
        <section aria-labelledby="research-heading" className="col-span-12 mb-8">
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

      {/* Main Content Area — strictly stage-gated navigation */}
      <div className="col-span-12 flex flex-col gap-12">
        
        {currentView === 'stage_1' && (
          <section aria-labelledby="stage1-heading">
            <h2 id="stage1-heading" className="sr-only">First Opinions</h2>
            <MemberTabs
              members={members}
              responses={state.stage_1_responses ?? []}
              streamingMemberIds={streamingMemberIds}
            />
          </section>
        )}

        {currentView === 'stage_2' && (
          <section aria-labelledby="stage2-heading">
            <RankingTable
              rankings={state.rankings ?? []}
              aggregateScores={state.aggregate_scores ?? {}}
              members={members}
              anonymizationMap={state.anonymization_map ?? {}}
              stage2Status={state.stage_2_status}
              sessionStatus={state.session_status}
            />
          </section>
        )}

        {currentView === 'stage_3' && (
          <section aria-labelledby="stage3-heading">
            <ChairmanReport
              reportMd={state.final_report_md ?? ''}
              citations={state.citations ?? []}
              members={members}
              stage1Responses={state.stage_1_responses ?? []}
              aggregateScores={state.aggregate_scores ?? {}}
              chairmanMemberId={state.chairman_member_id ?? ''}
              notionPageUrl={state.notion_page_url}
              traceId={state.trace_id}
              stage3Status={state.stage_3_status}
              sessionStatus={state.session_status}
              excludedMemberIds={state.excluded_member_ids}
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
