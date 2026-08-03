'use client';

import React, { useState } from 'react';
import { researchApi } from '@/lib/api-client';
import { SecureApiKeyInput } from '@/components/ui/SecureApiKeyInput';

interface ResearchProviderCardProps {
  provider: 'tavily' | 'anakin';
  title: string;
  description: string;
  placeholder: string;
  savedFingerprint?: string;
  hasKey?: boolean;
  onUpdate: () => void;
}

export function ResearchProviderCard({
  provider,
  title,
  description,
  placeholder,
  savedFingerprint,
  hasKey,
  onUpdate,
}: ResearchProviderCardProps) {
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<'none' | 'success' | 'failed'>('none');
  const [errorText, setErrorText] = useState('');

  async function handleSave() {
    const trimmedKey = key.trim();
    if (!trimmedKey) {
      setErrorText('API key is required.');
      return;
    }
    
    setSaving(true);
    setErrorText('');
    setTestResult('none');
    
    try {
      await researchApi.saveKey({ provider, api_key: trimmedKey });
      setKey('');
      onUpdate(); // refresh parent state
    } catch (err) {
      setErrorText(err instanceof Error ? err.message : 'Failed to save key.');
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setErrorText('');
    setTestResult('none');
    
    try {
      const res = await researchApi.testKey(provider);
      if (res.success) {
        setTestResult('success');
      } else {
        setTestResult('failed');
        setErrorText(res.message);
      }
    } catch (err) {
      setTestResult('failed');
      setErrorText(err instanceof Error ? err.message : 'Failed to test connection.');
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="bg-surface border border-border rounded-xl shadow-sm p-6 flex flex-col gap-5">
      <div>
        <div className="flex justify-between items-center mb-1">
          <h3 className="text-lg font-bold text-foreground">{title}</h3>
          <div className="flex gap-2">
            {hasKey && (
              <span className="inline-flex items-center text-xs font-bold text-foreground border-2 border-border-strong rounded-md px-2 py-0.5 uppercase tracking-wider">
                Saved
              </span>
            )}
            {testResult === 'success' && (
              <span className="inline-flex items-center text-xs font-bold text-foreground border-2 border-border-strong rounded-md px-2 py-0.5 uppercase tracking-wider">
                Connected
              </span>
            )}
            {testResult === 'failed' && (
              <span className="inline-flex items-center text-xs font-bold text-foreground border-2 border-border-strong rounded-md px-2 py-0.5 uppercase tracking-wider">
                Failed
              </span>
            )}
          </div>
        </div>
        <p className="text-sm text-muted m-0">{description}</p>
      </div>

      <div className="flex gap-3 items-center">
        <SecureApiKeyInput
          placeholder={hasKey ? (savedFingerprint || placeholder) : placeholder}
          value={key}
          onChange={(e) => setKey(e.target.value)}
          className="flex-1"
          onKeyDown={(e) => e.key === 'Enter' && handleSave()}
          disabled={saving || testing}
        />
        <button
          className="bg-secondary text-secondary-fg px-4 py-2 border-2 border-border-strong font-bold text-sm rounded-lg hover:bg-secondary-hover transition-colors disabled:opacity-50 shadow-sm"
          onClick={handleTest}
          disabled={testing || (!hasKey && !key.trim())}
        >
          {testing ? 'Testing...' : 'Test Connection'}
        </button>
        <button
          className="bg-primary text-primary-fg px-6 py-2 border-2 border-border-strong font-bold text-sm rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 shadow-sm"
          onClick={handleSave}
          disabled={!key.trim() || saving}
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>

      {errorText && (
        <p className="text-sm font-semibold text-foreground m-0 mt-2">
          {errorText}
        </p>
      )}
    </div>
  );
}
