'use client';

/**
 * useCouncilSession — subscribes to a council session's SSE stream.
 * Exposes current stage, state, loading/error status, and cost totals.
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { sessionsApi, type CouncilState, type Stage } from '@/lib/api-client';
import { createSessionStream, type SseSubscription } from '@/lib/sse';

export type SessionStatus = 'loading' | 'streaming' | 'done' | 'error';

export interface UseCouncilSessionResult {
  state: CouncilState | null;
  status: SessionStatus;
  stage: Stage | null;
  error: string | null;
  totalCostUsd: number;
  totalTokens: number;
  refetch: () => void;
}

export function useCouncilSession(sessionId: string | null): UseCouncilSessionResult {
  const [state, setState] = useState<CouncilState | null>(null);
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [error, setError] = useState<string | null>(null);
  const subRef = useRef<SseSubscription | null>(null);

  const startStream = useCallback(async (id: string) => {
    setStatus('loading');
    setError(null);

    try {
      // 1. Fetch current state snapshot
      const initial = await sessionsApi.get(id);
      setState(initial);

      // If already done, no need to stream
      if (initial.stage === 'done' || initial.stage === 'error') {
        setStatus(initial.stage === 'error' ? 'error' : 'done');
        return;
      }

      setStatus('streaming');

      // 2. Subscribe to SSE deltas
      const streamUrl = sessionsApi.getStreamUrl(id);
      subRef.current?.unsubscribe();
      subRef.current = createSessionStream(
        id,
        streamUrl,
        initial,
        (updated) => {
          setState(updated);
          if (updated.stage === 'done') setStatus('done');
          if (updated.stage === 'error') {
            setStatus('error');
            const lastError = updated.errors?.[updated.errors.length - 1];
            setError(
              typeof lastError === 'object' && lastError !== null && 'message' in lastError
                ? String((lastError as Record<string, unknown>).message)
                : 'An unexpected error occurred. Check your provider keys in Settings.',
            );
          }
        },
        (err) => {
          console.error('[useCouncilSession] SSE error:', err);
          setError('Connection to the session stream was interrupted. Retrying…');
        },
      );
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Failed to load session.');
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    startStream(sessionId);

    return () => {
      subRef.current?.unsubscribe();
      subRef.current = null;
    };
  }, [sessionId, startStream]);

  // Compute derived cost/token totals
  const totalCostUsd = state
    ? [
        ...state.stage_1_responses,
        ...state.stage_2_responses,
      ].reduce((sum, r) => sum + (r.cost_usd ?? 0), 0)
    : 0;

  const totalTokens = state
    ? [
        ...state.stage_1_responses,
        ...state.stage_2_responses,
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
  };
}
