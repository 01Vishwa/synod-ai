'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '@/lib/supabase/client';
import { AuthModal } from '@/components/auth/AuthModal';

export function UserMenu() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const router = useRouter();

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
  }, []);

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
          className="flex items-center gap-2 px-3 py-1.5 text-sm font-bold bg-black text-white border border-black hover:bg-white hover:text-black transition-colors rounded"
        >
          Sign In
        </button>
      ) : (
        <div className="relative">
          <button
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-bold border border-black bg-white text-black hover:bg-grey-93 transition-colors rounded"
          >
            <div className="w-5 h-5 rounded-full bg-black text-white flex items-center justify-center text-xs">
              {userEmail ? userEmail[0].toUpperCase() : 'U'}
            </div>
            <span className="hidden sm:inline">{truncatedEmail}</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`transition-transform ${isMenuOpen ? 'rotate-180' : ''}`}>
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </button>

          {isMenuOpen && (
            <div className="absolute right-0 mt-1 w-48 bg-white border border-black shadow-lg z-50">
              <div className="p-3 border-b border-black sm:hidden">
                <span className="text-sm font-bold text-black break-all">{userEmail}</span>
              </div>
              <button
                onClick={handleSignOut}
                className="w-full text-left px-4 py-2 text-sm font-bold text-black hover:bg-grey-93 transition-colors"
              >
                Sign Out
              </button>
            </div>
          )}
        </div>
      )}

      <AuthModal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} />
    </>
  );
}
