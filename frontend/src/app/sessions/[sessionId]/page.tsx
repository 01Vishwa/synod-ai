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
import { TimelineStep, type StepState } from '@/components/ui/TimelineStep';
import { StatusBadge } from '@/components/ui/StatusBadge';
import type { CouncilMemberConfig, Stage } from '@/lib/api-client';

// ─── Stage Progress Bar ────────────────────────────────────────────────────

interface StageStripProps {
  currentStage: Stage | null;
  viewStage: Stage | null;
  onViewChange: (s: Stage) => void;
  stage1Completed: number;
  totalMembers: number;
  reviewsCompleted: number;
  isChairmanStreaming: boolean;
}

function StageStrip({
  currentStage,
  viewStage,
  onViewChange,
  stage1Completed,
  totalMembers,
  reviewsCompleted,
  isChairmanStreaming,
}: StageStripProps) {
  const getStageIndex = (s: Stage | null) => {
    if (s === 'done' || s === 'archiving') return 2;
    if (s === 'error') return -1;
    const order: Stage[] = ['stage_1', 'stage_2', 'stage_3'];
    return order.indexOf(s as Stage);
  };

  const activeIndex = Math.max(0, getStageIndex(currentStage));
  const viewIndex = Math.max(0, getStageIndex(viewStage || currentStage));
  const isGlobalError = currentStage === 'error';

  const steps: { id: Stage; label: string; progress: string | null }[] = [
    {
      id: 'stage_1',
      label: 'First Opinions',
      progress:
        currentStage === 'stage_1' && totalMembers > 0
          ? `${stage1Completed} of ${totalMembers} complete`
          : null,
    },
    {
      id: 'stage_2',
      label: 'Peer Review',
      progress:
        currentStage === 'stage_2' && totalMembers > 0
          ? `${reviewsCompleted} of ${totalMembers} reviews`
          : null,
    },
    {
      id: 'stage_3',
      label: 'Chairman Report',
      progress:
        currentStage === 'stage_3'
          ? isChairmanStreaming
            ? 'Generating...'
            : 'Complete'
          : null,
    },
  ];

  return (
    <div
      className="flex flex-wrap items-center gap-2 mb-8 w-full bg-surface border border-border p-2 sm:px-4 sm:py-3 rounded-xl shadow-sm"
      role="tablist"
    >
      {steps.map((step, i) => {
        const isPastOrCurrent = i <= activeIndex;
        const isSelected = i === viewIndex;
        const isActiveStep = i === activeIndex && currentStage !== 'done';

        let state: StepState = 'pending';
        if (isGlobalError && i === activeIndex) {
          state = 'failed';
        } else if (isSelected) {
          state = 'selected';
        } else if (isActiveStep) {
          state = 'running';
        } else if (isPastOrCurrent) {
          state = 'completed';
        }

        // Build the full label with inline progress text
        const isCompleted = isPastOrCurrent && !isActiveStep && !isSelected;
        const displayLabel = isCompleted
          ? `✓ ${step.label}`
          : step.progress
          ? `${step.label}  [${step.progress}]`
          : step.label;

        return (
          <TimelineStep
            key={step.id}
            label={displayLabel}
            state={state}
            isLast={i === steps.length - 1}
            onClick={() => isPastOrCurrent && onViewChange(step.id)}
          />
        );
      })}
    </div>
  );
}

// ─── Error State ───────────────────────────────────────────────────────────

function SessionError({ error, refetch }: { error: string; refetch: () => void }) {
  return (
    <div className="max-w-[1200px] mx-auto px-6 py-12 flex justify-center">
      <div className="bg-surface border border-black rounded-xl p-8 shadow-sm max-w-lg text-center w-full">
        <div className="w-12 h-12 bg-white border-2 border-black text-black rounded-full flex items-center justify-center mx-auto mb-4">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold mb-2 text-foreground">Failed to load session</h2>
        <p className="text-muted mb-6 text-sm">{error}</p>
        <button
          className="bg-primary text-primary-fg px-6 py-2.5 font-bold text-sm rounded-lg hover:bg-primary-hover transition-colors shadow-sm inline-flex items-center gap-2"
          onClick={refetch}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Retry
        </button>
      </div>
    </div>
  );
}

// ─── Page Component ────────────────────────────────────────────────────────

export default function SessionPage({ params }: { params: { sessionId: string } }) {
  const { sessionId } = params;

  // Read member configs written by the new-session form before navigation.
  // This allows member cards to render immediately without waiting for
  // the GET /sessions/:id HTTP round-trip.
  const [immediateMembers] = React.useState<CouncilMemberConfig[]>(() => {
    if (typeof window === 'undefined') return [];
    try {
      const raw = sessionStorage.getItem(`synod-session-members-${sessionId}`);
      if (raw) {
        sessionStorage.removeItem(`synod-session-members-${sessionId}`);
        return JSON.parse(raw) as CouncilMemberConfig[];
      }
    } catch {
      // ignore — corrupt or missing storage
    }
    return [];
  });

  const { state, status, stage, error, totalCostUsd, totalTokens, refetch } =
    useCouncilSession(sessionId, immediateMembers);
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

  // Hard error with no data at all — show error screen
  if (status === 'error' && !state) {
    return <SessionError error={error ?? 'Unknown error'} refetch={refetch} />;
  }

  // Use members from live state once available; fall back to immediateMembers
  // so member cards appear on the very first render.
  const members: CouncilMemberConfig[] =
    (state?.members?.length ? state.members : immediateMembers);

  const streamingMemberIds = new Set<string>();
  if (stage === 'stage_1' && status === 'streaming') {
    members.forEach((m) => {
      const hasResponse = (state?.stage_1_responses ?? []).some(
        (r) => r.member_id === m.member_id
      );
      if (!hasResponse) streamingMemberIds.add(m.member_id);
    });
  }

  // Stage-1 progress: count completed responses (those without a fatal error)
  const stage1Completed = (state?.stage_1_responses ?? []).filter(
    (r) => !r.error
  ).length;
  const totalMembersCount = members.length;
  const reviewsCompleted = state?.peerReviewProgress?.completed ?? 0;
  const isChairmanStreaming =
    state?.stage_3_status === 'running' && !state?.final_report_md;

  const isActive = stage !== 'done' && stage !== 'error';
  const currentView =
    viewStage ||
    (stage === 'done' || stage === 'archiving' ? 'stage_3' : stage);

  // Derive header fields — fall back gracefully while initial fetch is in-flight
  const userQuery = state?.user_query ?? '';
  const sessionIdDisplay = state?.session_id ?? sessionId;
  const createdAt = state?.created_at ? new Date(state.created_at).toLocaleString() : '';

  const isNoValidStage1 = state?.session_status === 'failed' && state?.terminal_error?.code === 'NO_VALID_STAGE_1_RESPONSES';
  let allAuthErrorProvider: string | null = null;
  const failedMembersData: Array<{ provider: string; model: string; errorClass: string; message: string }> = [];

  if (isNoValidStage1 && state?.stage_1_responses && state?.members) {
    let authErrorProvider: string | null = null;
    let allAuth = true;

    for (const resp of state.stage_1_responses) {
      if (resp.error) {
        const member = state.members.find(m => m.member_id === resp.member_id);
        const provider = member?.provider || 'Unknown';
        const model = member?.model_id || 'Unknown';
        const eClass = resp.error_class || 'UnknownError';
        
        failedMembersData.push({
          provider,
          model,
          errorClass: eClass,
          message: resp.error
        });

        if (eClass !== 'AuthenticationError') {
          allAuth = false;
        } else {
          if (!authErrorProvider) authErrorProvider = provider;
          else if (authErrorProvider !== provider) allAuth = false;
        }
      }
    }

    if (allAuth && authErrorProvider && failedMembersData.length > 0) {
      allAuthErrorProvider = authErrorProvider;
    }
  }

  return (
    <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-8 w-full flex flex-col animate-in fade-in duration-300">
      {/* Session Header */}
      <div className="flex flex-col lg:flex-row justify-between items-start gap-6 mb-8 w-full">
        <div className="flex-1 min-w-0">
          {userQuery ? (
            <h1 className="font-display text-2xl sm:text-3xl font-bold leading-tight mb-3 text-foreground break-words">
              {userQuery}
            </h1>
          ) : (
            <div className="h-10 w-3/4 bg-bgSubtle rounded-lg animate-pulse mb-3" />
          )}
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <StatusBadge status={isActive ? 'running' : stage === 'error' ? 'failed' : 'completed'} />
            <span className="font-mono text-muted border-l border-border pl-3 truncate">
              ID: {sessionIdDisplay}
            </span>
            {createdAt && (
              <span className="font-mono text-muted border-l border-border pl-3">
                {createdAt}
              </span>
            )}
          </div>
        </div>
        <div className="w-full lg:w-auto shrink-0">
          <CostMeter totalCostUsd={totalCostUsd} totalTokens={totalTokens} stage={stage} />
        </div>
      </div>

      <StageStrip
        currentStage={stage}
        viewStage={viewStage}
        onViewChange={setViewStage}
        stage1Completed={stage1Completed}
        totalMembers={totalMembersCount}
        reviewsCompleted={reviewsCompleted}
        isChairmanStreaming={isChairmanStreaming}
      />

      {state && !state.members && (
        <div
          role="alert"
          className="border-l-4 border-black bg-white rounded-xl p-6 mb-8 shadow-sm flex items-start gap-4"
        >
          <div className="text-black shrink-0 mt-0.5">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold mb-1 text-black font-medium">Session failed to start</h3>
            <p className="text-gray-700 m-0 text-sm">
              The council session could not be initialised. The server encountered
              an error before any members were assigned. Please create a new session.
            </p>
          </div>
        </div>
      )}

      {/* Global Error Banner */}
      {isNoValidStage1 ? (
        <div
          role="alert"
          className="border-l-4 border-black bg-white rounded-xl p-6 mb-8 shadow-sm flex items-start gap-4"
        >
          <div className="text-black shrink-0 mt-0.5">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className="w-full min-w-0">
            <h3 className="text-lg font-bold mb-1 text-black font-medium">Council Stopped</h3>
            {allAuthErrorProvider ? (
              <>
                <p className="text-gray-700 text-sm mb-4">
                  All Council members failed because the <span className="font-semibold">{allAuthErrorProvider}</span> credential was rejected. Update and
                  validate your {allAuthErrorProvider} API key in Settings, then start a new Council session.
                </p>
                <Link
                  href="/settings"
                  className="inline-flex bg-surface text-foreground font-bold px-4 py-2 rounded-lg text-sm hover:bg-surface-hover transition-colors border border-border shadow-sm"
                >
                  Go to Settings
                </Link>
              </>
            ) : (
              <>
                <p className="text-gray-700 text-sm mb-4">
                  All Council members failed to produce a valid response. Below is a breakdown of the errors encountered:
                </p>
                <div className="bg-bgSubtle rounded border border-border overflow-hidden mb-4 text-xs font-mono w-full max-w-full">
                  <div className="overflow-x-auto">
                    <table className="w-full text-left">
                      <thead className="bg-surface border-b border-border">
                        <tr>
                          <th className="px-3 py-2 font-semibold">Provider</th>
                          <th className="px-3 py-2 font-semibold">Model</th>
                          <th className="px-3 py-2 font-semibold">Error Class</th>
                          <th className="px-3 py-2 font-semibold min-w-[200px]">Message</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {failedMembersData.map((fm, idx) => (
                          <tr key={idx} className="bg-white">
                            <td className="px-3 py-2 whitespace-nowrap">{fm.provider}</td>
                            <td className="px-3 py-2 whitespace-nowrap text-muted">{fm.model}</td>
                            <td className="px-3 py-2 whitespace-nowrap text-red-600">{fm.errorClass}</td>
                            <td className="px-3 py-2 text-muted max-w-sm truncate" title={fm.message}>{fm.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <Link
                  href="/settings"
                  className="inline-flex bg-surface text-foreground font-bold px-4 py-2 rounded-lg text-sm hover:bg-surface-hover transition-colors border border-border shadow-sm"
                >
                  Check Settings
                </Link>
              </>
            )}
          </div>
        </div>
      ) : (status === 'error' ||
          state?.session_status === 'failed' ||
          state?.stage === 'error') && (
        <div
          role="alert"
          className="border-l-4 border-black bg-white rounded-xl p-6 mb-8 shadow-sm flex items-start gap-4"
        >
          <div className="text-black shrink-0 mt-0.5">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-bold mb-1 text-black font-medium">Session Halted</h3>
            <p className="text-gray-700 m-0 text-sm">
              {state?.terminal_error?.message || error || 'All Council Members failed during execution.'}
            </p>
          </div>
        </div>
      )}

      {/* Research Digest */}
      {state?.research_digest && (
        <section aria-labelledby="research-heading" className="mb-8 bg-surface border border-border rounded-xl shadow-sm overflow-hidden">
          <div className="px-5 py-3 border-b border-border bg-bgSubtle flex items-center gap-2">
            <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <h2 id="research-heading" className="text-xs font-bold text-muted uppercase tracking-wider">
              Research Context
            </h2>
          </div>
          <div className="p-5 flex flex-col lg:flex-row gap-6">
            <div className="flex-1">
              <p className="text-sm text-foreground m-0 font-medium leading-relaxed">
                {state.research_digest.summary}
              </p>
            </div>
            <div className="w-full lg:w-72 shrink-0 flex flex-col gap-2 bg-bgSubtle p-3 rounded-lg border border-border">
              <h4 className="text-[10px] font-bold text-subtle uppercase tracking-wider mb-1">Sources</h4>
              {state.research_digest.sources.slice(0, 5).map((src, i) => (
                <a
                  key={i}
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-muted hover:text-primary transition-colors font-mono flex items-center gap-2 truncate"
                >
                  <span className="shrink-0 text-[10px] bg-border px-1.5 py-0.5 rounded text-foreground">[{i + 1}]</span>
                  <span className="truncate">{src.title || src.url}</span>
                </a>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Main Content Area */}
      <div className="flex flex-col gap-12 flex-1">
        {currentView === 'stage_1' && (
          <section aria-labelledby="stage1-heading" className="flex-1 flex flex-col">
            <h2 id="stage1-heading" className="sr-only">First Opinions</h2>
            <MemberTabs
              members={members}
              responses={state?.stage_1_responses ?? []}
              streamingMemberIds={streamingMemberIds}
            />
          </section>
        )}

        {currentView === 'stage_2' && (
          <section aria-labelledby="stage2-heading" className="flex-1 flex flex-col">
            <h2 id="stage2-heading" className="sr-only">Peer Review</h2>
            <RankingTable
              rankings={state?.rankings ?? []}
              aggregateScores={state?.aggregate_scores ?? {}}
              members={members}
              anonymizationMap={state?.anonymization_map ?? {}}
              stage2Status={state?.stage_2_status}
              sessionStatus={state?.session_status}
              totalMembers={state?.peerReviewProgress?.total ?? totalMembersCount}
              reviewsCompleted={reviewsCompleted}
            />
          </section>
        )}

        {currentView === 'stage_3' && (
          <section aria-labelledby="stage3-heading" className="flex-1 flex flex-col">
            <h2 id="stage3-heading" className="sr-only">Chairman Report</h2>
            <ChairmanReport
              reportMd={state?.final_report_md ?? ''}
              citations={state?.citations ?? []}
              members={members}
              stage1Responses={state?.stage_1_responses ?? []}
              aggregateScores={state?.aggregate_scores ?? {}}
              chairmanMemberId={state?.chairman_member_id ?? ''}
              notionPageUrl={state?.notion_page_url}
              traceId={state?.trace_id}
              stage3Status={state?.stage_3_status}
              sessionStatus={state?.session_status}
              excludedMemberIds={state?.excluded_member_ids}
              chairmanStreamingContent={state?.chairmanStreamingContent ?? ''}
              isStreaming={isChairmanStreaming}
            />
          </section>
        )}

        {/* Dashboard Region */}
        {dashboardSpec && (
          <section
            aria-labelledby="dashboard-heading"
            className="border-t border-border pt-8 mt-4"
          >
            <h2 id="dashboard-heading" className="sr-only">Session Metrics</h2>
            <DashboardRenderer spec={dashboardSpec} />
          </section>
        )}
      </div>
    </div>
  );
}
