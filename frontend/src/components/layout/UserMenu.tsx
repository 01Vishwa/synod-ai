'use client';

import React, { useEffect, useState, useRef } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { supabase } from '@/lib/supabase/client';
import { AuthModal } from '@/components/auth/AuthModal';
import { Suspense } from 'react';

function UserMenuInner() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        isMenuOpen &&
        menuRef.current &&
        !menuRef.current.contains(event.target as Node)
      ) {
        setIsMenuOpen(false);
      }
    };

    if (isMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isMenuOpen]);

  const handleMenuKeyDown = (e: React.KeyboardEvent) => {
    if (!isMenuOpen) return;

    if (e.key === 'Escape') {
      e.preventDefault();
      setIsMenuOpen(false);
      buttonRef.current?.focus();
      return;
    }

    const menu = menuRef.current;
    if (!menu) return;

    const items = Array.from(menu.querySelectorAll<HTMLElement>('[role="menuitem"]'));
    if (items.length === 0) return;

    const index = items.indexOf(document.activeElement as HTMLElement);

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const nextIndex = index >= 0 ? (index + 1) % items.length : 0;
      items[nextIndex]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prevIndex = index >= 0 ? (index - 1 + items.length) % items.length : items.length - 1;
      items[prevIndex]?.focus();
    }
  };

  useEffect(() => {
    // Check initial session
    const fetchSession = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.user) {
        setIsAuthenticated(true);
        setUserEmail(session.user.email ?? null);
      } else {
        setIsAuthenticated(false);
        setUserEmail(null);
        if (searchParams.get('auth') === 'required') {
          setIsModalOpen(true);
        }
      }
    };

    fetchSession();

    // Listen for auth state changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        setIsAuthenticated(true);
        setUserEmail(session.user.email ?? null);
      } else {
        setIsAuthenticated(false);
        setUserEmail(null);
      }
    });

    return () => {
      subscription.unsubscribe();
    };
  }, [searchParams]);

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    setIsMenuOpen(false);
    router.refresh();
  };

  const truncatedEmail = userEmail ? (userEmail.length > 20 ? userEmail.substring(0, 17) + '...' : userEmail) : '';

  return (
    <>
      {!isAuthenticated ? (
        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-3 py-1.5 text-sm font-bold bg-primary text-primary-fg border border-border-strong hover:bg-primary-hover transition-colors rounded"
        >
          Sign In
        </button>
      ) : (
        <div className="relative" ref={menuRef} onKeyDown={handleMenuKeyDown}>
          <button
            ref={buttonRef}
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            aria-expanded={isMenuOpen}
            aria-haspopup="true"
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-bold border border-border-strong bg-surface text-foreground hover:bg-surface-hover transition-colors rounded"
          >
            <div className="w-5 h-5 rounded-full bg-primary text-primary-fg flex items-center justify-center text-xs">
              {userEmail ? userEmail[0].toUpperCase() : 'U'}
            </div>
            <span className="hidden sm:inline">{truncatedEmail}</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`transition-transform ${isMenuOpen ? 'rotate-180' : ''}`}>
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </button>

          {isMenuOpen && (
            <div 
              className="absolute right-0 mt-1 w-48 bg-surface border border-border-strong rounded-md shadow-lg z-50 origin-top-right overflow-hidden"
              role="menu"
            >
              <div className="p-3 border-b border-border-strong sm:hidden">
                <span className="text-sm font-bold text-foreground break-all">{userEmail}</span>
              </div>
              <Link
                href="/settings"
                role="menuitem"
                onClick={() => setIsMenuOpen(false)}
                className="flex items-center justify-start gap-[10px] w-full h-11 px-4 text-sm font-bold text-foreground no-underline hover:bg-surface-hover transition-colors border-b border-border-strong focus:outline-none focus:bg-surface-hover cursor-pointer text-left"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-foreground">
                  <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
                <span>Settings</span>
              </Link>
              <button
                role="menuitem"
                onClick={handleSignOut}
                className="flex items-center justify-start gap-[10px] w-full h-11 px-4 text-sm font-bold text-foreground no-underline hover:bg-surface-hover transition-colors focus:outline-none focus:bg-surface-hover cursor-pointer text-left"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-foreground">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                  <polyline points="16 17 21 12 16 7"/>
                  <line x1="21" y1="12" x2="9" y2="12"/>
                </svg>
                <span>Sign Out</span>
              </button>
            </div>
          )}
        </div>
      )}

      <AuthModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} />
    </>
  );
}

export function UserMenu() {
  return (
    <Suspense fallback={<div className="w-8 h-8 rounded-full bg-border animate-pulse"></div>}>
      <UserMenuInner />
    </Suspense>
  );
}
