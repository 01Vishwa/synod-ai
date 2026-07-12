'use client';

/**
 * SessionHistorySidebar — left sidebar with session history list,
 * navigation links, and New Session CTA.
 */

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { sessionsApi, type SessionSummary } from '@/lib/api-client';

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="8" y1="2" x2="8" y2="14" />
      <line x1="2" y1="8" x2="14" y2="8" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="8" cy="8" r="6.5" />
      <polyline points="8,4 8,8 11,10" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="7" cy="7" r="5" />
      <line x1="11" y1="11" x2="15" y2="15" />
    </svg>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const hours = diff / 1000 / 60 / 60;
    if (hours < 1) return 'just now';
    if (hours < 24) return `${Math.floor(hours)}h ago`;
    if (hours < 48) return 'yesterday';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
}

function stageBadge(stage: string): string {
  switch (stage) {
    case 'done': return '✓ Done';
    case 'stage_1': return '◌ Stage 1';
    case 'stage_2': return '◌ Stage 2';
    case 'stage_3': return '◌ Stage 3';
    case 'archiving': return '◌ Archiving';
    case 'error': return '✕ Error';
    default: return stage;
  }
}

interface NavLinkProps {
  href: string;
  children: React.ReactNode;
  id?: string;
}

function NavLink({ href, children, id }: NavLinkProps) {
  const pathname = usePathname();
  const isActive = pathname === href || pathname.startsWith(href + '/');

  return (
    <Link
      href={href}
      id={id}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        padding: 'var(--space-2) var(--space-4)',
        fontSize: 'var(--text-sm)',
        fontWeight: isActive ? 600 : 400,
        color: isActive ? 'var(--grey-0)' : 'var(--color-text-muted)',
        textDecoration: 'none',
        borderRadius: 'var(--radius-sm)',
        transition: 'background-color var(--transition-fast), color var(--transition-fast)',
        background: isActive ? 'var(--grey-93)' : 'transparent',
        margin: '0 var(--space-2)',
      }}
      onMouseEnter={(e) => {
        if (!isActive) {
          (e.currentTarget as HTMLElement).style.background = 'var(--grey-93)';
          (e.currentTarget as HTMLElement).style.color = 'var(--grey-0)';
        }
      }}
      onMouseLeave={(e) => {
        if (!isActive) {
          (e.currentTarget as HTMLElement).style.background = 'transparent';
          (e.currentTarget as HTMLElement).style.color = 'var(--color-text-muted)';
        }
      }}
    >
      {children}
    </Link>
  );
}

export function SessionHistorySidebar() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const pathname = usePathname();

  useEffect(() => {
    sessionsApi.list()
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, [pathname]); // re-fetch on route change

  const filtered = sessions.filter((s) =>
    s.user_query.toLowerCase().includes(search.toLowerCase()) ||
    (s.headline ?? '').toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <nav
      aria-label="Sidebar navigation"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        paddingTop: 'var(--space-4)',
      }}
    >
      {/* Primary actions */}
      <div style={{ padding: '0 var(--space-4)', marginBottom: 'var(--space-4)' }}>
        <Link href="/" style={{ textDecoration: 'none', display: 'block' }}>
          <button
            id="sidebar-new-session-btn"
            className="btn-primary"
            style={{ width: '100%', justifyContent: 'center' }}
          >
            <PlusIcon />
            New Session
          </button>
        </Link>
      </div>

      {/* Main nav */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-1)',
          marginBottom: 'var(--space-4)',
        }}
      >
        <NavLink href="/history" id="sidebar-history-link">
          <ClockIcon />
          History
        </NavLink>
        <NavLink href="/settings/providers" id="sidebar-settings-providers-link">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="2.5" />
            <path d="M8 1v2M8 13v2M1 8h2M13 8h2" />
          </svg>
          Settings
        </NavLink>
      </div>

      <div
        style={{
          height: '1px',
          background: 'var(--color-border)',
          margin: '0 var(--space-4) var(--space-4)',
        }}
      />

      {/* Recent Sessions */}
      <div
        style={{
          padding: '0 var(--space-4)',
          marginBottom: 'var(--space-2)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          flex: 1,
          overflow: 'hidden',
        }}
      >
        <p
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            color: 'var(--color-text-subtle)',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            marginBottom: 'var(--space-1)',
          }}
        >
          Recent Sessions
        </p>

        {/* Search */}
        <div style={{ position: 'relative' }}>
          <span
            style={{
              position: 'absolute',
              left: 'var(--space-2)',
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--color-text-subtle)',
              pointerEvents: 'none',
            }}
          >
            <SearchIcon />
          </span>
          <input
            id="sidebar-session-search"
            type="search"
            placeholder="Search sessions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search past sessions"
            style={{
              paddingLeft: '28px',
              fontSize: 'var(--text-xs)',
              height: '32px',
            }}
          />
        </div>

        {/* Session list */}
        <div
          style={{
            overflowY: 'auto',
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-1)',
          }}
        >
          {loading && (
            <>
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="skeleton"
                  style={{ height: '60px', borderRadius: 'var(--radius-sm)' }}
                />
              ))}
            </>
          )}

          {!loading && filtered.length === 0 && (
            <div
              style={{
                padding: 'var(--space-4)',
                textAlign: 'center',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-subtle)',
              }}
            >
              {search ? 'No sessions match your search.' : 'No sessions yet.'}
            </div>
          )}

          {filtered.map((session) => {
            const isActive = pathname.includes(session.session_id);
            return (
              <Link
                key={session.session_id}
                href={`/sessions/${session.session_id}`}
                style={{ textDecoration: 'none' }}
              >
                <div
                  style={{
                    padding: 'var(--space-2) var(--space-3)',
                    borderRadius: 'var(--radius-sm)',
                    border: isActive ? '2px solid var(--grey-0)' : '1px solid var(--color-border)',
                    background: isActive ? 'var(--grey-93)' : 'var(--color-bg)',
                    cursor: 'pointer',
                    transition: 'border-color var(--transition-fast)',
                  }}
                >
                  <div
                    style={{
                      fontSize: 'var(--text-xs)',
                      fontWeight: 600,
                      color: 'var(--color-text)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      marginBottom: 'var(--space-1)',
                    }}
                  >
                    {session.user_query}
                  </div>
                  <div
                    style={{
                      fontSize: '11px',
                      color: 'var(--color-text-subtle)',
                      display: 'flex',
                      justifyContent: 'space-between',
                    }}
                  >
                    <span style={{ fontFamily: 'var(--font-mono)' }}>
                      {stageBadge(session.stage)}
                    </span>
                    <span>{formatDate(session.created_at)}</span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
