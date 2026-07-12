'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { sessionsApi, type SessionSummary } from '@/lib/api-client';
import { observabilityApi } from '@/lib/api-client';

function formatDateFull(iso: string) {
  try {
    return new Date(iso).toLocaleString('en-US', {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

export default function HistoryPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    sessionsApi.list()
      .then(setSessions)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = sessions.filter((s) =>
    s.user_query.toLowerCase().includes(search.toLowerCase()) ||
    (s.headline ?? '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', padding: 'var(--space-8) var(--content-gutter)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 'var(--space-8)' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 'var(--text-2xl)', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
            Session History
          </h1>
          <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
            Review past council deliberations and their outcomes.
          </p>
        </div>
        <Link href="/">
          <button className="btn-primary">New Session</button>
        </Link>
      </div>

      <div style={{ marginBottom: 'var(--space-6)' }}>
        <input
          type="search"
          placeholder="Search by query or outcome…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ maxWidth: '400px' }}
        />
      </div>

      {loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="skeleton" style={{ height: '120px' }} />
          ))}
        </div>
      )}

      {error && (
        <div className="card" style={{ borderColor: 'var(--grey-0)' }}>
          <p style={{ fontWeight: 700, margin: 0 }}>Failed to load history.</p>
          <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>{error}</p>
        </div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="card-subtle" style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
          <p style={{ color: 'var(--color-text-muted)', margin: 0 }}>
            {search ? 'No sessions match your search.' : 'No sessions yet.'}
          </p>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {filtered.map(session => (
          <div key={session.session_id} className="card" style={{ transition: 'border-color var(--transition-fast)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-4)' }}>
              <div>
                <Link href={`/sessions/${session.session_id}`} style={{ textDecoration: 'none' }}>
                  <h3 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: 'var(--space-1)' }}>
                    {session.user_query}
                  </h3>
                </Link>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-subtle)', fontFamily: 'var(--font-mono)', display: 'flex', gap: 'var(--space-4)' }}>
                  <span>{formatDateFull(session.created_at)}</span>
                  <span>{session.member_count} members</span>
                  <span>${session.total_cost_usd.toFixed(4)}</span>
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
                <span className="badge badge-muted" style={{ fontSize: '11px' }}>
                  {session.stage === 'done' ? '✓ Complete' : session.stage === 'error' ? '✕ Failed' : '◌ In Progress'}
                </span>
              </div>
            </div>

            {session.headline && (
              <div style={{ padding: 'var(--space-3)', background: 'var(--grey-93)', borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-sm)' }}>
                <span style={{ fontWeight: 600 }}>Outcome: </span>
                <span style={{ color: 'var(--color-text-muted)' }}>{session.headline}</span>
              </div>
            )}

            <div style={{ display: 'flex', gap: 'var(--space-4)', marginTop: 'var(--space-4)', fontSize: 'var(--text-xs)' }}>
              <Link href={`/sessions/${session.session_id}`}>
                View full session →
              </Link>
              {session.notion_page_url && (
                <a href={session.notion_page_url} target="_blank" rel="noopener noreferrer">
                  View in Notion ↗
                </a>
              )}
              {session.trace_id && (
                <a href={observabilityApi.getTraceUrl(session.trace_id)} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-text-subtle)' }}>
                  View Trace ↗
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
