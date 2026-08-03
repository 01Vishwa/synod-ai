/**
 * Synod — Typed API Client
 * Wraps all FastAPI endpoints with full TypeScript types.
 * All API calls go through this module — never raw fetch() in components.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ─── Types ────────────────────────────────────────────────────────────────

export type Provider = 'openrouter' | 'nvidia_nim';
export type ResearchProvider = 'tavily' | 'anakin';
export type Stage = 'stage_1' | 'stage_2' | 'stage_3' | 'archiving' | 'done' | 'error';

export interface CouncilMemberConfig {
  member_id: string;
  provider: Provider;
  model_id: string;
  display_label: string;
  role: 'member' | 'chairman';
}

export interface MemberResponse {
  member_id: string;
  stage: 'stage_1' | 'stage_2';
  content: string;
  anonymized_label?: string;
  latency_ms: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  error?: string;
  error_class?: string;
}

export interface RankingEntry {
  ranked_by_member_id: string;
  ranking_order: string[];
  justification: string;
}

export interface ResearchDigest {
  provider: ResearchProvider;
  query_terms: string[];
  sources: Array<{ url: string; title: string; snippet: string; retrieved_at: string }>;
  summary: string;
}

export type MemberLifecycle =
  | 'queued'
  | 'initializing'
  | 'connecting'
  | 'waiting_first_token'
  | 'streaming'
  | 'completed'
  | 'failed'
  | 'timeout';

export interface MemberExecutionState {
  lifecycle: MemberLifecycle;
  tokens_generated: number;
  elapsed_ms: number;
  first_token_ms?: number;
}

export interface CouncilState {
  session_id: string;
  trace_id: string;
  user_query: string;
  stage: Stage;
  research_enabled: boolean;
  research_provider?: ResearchProvider;
  research_digest?: ResearchDigest;
  dashboard_spec?: Record<string, unknown>;
  members: CouncilMemberConfig[];
  stage_1_responses: MemberResponse[];
  anonymization_map: Record<string, string>;
  stage_2_responses: MemberResponse[];
  rankings: RankingEntry[];
  aggregate_scores: Record<string, number>;
  chairman_member_id: string;
  final_report_md?: string;
  citations: Array<Record<string, unknown>>;
  notion_page_url?: string;
  errors: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
  session_status?: string;
  stage_1_status?: string;
  stage_2_status?: string;
  stage_3_status?: string;
  terminal_error?: { code: string; message: string };
  successful_member_ids?: string[];
  excluded_member_ids?: string[];
  effective_chairman_id?: string;

  // Client-side only — not persisted to DB
  member_execution_states?: Record<string, MemberExecutionState>;
  streaming_content?: Record<string, string>;   // member_id → live buffer
  chairman_streaming_content?: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  publisher: string;
  is_free: boolean;
  capabilities: string[];
}

export interface CreateSessionRequest {
  user_query: string;
  members: Array<{ member_id: string; provider: Provider; model_id: string; display_label: string; role?: 'member' | 'chairman' }>;
  chairman_member_id?: string;
  research_enabled: boolean;
  research_provider?: ResearchProvider;
  archive_to_notion: boolean;
}

export interface SessionSummary {
  session_id: string;
  user_query: string;
  stage: Stage;
  created_at: string;
  updated_at: string;
  member_count: number;
  total_cost_usd: number;
  notion_page_url?: string;
  trace_id: string;
  headline?: string;
}

export interface ProviderKeyResponse {
  id: string;
  provider: Provider;
  key_fingerprint: string;
  last_test_ok?: boolean;
  last_tested_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ProviderKeyRequest {
  provider: Provider;
  api_key: string;
}

export interface TestConnectionResult {
  success: boolean;
  message: string;
  latency_ms?: number;
}

// ─── HTTP Helper ──────────────────────────────────────────────────────────

import { supabase } from '@/lib/supabase/client';
import { mapApiError } from '@/lib/errors';

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}/api/v1${path}`;
  
  // Always call getUser() first — it validates the session server-side and
  // triggers a token refresh if the current access_token is expired.
  // Then call getSession() to pick up the (potentially refreshed) access_token.
  await supabase.auth.getUser();
  const { data, error } = await supabase.auth.getSession();

  if (error?.code === 'refresh_token_not_found' || error?.message?.includes('Refresh Token')) {
    window.location.href = '/?auth=required';
    throw new Error('Session expired');
  }

  if (error || !data.session?.access_token) {
    throw new Error('Not authenticated');
  }

  const { session } = data;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> ?? {}),
  };

  if (session?.access_token) {
    headers['Authorization'] = `Bearer ${session.access_token}`;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      headers,
      ...options,
    });
  } catch (error) {
    throw mapApiError(error);
  }

  if (!res.ok) {
    const body = await res.text();
    throw mapApiError(new ApiError(res.status, res.statusText, body));
  }

  if (res.status === 204) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: string,
  ) {
    super(`API ${status} ${statusText}: ${body}`);
    this.name = 'ApiError';
  }
}

export interface SessionListResponse {
  items: SessionSummary[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Council Sessions ─────────────────────────────────────────────────────

export const sessionsApi = {
  create: (req: CreateSessionRequest) =>
    apiFetch<CouncilState>('/sessions', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  get: (sessionId: string) =>
    apiFetch<CouncilState>(`/sessions/${sessionId}`),

  list: () =>
    apiFetch<SessionListResponse>('/sessions'),

  getStreamUrl: async (sessionId: string): Promise<string> => {
    // EventSource (browser SSE) cannot send Authorization headers, so we
    // pass the JWT as a query parameter instead. The backend SSE endpoint
    // accepts ?token=<jwt> via the CurrentUserIdSse dependency.
    await supabase.auth.getUser(); // refresh token if expired
    const { data, error } = await supabase.auth.getSession();

    if (error?.code === 'refresh_token_not_found' || error?.message?.includes('Refresh Token')) {
      window.location.href = '/?auth=required';
      throw new Error('Session expired');
    }

    const { session } = data;
    const base = `${API_BASE}/api/v1/sessions/${sessionId}/stream`;
    return session?.access_token
      ? `${base}?token=${encodeURIComponent(session.access_token)}`
      : base;
  },
};

// ─── Providers ────────────────────────────────────────────────────────────

export const providersApi = {
  saveKey: (req: ProviderKeyRequest, options?: RequestInit) =>
    apiFetch<{ ok: boolean }>('/providers', {
      method: 'POST',
      body: JSON.stringify(req),
      ...options,
    }),

  testConnection: (provider: Provider) =>
    apiFetch<TestConnectionResult>(`/providers/${provider}/test`, {
      method: 'POST',
      body: JSON.stringify({ api_key: "dummy" }), // Using test endpoint req schema
    }),

  listModels: async (provider: Provider) => {
    const res = await apiFetch<{ items: ModelInfo[] }>(`/providers/${provider}/models`);
    return res.items;
  },

  getConfiguredProviders: () =>
    apiFetch<Array<ProviderKeyResponse>>('/providers'),

  deleteKey: (provider: Provider) =>
    apiFetch<void>(`/providers/${provider}`, { method: 'DELETE' }),
};

// ─── Integrations ─────────────────────────────────────────────────────────

export const integrationsApi = {
  getStatus: async () => {
    const [researchRes, notionRes] = await Promise.allSettled([
      apiFetch<any[]>('/research/keys'),
      apiFetch<any>('/notion/status')
    ]);

    const researchKeys = researchRes.status === 'fulfilled' ? researchRes.value : [];
    const notionConnected = notionRes.status === 'fulfilled';

    return {
      research: {
        tavily: researchKeys.some(k => k.provider === 'tavily'),
        anakin: researchKeys.some(k => k.provider === 'anakin'),
      },
      notion: { connected: notionConnected },
      langfuse: { connected: false },
    };
  },

  saveResearchKey: (provider: ResearchProvider, api_key: string) =>
    apiFetch<{ ok: boolean }>(`/research/keys`, {
      method: 'POST',
      body: JSON.stringify({ provider, api_key }),
    }),

  testResearchConnection: (provider: ResearchProvider) =>
    apiFetch<TestConnectionResult>(`/research/keys/${provider}/test`, {
      method: 'POST',
      body: JSON.stringify({ api_key: "dummy" }),
    }),

  connectNotion: () =>
    apiFetch<{ auth_url: string }>('/notion/connect', { method: 'POST' }),

  publishToNotion: (sessionId: string) =>
    apiFetch<{ notion_page_url: string }>(`/notion/publish/${sessionId}`, {
      method: 'POST',
    }),

    saveLangfuseKeys: (public_key: string, secret_key: string, host?: string) =>
    apiFetch<{ ok: boolean }>('/observability/keys', {
      method: 'POST',
      body: JSON.stringify({ public_key, secret_key, host }),
    }),
};

export const researchApi = {
  saveKey: (body: { provider: string; api_key: string }) =>
    apiFetch<void>('/research/keys', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  testKey: (provider: string) =>
    apiFetch<{ success: boolean; message: string }>(`/research/keys/${provider}/test`, {
      method: 'POST',
      body: JSON.stringify({ api_key: "dummy" }),
    }),
  getKeys: async () => {
    const keys = await apiFetch<Array<{ provider: string; key_fingerprint: string; last_test_ok?: boolean }>>('/research/keys');
    return keys.map(k => ({
      provider: k.provider,
      has_key: true,
      fingerprint: k.key_fingerprint,
      last_test_ok: k.last_test_ok,
    }));
  },
};


// ─── Observability ────────────────────────────────────────────────────────

export const observabilityApi = {
  getTraceUrl: (traceId: string) =>
    `${API_BASE}/api/v1/observability/trace/${traceId}`,
};

// ─── System ───────────────────────────────────────────────────────────────

export const systemApi = {
  checkHealth: async () => {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error('Backend not reachable');
    return res.json() as Promise<{ status: string }>;
  }
};
