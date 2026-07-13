'use client';

import React, { useState, useCallback } from 'react';
import { ToastContext, type Toast, type ToastType } from '@/hooks/useToast';

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((message: string, type: ToastType = 'info') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);
    
    if (type !== 'error') {
      const duration = type === 'success' ? 4000 : 6500;
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast, removeToast }}>
      {children}
      <div
        style={{
          position: 'fixed',
          top: 'var(--space-4)',
          right: 'var(--space-4)',
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          pointerEvents: 'none',
        }}
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            aria-live="polite"
            style={{
              background: t.type === 'error' ? 'var(--grey-0)' : 'var(--color-bg)',
              color: t.type === 'error' ? 'var(--grey-100)' : 'var(--color-text)',
              border: t.type === 'error' ? '1px solid var(--grey-0)' : '1px solid var(--color-border)',
              padding: 'var(--space-3) var(--space-4)',
              borderRadius: 'var(--radius-sm)',
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 'var(--space-3)',
              pointerEvents: 'auto',
              animation: 'slideInRight 300ms cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              {t.type === 'success' && <span>✓</span>}
              {t.type === 'error' && <span>✕</span>}
              {t.type === 'info' && <span>ℹ</span>}
              {t.message}
            </div>
            <button
              onClick={() => removeToast(t.id)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'inherit',
                cursor: 'pointer',
                opacity: 0.6,
                padding: '2px',
                fontSize: '14px',
                lineHeight: 1,
              }}
              aria-label="Close"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}} />
    </ToastContext.Provider>
  );
}
