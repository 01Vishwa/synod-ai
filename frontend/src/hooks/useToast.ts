import { createContext, useContext } from 'react';

export type ToastType = 'success' | 'error' | 'info' | 'warning' | 'loading';

export interface ToastOptions {
  title?: string;
  duration?: number; // 0 means infinite
}

export interface Toast {
  id: string;
  message: string;
  title?: string;
  type: ToastType;
  duration?: number;
}

export interface ToastContextType {
  toast: (message: string, type?: ToastType, options?: ToastOptions) => string;
  updateToast: (id: string, message: string, type?: ToastType, options?: ToastOptions) => void;
  removeToast: (id: string) => void;
}

export const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
