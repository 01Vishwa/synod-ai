'use client';

/**
 * SessionHistorySidebar — left sidebar with session history list,
 * navigation links, and New Session CTA.
 */

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useSessionHistory } from './SessionHistoryContext';

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
      className={`flex items-center gap-2 px-4 py-2 text-sm rounded transition-colors mx-2 no-underline
        ${isActive 
          ? 'font-semibold text-black bg-grey-93' 
          : 'font-normal text-muted hover:bg-grey-93 hover:text-black'
        }`}
    >
      {children}
    </Link>
  );
}

export function SessionHistorySidebar() {
  const { sessions, status } = useSessionHistory();
  const [search, setSearch] = useState('');
  const pathname = usePathname();

  const filtered = Array.isArray(sessions) ? sessions.filter((s) =>
    s.user_query?.toLowerCase().includes(search.toLowerCase()) ||
    (s.headline ?? '').toLowerCase().includes(search.toLowerCase()),
  ) : [];

  const isLoading = status === 'loading';
  const isError = status === 'error';
  const isEmpty = status === 'empty' || status === 'unauthenticated';
  const isSuccess = status === 'success';

  return (
    <nav aria-label="Sidebar navigation" className="flex flex-col h-full pt-4">
      {/* Primary actions */}
      <div className="px-4 mb-4">
        <Link href="/" className="block no-underline">
          <button
            id="sidebar-new-session-btn"
            className="w-full flex items-center justify-center gap-2 bg-black text-white px-6 py-3 font-semibold text-sm rounded border-2 border-black hover:bg-grey-10 transition-colors"
          >
            <PlusIcon />
            New Session
          </button>
        </Link>
      </div>

      {/* Main nav */}
      <div className="flex flex-col gap-1 mb-4">
        <NavLink href="/history" id="sidebar-history-link">
          <ClockIcon />
          History
        </NavLink>
        <NavLink href="/settings" id="sidebar-settings-providers-link">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="2.5" />
            <path d="M8 1v2M8 13v2M1 8h2M13 8h2" />
          </svg>
          Settings
        </NavLink>
      </div>

      <div className="h-px bg-border mx-4 mb-4" />

      {/* Recent Sessions */}
      <div className="px-4 mb-2 flex flex-col gap-2 flex-1 overflow-hidden">
        {(isLoading || isSuccess) ? (
          <p className="text-xs font-semibold text-subtle uppercase tracking-widest mb-1">
            Recent Sessions
          </p>
        ) : null}

        {/* Loading State */}
        {isLoading && (
          <div className="overflow-y-auto flex-1 flex flex-col gap-1">
            <p className="text-xs font-semibold text-subtle uppercase tracking-widest text-center my-4">
              Loading Sessions...
            </p>
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-grey-93 rounded h-[60px] animate-pulse" />
            ))}
          </div>
        )}

        {/* Error State */}
        {isError && (
          <div className="flex-1 flex flex-col justify-center items-center text-center p-4">
            <p className="text-xs font-semibold text-subtle uppercase tracking-widest mb-4">
              History Unavailable
            </p>
          </div>
        )}

        {/* Empty State */}
        {isEmpty && (
          <div className="flex-1 flex flex-col justify-center items-center text-center p-4">
            <p className="text-xs font-semibold text-subtle uppercase tracking-widest mb-4">
              No previous sessions
            </p>
          </div>
        )}

        {/* Success State */}
        {isSuccess && (
          <>
            {/* Search */}
            <div className="relative">
              <span className="absolute left-2 top-1/2 -translate-y-1/2 text-subtle pointer-events-none">
                <SearchIcon />
              </span>
              <input
                id="sidebar-session-search"
                type="search"
                placeholder="Search sessions…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Search past sessions"
                className="w-full pl-7 text-xs h-8 bg-background border border-border rounded focus:border-black focus:ring-2 focus:ring-black/10 outline-none transition-all placeholder-subtle text-foreground"
              />
            </div>

            {/* Session list */}
            <div className="overflow-y-auto flex-1 flex flex-col gap-1">
              {filtered.length === 0 && search && (
                <div className="p-4 text-center text-xs text-subtle">
                  No sessions match your search.
                </div>
              )}

              {filtered.map((session) => {
                const isActive = pathname.includes(session.session_id);
                return (
                  <Link
                    key={session.session_id}
                    href={`/sessions/${session.session_id}`}
                    className="no-underline"
                  >
                    <div
                      className={`px-3 py-2 rounded border transition-colors cursor-pointer
                        ${isActive 
                          ? 'border-2 border-black bg-grey-93' 
                          : 'border border-border bg-background hover:bg-grey-93/50'
                        }`}
                    >
                      <div className="text-xs font-semibold text-foreground overflow-hidden text-ellipsis whitespace-nowrap mb-1">
                        {session.user_query}
                      </div>
                      <div className="text-[11px] text-subtle flex justify-between">
                        <span className="font-mono">{stageBadge(session.stage)}</span>
                        <span>{formatDate(session.created_at)}</span>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </>
        )}
      </div>
    </nav>
  );
}
