'use client';

import React, { useState, useCallback } from 'react';
import { ToastContext, type Toast, type ToastType, type ToastOptions } from '@/hooks/useToast';

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback((message: string, type: ToastType = 'info', options?: ToastOptions) => {
    const id = Math.random().toString(36).substring(2, 9);
    
    let defaultDuration = 5000;
    if (type === 'error') defaultDuration = 8000;
    if (type === 'loading') defaultDuration = 0; // Infinite until updated
    if (type === 'success') defaultDuration = 4000;

    const duration = options?.duration !== undefined ? options.duration : defaultDuration;

    setToasts((prev) => [...prev, { id, message, type, title: options?.title, duration }]);
    
    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }

    return id;
  }, [removeToast]);

  const updateToast = useCallback((id: string, message: string, type: ToastType = 'info', options?: ToastOptions) => {
    setToasts((prev) => 
      prev.map((t) => {
        if (t.id === id) {
          let defaultDuration = 5000;
          if (type === 'error') defaultDuration = 8000;
          if (type === 'loading') defaultDuration = 0;
          if (type === 'success') defaultDuration = 4000;
          
          const duration = options?.duration !== undefined ? options.duration : defaultDuration;
          
          if (duration > 0) {
            setTimeout(() => {
              removeToast(id);
            }, duration);
          }
          
          return { ...t, message, type, title: options?.title, duration };
        }
        return t;
      })
    );
  }, [removeToast]);

  return (
    <ToastContext.Provider value={{ toast, updateToast, removeToast }}>
      {children}
      <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-3 pointer-events-none sm:w-[380px] w-[calc(100vw-2rem)]">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onClose={() => removeToast(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const getIcon = () => {
    switch (toast.type) {
      case 'success':
        return (
          <svg className="w-5 h-5 text-emerald-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
          </svg>
        );
      case 'error':
        return (
          <svg className="w-5 h-5 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        );
      case 'warning':
        return (
          <svg className="w-5 h-5 text-amber-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        );
      case 'info':
        return (
          <svg className="w-5 h-5 text-blue-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
      case 'loading':
        return (
          <svg className="w-5 h-5 text-primary animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        );
    }
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-surface border border-border-strong text-foreground p-4 rounded-xl shadow-lg flex items-start gap-3 pointer-events-auto w-full overflow-hidden animate-in slide-in-from-right-8 fade-in duration-300 max-h-[150px] overflow-y-auto"
    >
      <div className="pt-0.5">
        {getIcon()}
      </div>
      
      <div className="flex-1 flex flex-col gap-1 min-w-0">
        {toast.title && (
          <p className="text-sm font-bold text-foreground leading-tight truncate">
            {toast.title}
          </p>
        )}
        <p className="text-sm text-muted leading-relaxed break-words line-clamp-3">
          {toast.message}
        </p>
      </div>

      <button
        onClick={onClose}
        className="text-muted hover:text-foreground transition-colors p-1 -mt-1 -mr-1 rounded-md hover:bg-bgSubtle shrink-0"
        aria-label="Close"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}
