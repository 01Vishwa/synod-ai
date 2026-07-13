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
    <div className="grid grid-cols-1 md:grid-cols-2 desktop:grid-cols-4 gap-6 w-full animate-fade-in">
      <Renderer spec={spec as any} registry={registry} />
    </div>
  );
}
