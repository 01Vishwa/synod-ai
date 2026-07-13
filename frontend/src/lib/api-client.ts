/**
 * Synod — Typed API Client
 * Wraps all FastAPI endpoints with full TypeScript types.
 * All API calls go through this module — never raw fetch() in components.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ─── Types ────────────────────────────────────────────────────────────────

export type Provider = 'openrouter' | 'nvidia_nim' | 'github_models';
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
}

export interface ModelInfo {
  id: string;
  name: string;
  context_length?: number;
  pricing?: { prompt: number; completion: number };
}

export interface CreateSessionRequest {
  user_query: string;
  members: Array<{ provider: Provider; model_id: string; display_label: string; role?: 'member' | 'chairman' }>;
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

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}/api/v1${path}`;
  
  // Always call getUser() first — it validates the session server-side and
  // triggers a token refresh if the current access_token is expired.
  // Then call getSession() to pick up the (potentially refreshed) access_token.
  await supabase.auth.getUser();
  const { data: { session } } = await supabase.auth.getSession();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> ?? {}),
  };

  if (session?.access_token) {
    headers['Authorization'] = `Bearer ${session.access_token}`;
  }

  const res = await fetch(url, {
    headers,
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, res.statusText, body);
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

  getStreamUrl: (sessionId: string) =>
    `${API_BASE}/api/v1/sessions/${sessionId}/stream`,
};

// ─── Providers ────────────────────────────────────────────────────────────

export const providersApi = {
  saveKey: (req: ProviderKeyRequest) =>
    apiFetch<{ ok: boolean }>('/providers', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  testConnection: (provider: Provider) =>
    apiFetch<TestConnectionResult>(`/providers/${provider}/test`, {
      method: 'POST',
      body: JSON.stringify({ api_key: "dummy" }), // Using test endpoint req schema
    }),

  listModels: (provider: Provider) =>
    apiFetch<ModelInfo[]>(`/providers/${provider}/models`),

  getConfiguredProviders: () =>
    apiFetch<Array<{ provider: Provider; configured: boolean }>>('/providers'), // we mapped this to GET /providers
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
