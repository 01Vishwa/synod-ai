'use client';

import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { sessionsApi, type SessionSummary } from '@/lib/api-client';
import { supabase } from '@/lib/supabase/client';

export type HistoryState = 'loading' | 'empty' | 'success' | 'error' | 'unauthenticated';

interface SessionHistoryContextType {
  sessions: SessionSummary[];
  status: HistoryState;
  refresh: () => Promise<void>;
}

const SessionHistoryContext = createContext<SessionHistoryContextType | undefined>(undefined);

export function SessionHistoryProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [status, setStatus] = useState<HistoryState>('loading');
  const pathname = usePathname();

  const fetchHistory = async () => {
    // Prevent flickering to loading if we already have success/empty
    // We only set loading if it's the first time or error state, 
    // or just let it update gracefully in the background.
    if (status === 'error' || status === 'unauthenticated') {
      setStatus('loading');
    }
    
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        setSessions([]);
        setStatus('unauthenticated');
        return;
      }
      
      const res = await sessionsApi.list();
      if (res && Array.isArray(res.items)) {
        setSessions(res.items);
        setStatus(res.items.length > 0 ? 'success' : 'empty');
      } else {
        setSessions([]);
        setStatus('empty');
      }
    } catch (error) {
      console.error("Failed to load history:", error);
      setSessions([]);
      setStatus('error');
    }
  };

  useEffect(() => {
    fetchHistory();

    const { data: authListener } = supabase.auth.onAuthStateChange((event, session) => {
      fetchHistory();
    });

    return () => {
      authListener.subscription.unsubscribe();
    };
  }, [pathname]);

  return (
    <SessionHistoryContext.Provider value={{ sessions, status, refresh: fetchHistory }}>
      {children}
    </SessionHistoryContext.Provider>
  );
}

export function useSessionHistory() {
  const context = useContext(SessionHistoryContext);
  if (context === undefined) {
    throw new Error('useSessionHistory must be used within a SessionHistoryProvider');
  }
  return context;
}
