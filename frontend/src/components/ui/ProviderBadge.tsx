import React from 'react';

interface ProviderBadgeProps {
  provider: string;
}

export function ProviderBadge({ provider }: ProviderBadgeProps) {
  const labels: Record<string, string> = {
    openrouter: 'OR',
    nvidia_nim: 'NIM',
    tavily: 'TVL',
    anakin: 'ANK',
  };
  
  const label = labels[provider] ?? provider.slice(0, 3).toUpperCase();
  
  return (
    <span
      className="inline-flex items-center justify-center px-1.5 py-0.5 rounded-md text-[10px] font-bold font-mono bg-bgSubtle text-foreground border border-border shadow-sm min-w-[32px] shrink-0"
      title={provider}
    >
      {label}
    </span>
  );
}
