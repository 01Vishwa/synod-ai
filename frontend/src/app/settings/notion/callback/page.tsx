'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export default function NotionCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;

    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const notionError = searchParams.get('error');

    if (notionError) {
      window.location.href = `/settings/integrations?notion_error=${notionError}`;
      return;
    }

    if (!code || !state) {
      window.location.href = `/settings/integrations?notion_error=missing_parameters`;
      return;
    }

    // Call the backend callback endpoint. It will complete the OAuth flow
    // and return a redirect response (handled seamlessly by the browser) 
    // or an error if it fails.
    window.location.href = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/notion/oauth/callback?code=${code}&state=${state}`;

  }, [searchParams, router]);

  return (
    <div style={{ maxWidth: '600px', margin: '4rem auto', textAlign: 'center' }}>
      {error ? (
        <div style={{ border: '1px solid var(--color-error)', padding: 'var(--space-4)', borderRadius: 'var(--radius-md)' }}>
          <h2 style={{ color: 'var(--color-error)' }}>Connection Failed</h2>
          <p>{error}</p>
          <button className="btn-primary" onClick={() => router.push('/settings/integrations')} style={{ marginTop: 'var(--space-4)' }}>
            Return to Settings
          </button>
        </div>
      ) : (
        <div style={{ padding: 'var(--space-4)' }}>
          <h2>Connecting Notion...</h2>
          <p style={{ color: 'var(--color-text-subtle)' }}>Please wait while we complete the secure setup.</p>
        </div>
      )}
    </div>
  );
}
