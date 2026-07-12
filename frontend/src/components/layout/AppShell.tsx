'use client';

/**
 * AppShell — three-region layout: Header + Sidebar + Main Content
 * Collapses to single-column stack on mobile with slide-over drawer for sidebar.
 */

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { SessionHistorySidebar } from './SessionHistorySidebar';

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
    <span
      style={{
        fontFamily: 'var(--font-display)',
        fontWeight: 700,
        fontSize: '18px',
        letterSpacing: '-0.5px',
        color: 'var(--grey-0)',
      }}
    >
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
      style={{
        height: 'var(--header-height)',
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 var(--space-6)',
        gap: 'var(--space-4)',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}
    >
      <button
        id="mobile-menu-toggle"
        className="btn-ghost"
        onClick={onMenuToggle}
        aria-label={isMobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}
        aria-expanded={isMobileMenuOpen}
        style={{ display: 'none' }}
        data-mobile-only="true"
      >
        {isMobileMenuOpen ? <CloseIcon /> : <MenuIcon />}
      </button>

      <Link href="/" style={{ textDecoration: 'none' }}>
        <SynodWordmark />
      </Link>

      <span
        style={{
          fontSize: 'var(--text-xs)',
          color: 'var(--color-text-subtle)',
          fontFamily: 'var(--font-mono)',
          marginLeft: 'var(--space-2)',
        }}
      >
        Where Models Convene, Truth Concludes.
      </span>

      <div style={{ flex: 1 }} />

      <Link href="/settings/providers" style={{ textDecoration: 'none' }}>
        <button className="btn-ghost btn-sm" id="header-settings-link">
          <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="10" cy="10" r="3" />
            <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.22 4.22l1.42 1.42M14.36 14.36l1.42 1.42M4.22 15.78l1.42-1.42M14.36 5.64l1.42-1.42" />
          </svg>
          <span>Settings</span>
        </button>
      </Link>
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
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        background: 'var(--color-bg)',
      }}
    >
      <Header
        onMenuToggle={() => setIsMobileMenuOpen((v) => !v)}
        isMobileMenuOpen={isMobileMenuOpen}
      />

      <div
        style={{
          display: 'flex',
          flex: 1,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <aside
          id="desktop-sidebar"
          aria-label="Session navigation"
          style={{
            width: 'var(--sidebar-width)',
            minWidth: 'var(--sidebar-width)',
            borderRight: '1px solid var(--color-border)',
            background: 'var(--color-bg)',
            overflowY: 'auto',
            height: 'calc(100vh - var(--header-height))',
            position: 'sticky',
            top: 'var(--header-height)',
          }}
        >
          <SessionHistorySidebar />
        </aside>

        {isMobileMenuOpen && (
          <>
            <div
              id="mobile-overlay"
              onClick={() => setIsMobileMenuOpen(false)}
              style={{
                position: 'fixed',
                inset: 0,
                background: 'rgba(0,0,0,0.5)',
                zIndex: 40,
              }}
              aria-hidden="true"
            />
            <aside
              id="mobile-sidebar"
              aria-label="Session navigation"
              style={{
                position: 'fixed',
                top: 'var(--header-height)',
                left: 0,
                bottom: 0,
                width: 'var(--sidebar-width)',
                background: 'var(--color-bg)',
                borderRight: '1px solid var(--color-border)',
                overflowY: 'auto',
                zIndex: 45,
                animation: 'fadeIn 200ms ease',
              }}
            >
              <SessionHistorySidebar />
            </aside>
          </>
        )}

        <main
          id="main-content"
          role="main"
          style={{
            flex: 1,
            overflowY: 'auto',
            height: 'calc(100vh - var(--header-height))',
          }}
        >
          {children}
        </main>
      </div>

      <style>{`
        @media (max-width: 768px) {
          #desktop-sidebar { display: none; }
          button[data-mobile-only] { display: inline-flex !important; }
        }
      `}</style>
    </div>
  );
}
