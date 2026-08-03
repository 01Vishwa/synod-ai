'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '@/lib/supabase/client';

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AuthModal({ isOpen, onClose }: AuthModalProps) {
  const [mode, setMode] = useState<'sign_in' | 'sign_up'>('sign_in');
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (isOpen) {
      setEmail('');
      setPassword('');
      setFirstName('');
      setLastName('');
      setShowPassword(false);
      setError(null);
      setMode('sign_in');
    }
  }, [isOpen]);

  function togglePasswordVisibility() {
    setShowPassword((prev) => !prev);
    requestAnimationFrame(() => passwordRef.current?.focus());
  }

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setError('Please enter a valid email address.');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters long.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      if (mode === 'sign_in') {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      } else {
        const { error } = await supabase.auth.signUp({ 
          email, 
          password,
          options: {
            data: {
              first_name: firstName,
              last_name: lastName
            }
          }
        });
        if (error) throw error;
      }
      onClose();
      router.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div 
      className="fixed inset-0 bg-overlay backdrop-blur-sm flex items-center justify-center z-[100] transition-opacity duration-200"
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-modal-title"
    >
      <div className="bg-surface border border-border-strong shadow-xl rounded-xl p-8 w-full max-w-md relative">
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-muted hover:text-foreground transition-colors bg-bgSubtle hover:bg-surface-hover p-1.5 rounded-md"
          aria-label="Close"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        <h2 id="auth-modal-title" className="text-2xl font-bold tracking-tight mb-6 text-foreground">
          {mode === 'sign_in' ? 'Sign In' : 'Create an account'}
        </h2>

        {error && (
          <div className="mb-4 p-3 bg-bgSubtle border border-border-strong rounded-lg font-bold text-foreground text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {mode === 'sign_up' && (
            <div className="flex gap-4">
              <div className="flex-1">
                <label className="block text-sm font-semibold text-foreground mb-1" htmlFor="first_name">
                  First Name
                </label>
                <input
                  id="first_name"
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="w-full border border-border rounded-lg p-2.5 text-foreground bg-background focus:outline-none focus:border-border-strong focus:ring-2 focus:ring-foreground/10 transition-all"
                  required
                />
              </div>
              <div className="flex-1">
                <label className="block text-sm font-semibold text-foreground mb-1" htmlFor="last_name">
                  Last Name
                </label>
                <input
                  id="last_name"
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="w-full border border-border rounded-lg p-2.5 text-foreground bg-background focus:outline-none focus:border-border-strong focus:ring-2 focus:ring-foreground/10 transition-all"
                  required
                />
              </div>
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-foreground mb-1" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-border rounded-lg p-2.5 text-foreground bg-background focus:outline-none focus:border-border-strong focus:ring-2 focus:ring-foreground/10 transition-all"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-foreground mb-1" htmlFor="password">
              Password
            </label>
            <div className="relative">
              <input
                ref={passwordRef}
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border border-border rounded-lg p-2.5 pr-10 text-foreground bg-background focus:outline-none focus:border-border-strong focus:ring-2 focus:ring-foreground/10 transition-all"
                required
                autoComplete={showPassword ? 'off' : 'current-password'}
              />
              <button
                type="button"
                onClick={togglePasswordVisibility}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                aria-pressed={showPassword}
                className="absolute inset-y-0 right-0 flex items-center px-3 text-subtle hover:text-muted transition-colors focus:outline-none rounded-r-lg"
              >
                {showPassword ? (
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full h-12 flex items-center justify-center bg-primary text-primary-fg border border-border-strong font-bold rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 mt-2 shadow-sm focus:ring-2 focus:ring-foreground focus:ring-offset-2"
          >
            {loading ? 'Processing...' : (mode === 'sign_in' ? 'Sign In' : 'Create Account')}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-muted">
          {mode === 'sign_in' ? (
            <p>
              Don&apos;t have an account?{' '}
              <button
                type="button"
                onClick={() => setMode('sign_up')}
                className="font-bold text-foreground hover:underline transition-colors"
              >
                Sign Up
              </button>
            </p>
          ) : (
            <p>
              Already have an account?{' '}
              <button
                type="button"
                onClick={() => setMode('sign_in')}
                className="font-bold text-foreground hover:underline transition-colors"
              >
                Sign In
              </button>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
