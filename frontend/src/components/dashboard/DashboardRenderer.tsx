'use client';

/**
 * DashboardRenderer — thin wrapper around json-render's <Renderer>
 * that binds the backend-emitted spec to our local B&W registry.
 */

import React from 'react';
import { Renderer } from '@json-render/react';
import { registry } from './registry';

interface DashboardRendererProps {
  spec: {
    root: string;
    elements: Record<string, unknown>;
  };
}

export function DashboardRenderer({ spec }: DashboardRendererProps) {
  // Add a grid container around the rendered root component
  // so widgets can flow naturally in 2–4 columns.
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
        gap: 'var(--space-4)',
        width: '100%',
        animation: 'fadeIn 200ms ease',
      }}
    >
      <Renderer spec={spec as any} registry={registry} />
    </div>
  );
}
