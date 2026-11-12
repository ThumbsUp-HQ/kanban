import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const EXPECTED_S61_TOKENS: Record<string, string> = {
  '--font-sans': "'Inter Variable', -apple-system, BlinkMacSystemFont, sans-serif",
  '--font-mono': "'JetBrains Mono Variable', ui-monospace, monospace",
  '--text-body': '0.9375rem',
  '--leading-prose': '1.73',
  '--sidebar-w': '256px',
  '--topbar-h': '52px',
  '--board-canvas-pad': '24px 28px',
  '--board-col-w': '324px',
  '--board-col-gap': '20px',
  '--card-pad': '16px 18px',
  '--card-gap': '12px',
  '--list-row-h': '46px',
  '--drawer-w': 'min(960px, 68vw)',
  '--prose-pad': '32px 40px',
  '--prop-row-h': '38px',
  '--section-gap': '32px',
};

const STYLES_DIR = path.resolve(import.meta.dirname, '.');

describe('S6.1 Design Tokens (tokens.css)', () => {
  const tokensCssPath = path.join(STYLES_DIR, 'tokens.css');
  const tokensCssContent = fs.readFileSync(tokensCssPath, 'utf8');

  it('contains exactly the 16 S6.1 token names with exact declared values', () => {
    // Strip comments
    const stripped = tokensCssContent.replace(/\/\*[\s\S]*?\*\//g, '');
    const rootMatch = /:root\s*\{([^}]*)\}/.exec(stripped);
    expect(rootMatch).toBeTruthy();

    const rootBody = rootMatch?.[1] ?? '';
    const propRegex = /(--[a-z-]+)\s*:\s*([^;]+);/g;
    const foundTokens: Record<string, string> = {};

    let match: RegExpExecArray | null;
    while ((match = propRegex.exec(rootBody)) !== null) {
      const propName = match[1]?.trim() ?? '';
      const propVal = match[2]?.trim() ?? '';
      foundTokens[propName] = propVal;
    }

    const foundKeys = Object.keys(foundTokens);
    const expectedKeys = Object.keys(EXPECTED_S61_TOKENS);

    // Exact count: 16
    expect(foundKeys.length).toBe(16);
    expect(foundKeys.sort()).toEqual(expectedKeys.sort());

    for (const [name, expectedVal] of Object.entries(EXPECTED_S61_TOKENS)) {
      expect(foundTokens[name]).toBe(expectedVal);
    }
  });

  it('index.css imports files in the exact order: fonts, tokens, spacing, theme, base', () => {
    const indexPath = path.join(STYLES_DIR, 'index.css');
    const indexContent = fs.readFileSync(indexPath, 'utf8');
    const stripped = indexContent.replace(/\/\*[\s\S]*?\*\//g, '');
    const importRegex = /@import\s+['"]([^'"]+)['"];/g;

    const imports: string[] = [];
    let match: RegExpExecArray | null;
    while ((match = importRegex.exec(stripped)) !== null) {
      if (match[1]) {
        imports.push(match[1]);
      }
    }

    expect(imports).toEqual([
      './fonts.css',
      './tokens.css',
      './spacing.css',
      './theme.css',
      './base.css',
    ]);
  });

  it('enforces zero http/https URLs across all src/styles/*.css files', () => {
    const cssFiles = fs
      .readdirSync(STYLES_DIR)
      .filter((file) => file.endsWith('.css'));

    expect(cssFiles.length).toBeGreaterThanOrEqual(5);

    for (const file of cssFiles) {
      const content = fs.readFileSync(path.join(STYLES_DIR, file), 'utf8');
      expect(content).not.toMatch(/https?:\/\//i);
      expect(content).not.toMatch(/@import\s+url\(/i);
    }
  });

  it('strictly forbids any "dense" or "compact" token variants across styles', () => {
    const cssFiles = fs
      .readdirSync(STYLES_DIR)
      .filter((file) => file.endsWith('.css'));

    for (const file of cssFiles) {
      const content = fs.readFileSync(path.join(STYLES_DIR, file), 'utf8');
      expect(content).not.toMatch(/dense/i);
      expect(content).not.toMatch(/compact/i);
    }
  });
});
