'use client';

import React from 'react';
import { MetricCard } from '@/components/ui/MetricCard';

interface CostMeterProps {
  totalCostUsd: number;
  totalTokens: number;
  stage?: string | null;
}

function formatCost(usd: number): string {
  if (usd === 0) return '$0.0000';
  if (usd < 0.001) return `$${usd.toFixed(6)}`;
  if (usd < 0.01)  return `$${usd.toFixed(5)}`;
  return `$${usd.toFixed(4)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

export function CostMeter({ totalCostUsd, totalTokens, stage }: CostMeterProps) {
  const isRunning = stage && stage !== 'done' && stage !== 'error';

  return (
    <div className="flex flex-wrap gap-4" aria-label={`Session cost: ${formatCost(totalCostUsd)}, tokens used: ${formatTokens(totalTokens)}`}>
      <MetricCard
        label="Total Cost"
        value={formatCost(totalCostUsd)}
        icon={
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
      />
      <MetricCard
        label="Tokens"
        value={formatTokens(totalTokens)}
        icon={
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        }
        subValue={isRunning ? <span className="animate-pulse text-primary font-bold">◌</span> : null}
      />
    </div>
  );
}
