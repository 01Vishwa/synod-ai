'use client';

import React, { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ResearchProviderCard } from '@/components/settings/ResearchProviderCard';
import { NotionConnectCard } from '@/components/settings/NotionConnectCard';
import { integrationsApi, researchApi, type ResearchProvider } from '@/lib/api-client';
import { useToast } from '@/hooks/useToast';

function Toggle({
  id, checked, onChange, label, description,
}: {
  id: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: React.ReactNode;
}) {
  return (
    <label htmlFor={id} className="flex items-start gap-3 cursor-pointer">
      <div className="relative mt-[2px]">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="absolute opacity-0 w-0 h-0"
        />
        <div className={`w-10 h-[22px] rounded-full relative transition-colors ${checked ? 'bg-primary' : 'bg-bgMuted'}`}>
          <div className={`w-4 h-4 rounded-full bg-primary-fg absolute top-[3px] transition-all ${checked ? 'left-[21px]' : 'left-[3px]'}`} />
        </div>
      </div>
      <div>
        <div className="text-sm font-bold text-foreground">{label}</div>
        {description && <div className="text-xs text-muted mt-0.5">{description}</div>}
      </div>
    </label>
  );
}

import { Suspense } from 'react';

function IntegrationsSettingsPageInner() {
  const [tavilyKey, setTavilyKey] = useState<{ has_key: boolean; fingerprint?: string }>({ has_key: false });
  const [anakinKey, setAnakinKey] = useState<{ has_key: boolean; fingerprint?: string }>({ has_key: false });
  const [notionConnected, setNotionConnected] = useState(false);
  const [researchEnabled, setResearchEnabled] = useState(false);
  const [researchProvider, setResearchProvider] = useState<ResearchProvider>('tavily');
  const [archiveToNotion, setArchiveToNotion] = useState(false);
  const [mounted, setMounted] = useState(false);
  const searchParams = useSearchParams();
  const router = useRouter();
  const { toast } = useToast();

  useEffect(() => {
    setMounted(true);
    setResearchEnabled(localStorage.getItem('synod_research_enabled') === 'true');
    setResearchProvider((localStorage.getItem('synod_research_provider') as ResearchProvider) || 'tavily');
    setArchiveToNotion(localStorage.getItem('synod_archive_notion') === 'true');
    fetchStatus();

    const notionStatus = searchParams.get('notion');
    const notionError = searchParams.get('notion_error');

    if (notionStatus === 'connected') {
      toast('Notion connected successfully!', 'success');
      router.replace('/settings/integrations');
    } else if (notionError) {
      toast(`Notion connection failed: ${notionError}`, 'error');
      router.replace('/settings/integrations');
    }
  }, [searchParams, toast, router]);

  function handleResearchEnabledChange(val: boolean) {
    setResearchEnabled(val);
    localStorage.setItem('synod_research_enabled', String(val));
  }

  function handleResearchProviderChange(val: ResearchProvider) {
    setResearchProvider(val);
    localStorage.setItem('synod_research_provider', val);
  }

  function handleArchiveToNotionChange(val: boolean) {
    setArchiveToNotion(val);
    localStorage.setItem('synod_archive_notion', String(val));
  }

  async function fetchStatus() {
    try {
      const data = await integrationsApi.getStatus();
      setNotionConnected(data.notion.connected);
      
      const keys = await researchApi.getKeys();
      const tav = keys.find(k => k.provider === 'tavily');
      const ank = keys.find(k => k.provider === 'anakin');
      setTavilyKey({ has_key: !!tav, fingerprint: tav?.fingerprint });
      setAnakinKey({ has_key: !!ank, fingerprint: ank?.fingerprint });
    } catch {
      // gracefully handle missing backend
    }
  }

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <p className="text-muted text-sm m-0">
          Connect auxiliary services for live web research and session archiving.
        </p>
      </div>

      {mounted && (
        <div className="flex flex-col gap-8">
          <section aria-labelledby="integrations-heading">
            <h2 id="integrations-heading" className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">
              Integrations
            </h2>

            {/* Research Toggle */}
            <div className="bg-surface border border-border rounded-md p-4 mb-4">
              <Toggle
                id="research-toggle"
                checked={researchEnabled}
                onChange={handleResearchEnabledChange}
                label="Enable Live Web Research"
                description="A research sub-agent fetches evidence before Council Members respond."
              />
              {researchEnabled && (
                <div className="mt-4 ml-[52px] flex flex-col gap-4">
                  <div>
                    <label htmlFor="research-provider-select" className="block text-xs font-semibold text-foreground mb-1">
                      Research provider
                    </label>
                    <select
                      id="research-provider-select"
                      value={researchProvider}
                      onChange={(e) => handleResearchProviderChange(e.target.value as ResearchProvider)}
                      className="max-w-[200px] w-full text-sm bg-background text-foreground border border-border rounded px-2 py-1.5 focus:border-border-strong focus:ring-2 focus:ring-foreground/10 outline-none transition-all"
                    >
                      <option value="tavily">Tavily</option>
                      <option value="anakin">Anakin API</option>
                    </select>
                  </div>

                  <div className="flex flex-col gap-4">
                    <ResearchProviderCard
                      provider="tavily"
                      title="Tavily"
                      description="Web search and extraction for live research grounding."
                      placeholder="tvly-..."
                      hasKey={tavilyKey.has_key}
                      savedFingerprint={tavilyKey.fingerprint}
                      onUpdate={fetchStatus}
                    />
                    <ResearchProviderCard
                      provider="anakin"
                      title="Anakin"
                      description="Agentic web research and deep content extraction."
                      placeholder="Enter Anakin API key"
                      hasKey={anakinKey.has_key}
                      savedFingerprint={anakinKey.fingerprint}
                      onUpdate={fetchStatus}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Notion Toggle */}
            <div className="bg-surface border border-border rounded-md p-4">
              <Toggle
                id="notion-toggle"
                checked={archiveToNotion}
                onChange={handleArchiveToNotionChange}
                label="Archive to Notion"
                description={
                  <>
                    Save the Chairman&apos;s report and full deliberation trail to Notion via the official MCP server.
                  </>
                }
              />
              {archiveToNotion && (
                <div id="notion-connect" className="mt-4 ml-[52px]">
                  <NotionConnectCard isConnected={notionConnected} />
                </div>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default function IntegrationsSettingsPage() {
  return (
    <Suspense fallback={<div className="p-8"><div className="w-8 h-8 rounded-full border-4 border-primary border-t-transparent animate-spin mx-auto"></div></div>}>
      <IntegrationsSettingsPageInner />
    </Suspense>
  );
}
