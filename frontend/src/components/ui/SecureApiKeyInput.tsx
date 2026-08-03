import React, { useState } from 'react';

interface SecureApiKeyInputProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function SecureApiKeyInput({
  value,
  onChange,
  onKeyDown,
  placeholder,
  disabled,
  className,
}: SecureApiKeyInputProps) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <div className={`relative flex items-center ${className || ''}`}>
      <input
        type={isVisible ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full font-mono text-sm bg-background text-foreground border border-border rounded-lg pl-3 pr-10 py-2.5 focus:border-border-strong focus:ring-2 focus:ring-foreground/10 outline-none transition-all placeholder:text-subtle disabled:opacity-50 disabled:cursor-not-allowed"
      />
      <button
        type="button"
        tabIndex={0}
        disabled={disabled}
        onClick={() => setIsVisible(!isVisible)}
        aria-label={isVisible ? 'Hide API key' : 'Show API key'}
        className="absolute right-2 p-1.5 text-muted hover:text-foreground focus:outline-none focus:text-foreground rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isVisible ? (
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
            <line x1="1" y1="1" x2="23" y2="23"></line>
          </svg>
        ) : (
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
            <circle cx="12" cy="12" r="3"></circle>
          </svg>
        )}
      </button>
    </div>
  );
}
