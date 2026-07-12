'use client';

import React, { useState } from 'react';
import type { ResearchProvider } from '@/lib/api-client';
import { integrationsApi } from '@/lib/api-client';

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
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  async function handleSave() {
    const trimmedKey = key.trim();
    if (!trimmedKey) {
      setTestResult({ success: false, message: 'API key is required.' });
      return;
    }
    if (trimmedKey.length < 10) {
      setTestResult({ success: false, message: 'API key is too short.' });
      return;
    }

    setSaving(true);
    setTestResult(null);
    try {
      // Backend will perform format validation, test connection, and then save
      await integrationsApi.saveResearchKey(provider, trimmedKey);
      setKey('');
      setTestResult({ success: true, message: 'Successfully connected and saved.' });
      onUpdate();
    } catch (err) {
      setTestResult({ success: false, message: err instanceof Error ? err.message : 'Failed to validate or save key.' });
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

      {testResult && (
        <div
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: testResult.success ? 400 : 600,
            color: 'var(--color-text)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {testResult.success ? '✓ ' : '✕ '}{testResult.message}
        </div>
      )}
    </div>
  );
}
