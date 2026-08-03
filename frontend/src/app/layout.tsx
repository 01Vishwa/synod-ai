import type { Metadata } from 'next';
import '@/styles/globals.css';
import { AppShell } from '@/components/layout/AppShell';
import { ToastProvider } from '@/components/ui/ToastProvider';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';

export const metadata: Metadata = {
  title: {
    default: 'Synod',
    template: '%s | Synod',
  },
  description:
    'Synod is a supervisor-orchestrated council of independent AI models that debate, critique, and rank each other\'s answers before a Chairman synthesizes the strongest response.',
  keywords: ['AI', 'LLM', 'multi-agent', 'deliberation', 'council', 'OpenRouter', 'NVIDIA NIM'],
  metadataBase: new URL('http://localhost:3000'),
  openGraph: {
    title: 'Synod',
    description: 'Synod',
    type: 'website',
  },
};

import { SessionHistoryProvider } from '@/components/layout/SessionHistoryContext';
import { ThemeProvider } from '@/components/theme/ThemeProvider';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var saved = localStorage.getItem('synod_theme');
                  var theme = saved || 'system';
                  var isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
                  if (isDark) {
                    document.documentElement.classList.add('dark');
                    document.documentElement.setAttribute('data-theme', 'dark');
                  } else {
                    document.documentElement.classList.remove('dark');
                    document.documentElement.setAttribute('data-theme', 'light');
                  }
                  document.documentElement.setAttribute('data-theme-setting', theme);
                } catch (e) {}
              })();
            `,
          }}
        />
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
      </head>
      <body>
        <ThemeProvider>
          <ToastProvider>
            <SessionHistoryProvider>
              <ErrorBoundary>
                <AppShell>{children}</AppShell>
              </ErrorBoundary>
            </SessionHistoryProvider>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
