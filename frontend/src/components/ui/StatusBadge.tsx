import React from 'react';

type StatusType = 
  | 'Not configured' | 'Connecting' | 'Connected' | 'Disconnected' | 'Unavailable' | 'Invalid'
  | 'Draft' | 'Queued' | 'Running' | 'Waiting' | 'Completed' | 'Completed with warnings' | 'Incomplete' | 'Failed' | 'Cancelled'
  | 'Pending' | 'Skipped' | 'Retrying'
  | 'Supported' | 'Partially supported' | 'Contradicted' | 'Unsupported' | 'Not verifiable';

interface StatusBadgeProps {
  status: StatusType | string;
  muted?: boolean;
}

function getIconForStatus(status: string) {
  switch (status.toLowerCase()) {
    case 'completed':
    case 'connected':
    case 'supported':
      return '✓';
    case 'failed':
    case 'invalid':
    case 'disconnected':
    case 'cancelled':
    case 'unsupported':
    case 'contradicted':
      return '✕';
    case 'running':
    case 'connecting':
    case 'retrying':
      return '◌';
    case 'pending':
    case 'queued':
    case 'waiting':
    case 'draft':
      return '○';
    case 'completed with warnings':
    case 'partially supported':
    case 'incomplete':
    case 'not verifiable':
    case 'unavailable':
    case 'not configured':
      return '⚠';
    case 'skipped':
      return '⏭';
    default:
      return 'ℹ';
  }
}

export function StatusBadge({ status, muted = false }: StatusBadgeProps) {
  const icon = getIconForStatus(status);
  
  return (
    <span className={`badge ${muted ? 'badge-muted' : ''}`}>
      <span aria-hidden="true" style={{ opacity: 0.7 }}>{icon}</span>
      <span>{status}</span>
    </span>
  );
}
