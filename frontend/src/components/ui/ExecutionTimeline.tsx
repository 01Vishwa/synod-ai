import React from 'react';
import { StageStatus } from './StageStatus';

export interface TimelineStage {
  id: string;
  name: string;
  status: 'Pending' | 'Running' | 'Completed' | 'Skipped' | 'Retrying' | 'Failed' | string;
}

interface ExecutionTimelineProps {
  stages: TimelineStage[];
}

export function ExecutionTimeline({ stages }: ExecutionTimelineProps) {
  return (
    <div 
      style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        gap: 'var(--space-3)',
        padding: 'var(--space-4)',
        background: 'var(--color-bg)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)'
      }}
    >
      {stages.map((stage, index) => {
        const stepNum = (index + 1).toString().padStart(2, '0');
        return (
          <div 
            key={stage.id} 
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'space-between',
              padding: 'var(--space-2) 0',
              borderBottom: index < stages.length - 1 ? '1px solid var(--grey-93)' : 'none'
            }}
          >
            <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center' }}>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-text-subtle)' }}>
                {stepNum}
              </span>
              <span style={{ fontWeight: 500 }}>
                {stage.name}
              </span>
            </div>
            <div>
              <StageStatus status={stage.status} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
