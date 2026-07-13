import React from 'react';

type WorkflowStageStatus = 'Pending' | 'Running' | 'Completed' | 'Skipped' | 'Retrying' | 'Failed';

interface StageStatusProps {
  status: WorkflowStageStatus | string;
}

export function StageStatus({ status }: StageStatusProps) {
  let icon = '○';
  let isAnimated = false;
  let isDimmed = false;

  switch (status.toLowerCase()) {
    case 'completed':
      icon = '✓';
      break;
    case 'failed':
      icon = '✕';
      break;
    case 'running':
    case 'retrying':
      icon = '◌';
      isAnimated = true;
      break;
    case 'skipped':
      icon = '⏭';
      isDimmed = true;
      break;
    case 'pending':
    default:
      icon = '○';
      isDimmed = true;
      break;
  }

  return (
    <div 
      style={{ 
        display: 'flex', 
        alignItems: 'center', 
        gap: 'var(--space-3)',
        color: isDimmed ? 'var(--color-text-subtle)' : 'var(--color-text)',
        fontFamily: 'var(--font-mono)',
        fontSize: 'var(--text-sm)',
        fontWeight: isDimmed ? 400 : 500,
      }}
    >
      <span 
        aria-hidden="true" 
        style={{ 
          display: 'inline-block',
          animation: isAnimated ? 'skeleton-pulse 1.5s ease-in-out infinite' : 'none',
          width: '1em',
          textAlign: 'center'
        }}
      >
        {icon}
      </span>
      <span>{status}</span>
    </div>
  );
}
