'use client';

import React from 'react';
import { ThemeSegmentedControl } from '@/components/settings/ThemeSegmentedControl';

export default function AppearanceSettingsPage() {
  return (
    <div className="animate-fade-in space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-foreground mb-1">
          Appearance
        </h2>
        <p className="text-sm text-muted m-0">
          Customize the look and feel of Synod.
        </p>
      </div>

      <div className="bg-surface border border-border rounded-xl p-6 space-y-4 shadow-sm">
        <div>
          <label className="text-sm font-bold text-foreground block mb-1">
            Interface Theme
          </label>
          <p className="text-xs text-muted mb-4">
            Select your preferred color theme or synchronize automatically with your operating system.
          </p>
          <ThemeSegmentedControl />
        </div>
      </div>
    </div>
  );
}
