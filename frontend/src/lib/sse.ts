/**
 * Synod — SSE (Server-Sent Events) subscription helper
 * Client-side Observer pattern. Subscribes to CouncilState delta stream
 * and emits typed events to handlers.
 */

import type { CouncilState } from './api-client';

export type SseEventType =
  | 'state_delta'
  | 'stage_transition'
  | 'member_response'
  | 'dashboard_spec_update'
  | 'error'
  | 'done'
  // Structured terminal events emitted by the backend (Phase 3 fix)
  | 'session.failed'
  | 'session.completed'
  | 'session.stream_timeout'
  | 'member.queued'
  | 'member.started'
  | 'member.connecting'
  | 'member.first_token'
  | 'member.stream_chunk'
  | 'member.completed'
  | 'member.failed'
  | 'peer_review.started'
  | 'peer_review.progress'
  | 'ranking.updated'
  | 'chairman.started'
  | 'chairman.stream_chunk'
  | 'chairman.completed'
  | 'state_snapshot';

export interface SseEvent<T = unknown> {
  type: SseEventType;
  data: T;
  session_id: string;
  timestamp: string;
}

export type SseHandler<T = unknown> = (event: SseEvent<T>) => void;

export interface SseSubscription {
  unsubscribe: () => void;
}

/**
 * Subscribe to a council session's SSE stream.
 * Returns an unsubscribe function.
 *
 * @example
 * const sub = subscribeToSession(url, {
 *   onStateDelta: (state) => setSession(state),
 *   onError: (err) => console.error(err),
 * });
 * // cleanup
 * sub.unsubscribe();
 */
export interface SessionFailedPayload {
  session_id: string;
  stage: string;
  state: string;
  error: { code: string; message: string };
}

export interface SessionStreamTimeoutPayload {
  session_id: string;
  stage: string;
  error: { code: string; message: string };
}

export interface SseOptions {
  onStateDelta?: (state: Partial<CouncilState>) => void;
  onStageTransition?: (stage: CouncilState['stage']) => void;
  onMemberResponse?: (data: unknown) => void;
  onDashboardSpecUpdate?: (spec: Record<string, unknown>) => void;
  onError?: (error: unknown) => void;
  onDone?: () => void;
  onConnectionError?: (err: Event) => void;
  /** Emitted when stage=error is committed to DB and SSE stream terminates */
  onSessionFailed?: (payload: SessionFailedPayload) => void;
  /** Emitted when stage=done and session is complete */
  onSessionCompleted?: () => void;
  /** Emitted when SSE idle timeout is reached without a state change */
  onStreamTimeout?: (payload: SessionStreamTimeoutPayload) => void;
}

export function subscribeToSession(
  streamUrl: string,
  options: SseOptions,
): SseSubscription {
  let es: EventSource | null = null;
  let closed = false;

  function connect() {
    if (closed) return;

    es = new EventSource(streamUrl);

    // Generic message handler for JSON-encoded events
    es.onmessage = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data as string) as SseEvent;

        switch (parsed.type) {
          case 'state_delta':
            options.onStateDelta?.(parsed.data as Partial<CouncilState>);
            break;
          case 'stage_transition':
            options.onStageTransition?.(parsed.data as CouncilState['stage']);
            break;
          case 'member_response':
            options.onMemberResponse?.(parsed.data);
            break;
          case 'dashboard_spec_update':
            options.onDashboardSpecUpdate?.(parsed.data as Record<string, unknown>);
            break;
          case 'error':
            options.onError?.(parsed.data);
            break;
          case 'done':
            options.onDone?.();
            es?.close();
            break;
        }
      } catch {
        // non-JSON ping or heartbeat line — ignore
      }
    };

    // Named event handlers (sse_starlette emits named events)
    es.addEventListener('state_delta', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string) as Partial<CouncilState>;
        options.onStateDelta?.(data);
      } catch { /* ignore */ }
    });

    es.addEventListener('done', () => {
      options.onDone?.();
      es?.close();
    });

    // ── Structured terminal events (Phase 3 backend fix) ─────────────────
    es.addEventListener('session.failed', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data as string) as SessionFailedPayload;
        options.onSessionFailed?.(payload);
      } catch { /* ignore */ }
      es?.close();
    });

    es.addEventListener('session.completed', () => {
      options.onSessionCompleted?.();
      es?.close();
    });

    es.addEventListener('session.stream_timeout', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data as string) as SessionStreamTimeoutPayload;
        options.onStreamTimeout?.(payload);
      } catch { /* ignore */ }
      es?.close();
    });

    es.onerror = (err) => {
      options.onConnectionError?.(err);
      // EventSource auto-reconnects on transient errors.
      // If the stream ends (server closes), it will error here — don't reconnect.
      if (es?.readyState === EventSource.CLOSED) {
        es = null;
      }
    };
  }

  connect();

  return {
    unsubscribe() {
      closed = true;
      es?.close();
      es = null;
    },
  };
}

/**
 * Convenience: read the full current state via GET, then subscribe to deltas.
 * Merges deltas into a running state object and calls onUpdate on each change.
 */
export function createSessionStream(
  sessionId: string,
  streamUrl: string,
  initialState: CouncilState,
  onUpdate: (state: CouncilState) => void,
  onError?: (err: unknown) => void,
): SseSubscription {
  let state: CouncilState = { ...initialState };

  const sub = subscribeToSession(streamUrl, {
    onStateDelta: (delta) => {
      state = { ...state, ...delta };
      onUpdate(state);
    },
    onStageTransition: (stage) => {
      state = { ...state, stage };
      onUpdate(state);
    },
    onDashboardSpecUpdate: (spec) => {
      state = { ...state, dashboard_spec: spec };
      onUpdate(state);
    },
    onError: onError,
    onDone: () => {
      onUpdate(state);
    },
    // Structured terminal events — merge into state so the UI can react
    onSessionFailed: (payload) => {
      state = { ...state, stage: 'error' as CouncilState['stage'] };
      onUpdate(state);
      onError?.(new Error(payload.error.message));
    },
    onSessionCompleted: () => {
      state = { ...state, stage: 'done' as CouncilState['stage'] };
      onUpdate(state);
    },
    onStreamTimeout: (payload) => {
      // Stream timed out — treat as an error so the UI stops spinning
      onError?.(new Error(payload.error.message));
    },
  });

  return sub;
}
