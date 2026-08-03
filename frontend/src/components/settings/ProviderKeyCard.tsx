'use client';

import React, { useState } from 'react';
import type { Provider, ProviderKeyResponse } from '@/lib/api-client';
import { providersApi } from '@/lib/api-client';
import { useToast } from '@/hooks/useToast';
import { SecureApiKeyInput } from '@/components/ui/SecureApiKeyInput';
import { apiKeySchema } from '@/lib/validation';

interface ProviderKeyCardProps {
  provider: Provider;
  title: string;
  description: string;
  providerKey?: ProviderKeyResponse | null;
  onUpdate: () => void;
  onDelete: (provider: Provider) => Promise<void>;
  retirementWarning?: string;
}

export function ProviderKeyCard({
  provider,
  title,
  description,
  providerKey,
  onUpdate,
  onDelete,
  retirementWarning,
}: ProviderKeyCardProps) {
  const [key, setKey] = useState('');
  const [inlineError, setInlineError] = useState('');
  const [saving, setSaving] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [elapsedSecs, setElapsedSecs] = useState(0);
  const { toast, updateToast } = useToast();

  const hasKey = !!providerKey;
  const isConnected = hasKey && providerKey.last_test_ok === true;
  const cardState = !hasKey ? 'no_key' : isConnected ? 'connected' : 'key_invalid';

  React.useEffect(() => {
    if (!saving) { setElapsedSecs(0); return; }
    const id = setInterval(() => setElapsedSecs(s => s + 1), 1000);
    return () => clearInterval(id);
  }, [saving]);

  const handleKeyChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setKey(e.target.value);
    if (inlineError) {
      setInlineError(''); // clear error when typing
    }
  };

  async function handleSave() {
    const result = apiKeySchema.safeParse(key);
    if (!result.success) {
      setInlineError(result.error.errors[0].message);
      return;
    }

    setSaving(true);
    const toastId = toast('Verifying and saving API key...', 'loading', { title: 'Connecting' });
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s

    try {
      await providersApi.saveKey({ provider, api_key: result.data }, { signal: controller.signal });
      clearTimeout(timeoutId);
      setKey('');
      setInlineError('');
      updateToast(toastId, 'API key verified successfully.', 'success', { title: 'Connected' });
      onUpdate();
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setInlineError("Request timed out. The provider may be slow — try again.");
        updateToast(toastId, "Request timed out.", 'error', { title: 'Connection Failed' });
      } else {
        setInlineError(err.message ?? "Failed to save key.");
        updateToast(toastId, err.message ?? "Failed to save key.", 'error', { title: 'Connection Failed' });
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleRevoke() {
    setRevoking(true);
    const toastId = toast('Removing API key...', 'loading', { title: 'Revoking' });
    try {
      await onDelete(provider);
      setKey('');
      setInlineError('');
      updateToast(toastId, 'API key revoked successfully.', 'success', { title: 'Revoked' });
    } catch (err) {
      updateToast(toastId, err instanceof Error ? err.message : 'Failed to revoke key.', 'error', { title: 'Revoke Failed' });
    } finally {
      setRevoking(false);
    }
  }

  return (
    <div className="bg-surface border border-border rounded-xl shadow-sm p-6 flex flex-col gap-5">
      {retirementWarning && (
        <div className="p-3 bg-bgSubtle border border-border-strong rounded-lg">
          <p className="m-0 text-sm font-semibold text-foreground">
            ⚠️ {retirementWarning}
          </p>
        </div>
      )}

      <div>
        <div className="flex justify-between items-center mb-1">
          <h3 className="text-lg font-bold text-foreground">{title}</h3>
          
          {cardState === 'connected' && (
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-black bg-white px-2.5 py-1 border border-black rounded-md">
              <span>●</span> Connected (Standard)
            </span>
          )}
          {cardState === 'no_key' && (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-500 bg-white px-2.5 py-1 border border-gray-400 rounded-md">
              <span>○</span> Not connected
            </span>
          )}
          {cardState === 'key_invalid' && (
            <span className="inline-flex items-center gap-1.5 text-xs font-bold text-black bg-white px-2.5 py-1 border border-black rounded-md">
              <span>○</span> Key invalid
            </span>
          )}
        </div>
        <p className="text-sm text-gray-500 m-0">{description}</p>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex gap-3 items-center">
          <SecureApiKeyInput
            placeholder={cardState === 'key_invalid' ? 'Enter new API key...' : 'Enter API key...'}
            value={key}
            onChange={handleKeyChange}
            className={`flex-1 ${inlineError ? 'border-black focus:ring-black/20' : ''}`}
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
            disabled={saving}
          />
          {cardState === 'connected' && !key ? (
            <button
              className="bg-secondary text-secondary-fg border border-border px-6 py-2.5 font-bold text-sm rounded-lg shadow-sm flex items-center justify-center min-w-[100px] opacity-50 cursor-not-allowed"
              disabled
            >
              Connected
            </button>
          ) : (
            <button
              className="bg-primary text-primary-fg border border-border-strong px-6 py-2.5 font-bold text-sm rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm flex items-center justify-center min-w-[100px]"
              onClick={handleSave}
              disabled={!key || saving}
            >
              {saving ? (
                <div className="flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin text-primary-fg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Verifying API key...{elapsedSecs > 2 ? ` (${elapsedSecs}s)` : ''}</span>
                </div>
              ) : cardState === 'connected' ? 'Update Key' : 'Connect'}
            </button>
          )}
        </div>
        
        {inlineError && (
          <p className="text-sm font-medium border-l-2 border-black pl-2 mt-2">
            {inlineError}
          </p>
        )}

        {cardState === 'connected' && (
          <div className="flex flex-col gap-1 mt-1">
            <p className="text-sm text-gray-500 m-0">Saved key: {providerKey?.key_fingerprint}</p>
            <p className="text-xs text-gray-500 italic m-0">Verified for standard models — some premium models may still require additional access.</p>
            <button onClick={handleRevoke} disabled={revoking} className="text-sm text-gray-500 underline text-left hover:text-black self-start w-auto">
              {revoking ? 'Removing...' : 'Remove key'}
            </button>
          </div>
        )}

        {cardState === 'key_invalid' && (
          <div className="flex flex-col gap-1 mt-1">
            <p className="text-sm text-gray-500 m-0">Previous key ({providerKey?.key_fingerprint}) is no longer valid. Enter a new key.</p>
            <button onClick={handleRevoke} disabled={revoking} className="text-sm text-gray-500 underline text-left hover:text-black self-start w-auto">
              {revoking ? 'Removing...' : 'Remove key'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
