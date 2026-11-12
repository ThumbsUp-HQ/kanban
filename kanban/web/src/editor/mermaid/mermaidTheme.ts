/**
 * Mermaid Theme Sync (KB-P3-47, S5.3).
 * Extracts resolved semantic CSS tokens (--bg-surface, --fg-primary,
 * --border-strong, --accent-primary) from document.documentElement
 * for passing to beautiful-mermaid renderer in Web Worker.
 */

export interface MermaidThemeTokens {
  readonly bgSurface: string;
  readonly fgPrimary: string;
  readonly borderStrong: string;
  readonly accentPrimary: string;
}

export const DEFAULT_LIGHT_THEME_TOKENS: MermaidThemeTokens = Object.freeze({
  bgSurface: '#ffffff',
  fgPrimary: '#111827',
  borderStrong: '#d1d5db',
  accentPrimary: '#1d4ed8',
});

export const DEFAULT_DARK_THEME_TOKENS: MermaidThemeTokens = Object.freeze({
  bgSurface: '#16181d',
  fgPrimary: '#f9fafb',
  borderStrong: '#3f4756',
  accentPrimary: '#1d4ed8',
});

/**
 * Reads resolved semantic CSS tokens from document root.
 */
export function readMermaidThemeTokens(): MermaidThemeTokens {
  if (typeof document === 'undefined' || typeof window === 'undefined') {
    return DEFAULT_LIGHT_THEME_TOKENS;
  }

  const computed = window.getComputedStyle(document.documentElement);
  const bgSurface = computed.getPropertyValue('--bg-surface').trim() || DEFAULT_LIGHT_THEME_TOKENS.bgSurface;
  const fgPrimary = computed.getPropertyValue('--fg-primary').trim() || DEFAULT_LIGHT_THEME_TOKENS.fgPrimary;
  const borderStrong = computed.getPropertyValue('--border-strong').trim() || DEFAULT_LIGHT_THEME_TOKENS.borderStrong;
  const accentPrimary = computed.getPropertyValue('--accent-primary').trim() || DEFAULT_LIGHT_THEME_TOKENS.accentPrimary;

  return {
    bgSurface,
    fgPrimary,
    borderStrong,
    accentPrimary,
  };
}

/**
 * Returns a stable string key representing the theme tokens for cache indexing.
 */
export function getMermaidThemeKey(tokens: MermaidThemeTokens): string {
  return `${tokens.bgSurface}|${tokens.fgPrimary}|${tokens.borderStrong}|${tokens.accentPrimary}`;
}
