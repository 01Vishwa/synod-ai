import type { Config } from "tailwindcss";

const config: Config = {
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
        border: "var(--color-border)",
        "border-strong": "var(--color-border-strong)",
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
