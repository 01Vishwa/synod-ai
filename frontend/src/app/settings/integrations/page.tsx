'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { ResearchProviderCard } from '@/components/settings/ResearchProviderCard';
import { NotionConnectCard } from '@/components/settings/NotionConnectCard';
import { integrationsApi, type ResearchProvider } from '@/lib/api-client';

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
        <div className={`w-10 h-[22px] rounded-full relative transition-colors ${checked ? 'bg-black' : 'bg-grey-85'}`}>
          <div className={`w-4 h-4 rounded-full bg-white absolute top-[3px] transition-all ${checked ? 'left-[21px]' : 'left-[3px]'}`} />
        </div>
      </div>
      <div>
        <div className="text-sm font-semibold">{label}</div>
        {description && <div className="text-xs text-subtle mt-0.5">{description}</div>}
      </div>
    </label>
  );
}

export default function IntegrationsSettingsPage() {
  const [configured, setConfigured] = useState<Record<ResearchProvider, boolean>>({
    tavily: false,
    anakin: false,
  });
  const [notionConnected, setNotionConnected] = useState(false);
  const [researchEnabled, setResearchEnabled] = useState(false);
  const [researchProvider, setResearchProvider] = useState<ResearchProvider>('tavily');
  const [archiveToNotion, setArchiveToNotion] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setResearchEnabled(localStorage.getItem('synod_research_enabled') === 'true');
    setResearchProvider((localStorage.getItem('synod_research_provider') as ResearchProvider) || 'tavily');
    setArchiveToNotion(localStorage.getItem('synod_archive_notion') === 'true');
    fetchStatus();
  }, []);

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
      setConfigured({ tavily: data.research.tavily, anakin: data.research.anakin });
      setNotionConnected(data.notion.connected);
    } catch {
      // gracefully handle missing backend
    }
  }

  return (
    <div className="max-w-[720px] mx-auto px-6 py-8">
      <div className="mb-6">
        <Link href="/" className="no-underline text-muted text-sm inline-flex items-center gap-2 hover:text-foreground transition-colors">
          <span>←</span> Back to Council
        </Link>
      </div>

      <div className="mb-8">
        <h1 className="font-display text-3xl font-bold mb-2">Integrations</h1>
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
            <div className="bg-background border border-border rounded-md p-4 mb-4">
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
                    <label htmlFor="research-provider-select" className="block text-xs font-semibold mb-1">
                      Research provider
                    </label>
                    <select
                      id="research-provider-select"
                      value={researchProvider}
                      onChange={(e) => handleResearchProviderChange(e.target.value as ResearchProvider)}
                      className="max-w-[200px] w-full text-sm bg-background border border-border rounded px-2 py-1.5 focus:border-black focus:ring-2 focus:ring-black/10 outline-none transition-all"
                    >
                      <option value="tavily">Tavily</option>
                      <option value="anakin">Anakin API</option>
                    </select>
                  </div>

                  <div className="flex flex-col gap-4">
                    <ResearchProviderCard
                      provider="tavily"
                      title="Tavily API"
                      description="AI-native search engine. Requires a tvly-... API key."
                      isConfigured={configured.tavily}
                      onUpdate={fetchStatus}
                    />
                    <ResearchProviderCard
                      provider="anakin"
                      title="Anakin API"
                      description="Deep web scraping and crawling capabilities."
                      isConfigured={configured.anakin}
                      onUpdate={fetchStatus}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Notion Toggle */}
            <div className="bg-background border border-border rounded-md p-4">
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
