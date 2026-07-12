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
      // Redirect to the Notion OAuth URL returned by the backend
      window.location.href = res.auth_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start Notion connection.');
      setConnecting(false);
    }
  }

  return (
    <div className="card-subtle" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-1)' }}>Notion Archive</h3>
          {isConnected ? (
            <span className="badge">✓ Connected</span>
          ) : (
            <span className="badge badge-muted">Not connected</span>
          )}
        </div>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-subtle)', margin: 0 }}>
          Allow Synod to save completed Council reports and deliberation trails directly to a Notion page.
        </p>
      </div>

      <div>
        {isConnected ? (
          <div style={{ padding: 'var(--space-3)', background: 'var(--grey-93)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-sm)' }}>
            <span style={{ fontWeight: 600 }}>Notion is connected.</span>
            <br />
            <span style={{ color: 'var(--color-text-subtle)' }}>
              Synod only has access to the specific pages you shared during the connection process.
            </span>
          </div>
        ) : (
          <div>
            <button
              className="btn-primary"
              onClick={handleConnect}
              disabled={connecting}
            >
              {connecting ? 'Connecting…' : 'Connect Notion Workspace'}
            </button>
            {error && (
              <div style={{ color: 'var(--color-text)', marginTop: 'var(--space-2)', fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                ✕ {error}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
