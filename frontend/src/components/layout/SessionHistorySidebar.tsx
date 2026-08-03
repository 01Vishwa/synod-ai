'use client';

/**
 * SessionHistorySidebar — left sidebar with session history list,
 * navigation links, and New Session CTA.
 */

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useSessionHistory } from './SessionHistoryContext';
import { StatusBadge, type StatusType } from '@/components/ui/StatusBadge';

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

function getSessionStatus(stage: string): StatusType {
  switch (stage) {
    case 'done': return 'completed';
    case 'archiving': return 'running';
    case 'error': return 'failed';
    default: return 'running';
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
      className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg transition-colors mx-3 no-underline outline-none focus-visible:ring-2 focus-visible:ring-primary/20
        ${isActive 
          ? 'font-bold text-foreground bg-surface-hover shadow-[inset_2px_0_0_0_var(--color-primary)]' 
          : 'font-medium text-muted hover:bg-surface-hover hover:text-foreground'
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
    <nav aria-label="Sidebar navigation" className="flex flex-col h-full pt-4 w-full">
      {/* Primary actions */}
      <div className="px-4 mb-6">
        <Link href="/" className="block no-underline outline-none">
          <button
            id="sidebar-new-session-btn"
            className="w-full flex items-center justify-center gap-2 bg-primary text-primary-fg border border-primary/20 px-4 py-2.5 font-bold text-sm rounded-lg hover:bg-primary-hover transition-colors shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
          >
            <PlusIcon />
            New Session
          </button>
        </Link>
      </div>

      {/* Main nav */}
      <div className="flex flex-col gap-1 mb-6">
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

      <div className="h-px bg-border mx-4 mb-6" />

      {/* Recent Sessions */}
      <div className="px-4 mb-2 flex flex-col gap-3 flex-1 overflow-hidden">
        {(isLoading || isSuccess) ? (
          <p className="text-[10px] font-bold text-subtle uppercase tracking-widest px-1">
            Recent Sessions
          </p>
        ) : null}

        {/* Loading State */}
        {isLoading && (
          <div className="overflow-y-auto flex-1 flex flex-col gap-2 pb-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="bg-bgSubtle rounded-xl h-[72px] animate-pulse border border-border" />
            ))}
          </div>
        )}

        {/* Error State */}
        {isError && (
          <div className="flex-1 flex flex-col justify-center items-center text-center p-4">
            <p className="text-xs font-bold text-subtle uppercase tracking-widest mb-4">
              History Unavailable
            </p>
          </div>
        )}

        {/* Empty State */}
        {isEmpty && (
          <div className="flex-1 flex flex-col justify-center items-center text-center p-4 opacity-50">
            <svg className="w-8 h-8 text-muted mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <p className="text-xs font-bold text-subtle uppercase tracking-widest">
              No previous sessions
            </p>
          </div>
        )}

        {/* Success State */}
        {isSuccess && (
          <>
            {/* Search */}
            <div className="relative shrink-0">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-subtle pointer-events-none">
                <SearchIcon />
              </span>
              <input
                id="sidebar-session-search"
                type="search"
                placeholder="Search sessions…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Search past sessions"
                className="w-full pl-9 pr-3 text-xs h-9 bg-surface border border-border rounded-lg focus:border-primary/50 focus:ring-2 focus:ring-primary/20 outline-none transition-all placeholder:text-muted text-foreground shadow-sm"
              />
            </div>

            {/* Session list */}
            <div className="overflow-y-auto flex-1 flex flex-col gap-2 pb-4 hide-scrollbar">
              {filtered.length === 0 && search && (
                <div className="p-6 text-center text-xs text-subtle">
                  No sessions match your search.
                </div>
              )}

              {filtered.map((session) => {
                const isActive = pathname.includes(session.session_id);
                const sessionStatus = getSessionStatus(session.stage);
                
                return (
                  <Link
                    key={session.session_id}
                    href={`/sessions/${session.session_id}`}
                    className="no-underline outline-none"
                  >
                    <div
                      className={`px-4 py-3 rounded-xl border transition-all cursor-pointer group
                        ${isActive 
                          ? 'border-border-strong bg-surface shadow-sm' 
                          : 'border-transparent bg-transparent hover:bg-surface-hover hover:border-border'
                        }`}
                    >
                      <div className={`text-sm font-bold mb-2 line-clamp-2 leading-snug transition-colors
                        ${isActive ? 'text-foreground' : 'text-muted group-hover:text-foreground'}`}>
                        {session.user_query}
                      </div>
                      <div className="flex items-center justify-between">
                        <StatusBadge status={sessionStatus} />
                        <span className="text-[10px] font-mono text-muted group-hover:text-subtle transition-colors">
                          {formatDate(session.created_at)}
                        </span>
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
