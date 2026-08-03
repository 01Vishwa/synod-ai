import React from 'react';

export type StepState = 'pending' | 'running' | 'completed' | 'failed' | 'selected';

interface TimelineStepProps {
  label: string;
  state: StepState;
  isLast?: boolean;
  onClick?: () => void;
}

export function TimelineStep({ label, state, isLast, onClick }: TimelineStepProps) {
  const isClickable = state !== 'pending' && onClick;
  
  const stateStyles: Record<StepState, string> = {
    pending: 'text-subtle opacity-60 cursor-not-allowed',
    running: 'text-primary font-bold',
    completed: 'text-muted font-medium hover:text-foreground hover:bg-surface-hover cursor-pointer transition-colors',
    selected: 'text-foreground font-bold bg-surface border border-border shadow-sm cursor-pointer',
    failed: 'text-red-600 font-bold',
  };
  
  const iconMap: Record<StepState, React.ReactNode> = {
    pending: <span className="text-[10px]">○</span>,
    running: <span className="text-[10px] animate-pulse">◌</span>,
    completed: <span className="text-[10px]">✓</span>,
    selected: <span className="text-[10px]">✓</span>,
    failed: <span className="text-[10px]">✕</span>,
  };

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        disabled={!isClickable}
        onClick={isClickable ? onClick : undefined}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-primary/20 ${stateStyles[state]}`}
      >
        <span className="flex-shrink-0 flex items-center justify-center w-4 h-4">
          {iconMap[state]}
        </span>
        <span className="text-sm font-display tracking-tight">{label}</span>
      </button>
      {!isLast && (
        <span className="text-border mx-1">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
          </svg>
        </span>
      )}
    </div>
  );
}
