'use client';

/**
 * New Session Screen — the home page of Synod.
 * Allows the user to compose a query, pick Council Members, configure
 * optional research and Notion archiving, and convene the council.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import type { Provider, ResearchProvider, ModelInfo } from '@/lib/api-client';
import { sessionsApi, providersApi } from '@/lib/api-client';

// ─── Types ────────────────────────────────────────────────────────────────

interface SelectedMember {
  id: string;
  provider: Provider;
  model_id: string;
  display_label: string;
  role: 'member' | 'chairman';
}

const PROVIDERS: { value: Provider; label: string; desc: string }[] = [
  { value: 'openrouter',    label: 'OpenRouter',    desc: 'Access hundreds of models via one key' },
  { value: 'nvidia_nim',   label: 'NVIDIA NIM',    desc: 'Enterprise-grade NVIDIA hosted models' },
  { value: 'github_models', label: 'GitHub Models', desc: '⚠ Retiring July 30, 2026' },
];

function generateMemberId() {
  return `member_${Math.random().toString(36).slice(2, 9)}`;
}

// ─── Sub-components ───────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p
      style={{
        fontSize: 'var(--text-xs)',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        color: 'var(--color-text-subtle)',
        marginBottom: 'var(--space-2)',
      }}
    >
      {children}
    </p>
  );
}

interface MemberCardProps {
  member: SelectedMember;
  index: number;
  models: Record<Provider, ModelInfo[]>;
  loadingModels: Record<Provider, boolean>;
  onUpdate: (id: string, updates: Partial<SelectedMember>) => void;
  onRemove: (id: string) => void;
  onSetChairman: (id: string) => void;
  isChairman: boolean;
}

function MemberCard({
  member,
  index,
  models,
  loadingModels,
  onUpdate,
  onRemove,
  onSetChairman,
  isChairman,
}: MemberCardProps) {
  const providerModels = models[member.provider] ?? [];

  return (
    <div
      style={{
        border: isChairman ? '2px solid var(--grey-0)' : '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-4)',
        background: isChairman ? 'var(--grey-93)' : 'var(--color-bg)',
        transition: 'border-color var(--transition-fast)',
        animation: 'fadeIn 200ms ease',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--space-3)',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 700,
            fontSize: 'var(--text-sm)',
          }}
        >
          Council Seat {index + 1}
          {isChairman && (
            <span
              style={{
                marginLeft: 'var(--space-2)',
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                fontWeight: 400,
                padding: '1px 6px',
                border: '1px solid var(--grey-0)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              CHAIRMAN
            </span>
          )}
        </span>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          {!isChairman && (
            <button
              className="btn-ghost btn-sm"
              onClick={() => onSetChairman(member.id)}
              title="Set as Chairman"
              aria-label={`Set Council Seat ${index + 1} as Chairman`}
            >
              ★ Set Chairman
            </button>
          )}
          <button
            className="btn-ghost btn-sm"
            onClick={() => onRemove(member.id)}
            aria-label={`Remove Council Seat ${index + 1}`}
          >
            ✕
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
        {/* Provider */}
        <div>
          <label
            htmlFor={`provider-${member.id}`}
            style={{ fontSize: 'var(--text-xs)', fontWeight: 600, display: 'block', marginBottom: 'var(--space-1)' }}
          >
            Provider
          </label>
          <select
            id={`provider-${member.id}`}
            value={member.provider}
            onChange={(e) =>
              onUpdate(member.id, { provider: e.target.value as Provider, model_id: '' })
            }
          >
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        {/* Model */}
        <div>
          <label
            htmlFor={`model-${member.id}`}
            style={{ fontSize: 'var(--text-xs)', fontWeight: 600, display: 'block', marginBottom: 'var(--space-1)' }}
          >
            Model
          </label>
          {loadingModels[member.provider] ? (
            <div className="skeleton" style={{ height: '38px', borderRadius: 'var(--radius-sm)' }} />
          ) : (
            <select
              id={`model-${member.id}`}
              value={member.model_id}
              onChange={(e) => onUpdate(member.id, { model_id: e.target.value })}
            >
              <option value="">Select model…</option>
              {providerModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name || m.id}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Display label */}
      <div style={{ marginTop: 'var(--space-3)' }}>
        <label
          htmlFor={`label-${member.id}`}
          style={{ fontSize: 'var(--text-xs)', fontWeight: 600, display: 'block', marginBottom: 'var(--space-1)' }}
        >
          Display label (optional)
        </label>
        <input
          id={`label-${member.id}`}
          type="text"
          placeholder={`Council Seat ${index + 1}`}
          value={member.display_label}
          onChange={(e) => onUpdate(member.id, { display_label: e.target.value })}
        />
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────

export default function NewSessionPage() {
  const router = useRouter();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [query, setQuery] = useState('');
  const [members, setMembers] = useState<SelectedMember[]>([]);
  const [chairmanId, setChairmanId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [models, setModels] = useState<Record<Provider, ModelInfo[]>>({
    openrouter: [],
    nvidia_nim: [],
    github_models: [],
  });
  const [loadingModels, setLoadingModels] = useState<Record<Provider, boolean>>({
    openrouter: false,
    nvidia_nim: false,
    github_models: false,
  });

  // Fetch model catalog for a provider
  const fetchModels = useCallback(async (provider: Provider) => {
    if (models[provider].length > 0) return;
    setLoadingModels((prev) => ({ ...prev, [provider]: true }));
    try {
      const list = await providersApi.listModels(provider);
      setModels((prev) => ({ ...prev, [provider]: list }));
    } catch {
      // Provider not configured yet — show empty list with graceful message
    } finally {
      setLoadingModels((prev) => ({ ...prev, [provider]: false }));
    }
  }, [models]);

  // Auto-fetch models for all providers used by current members
  useEffect(() => {
    const providers = [...new Set(members.map((m) => m.provider))];
    providers.forEach(fetchModels);
  }, [members, fetchModels]);

  // Auto-grow textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.max(120, ta.scrollHeight)}px`;
  }, [query]);

  // Keyboard shortcut: Cmd/Ctrl+Enter to submit
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !submitting) {
        e.preventDefault();
        document.getElementById('convene-btn')?.click();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [submitting]);

  function addMember() {
    if (members.length >= 6) return;
    const id = generateMemberId();
    setMembers((prev) => [
      ...prev,
      { id, provider: 'openrouter', model_id: '', display_label: '', role: 'member' },
    ]);
    fetchModels('openrouter');
  }

  function updateMember(id: string, updates: Partial<SelectedMember>) {
    setMembers((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    );
    if (updates.provider) fetchModels(updates.provider);
  }

  function removeMember(id: string) {
    setMembers((prev) => prev.filter((m) => m.id !== id));
    if (chairmanId === id) setChairmanId(null);
  }

  function setChairman(id: string) {
    setChairmanId(id);
    setMembers((prev) =>
      prev.map((m) => ({ ...m, role: m.id === id ? 'chairman' : 'member' })),
    );
  }

  // Validation
  const configured = members.filter((m) => m.model_id);
  const canConvene = query.trim().length >= 10 && configured.length >= 3;
  const validationMessage =
    query.trim().length < 10
      ? 'Query must be at least 10 characters.'
      : configured.length < 3
      ? `Select at least 3 Council Members with a model. (${configured.length}/3 ready)`
      : null;

  async function handleConvene() {
    if (!canConvene || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const researchEnabled = localStorage.getItem('synod_research_enabled') === 'true';
      const researchProvider = (localStorage.getItem('synod_research_provider') || 'tavily') as ResearchProvider;
      const archiveToNotion = localStorage.getItem('synod_archive_notion') === 'true';

      const session = await sessionsApi.create({
        user_query: query.trim(),
        members: members
          .filter((m) => m.model_id)
          .map((m) => ({
            provider: m.provider,
            model_id: m.model_id,
            display_label: m.display_label || `Council Seat ${members.indexOf(m) + 1}`,
            role: m.role,
          })),
        chairman_member_id: chairmanId ?? undefined,
        research_enabled: researchEnabled,
        research_provider: researchEnabled ? researchProvider : undefined,
        archive_to_notion: archiveToNotion,
      });
      router.push(`/sessions/${session.session_id}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to start session. Check your API keys in Settings.');
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        maxWidth: 'var(--content-max)',
        margin: '0 auto',
        padding: 'var(--space-8) var(--content-gutter)',
      }}
    >
      {/* Page heading */}
      <div style={{ marginBottom: 'var(--space-8)' }}>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'var(--text-2xl)',
            fontWeight: 700,
            marginBottom: 'var(--space-2)',
          }}
        >
          Convene a New Council
        </h1>
        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', marginBottom: 0 }}>
          Submit one question. A panel of independent AI models will deliberate, critique each other anonymously, and synthesize a final answer.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>

        {/* ── Query Input ─── */}
        <section aria-labelledby="query-label">
          <SectionLabel>Your Question</SectionLabel>
          <label
            id="query-label"
            htmlFor="session-query"
            style={{ display: 'block', marginBottom: 'var(--space-2)', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}
          >
            The same query is sent to all Council Members simultaneously.
          </label>
          <textarea
            id="session-query"
            ref={textareaRef}
            placeholder="What question should the council deliberate on?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{
              minHeight: '120px',
              resize: 'none',
              fontFamily: 'var(--font-body)',
              lineHeight: 1.6,
              overflowY: 'hidden',
            }}
            aria-describedby="query-hint"
          />
          <p id="query-hint" style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', marginTop: 'var(--space-1)', marginBottom: 0 }}>
            Press <kbd style={{ fontFamily: 'var(--font-mono)', padding: '0 4px', border: '1px solid var(--color-border)', borderRadius: '3px' }}>⌘ Enter</kbd> to convene.
            {query.trim().length > 0 && (
              <span style={{ marginLeft: 'var(--space-2)' }}>{query.trim().length} characters</span>
            )}
          </p>
        </section>

        {/* ── Council Members ─── */}
        <section aria-labelledby="members-label">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 'var(--space-3)',
            }}
          >
            <div>
              <SectionLabel>Council Members</SectionLabel>
              <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', margin: 0 }}>
                Select 3–6 models from any provider. Each model reasons independently.
              </p>
            </div>
            <button
              id="add-member-btn"
              className="btn-secondary btn-sm"
              onClick={addMember}
              disabled={members.length >= 6}
              aria-label="Add a Council Member seat"
            >
              + Add Member
            </button>
          </div>

          {members.length === 0 ? (
            <div
              style={{
                border: '2px dashed var(--color-border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-8)',
                textAlign: 'center',
              }}
            >
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-subtle)', marginBottom: 'var(--space-4)' }}>
                No Council Members added yet. Add at least 3 to begin.
              </p>
              <button id="add-first-member-btn" className="btn-secondary" onClick={addMember}>
                + Add First Member
              </button>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 'var(--space-4)' }}>
              {members.map((member, i) => (
                <MemberCard
                  key={member.id}
                  member={member}
                  index={i}
                  models={models}
                  loadingModels={loadingModels}
                  onUpdate={updateMember}
                  onRemove={removeMember}
                  onSetChairman={setChairman}
                  isChairman={chairmanId === member.id}
                />
              ))}
              {members.length < 6 && (
                <button
                  id="add-member-inline-btn"
                  className="btn-ghost"
                  onClick={addMember}
                  style={{
                    border: '2px dashed var(--color-border)',
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-3)',
                    justifyContent: 'center',
                  }}
                >
                  + Add another member ({members.length}/6)
                </button>
              )}
            </div>
          )}
        </section>

        {/* ── Submit ─── */}
        <section aria-labelledby="convene-section">
          {validationMessage && (
            <p
              role="status"
              style={{
                fontSize: 'var(--text-sm)',
                color: 'var(--color-text-muted)',
                marginBottom: 'var(--space-3)',
                borderLeft: '3px solid var(--grey-50)',
                paddingLeft: 'var(--space-3)',
              }}
            >
              {validationMessage}
            </p>
          )}

          {submitError && (
            <div
              role="alert"
              style={{
                border: '2px solid var(--grey-0)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-4)',
                marginBottom: 'var(--space-4)',
                fontSize: 'var(--text-sm)',
              }}
            >
              <strong>Failed to start session.</strong> {submitError}
            </div>
          )}

          <button
            id="convene-btn"
            className="btn-primary btn-lg"
            onClick={handleConvene}
            disabled={!canConvene || submitting}
            style={{ minWidth: '240px' }}
          >
            {submitting ? (
              <>
                <span
                  style={{
                    display: 'inline-block',
                    width: '16px',
                    height: '16px',
                    border: '2px solid rgba(255,255,255,0.3)',
                    borderTopColor: '#fff',
                    borderRadius: '50%',
                    animation: 'spin 0.8s linear infinite',
                  }}
                />
                Convening…
              </>
            ) : (
              'Convene the Council →'
            )}
          </button>

          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', marginTop: 'var(--space-2)', marginBottom: 0 }}>
            This will make {configured.length || 'N'} API call{configured.length !== 1 ? 's' : ''} in parallel, billed to your configured provider keys.
          </p>
        </section>
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @media (max-width: 768px) {
          div[style*="gridTemplateColumns"] {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
}
