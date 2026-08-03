'use client';

/**
 * useCouncilSession — subscribes to a council session's SSE stream.
 * Exposes current stage, state, loading/error status, and cost totals.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { sessionsApi, type CouncilState, type Stage, type CouncilMemberConfig, type MemberLifecycle } from '@/lib/api-client';

export type SessionStatus = 'loading' | 'streaming' | 'done' | 'error';

export interface LiveSessionState extends CouncilState {
  memberLifecycles: Record<string, MemberLifecycle>;
  streamingContent: Record<string, string>;
  chairmanStreamingContent: string;
  peerReviewProgress?: { completed: number; total: number };
}

function emptyCouncilState(): CouncilState {
  return {
    session_id: '',
    trace_id: '',
    user_query: '',
    stage: 'stage_1',
    research_enabled: false,
    members: [],
    stage_1_responses: [],
    anonymization_map: {},
    stage_2_responses: [],
    rankings: [],
    aggregate_scores: {},
    chairman_member_id: '',
    citations: [],
    errors: [],
    created_at: '',
    updated_at: '',
    member_execution_states: {},
  };
}

const initialLiveState = (members: CouncilMemberConfig[]): LiveSessionState => ({
  ...emptyCouncilState(),
  memberLifecycles: Object.fromEntries(
    members.map(m => [m.member_id, 'queued'])
  ),
  streamingContent: {},
  chairmanStreamingContent: '',
});

function mergeArrays(existing: any[], incoming: any[]): any[] {
  const merged = [...existing];
  for (const item of incoming) {
    if (item && typeof item === 'object' && ('member_id' in item || 'ranked_by_member_id' in item)) {
      const idKey = 'member_id' in item ? 'member_id' : 'ranked_by_member_id';
      const idx = merged.findIndex(x => x[idKey] === item[idKey]);
      if (idx >= 0) merged[idx] = item;
      else merged.push(item);
    } else {
      merged.push(item);
    }
  }
  return merged;
}

export interface UseCouncilSessionResult {
  state: LiveSessionState | null;
  status: SessionStatus;
  stage: Stage | null;
  error: string | null;
  totalCostUsd: number;
  totalTokens: number;
  refetch: () => void;
  isConnected: boolean;
}

export function useCouncilSession(
  sessionId: string | null,
  initialMembers: CouncilMemberConfig[] = []
): UseCouncilSessionResult {
  // Seed state immediately from pre-fetched member configs so the page
  // renders cards without waiting for the GET /sessions/:id round-trip.
  const [state, setState] = useState<LiveSessionState | null>(
    initialMembers.length > 0 ? initialLiveState(initialMembers) : null
  );
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const startStream = useCallback(async (id: string) => {
    setStatus('loading');
    setError(null);
    setIsConnected(false);

    try {
      const initial = await sessionsApi.get(id);
      
      const liveInitial: LiveSessionState = {
        ...initialLiveState(initial.members || []),
        ...initial,
        memberLifecycles: Object.fromEntries((initial.members || []).map(m => [m.member_id, 'queued'])),
        streamingContent: {},
        chairmanStreamingContent: '',
      };
      
      setState(liveInitial);

      if (initial.stage === 'done' || initial.stage === 'error') {
        setStatus(initial.stage === 'error' ? 'error' : 'done');
        return;
      }

      setStatus('streaming');
      const streamUrl = await sessionsApi.getStreamUrl(id);
      
      if (esRef.current) {
        esRef.current.close();
      }

      const es = new EventSource(streamUrl);
      esRef.current = es;
      
      es.onopen = () => setIsConnected(true);

      const eventTypes = [
        'state_snapshot', 'state_delta',
        'member.queued', 'member.started', 'member.connecting', 'member.first_token',
        'member.stream_chunk', 'member.completed', 'member.failed',
        'peer_review.started', 'peer_review.progress', 'ranking.updated',
        'chairman.started', 'chairman.stream_chunk', 'chairman.completed',
        'session.completed', 'session.failed', 'session.stream_timeout',
        'error', 'done'
      ];

      eventTypes.forEach(type => {
        es.addEventListener(type, (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data);
            setState(prev => {
              if (!prev) return prev;
              const next = { ...prev };

              if (type === 'state_snapshot' || type === 'state_delta') {
                for (const [k, v] of Object.entries(data)) {
                  if (Array.isArray(v)) {
                    (next as any)[k] = mergeArrays((prev as any)[k] || [], v);
                  } else if (v !== undefined) {
                    (next as any)[k] = v;
                  }
                }
              }
              else if (type === 'member.queued') {
                next.memberLifecycles = { ...next.memberLifecycles, [data.member_id]: 'queued' };
              }
              else if (type === 'member.connecting') {
                next.memberLifecycles = { ...next.memberLifecycles, [data.member_id]: 'connecting' };
              }
              else if (type === 'member.first_token') {
                next.memberLifecycles = { ...next.memberLifecycles, [data.member_id]: 'streaming' };
              }
              else if (type === 'member.stream_chunk') {
                next.streamingContent = {
                  ...next.streamingContent,
                  [data.member_id]: (next.streamingContent[data.member_id] || '') + data.delta
                };
                const execState = next.member_execution_states?.[data.member_id] || { 
                   lifecycle: 'streaming', tokens_generated: 0, elapsed_ms: 0 
                };
                next.member_execution_states = {
                  ...next.member_execution_states,
                  [data.member_id]: {
                    ...execState,
                    tokens_generated: (execState.tokens_generated || 0) + 1
                  }
                };
              }
              else if (type === 'member.completed') {
                next.memberLifecycles = { ...next.memberLifecycles, [data.member_id]: 'completed' };
                next.streamingContent = { ...next.streamingContent };
                delete next.streamingContent[data.member_id];
              }
              else if (type === 'member.failed') {
                next.memberLifecycles = { ...next.memberLifecycles, [data.member_id]: 'failed' };
              }
              else if (type === 'peer_review.progress') {
                next.peerReviewProgress = { completed: data.completed, total: data.total };
              }
              else if (type === 'ranking.updated') {
                if (data.rankings) next.rankings = mergeArrays(next.rankings || [], data.rankings);
                if (data.aggregate_scores) next.aggregate_scores = { ...next.aggregate_scores, ...data.aggregate_scores };
              }
              else if (type === 'chairman.stream_chunk') {
                next.chairmanStreamingContent = (next.chairmanStreamingContent || '') + data.delta;
              }
              else if (type === 'chairman.completed') {
                next.final_report_md = next.chairmanStreamingContent;
                next.chairmanStreamingContent = '';
              }
              else if (type === 'session.completed' || type === 'done') {
                next.stage = 'done';
                setStatus('done');
                es.close();
                setIsConnected(false);
              }
              else if (type === 'session.failed') {
                next.stage = 'error';
                setStatus('error');
                if (data.error?.message) setError(data.error.message);
                es.close();
                setIsConnected(false);
              }
              else if (type === 'session.stream_timeout') {
                setStatus('error');
                setError(data.error?.message || 'Stream timed out');
                es.close();
                setIsConnected(false);
              }
              else if (type === 'error') {
                setStatus('error');
                setError(data.message || 'Unknown error');
                es.close();
                setIsConnected(false);
              }

              return next;
            });
          } catch (err) {
            // ignore JSON parse errors
          }
        });
      });

      es.onerror = (e) => {
        if (es.readyState === EventSource.CLOSED) {
          setIsConnected(false);
        }
      };

    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Failed to load session.');
      setIsConnected(false);
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    startStream(sessionId);

    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [sessionId, startStream]);

  const totalCostUsd = state
    ? [
        ...(state.stage_1_responses || []),
        ...(state.stage_2_responses || []),
      ].reduce((sum, r) => sum + (r.cost_usd ?? 0), 0)
    : 0;

  const totalTokens = state
    ? [
        ...(state.stage_1_responses || []),
        ...(state.stage_2_responses || []),
      ].reduce((sum, r) => sum + (r.tokens_in ?? 0) + (r.tokens_out ?? 0), 0)
    : 0;

  return {
    state,
    status,
    stage: state?.stage ?? null,
    error,
    totalCostUsd,
    totalTokens,
    refetch: () => { if (sessionId) startStream(sessionId); },
    isConnected,
  };
}
