'use client';

import React, { useEffect, useState } from 'react';
import { ProviderKeyCard } from '@/components/settings/ProviderKeyCard';
import { providersApi, type Provider, type ProviderKeyResponse } from '@/lib/api-client';

export default function ProvidersSettingsPage() {
  const [configured, setConfigured] = useState<Record<Provider, ProviderKeyResponse | null>>({
    openrouter: null,
    nvidia_nim: null,
  });
  const [loading, setLoading] = useState(true);

  async function fetchStatus() {
    try {
      const data = await providersApi.getConfiguredProviders();
      const status: Record<Provider, ProviderKeyResponse | null> = { openrouter: null, nvidia_nim: null };
      data.forEach((p) => { status[p.provider] = p; });
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
          <div key={i} className="h-[200px] mb-4 bg-bgSubtle rounded-md animate-pulse" />
        ))}
      </div>
    );
  }

  const handleDeleteKey = async (provider: Provider) => {
    await providersApi.deleteKey(provider);
    await fetchStatus();
  };

  return (
    <div className="animate-fade-in">
      <div className="mb-8">
        <p className="text-muted text-sm m-0">
          Synod connects exclusively to these inference providers. Your keys are encrypted at rest and never shared.
        </p>
      </div>

      <div className="flex flex-col gap-6">
        <ProviderKeyCard
          provider="openrouter"
          title="OpenRouter"
          description="Access hundreds of models (Anthropic, OpenAI, Meta) via a single unified API."
          providerKey={configured.openrouter}
          onUpdate={fetchStatus}
          onDelete={handleDeleteKey}
        />

        <ProviderKeyCard
          provider="nvidia_nim"
          title="NVIDIA NIM"
          description="Enterprise-grade NVIDIA hosted models with high throughput."
          providerKey={configured.nvidia_nim}
          onUpdate={fetchStatus}
          onDelete={handleDeleteKey}
        />
      </div>
    </div>
  );
}
