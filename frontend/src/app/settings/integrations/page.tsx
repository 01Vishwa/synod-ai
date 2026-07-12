'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { ResearchProviderCard } from '@/components/settings/ResearchProviderCard';
import { NotionConnectCard } from '@/components/settings/NotionConnectCard';
import { integrationsApi, type ResearchProvider } from '@/lib/api-client';

// ─── Toggle Component ───────────────────────────────────────────────────────

interface ToggleProps {
  id: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}

function Toggle({ id, checked, onChange, label, description }: ToggleProps) {
  return (
    <label
      htmlFor={id}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 'var(--space-3)',
        cursor: 'pointer',
      }}
    >
      <div style={{ position: 'relative', marginTop: '2px' }}>
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
        />
        <div
          style={{
            width: '40px',
            height: '22px',
            background: checked ? 'var(--grey-0)' : 'var(--grey-85)',
            borderRadius: '11px',
            position: 'relative',
            transition: 'background var(--transition-normal)',
          }}
        >
          <div
            style={{
              width: '16px',
              height: '16px',
              borderRadius: '50%',
              background: 'var(--grey-100)',
              position: 'absolute',
              top: '3px',
              left: checked ? '21px' : '3px',
              transition: 'left var(--transition-normal)',
            }}
          />
        </div>
      </div>
      <div>
        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{label}</div>
        {description && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', marginTop: '2px' }}>
            {description}
          </div>
        )}
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

  // Global settings for new sessions
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

  // In a real implementation, we would fetch the integration status here.
  // For the frontend skeleton, we just mock it out.
  function fetchStatus() {
    // Mock refresh
  }

  return (
    <div style={{ maxWidth: '720px', margin: '0 auto', padding: 'var(--space-8) var(--content-gutter)' }}>
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <Link href="/" style={{ textDecoration: 'none', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <span>←</span> Back to Council
        </Link>
      </div>

      <div style={{ marginBottom: 'var(--space-8)' }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-2xl)', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
          Integrations
        </h1>
        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
          Connect auxiliary services for live web research and session archiving.
        </p>
      </div>

      {mounted && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
          
          {/* Research Section */}
          <section aria-labelledby="research-heading">
            <h2 id="research-heading" style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
              Web Research
            </h2>
            <div style={{ marginBottom: 'var(--space-6)', padding: 'var(--space-4)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)' }}>
              <Toggle
                id="research-toggle"
                checked={researchEnabled}
                onChange={handleResearchEnabledChange}
                label="Enable live web research by default"
                description="A research sub-agent fetches evidence before Council Members respond in all new sessions."
              />
              {researchEnabled && (
                <div style={{ marginTop: 'var(--space-3)', marginLeft: '52px' }}>
                  <label
                    htmlFor="research-provider-select"
                    style={{ fontSize: 'var(--text-xs)', fontWeight: 600, display: 'block', marginBottom: 'var(--space-1)' }}
                  >
                    Research provider
                  </label>
                  <select
                    id="research-provider-select"
                    value={researchProvider}
                    onChange={(e) => handleResearchProviderChange(e.target.value as ResearchProvider)}
                    style={{ maxWidth: '200px' }}
                  >
                    <option value="tavily">Tavily</option>
                    <option value="anakin">Anakin API</option>
                  </select>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
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
          </section>

          {/* Archiving Section */}
          <section aria-labelledby="archiving-heading">
            <h2 id="archiving-heading" style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
              Archiving
            </h2>
            <div style={{ marginBottom: 'var(--space-6)', padding: 'var(--space-4)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)' }}>
              <Toggle
                id="notion-toggle"
                checked={archiveToNotion}
                onChange={handleArchiveToNotionChange}
                label="Archive to Notion when complete"
                description="The Chairman's report and full deliberation trail are saved to your connected Notion workspace automatically for all new sessions."
              />
            </div>
            
            <NotionConnectCard isConnected={notionConnected} />
          </section>

        </div>
      )}
    </div>
  );
}
