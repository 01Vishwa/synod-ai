'use client';

import React, { useState } from 'react';
import type { ResearchProvider } from '@/lib/api-client';
import { integrationsApi } from '@/lib/api-client';
import { useToast } from '@/hooks/useToast';

interface ResearchProviderCardProps {
  provider: ResearchProvider;
  title: string;
  description: string;
  isConfigured: boolean;
  onUpdate: () => void;
}

export function ResearchProviderCard({
  provider,
  title,
  description,
  isConfigured,
  onUpdate,
}: ResearchProviderCardProps) {
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  async function handleSave() {
    const trimmedKey = key.trim();
    if (!trimmedKey) {
      toast('API key is required.', 'error');
      return;
    }
    if (trimmedKey.length < 10) {
      toast('API key is too short.', 'error');
      return;
    }

    setSaving(true);
    try {
      // Backend will perform format validation, test connection, and then save
      await integrationsApi.saveResearchKey(provider, trimmedKey);
      setKey('');
      toast('Successfully connected and saved.', 'success');
      onUpdate();
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to validate or save key.', 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card-subtle" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-1)' }}>{title}</h3>
          {isConfigured ? (
            <span className="badge">✓ Connected</span>
          ) : (
            <span className="badge badge-muted">Not connected</span>
          )}
        </div>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-subtle)', margin: 0 }}>
          {description}
        </p>
      </div>

      <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
        <input
          type="password"
          placeholder={isConfigured ? 'Enter new key to replace existing…' : 'Enter API key…'}
          value={key}
          onChange={(e) => setKey(e.target.value)}
          style={{ flex: 1, fontFamily: 'var(--font-mono)' }}
        />
        <button
          className="btn-primary"
          onClick={handleSave}
          disabled={!key.trim() || saving}
        >
          {saving ? 'Connecting…' : 'Connect'}
        </button>
      </div>
    </div>
  );
}
