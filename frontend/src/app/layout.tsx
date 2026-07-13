import type { Metadata } from 'next';
import '@/styles/globals.css';
import { AppShell } from '@/components/layout/AppShell';
import { ToastProvider } from '@/components/ui/ToastProvider';

export const metadata: Metadata = {
  title: {
    default: 'Synod — Where Models Convene, Truth Concludes.',
    template: '%s | Synod',
  },
  description:
    'Synod is a supervisor-orchestrated council of independent AI models that debate, critique, and rank each other\'s answers before a Chairman synthesizes the strongest response.',
  keywords: ['AI', 'LLM', 'multi-agent', 'deliberation', 'council', 'OpenRouter', 'NVIDIA NIM'],
  metadataBase: new URL('http://localhost:3000'),
  openGraph: {
    title: 'Synod',
    description: 'Where Models Convene, Truth Concludes.',
    type: 'website',
  },
};

import { SessionHistoryProvider } from '@/components/layout/SessionHistoryContext';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="color-scheme" content="light" />
      </head>
      <body>
        <ToastProvider>
          <SessionHistoryProvider>
            <AppShell>{children}</AppShell>
          </SessionHistoryProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
