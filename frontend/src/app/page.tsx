'use client';

/**
 * New Session Screen — the home page of Synod.
 * Allows the user to compose a query, pick Council Members, configure
 * optional research and Notion archiving, and convene the council.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import type { Provider, ResearchProvider, ModelInfo } from '@/lib/api-client';
import { sessionsApi, providersApi, systemApi } from '@/lib/api-client';
import { useToast } from '@/hooks/useToast';
import { SearchableSelect } from '@/components/ui/SearchableSelect';

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
];

function generateMemberId() {
  return `member_${Math.random().toString(36).slice(2, 9)}`;
}

// ─── Sub-components ───────────────────────────────────────────────────────

interface ToggleProps {
  id: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: React.ReactNode;
  disabled?: boolean;
}

function Toggle({ id, checked, onChange, label, description, disabled }: ToggleProps) {
  return (
    <label
      htmlFor={id}
      className={`flex items-start gap-3 ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
    >
      <div className="relative mt-[2px]">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="absolute opacity-0 w-0 h-0"
        />
        <div
          className={`w-10 h-[22px] rounded-full relative transition-colors ${checked ? 'bg-black' : 'bg-grey-85'}`}
        >
          <div
            className={`w-4 h-4 rounded-full bg-white absolute top-[3px] transition-all ${checked ? 'left-[21px]' : 'left-[3px]'}`}
          />
        </div>
      </div>
      <div>
        <div className="text-sm font-semibold">{label}</div>
        {description && (
          <div className="text-xs text-subtle mt-0.5">
            {description}
          </div>
        )}
      </div>
    </label>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-bold uppercase tracking-widest text-subtle mb-2">
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
  modelErrors,
  onUpdate,
  onRemove,
  onSetChairman,
  isChairman,
}: MemberCardProps) {
  const providerModels = models[member.provider] ?? [];
  const isLoading = loadingModels[member.provider];
  const error = modelErrors[member.provider];

  return (
    <div
      className={`p-4 rounded-md transition-colors animate-fade-in border
        ${isChairman ? 'border-2 border-black bg-grey-93' : 'border-border bg-background'}`}
    >
      <div className="flex justify-between items-center mb-3">
        <span className="font-display font-bold text-sm">
          Council Seat {index + 1}
          {isChairman && (
            <span className="ml-2 font-mono text-xs font-normal px-1.5 py-px border border-black rounded-sm">
              CHAIRMAN
            </span>
          )}
        </span>
        <div className="flex gap-2">
          {!isChairman && (
            <button
              className="px-2 py-1 text-xs font-medium border border-transparent hover:bg-grey-93 rounded transition-colors"
              onClick={() => onSetChairman(member.id)}
              title="Set as Chairman"
              aria-label={`Set Council Seat ${index + 1} as Chairman`}
            >
              ★ Set Chairman
            </button>
          )}
          <button
            className="px-2 py-1 text-xs font-medium border border-transparent hover:bg-grey-93 rounded transition-colors"
            onClick={() => onRemove(member.id)}
            aria-label={`Remove Council Seat ${index + 1}`}
          >
            ✕
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Provider */}
        <div>
          <label htmlFor={`provider-${member.id}`} className="block text-xs font-semibold mb-1">
            Provider
          </label>
          <select
            id={`provider-${member.id}`}
            value={member.provider}
            onChange={(e) =>
              onUpdate(member.id, { provider: e.target.value as Provider, model_id: '' })
            }
            className="w-full text-base sm:text-sm bg-background border border-border rounded px-2 py-1.5 focus:border-black focus:ring-2 focus:ring-black/10 outline-none transition-all"
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
          <label htmlFor={`model-${member.id}`} className="block text-xs font-semibold mb-1">
            Model
          </label>
          <SearchableSelect
            id={`model-${member.id}`}
            value={member.model_id}
            onChange={(val) => onUpdate(member.id, { model_id: val })}
            options={
              member.provider && !isLoading && !error && providerModels.length > 0
                ? providerModels.map((m) => ({ value: m.id, label: m.name || m.id }))
                : []
            }
            disabled={!member.provider || isLoading || !!error || providerModels.length === 0}
            placeholder={
              !member.provider ? 'Select provider first' :
              isLoading ? 'Loading models...' :
              error ? (error.includes('No API key') 
                ? `Connect ${member.provider === 'nvidia_nim' ? 'NVIDIA NIM' : 'OpenRouter'} in Settings` 
                : 'Could not load models') :
              providerModels.length === 0 ? 'No models available' :
              'Select model…'
            }
            className={error ? 'border border-red-500 rounded text-red-700' : ''}
          />
        </div>
      </div>

      {/* Display label */}
      <div className="mt-3">
        <label htmlFor={`label-${member.id}`} className="block text-xs font-semibold mb-1">
          Display label (optional)
        </label>
        <input
          id={`label-${member.id}`}
          type="text"
          placeholder={`Council Seat ${index + 1}`}
          value={member.display_label}
          onChange={(e) => onUpdate(member.id, { display_label: e.target.value })}
          className="w-full text-base sm:text-sm bg-background border border-border rounded px-2 py-1.5 focus:border-black focus:ring-2 focus:ring-black/10 outline-none transition-all placeholder-subtle"
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
  const { toast } = useToast();

  const [researchEnabled, setResearchEnabled] = useState(false);
  const [researchProvider, setResearchProvider] = useState<ResearchProvider>('tavily');
  const [archiveToNotion, setArchiveToNotion] = useState(false);
  const [notionConnected, setNotionConnected] = useState(false);

  const healthChecked = useRef(false);

  useEffect(() => {
    setResearchEnabled(localStorage.getItem('synod_research_enabled') === 'true');
    setResearchProvider((localStorage.getItem('synod_research_provider') as ResearchProvider) || 'tavily');
    setArchiveToNotion(localStorage.getItem('synod_archive_notion') === 'true');
    setNotionConnected(localStorage.getItem('synod_notion_connected') === 'true');

    if (!healthChecked.current) {
      healthChecked.current = true;
      systemApi.checkHealth()
        .then(() => toast('Backend Connected', 'success'))
        .catch(() => toast('Backend Unreachable', 'error'));
    }
  }, [toast]);

  const [models, setModels] = useState<Record<Provider, ModelInfo[]>>({
    openrouter: [],
    nvidia_nim: [],
  });
  const [loadingModels, setLoadingModels] = useState<Record<Provider, boolean>>({
    openrouter: false,
    nvidia_nim: false,
  });
  const [modelErrors, setModelErrors] = useState<Record<Provider, string | null>>({
    openrouter: null,
    nvidia_nim: null,
  });

  const fetchAttempted = useRef<Record<Provider, boolean>>({
    openrouter: false,
    nvidia_nim: false,
  });

  const fetchModels = useCallback(async (provider: Provider) => {
    if (fetchAttempted.current[provider]) return;
    fetchAttempted.current[provider] = true;

    setLoadingModels((prev) => ({ ...prev, [provider]: true }));
    setModelErrors((prev) => ({ ...prev, [provider]: null }));
    try {
      const list = await providersApi.listModels(provider);
      setModels((prev) => ({ ...prev, [provider]: list }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch models';
      setModelErrors((prev) => ({
        ...prev,
        [provider]: msg
      }));
      
      if (msg.includes('No API key')) {
        const providerName = provider === 'nvidia_nim' ? 'NVIDIA NIM' : 'OpenRouter';
        toast(`Connect ${providerName} in Settings to view models.`, 'error');
      } else {
        toast(`Failed to load models for ${provider}`, 'error');
      }
    } finally {
      setLoadingModels((prev) => ({ ...prev, [provider]: false }));
    }
  }, [toast]);

  useEffect(() => {
    const providers = [...new Set(members.map((m) => m.provider))];
    providers.forEach(fetchModels);
  }, [members, fetchModels]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.max(120, ta.scrollHeight)}px`;
  }, [query]);

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

  const configured = members.filter((m) => m.model_id);
  const chairmen = members.filter((m) => m.role === 'chairman');
  
  let validationMessage: string | null = null;
  if (query.trim().length < 10) {
    validationMessage = 'Query must be at least 10 characters.';
  } else if (members.length < 3 || members.length > 6) {
    validationMessage = `Select between 3 and 6 Council Members. (${members.length}/3 ready)`;
  } else if (members.some(m => !m.id)) {
    validationMessage = 'All members must have an internal ID.';
  } else if (new Set(members.map(m => m.id)).size !== members.length) {
    validationMessage = 'All members must have unique IDs.';
  } else if (configured.length !== members.length) {
    validationMessage = 'All members must have a provider and model selected.';
  } else if (chairmen.length !== 1) {
    validationMessage = 'Exactly one member must be selected as the Chairman.';
  } else if (!chairmanId) {
    validationMessage = 'Chairman ID is missing.';
  } else if (!members.find(m => m.id === chairmanId)) {
    validationMessage = 'Selected Chairman does not exist in the council.';
  } else if (members.find(m => m.id === chairmanId)?.role !== 'chairman') {
    validationMessage = 'Chairman ID mismatch with member role.';
  }

  const canConvene = validationMessage === null;

  async function handleConvene() {
    if (!canConvene || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const session = await sessionsApi.create({
        user_query: query.trim(),
        members: members.map((m) => ({
            member_id: m.id,
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
      toast(err instanceof Error ? err.message : 'Failed to start session. Check your API keys in Settings.', 'error');
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-[960px] mx-auto px-6 py-8">
      {/* Page heading */}
      <div className="mb-8">
        <h1 className="font-display text-3xl font-bold mb-2">
          Convene a New Council
        </h1>
        <p className="text-muted text-sm m-0">
          Submit one question. A panel of independent AI models will deliberate, critique each other anonymously, and synthesize a final answer.
        </p>
      </div>

      <div className="flex flex-col gap-8">
        {/* ── Query Input ─── */}
        <section aria-labelledby="query-label">
          <SectionLabel>Your Question</SectionLabel>
          <label
            id="query-label"
            htmlFor="session-query"
            className="block mb-2 text-sm text-muted"
          >
            The same query is sent to all Council Members simultaneously.
          </label>
          <textarea
            id="session-query"
            ref={textareaRef}
            placeholder="What question should the council deliberate on?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full min-h-[120px] resize-none font-body text-base leading-relaxed overflow-y-hidden bg-background border border-border rounded-md p-3 focus:border-black focus:ring-2 focus:ring-black/10 outline-none transition-all"
            aria-describedby="query-hint"
          />
          <p id="query-hint" className="text-xs text-subtle mt-1 m-0">
            Press <kbd className="font-mono px-1 border border-border rounded-sm">⌘ Enter</kbd> to convene.
            {query.trim().length > 0 && (
              <span className="ml-2">{query.trim().length} characters</span>
            )}
          </p>
        </section>

        {/* ── Council Members ─── */}
        <section aria-labelledby="members-label">
          <div className="flex justify-between items-center mb-3">
            <div>
              <SectionLabel>Council Members</SectionLabel>
              <p className="text-xs text-subtle m-0">
                Select 3–6 models from any provider. Each model reasons independently.
              </p>
            </div>
            <button
              id="add-member-btn"
              className="bg-white text-black px-3 py-1.5 border-2 border-black font-semibold text-xs rounded hover:bg-grey-93 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              onClick={addMember}
              disabled={members.length >= 6}
              aria-label="Add a Council Member seat"
            >
              + Add Member
            </button>
          </div>

          {members.length === 0 ? (
            <div className="border-2 border-dashed border-border rounded-md p-8 text-center">
              <p className="text-sm text-subtle mb-4">
                No Council Members added yet. Add at least 3 to begin.
              </p>
              <button 
                id="add-first-member-btn" 
                className="bg-white text-black px-6 py-3 border-2 border-black font-semibold text-sm rounded hover:bg-grey-93 transition-colors" 
                onClick={addMember}
              >
                + Add First Member
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {members.map((member, i) => (
                <MemberCard
                  key={member.id}
                  member={member}
                  index={i}
                  models={models}
                  loadingModels={loadingModels}
                  modelErrors={modelErrors}
                  onUpdate={updateMember}
                  onRemove={removeMember}
                  onSetChairman={setChairman}
                  isChairman={chairmanId === member.id}
                />
              ))}
              {members.length < 6 && (
                <button
                  id="add-member-inline-btn"
                  className="flex items-center justify-center border-2 border-dashed border-border rounded-md p-3 text-sm font-medium text-black bg-transparent hover:bg-grey-93 hover:border-grey-85 transition-colors"
                  onClick={addMember}
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
              className="text-sm text-muted mb-3 border-l-4 border-grey-50 pl-3"
            >
              {validationMessage}
            </p>
          )}

          <button
            id="convene-btn"
            className="bg-black text-white px-8 py-4 border-2 border-black font-semibold text-base rounded hover:bg-grey-10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed min-w-[240px] flex items-center justify-center gap-2"
            onClick={handleConvene}
            disabled={!canConvene || submitting}
          >
            {submitting ? (
              <>
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Convening…
              </>
            ) : (
              'Convene the Council →'
            )}
          </button>

          <p className="text-xs text-subtle mt-2 m-0">
            This will make {configured.length || 'N'} API call{configured.length !== 1 ? 's' : ''} in parallel, billed to your configured provider keys.
          </p>
        </section>
      </div>
    </div>
  );
}
