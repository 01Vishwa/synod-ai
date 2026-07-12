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
      data.forEach((p) => { status[p.provider] = p.configured; });
      setConfigured(status);
    } catch {
      // gracefully handle missing backend
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchStatus(); }, []);

  if (loading) {
    return (
      <div className="max-w-[720px] mx-auto px-6 py-8">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-[200px] mb-4 bg-grey-93 rounded-md animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-[720px] mx-auto px-6 py-8">
      <div className="mb-6">
        <Link
          href="/"
          className="no-underline text-muted text-sm inline-flex items-center gap-2 hover:text-foreground transition-colors"
        >
          <span>←</span> Back to Council
        </Link>
      </div>

      <div className="mb-8">
        <h1 className="font-display text-3xl font-bold mb-2">Model Providers</h1>
        <p className="text-muted text-sm m-0">
          Synod connects exclusively to these three inference providers. Your keys are encrypted at rest and never shared.
        </p>
      </div>

      <div className="flex flex-col gap-6">
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
