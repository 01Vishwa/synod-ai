import React from 'react';

export type StatusType = 'running' | 'completed' | 'waiting' | 'failed' | 'excluded';

interface StatusBadgeProps {
  status: StatusType;
  label?: string;
  className?: string;
}

export function StatusBadge({ status, label, className = '' }: StatusBadgeProps) {
  const styles: Record<StatusType, string> = {
    running: 'bg-primary/10 text-primary border-primary/20',
    completed: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
    waiting: 'bg-bgSubtle text-muted border-border',
    failed: 'bg-red-500/10 text-red-600 border-red-500/20',
    excluded: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
  };

  const icons: Record<StatusType, React.ReactNode> = {
    running: <span className="font-mono animate-pulse">◌</span>,
    completed: (
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
      </svg>
    ),
    waiting: (
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="9" strokeWidth="2" strokeDasharray="2 4" />
      </svg>
    ),
    failed: (
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
    excluded: (
      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  };

  const defaultLabels: Record<StatusType, string> = {
    running: 'Running',
    completed: 'Done',
    waiting: 'Waiting',
    failed: 'Failed',
    excluded: 'Excluded',
  };

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-bold uppercase tracking-wider border shadow-sm shrink-0 ${styles[status]} ${className}`}>
      {icons[status]}
      {label || defaultLabels[status]}
    </span>
  );
}
