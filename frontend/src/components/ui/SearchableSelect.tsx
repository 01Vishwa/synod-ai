'use client';

import React, { useState, useRef, useEffect } from 'react';

export interface Option {
  value: string;
  label: string;
}

interface SearchableSelectProps {
  id?: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function SearchableSelect({
  id,
  value,
  options,
  onChange,
  placeholder = 'Select option...',
  disabled = false,
  className = '',
}: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectedOption = options.find((opt) => opt.value === value);
  const displayLabel = selectedOption ? selectedOption.label : placeholder;

  const normalizeSearch = (val: string): string => {
    return val
      .toLowerCase()
      .trim()
      .replace(/[\/:_-]+/g, ' ')
      .replace(/\s+/g, ' ');
  };

  const normalizedQuery = normalizeSearch(searchQuery);

  const filteredOptions = options.filter((opt) => {
    if (!normalizedQuery) return true;
    const slug = opt.value.includes('/') ? opt.value.split('/').pop() || '' : opt.value;
    const searchableText = normalizeSearch(`${opt.value} ${opt.label} ${slug}`);
    return searchableText.includes(normalizedQuery);
  });

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      <button
        id={id}
        type="button"
        className={`w-full text-left text-base sm:text-sm bg-background text-foreground border rounded px-2 py-1.5 focus:border-border-strong focus:ring-2 focus:ring-foreground/10 outline-none transition-all flex justify-between items-center ${
          disabled ? 'opacity-50 cursor-not-allowed bg-bgSubtle border-border' : 'border-border hover:border-border-strong'
        }`}
        onClick={() => {
          if (!disabled) {
            setIsOpen(!isOpen);
            setSearchQuery('');
          }
        }}
        disabled={disabled}
      >
        <span className="truncate">{displayLabel}</span>
        <svg
          className={`w-4 h-4 flex-shrink-0 ml-2 text-subtle transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute z-50 w-full mt-1 bg-surface border border-border-strong rounded shadow-lg overflow-hidden flex flex-col max-h-60">
          <div className="p-2 border-b border-border sticky top-0 bg-surface">
            <input
              type="text"
              className="w-full text-sm bg-background text-foreground border border-border rounded px-2 py-1.5 focus:border-border-strong focus:ring-1 focus:ring-border-strong outline-none"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              autoFocus
            />
          </div>
          <div className="overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <div className="px-3 py-2 text-sm text-subtle">No options found</div>
            ) : (
              filteredOptions.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-surface-hover text-foreground transition-colors truncate ${
                    opt.value === value ? 'bg-surface-secondary font-bold' : ''
                  }`}
                  onClick={() => {
                    onChange(opt.value);
                    setIsOpen(false);
                    setSearchQuery('');
                  }}
                  title={opt.label}
                >
                  {opt.label}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
