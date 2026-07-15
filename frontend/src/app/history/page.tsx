'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { observabilityApi } from '@/lib/api-client';
import { useSessionHistory } from '@/components/layout/SessionHistoryContext';

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
  const { sessions, status, refresh } = useSessionHistory();
  const [search, setSearch] = useState('');

  const filtered = Array.isArray(sessions) ? sessions.filter((s) =>
    s.user_query.toLowerCase().includes(search.toLowerCase()) ||
    (s.headline ?? '').toLowerCase().includes(search.toLowerCase())
  ) : [];

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

      {status === 'unauthenticated' && (
        <div
          className="card-subtle"
          style={{
            textAlign: 'center',
            padding: 'var(--space-12)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 'var(--space-4)',
          }}
        >
          <svg
            width="40"
            height="40"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ color: 'var(--color-text-subtle)' }}
          >
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
          </svg>
          <div>
            <p style={{ fontWeight: 600, margin: '0 0 var(--space-1)' }}>Sign in to view your history</p>
            <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
              Your past council sessions will appear here once you&apos;re signed in.
            </p>
          </div>
          <Link href="/">
            <button className="btn-primary" style={{ marginTop: 'var(--space-2)' }}>Sign In</button>
          </Link>
        </div>
      )}

      {status !== 'unauthenticated' && (
        <>
          <div style={{ marginBottom: 'var(--space-6)' }}>
            <input
              type="search"
              placeholder="Search by query or outcome…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ maxWidth: '400px' }}
              disabled={status === 'loading' || status === 'empty' || status === 'error'}
            />
          </div>

          {status === 'loading' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="skeleton" style={{ height: '120px' }} />
              ))}
            </div>
          )}

          {status === 'error' && (
            <div className="card-subtle" style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
              <p style={{ fontWeight: 600, margin: '0 0 var(--space-1)', color: 'var(--color-text)' }}>
                COULD NOT LOAD HISTORY
              </p>
              <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: '0 0 var(--space-4)' }}>
                Your session history could not be loaded.
              </p>
              <button className="btn-primary" onClick={() => refresh()}>Try Again</button>
            </div>
          )}

          {status === 'empty' && (
            <div style={{ 
              textAlign: 'center', 
              padding: 'var(--space-12)',
              borderTop: '1px solid var(--color-border)',
              marginTop: 'var(--space-8)'
            }}>
              {/* Illustration */}
              <svg
                width="40"
                height="40"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ color: 'var(--color-text-subtle)', margin: '0 auto var(--space-4)' }}
              >
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <path d="M8 12h8M12 8v8" />
              </svg>
              <p style={{ fontWeight: 600, color: 'var(--color-text)', margin: '0 0 var(--space-2)' }}>
                No Sessions Yet
              </p>
              <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0, maxWidth: '320px', marginInline: 'auto' }}>
                Your council sessions will appear here once you start your first deliberation.
                Use the <strong>New Session</strong> button in the top-right to get started.
              </p>
            </div>
          )}

          {status === 'success' && filtered.length === 0 && (
            <div className="card-subtle" style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
              <p style={{ fontWeight: 600, color: 'var(--color-text)', margin: '0 0 var(--space-2)' }}>
                No matching sessions
              </p>
              <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                No sessions match &quot;{search}&quot;.
              </p>
            </div>
          )}

          {status === 'success' && filtered.length > 0 && (
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
                        <span>Updated {formatDateFull(session.created_at)}</span>
                        <span>{session.member_count} Council Members</span>
                        {/* Evidence count placeholder if available, otherwise just these */}
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
          )}
        </>
      )}
    </div>
  );
}
