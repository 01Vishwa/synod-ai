'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="max-w-[720px] mx-auto px-6 py-8">
      <div className="mb-6">
        <Link
          href="/"
          className="no-underline text-muted text-sm inline-flex items-center gap-2 hover:text-foreground transition-colors"
        >
          <span>←</span> Back to Council
        </Link>
      </div>

      <div className="mb-8">
        <h1 className="font-display text-3xl font-bold mb-2">Settings</h1>
      </div>

      <div className="flex gap-6 mb-8 w-fit">
        <Link
          href="/settings/providers"
          className={`no-underline pb-2 text-sm font-semibold border-b-2 transition-colors -mb-[1px] ${
            pathname?.startsWith('/settings/providers') ? 'border-black text-black' : 'border-transparent text-muted hover:text-foreground'
          }`}
        >
          Model Providers
        </Link>
        <Link
          href="/settings/integrations"
          className={`no-underline pb-2 text-sm font-semibold border-b-2 transition-colors -mb-[1px] ${
            pathname?.startsWith('/settings/integrations') ? 'border-black text-black' : 'border-transparent text-muted hover:text-foreground'
          }`}
        >
          Integrations
        </Link>
      </div>

      <div>
        {children}
      </div>
    </div>
  );
}
