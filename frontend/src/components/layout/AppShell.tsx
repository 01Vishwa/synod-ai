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
    <span className="font-display font-bold text-lg tracking-tight text-black">
      SYNOD
    </span>
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
      className="sticky top-0 z-50 flex items-center h-14 px-6 gap-4 border-b border-border bg-background"
    >
      <button
        id="mobile-menu-toggle"
        className="md:hidden flex items-center justify-center p-2 text-foreground hover:bg-grey-93 rounded"
        onClick={onMenuToggle}
        aria-label={isMobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
        aria-expanded={isMobileMenuOpen}
      >
        {isMobileMenuOpen ? <CloseIcon /> : <MenuIcon />}
      </button>

      <Link href="/" className="no-underline hover:opacity-80 transition-opacity">
        <SynodWordmark />
      </Link>

      <span className="hidden sm:inline text-xs text-subtle font-mono ml-2">
        Where Models Convene, Truth Concludes.
      </span>

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
    <div className="flex flex-col min-h-screen bg-background">
      <Header
        onMenuToggle={() => setIsMobileMenuOpen((v) => !v)}
        isMobileMenuOpen={isMobileMenuOpen}
      />

      <div className="flex flex-1 overflow-hidden relative">
        <aside
          id="desktop-sidebar"
          aria-label="Session navigation"
          className="hidden md:block w-60 min-w-60 border-r border-border bg-background overflow-y-auto sticky top-14"
          style={{ height: 'calc(100vh - 56px)' }}
        >
          <SessionHistorySidebar />
        </aside>

        {isMobileMenuOpen && (
          <>
            <div
              id="mobile-overlay"
              onClick={() => setIsMobileMenuOpen(false)}
              className="fixed inset-0 bg-black/50 z-40 md:hidden"
              aria-hidden="true"
            />
            <aside
              id="mobile-sidebar"
              aria-label="Session navigation"
              className="fixed top-14 left-0 bottom-0 w-60 bg-background border-r border-border overflow-y-auto z-45 animate-fade-in md:hidden"
            >
              <SessionHistorySidebar />
            </aside>
          </>
        )}

        <main
          id="main-content"
          role="main"
          className="flex-1 overflow-y-auto"
          style={{ height: 'calc(100vh - 56px)' }}
        >
          {children}
        </main>
      </div>
    </div>
  );
}
