'use client';

/**
 * AppShell — three-region layout: Header + Sidebar + Main Content
 * Collapses to single-column stack on mobile with slide-over drawer for sidebar.
 */

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { SessionHistorySidebar } from './SessionHistorySidebar';
import { UserMenu } from './UserMenu';

function MenuIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="3" y1="6" x2="17" y2="6" />
      <line x1="3" y1="10" x2="17" y2="10" />
      <line x1="3" y1="14" x2="17" y2="14" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <line x1="4" y1="4" x2="16" y2="16" />
      <line x1="16" y1="4" x2="4" y2="16" />
    </svg>
  );
}

function SynodWordmark() {
  return (
    <div className="flex items-center gap-2">
      <svg className="w-5 h-5 text-foreground" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
        <circle cx="16" cy="16" r="16" fill="currentColor" />
        <line x1="16" y1="17" x2="16" y2="8" stroke="var(--color-bg)" strokeWidth="2" strokeLinecap="round" />
        <line x1="16" y1="17" x2="8" y2="22" stroke="var(--color-bg)" strokeWidth="2" strokeLinecap="round" />
        <line x1="16" y1="17" x2="24" y2="22" stroke="var(--color-bg)" strokeWidth="2" strokeLinecap="round" />
        <circle cx="16" cy="17" r="3" fill="var(--color-bg)" />
        <circle cx="16" cy="8" r="2" fill="var(--color-bg)" />
        <circle cx="8" cy="22" r="2" fill="var(--color-bg)" />
        <circle cx="24" cy="22" r="2" fill="var(--color-bg)" />
      </svg>
      <span className="font-display font-bold text-lg tracking-tight text-foreground">
        SYNOD
      </span>
    </div>
  );
}

interface HeaderProps {
  onMenuToggle: () => void;
  isMobileMenuOpen: boolean;
}

function Header({ onMenuToggle, isMobileMenuOpen }: HeaderProps) {
  return (
    <header
      role="banner"
      className="sticky top-0 z-50 flex items-center h-12 px-6 gap-4 border-b border-border bg-surface text-foreground"
    >
      <button
        id="mobile-menu-toggle"
        className="md:hidden flex items-center justify-center p-2 text-foreground hover:bg-surface-hover rounded"
        onClick={onMenuToggle}
        aria-label={isMobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
        aria-expanded={isMobileMenuOpen}
      >
        {isMobileMenuOpen ? <CloseIcon /> : <MenuIcon />}
      </button>

      <Link href="/" className="no-underline hover:opacity-80 transition-opacity">
        <SynodWordmark />
      </Link>

      <div className="flex-1" />

      <UserMenu />
    </header>
  );
}

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsMobileMenuOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="flex flex-col min-h-screen bg-background text-foreground">
      <Header
        onMenuToggle={() => setIsMobileMenuOpen((v) => !v)}
        isMobileMenuOpen={isMobileMenuOpen}
      />

      <div className="flex flex-1 overflow-hidden relative">
        <aside
          id="desktop-sidebar"
          aria-label="Session navigation"
          className="hidden md:block w-[220px] min-w-[220px] border-r border-border bg-background overflow-y-auto sticky top-12"
          style={{ height: 'calc(100vh - 48px)' }}
        >
          <SessionHistorySidebar />
        </aside>

        {isMobileMenuOpen && (
          <>
            <div
              id="mobile-overlay"
              onClick={() => setIsMobileMenuOpen(false)}
              className="fixed inset-0 bg-overlay backdrop-blur-sm z-40 md:hidden transition-opacity"
              aria-hidden="true"
            />
            <aside
              id="mobile-sidebar"
              aria-label="Session navigation"
              className="fixed top-12 left-0 bottom-0 w-[220px] bg-background border-r border-border overflow-y-auto z-45 animate-fade-in md:hidden shadow-lg"
            >
              <SessionHistorySidebar />
            </aside>
          </>
        )}

        <main
          id="main-content"
          role="main"
          className="flex-1 overflow-y-auto bg-background text-foreground flex justify-center"
          style={{ height: 'calc(100vh - 48px)' }}
        >
          <div className="w-full max-w-4xl px-8 py-10 mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
