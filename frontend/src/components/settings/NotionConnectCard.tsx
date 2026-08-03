'use client';

import React, { useState } from 'react';
import { integrationsApi } from '@/lib/api-client';

interface NotionConnectCardProps {
  isConnected: boolean;
}

export function NotionConnectCard({ isConnected }: NotionConnectCardProps) {
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const res = await integrationsApi.connectNotion();
      window.location.href = res.auth_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start Notion connection.');
      setConnecting(false);
    }
  }

  return (
    <div className="bg-surface border border-border rounded-xl shadow-sm p-6 flex flex-col gap-4">
      <div>
        <div className="flex justify-between items-center mb-1">
          <h3 className="text-lg font-bold text-foreground">Notion Archive</h3>
          {isConnected ? (
            <span className="inline-flex items-center text-xs font-bold text-foreground border-2 border-border-strong rounded-md px-2.5 py-1">
              ✓ Connected
            </span>
          ) : (
            <span className="inline-flex items-center text-xs font-medium text-muted bg-bgSubtle border border-border rounded-md px-2.5 py-1">
              Not connected
            </span>
          )}
        </div>
        <p className="text-sm text-muted m-0">
          Allow Synod to save completed Council reports and deliberation trails directly to a Notion page.
        </p>
      </div>

      <div>
        {isConnected ? (
          <div className="p-3 bg-bgSubtle border border-border rounded-lg text-sm text-foreground space-y-1">
            <span className="font-semibold block">Notion is connected.</span>
            <span className="text-muted block text-xs">
              Synod only has access to the specific pages you shared during the connection process.
            </span>
          </div>
        ) : (
          <div>
            <button
              className="bg-primary text-primary-fg border border-border-strong px-6 py-3 rounded-lg hover:bg-primary-hover transition-colors font-bold text-sm"
              onClick={handleConnect}
              disabled={connecting}
            >
              {connecting ? 'Connecting…' : 'Connect Notion Workspace'}
            </button>
            {error && (
              <div className="text-foreground mt-2 text-sm font-semibold">
                ✕ {error}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
