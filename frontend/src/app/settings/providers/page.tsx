'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { ProviderKeyCard } from '@/components/settings/ProviderKeyCard';
import { providersApi, type Provider } from '@/lib/api-client';

export default function ProvidersSettingsPage() {
  const [configured, setConfigured] = useState<Record<Provider, boolean>>({
    openrouter: false,
    nvidia_nim: false,
    github_models: false,
  });

  const [loading, setLoading] = useState(true);

  async function fetchStatus() {
    try {
      const data = await providersApi.getConfiguredProviders();
      const status = { openrouter: false, nvidia_nim: false, github_models: false };
      data.forEach((p) => {
        status[p.provider] = p.configured;
      });
      setConfigured(status);
    } catch {
      // gracefully handle error or missing backend
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchStatus();
  }, []);

  if (loading) {
    return (
      <div style={{ maxWidth: '720px', margin: '0 auto', padding: 'var(--space-8) var(--content-gutter)' }}>
        {[1, 2, 3].map((i) => (
          <div key={i} className="skeleton" style={{ height: '200px', marginBottom: 'var(--space-4)' }} />
        ))}
      </div>
    );
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
          Model Providers
        </h1>
        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
          Synod connects exclusively to these three inference providers. Your keys are encrypted at rest and never shared.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        <ProviderKeyCard
          provider="openrouter"
          title="OpenRouter"
          description="Access hundreds of models (Anthropic, OpenAI, Meta) via a single unified API."
          isConfigured={configured.openrouter}
          onUpdate={fetchStatus}
        />

        <ProviderKeyCard
          provider="nvidia_nim"
          title="NVIDIA NIM"
          description="Enterprise-grade NVIDIA hosted models with high throughput."
          isConfigured={configured.nvidia_nim}
          onUpdate={fetchStatus}
        />

        <ProviderKeyCard
          provider="github_models"
          title="GitHub Models"
          description="Access to models hosted on GitHub's inference infrastructure."
          isConfigured={configured.github_models}
          onUpdate={fetchStatus}
          retirementWarning="GitHub Models is being retired on July 30, 2026. After this date, this provider will cease to function."
        />
      </div>
    </div>
  );
}
