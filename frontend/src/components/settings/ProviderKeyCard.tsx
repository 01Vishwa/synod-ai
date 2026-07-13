'use client';

import React, { useState } from 'react';
import type { Provider, ProviderKeyResponse } from '@/lib/api-client';
import { providersApi } from '@/lib/api-client';
import { useToast } from '@/hooks/useToast';

interface ProviderKeyCardProps {
  provider: Provider;
  title: string;
  description: string;
  providerKey?: ProviderKeyResponse | null;
  onUpdate: () => void;
  retirementWarning?: string;
}

export function ProviderKeyCard({
  provider,
  title,
  description,
  providerKey,
  onUpdate,
  retirementWarning,
}: ProviderKeyCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const { toast } = useToast();

  async function handleSave() {
    const trimmedKey = key.trim();
    if (!trimmedKey) { toast('API key is required.', 'error'); return; }
    if (trimmedKey.length < 10) { toast('API key is too short.', 'error'); return; }

    setSaving(true);
    try {
      await providersApi.saveKey({ provider, api_key: trimmedKey });
      setKey('');
      setIsEditing(false);
      toast('Successfully connected and saved.', 'success');
      onUpdate();
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to validate or save key.', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleRevoke() {
    setRevoking(true);
    try {
      await providersApi.revokeKey(provider);
      setIsEditing(false);
      setKey('');
      toast('API key revoked.', 'success');
      onUpdate();
    } catch (err) {
      toast(err instanceof Error ? err.message : 'Failed to revoke key.', 'error');
    } finally {
      setRevoking(false);
    }
  }

  return (
    <div className="bg-background border border-border rounded-md p-6 flex flex-col gap-4">
      {retirementWarning && (
        <div className="p-3 border-2 border-black rounded-sm bg-grey-10">
          <p className="m-0 text-sm font-semibold text-white">
            ⚠️ {retirementWarning}
          </p>
        </div>
      )}

      <div>
        <div className="flex justify-between items-center">
          <h3 className="text-lg font-display font-bold mb-1">{title}</h3>
          {providerKey ? (
            <span className="inline-flex items-center font-mono text-xs font-semibold px-2 py-0.5 border border-black rounded-sm bg-background text-foreground whitespace-nowrap">
              ✓ Connected ({providerKey.key_fingerprint})
            </span>
          ) : (
            <span className="inline-flex items-center font-mono text-xs font-semibold px-2 py-0.5 border border-border rounded-sm bg-background text-muted whitespace-nowrap">
              Not connected
            </span>
          )}
        </div>
        <p className="text-sm text-subtle m-0">{description}</p>
      </div>

      {providerKey && !isEditing ? (
        <div className="flex gap-3">
          <button
            className="bg-black text-white px-5 py-2 border-2 border-black font-semibold text-sm rounded hover:bg-grey-10 transition-colors"
            onClick={() => setIsEditing(true)}
          >
            Update Key
          </button>
          <button
            className="bg-white text-black px-5 py-2 border-2 border-border font-semibold text-sm rounded hover:bg-grey-97 transition-colors disabled:opacity-40"
            onClick={handleRevoke}
            disabled={revoking}
          >
            {revoking ? 'Revoking…' : 'Revoke'}
          </button>
        </div>
      ) : (
        <div className="flex gap-3">
          <input
            type="password"
            placeholder={providerKey ? 'Enter new key to replace existing…' : 'Enter API key…'}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            className="flex-1 font-mono text-sm bg-background border border-border rounded px-3 py-2 focus:border-black focus:ring-2 focus:ring-black/10 outline-none transition-all placeholder-subtle"
            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
          />
          {providerKey && isEditing && (
            <button
              className="px-5 py-2 text-sm font-semibold text-muted hover:text-foreground transition-colors"
              onClick={() => {
                setIsEditing(false);
                setKey('');
              }}
              disabled={saving}
            >
              Cancel
            </button>
          )}
          <button
            className="bg-black text-white px-5 py-2 border-2 border-black font-semibold text-sm rounded hover:bg-grey-10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            onClick={handleSave}
            disabled={!key.trim() || saving}
          >
            {saving ? 'Connecting…' : 'Connect'}
          </button>
        </div>
      )}
    </div>
  );
}
