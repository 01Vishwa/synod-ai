import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      screens: {
        'desktop': '1200px',
      },
      colors: {
        background: "var(--color-bg)",
        foreground: "var(--color-text)",
        muted: "var(--color-text-muted)",
        subtle: "var(--color-text-subtle)",
        surface: {
          DEFAULT: "var(--color-surface)",
          hover: "var(--color-surface-hover)",
          secondary: "var(--color-surface-secondary)",
        },
        border: {
          DEFAULT: "var(--color-border)",
          strong: "var(--color-border-strong)",
        },
        primary: {
          DEFAULT: "var(--color-primary)",
          fg: "var(--color-primary-fg)",
          hover: "var(--color-primary-hover)",
        },
        secondary: {
          DEFAULT: "var(--color-secondary)",
          fg: "var(--color-secondary-fg)",
          hover: "var(--color-secondary-hover)",
        },
        overlay: "var(--color-overlay)",
        bgSubtle: "var(--color-bg-subtle)",
        bgMuted: "var(--color-bg-muted)",
        black: "var(--grey-0)",
        white: "var(--grey-100)",
        grey: {
          10: "var(--grey-10)",
          20: "var(--grey-20)",
          30: "var(--grey-30)",
          50: "var(--grey-50)",
          70: "var(--grey-70)",
          85: "var(--grey-85)",
          93: "var(--grey-93)",
        }
      },
      fontFamily: {
        display: "var(--font-display)",
        body: "var(--font-body)",
        mono: "var(--font-mono)",
      }
    },
  },
  plugins: [],
};
export default config;
