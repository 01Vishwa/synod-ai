'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex flex-col md:flex-row gap-12 w-full">
      {/* Sub-navigation Sidebar */}
      <aside className="w-full md:w-[180px] shrink-0">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground mb-6">Settings</h1>
        <nav className="flex flex-col gap-1">

          <Link
            href="/settings/providers"
            className={`px-3 py-2 text-sm rounded-lg transition-colors no-underline ${
              pathname?.startsWith('/settings/providers')
                ? 'bg-surface-hover text-foreground font-bold'
                : 'text-muted font-medium hover:bg-surface-hover hover:text-foreground'
            }`}
          >
            Providers & API Keys
          </Link>

          <Link
            href="/settings/appearance"
            className={`px-3 py-2 text-sm rounded-lg transition-colors no-underline ${
              pathname?.startsWith('/settings/appearance')
                ? 'bg-surface-hover text-foreground font-bold'
                : 'text-muted font-medium hover:bg-surface-hover hover:text-foreground'
            }`}
          >
            Appearance
          </Link>

        </nav>
      </aside>

      {/* Main Settings Panel */}
      <div className="flex-1 max-w-2xl">
        {children}
      </div>
    </div>
  );
}
