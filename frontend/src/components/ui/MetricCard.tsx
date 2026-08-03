import React from 'react';

interface MetricCardProps {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  subValue?: React.ReactNode;
}

export function MetricCard({ label, value, icon, subValue }: MetricCardProps) {
  return (
    <div className="flex items-center gap-3 bg-surface border border-border rounded-xl p-3 shadow-sm flex-1 min-w-[120px]">
      {icon && (
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-bgSubtle flex items-center justify-center text-muted">
          {icon}
        </div>
      )}
      <div className="flex flex-col min-w-0">
        <span className="text-[10px] font-bold text-subtle uppercase tracking-wider truncate">
          {label}
        </span>
        <div className="flex items-baseline gap-2 truncate">
          <span className="font-mono text-sm font-bold text-foreground">
            {value}
          </span>
          {subValue && (
            <span className="font-mono text-[10px] text-muted">
              {subValue}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
