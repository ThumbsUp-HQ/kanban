import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const THEME_CSS_PATH = path.resolve(import.meta.dirname, 'theme.css');

function hexToRgb(hex: string): [number, number, number] {
  const cleaned = hex.replace('#', '').trim();
  const num = parseInt(cleaned, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
}

function relativeLuminance(r: number, g: number, b: number): number {
  const [rs, gs, bs] = [r / 255, g / 255, b / 255].map((c) =>
    c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4),
  );
  return 0.2126 * (rs ?? 0) + 0.7152 * (gs ?? 0) + 0.0722 * (bs ?? 0);
}

function contrastRatio(hex1: string, hex2: string): number {
  const [r1, g1, b1] = hexToRgb(hex1);
  const [r2, g2, b2] = hexToRgb(hex2);
  const l1 = relativeLuminance(r1, g1, b1);
  const l2 = relativeLuminance(r2, g2, b2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

function parseCssCustomProperties(block: string): Record<string, string> {
  const stripped = block.replace(/\/\*[\s\S]*?\*\//g, '');
  const propRegex = /(--[a-z-]+)\s*:\s*([^;]+);/g;
  const props: Record<string, string> = {};

  let match: RegExpExecArray | null;
  while ((match = propRegex.exec(stripped)) !== null) {
    if (match[1] && match[2]) {
      props[match[1].trim()] = match[2].trim();
    }
  }
  return props;
}

function getPairRatio(props: Record<string, string>, fgKey: string, bgKey: string): number {
  const fg = props[fgKey];
  const bg = props[bgKey];
  if (!fg || !bg) {
    throw new Error(`Missing property for ${fgKey} or ${bgKey}`);
  }
  return contrastRatio(fg, bg);
}

describe('Semantic Theme and Color Contrast (theme.css)', () => {
  const themeCss = fs.readFileSync(THEME_CSS_PATH, 'utf8');

  // Extract :root block
  const rootMatch = /:root\s*\{([^}]*)\}/.exec(themeCss);
  expect(rootMatch).toBeTruthy();
  const lightProps = parseCssCustomProperties(rootMatch?.[1] ?? '');

  // Extract [data-theme="dark"] block
  const darkMatch = /\[data-theme=["']dark["']\]\s*\{([^}]*)\}/.exec(themeCss);
  expect(darkMatch).toBeTruthy();
  const darkProps = parseCssCustomProperties(darkMatch?.[1] ?? '');

  it('contains hex literals only for color properties in both themes', () => {
    for (const [, val] of Object.entries(lightProps)) {
      expect(val).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
    for (const [, val] of Object.entries(darkProps)) {
      expect(val).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });

  it('defines all 6 sticky palette colors in both light and dark themes', () => {
    const requiredStickies = [
      '--sticky-amber',
      '--sticky-mint',
      '--sticky-sky',
      '--sticky-lavender',
      '--sticky-coral',
      '--sticky-slate',
    ];

    for (const sticky of requiredStickies) {
      expect(lightProps[sticky]).toBeDefined();
      expect(darkProps[sticky]).toBeDefined();
    }
  });

  describe('Light theme WCAG contrast ratios', () => {
    it('--fg-primary on --bg-surface >= 7:1', () => {
      const ratio = getPairRatio(lightProps, '--fg-primary', '--bg-surface');
      expect(ratio).toBeGreaterThanOrEqual(7.0);
    });

    it('--fg-secondary on --bg-surface >= 4.5:1', () => {
      const ratio = getPairRatio(lightProps, '--fg-secondary', '--bg-surface');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });

    it('--fg-muted on --bg-surface >= 4.5:1', () => {
      const ratio = getPairRatio(lightProps, '--fg-muted', '--bg-surface');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });

    it('--accent-primary-fg on --accent-primary >= 4.5:1', () => {
      const ratio = getPairRatio(lightProps, '--accent-primary-fg', '--accent-primary');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });

    it('--warn-fg on --warn-bg >= 4.5:1', () => {
      const ratio = getPairRatio(lightProps, '--warn-fg', '--warn-bg');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });

    it('--danger-fg on --danger-bg >= 4.5:1', () => {
      const ratio = getPairRatio(lightProps, '--danger-fg', '--danger-bg');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });
  });

  describe('Dark theme WCAG contrast ratios', () => {
    it('--fg-primary on --bg-surface >= 7:1', () => {
      const ratio = getPairRatio(darkProps, '--fg-primary', '--bg-surface');
      expect(ratio).toBeGreaterThanOrEqual(7.0);
    });

    it('--fg-secondary on --bg-surface >= 4.5:1', () => {
      const ratio = getPairRatio(darkProps, '--fg-secondary', '--bg-surface');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });

    it('--fg-muted on --bg-surface >= 4.5:1', () => {
      const ratio = getPairRatio(darkProps, '--fg-muted', '--bg-surface');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });

    it('--accent-primary-fg on --accent-primary >= 4.5:1', () => {
      const ratio = getPairRatio(darkProps, '--accent-primary-fg', '--accent-primary');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });

    it('--warn-fg on --warn-bg >= 4.5:1', () => {
      const ratio = getPairRatio(darkProps, '--warn-fg', '--warn-bg');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });

    it('--danger-fg on --danger-bg >= 4.5:1', () => {
      const ratio = getPairRatio(darkProps, '--danger-fg', '--danger-bg');
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    });
  });
});
