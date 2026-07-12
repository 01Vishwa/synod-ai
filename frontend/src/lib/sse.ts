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
  | 'done';

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
export interface SseOptions {
  onStateDelta?: (state: Partial<CouncilState>) => void;
  onStageTransition?: (stage: CouncilState['stage']) => void;
  onMemberResponse?: (data: unknown) => void;
  onDashboardSpecUpdate?: (spec: Record<string, unknown>) => void;
  onError?: (error: unknown) => void;
  onDone?: () => void;
  onConnectionError?: (err: Event) => void;
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

    // Named event handlers (FastAPI/LangGraph may emit named events)
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
  });

  return sub;
}
