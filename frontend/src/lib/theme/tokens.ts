/**
 * Synod Design Tokens — Single Source of Truth
 * Strict black & white / greyscale only — NO other hues permitted.
 * Maps 1:1 to CSS custom properties in globals.css.
 */

// ─── Greyscale Ramp (7 steps: 0 = black, 100 = white) ──────────────────────
export const grey = {
  0:   '#000000',  // pure black — primary text, hard borders
  10:  '#1A1A1A',  // near-black — secondary content areas
  20:  '#333333',  // dark grey — hover backgrounds, secondary borders
  30:  '#4D4D4D',  // mid-dark — disabled text, tertiary borders
  50:  '#808080',  // mid grey — placeholder text, dividers
  70:  '#B3B3B3',  // light-mid — subtle backgrounds, skeleton shimmer
  85:  '#D9D9D9',  // light grey — card backgrounds, input borders
  93:  '#EDEDED',  // near-white — page backgrounds, hover states
  100: '#FFFFFF',  // pure white — primary background
} as const;

export type GreyStep = keyof typeof grey;

// ─── Spacing Scale (px) ─────────────────────────────────────────────────────
export const spacing = {
  1:  '4px',
  2:  '8px',
  3:  '12px',
  4:  '16px',
  6:  '24px',
  8:  '32px',
  12: '48px',
  16: '64px',
} as const;

// ─── Type Scale ─────────────────────────────────────────────────────────────
export const fontSize = {
  xs:    '12px',
  sm:    '14px',
  base:  '16px',
  lg:    '20px',
  xl:    '24px',
  '2xl': '32px',
  '3xl': '40px',
} as const;

export const fontFamily = {
  display: "'Space Grotesk', 'Space Mono', monospace",
  body:    "'Inter', system-ui, sans-serif",
  mono:    "'Space Mono', 'Fira Code', monospace",
} as const;

export const fontWeight = {
  normal:   400,
  medium:   500,
  semibold: 600,
  bold:     700,
} as const;

// ─── Radius Scale ───────────────────────────────────────────────────────────
export const radius = {
  none: '0px',
  sm:   '4px',
  md:   '8px',
} as const;

// ─── Elevation (border-only — no drop shadows) ──────────────────────────────
export const elevation = {
  base:   `1px solid ${grey[85]}`,
  raised: `1px solid ${grey[20]}`,
  focus:  `2px solid ${grey[0]}`,
  error:  `2px solid ${grey[0]}`,
} as const;

// ─── Animation ──────────────────────────────────────────────────────────────
export const transition = {
  fast:   '100ms ease',
  normal: '200ms ease',
  slow:   '350ms ease',
} as const;

// ─── Breakpoints ─────────────────────────────────────────────────────
// PRD §12.7: mobile <768px | tablet 768–1199px | desktop ≥1200px
export const breakpoint = {
  mobile:  768,
  tablet:  768,
  desktop: 1200,
} as const;

// ─── Layout ─────────────────────────────────────────────────────────────────
export const layout = {
  sidebarWidth:    '240px',
  headerHeight:    '56px',
  contentMaxWidth: '960px',
  contentGutter:   '24px',
} as const;
