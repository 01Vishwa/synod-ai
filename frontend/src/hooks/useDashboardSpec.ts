'use client';

/**
 * useDashboardSpec — extracts the current dashboard_spec slice
 * from CouncilState for use by the DashboardRenderer.
 */

import { useMemo } from 'react';
import type { CouncilState } from '@/lib/api-client';

export interface DashboardSpec {
  root: string;
  elements: Record<string, unknown>;
}

export function useDashboardSpec(
  state: CouncilState | null,
): DashboardSpec | null {
  return useMemo(() => {
    if (!state?.dashboard_spec) return null;

    const spec = state.dashboard_spec;

    // Validate minimal shape — must have root + elements
    if (
      typeof spec.root !== 'string' ||
      typeof spec.elements !== 'object' ||
      spec.elements === null
    ) {
      return null;
    }

    return spec as unknown as DashboardSpec;
  }, [state?.dashboard_spec]);
}
