/**
 * Unit Tests for Mermaid Theme Sync (KB-P3-47, S5.3).
 */

import { describe, it, expect } from 'vitest';
import {
  readMermaidThemeTokens,
  getMermaidThemeKey,
  DEFAULT_LIGHT_THEME_TOKENS,
  DEFAULT_DARK_THEME_TOKENS,
} from './mermaidTheme';

describe('mermaidTheme', () => {
  it('reads default light theme tokens when no CSS variables are set', () => {
    const tokens = readMermaidThemeTokens();
    expect(tokens.bgSurface).toBe('#ffffff');
    expect(tokens.fgPrimary).toBe('#111827');
    expect(tokens.borderStrong).toBe('#d1d5db');
    expect(tokens.accentPrimary).toBe('#1d4ed8');
  });

  it('reads custom CSS variables set on documentElement', () => {
    document.documentElement.style.setProperty('--bg-surface', '#16181d');
    document.documentElement.style.setProperty('--fg-primary', '#f9fafb');
    document.documentElement.style.setProperty('--border-strong', '#3f4756');
    document.documentElement.style.setProperty('--accent-primary', '#3b82f6');

    try {
      const tokens = readMermaidThemeTokens();
      expect(tokens.bgSurface).toBe('#16181d');
      expect(tokens.fgPrimary).toBe('#f9fafb');
      expect(tokens.borderStrong).toBe('#3f4756');
      expect(tokens.accentPrimary).toBe('#3b82f6');
    } finally {
      document.documentElement.style.removeProperty('--bg-surface');
      document.documentElement.style.removeProperty('--fg-primary');
      document.documentElement.style.removeProperty('--border-strong');
      document.documentElement.style.removeProperty('--accent-primary');
    }
  });

  it('generates stable theme keys', () => {
    const keyLight = getMermaidThemeKey(DEFAULT_LIGHT_THEME_TOKENS);
    const keyDark = getMermaidThemeKey(DEFAULT_DARK_THEME_TOKENS);

    expect(keyLight).toBe('#ffffff|#111827|#d1d5db|#1d4ed8');
    expect(keyDark).toBe('#16181d|#f9fafb|#3f4756|#1d4ed8');
    expect(keyLight).not.toBe(keyDark);
  });

  it('falls back to default tokens when window or document is undefined', () => {
    const origWindow = global.window;
    try {
      // @ts-expect-error test environment fallback
      delete global.window;
      const tokens = readMermaidThemeTokens();
      expect(tokens).toEqual(DEFAULT_LIGHT_THEME_TOKENS);
    } finally {
      global.window = origWindow;
    }
  });
});
