'use client';

import React, { useRef } from 'react';
import { useTheme, Theme } from '@/components/theme/ThemeProvider';

interface ThemeOption {
  value: Theme;
  label: string;
  icon: React.ReactNode;
}

const OPTIONS: ThemeOption[] = [
  {
    value: 'light',
    label: 'Light',
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2" />
        <path d="M12 20v2" />
        <path d="m4.93 4.93 1.41 1.41" />
        <path d="m17.66 17.66 1.41 1.41" />
        <path d="M2 12h2" />
        <path d="M20 12h2" />
        <path d="m6.34 17.66-1.41 1.41" />
        <path d="m19.07 4.93-1.41 1.41" />
      </svg>
    ),
  },
  {
    value: 'dark',
    label: 'Dark',
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0"
      >
        <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
      </svg>
    ),
  },
  {
    value: 'system',
    label: 'System',
    icon: (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0"
      >
        <rect width="20" height="14" x="2" y="3" rx="2" />
        <line x1="8" x2="16" y1="21" y2="21" />
        <line x1="12" x2="12" y1="17" y2="21" />
      </svg>
    ),
  },
];

export function ThemeSegmentedControl() {
  const { theme, setTheme, mounted } = useTheme();
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      const nextIndex = (index + 1) % OPTIONS.length;
      buttonRefs.current[nextIndex]?.focus();
      setTheme(OPTIONS[nextIndex].value);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      const prevIndex = (index - 1 + OPTIONS.length) % OPTIONS.length;
      buttonRefs.current[prevIndex]?.focus();
      setTheme(OPTIONS[prevIndex].value);
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label="Theme selection"
      className="flex w-full gap-2 p-1.5 bg-bgSubtle border border-border-strong rounded-xl transition-colors duration-200"
    >
      {OPTIONS.map((opt, idx) => {
        const isSelected = mounted && theme === opt.value;

        return (
          <button
            key={opt.value}
            ref={(el) => {
              buttonRefs.current[idx] = el;
            }}
            type="button"
            role="radio"
            aria-checked={isSelected}
            tabIndex={isSelected || (!mounted && idx === 0) ? 0 : -1}
            onClick={() => setTheme(opt.value)}
            onKeyDown={(e) => handleKeyDown(e, idx)}
            className={`flex-1 h-12 px-4 rounded-lg text-sm font-bold flex items-center justify-center gap-2 cursor-pointer transition-all duration-200 select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 ${
              isSelected
                ? 'bg-primary text-primary-fg border border-border-strong shadow-sm scale-[1.01]'
                : 'bg-transparent text-foreground hover:bg-surface-hover opacity-80 hover:opacity-100'
            }`}
          >
            {opt.icon}
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
