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
          className="bg-surface border border-border rounded-xl"
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
            className="text-subtle"
          >
            <circle cx="12" cy="8" r="4" />
            <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
          </svg>
          <div>
            <p style={{ fontWeight: 600, margin: '0 0 var(--space-1)', color: 'var(--color-text)' }}>Sign in to view your history</p>
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
                <div key={i} className="bg-bgSubtle rounded-xl h-[120px] animate-pulse" />
              ))}
            </div>
          )}

          {status === 'error' && (
            <div className="bg-surface border border-border rounded-xl" style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
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
              marginTop: 'var(--space-8)'
            }}>
              {/* Illustration */}
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-subtle mx-auto mb-4">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="16" y1="2" x2="16" y2="6"></line>
                <line x1="8" y1="2" x2="8" y2="6"></line>
                <line x1="3" y1="10" x2="21" y2="10"></line>
              </svg>
              <h3 className="text-lg font-bold text-foreground mb-2">
                No sessions yet
              </h3>
              <p className="text-sm text-muted max-w-sm mx-auto mb-6">
                Convene your first council to see results here.
              </p>
              <Link href="/">
                <button className="bg-primary text-primary-fg border border-border-strong px-6 h-12 font-bold text-sm rounded-lg hover:bg-primary-hover transition-colors shadow-sm inline-flex items-center justify-center">
                  Start a session
                </button>
              </Link>
            </div>
          )}

          {status === 'success' && filtered.length === 0 && (
            <div className="bg-surface border border-border rounded-xl" style={{ textAlign: 'center', padding: 'var(--space-12)' }}>
              <p style={{ fontWeight: 600, color: 'var(--color-text)', margin: '0 0 var(--space-2)' }}>
                No matching sessions
              </p>
              <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                No sessions match &quot;{search}&quot;.
              </p>
            </div>
          )}

          {status === 'success' && filtered.length > 0 && (
            <div className="flex flex-col gap-4">
              {filtered.map(session => (
                <div key={session.session_id} className="bg-surface border border-border rounded-xl p-5 shadow-sm hover:border-border-strong transition-colors">
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <Link href={`/sessions/${session.session_id}`} className="no-underline">
                        <h3 className="text-lg font-bold text-foreground mb-1 hover:opacity-80 transition-opacity">
                          {session.user_query}
                        </h3>
                      </Link>
                      <div className="text-xs text-muted flex items-center gap-3">
                        <span>{formatDateFull(session.created_at)}</span>
                        <span>•</span>
                        <span>{session.member_count} Models</span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold border border-border-strong bg-bgSubtle text-foreground">
                        {session.stage === 'done' ? 'Complete' : session.stage === 'error' ? 'Failed' : 'In Progress'}
                      </span>
                    </div>
                  </div>

                  {session.headline && (
                    <div className="bg-bgSubtle rounded-lg p-3 text-sm text-foreground border border-border">
                      <span className="font-bold text-foreground">Outcome: </span>
                      {session.headline}
                    </div>
                  )}

                  <div className="flex gap-4 mt-4 text-sm font-bold">
                    <Link href={`/sessions/${session.session_id}`} className="text-foreground hover:underline transition-colors">
                      View session →
                    </Link>
                    {session.notion_page_url && (
                      <a href={session.notion_page_url} target="_blank" rel="noopener noreferrer" className="text-muted hover:text-foreground transition-colors">
                        View in Notion ↗
                      </a>
                    )}
                    {session.trace_id && (
                      <a href={observabilityApi.getTraceUrl(session.trace_id)} target="_blank" rel="noopener noreferrer" className="text-subtle hover:text-muted transition-colors">
                        Trace ↗
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
