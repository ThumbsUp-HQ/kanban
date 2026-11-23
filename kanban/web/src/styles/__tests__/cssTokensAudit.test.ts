import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

const SRC_DIR = path.resolve(import.meta.dirname, '../..');
const STYLES_DIR = path.resolve(import.meta.dirname, '..');

function getCanonicalTokens(): Set<string> {
  const tokenSet = new Set<string>();
  const styleFiles = ['theme.css', 'tokens.css', 'spacing.css', 'fonts.css', 'base.css'];
  for (const file of styleFiles) {
    const filePath = path.join(STYLES_DIR, file);
    if (fs.existsSync(filePath)) {
      const content = fs.readFileSync(filePath, 'utf8');
      const matches = content.matchAll(/(--[a-zA-Z0-9_-]+)\s*:/g);
      for (const match of matches) {
        if (match[1]) {
          tokenSet.add(match[1]);
        }
      }
    }
  }
  return tokenSet;
}

function getAllCssFiles(dir: string): string[] {
  let results: string[] = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name !== 'node_modules' && entry.name !== 'dist' && entry.name !== '.git') {
        results = results.concat(getAllCssFiles(fullPath));
      }
    } else if (entry.isFile() && entry.name.endsWith('.css')) {
      results.push(fullPath);
    }
  }
  return results;
}

describe('CSS Tokens & Contrast Audit Gate (KANBA-190)', () => {
  const canonicalTokens = getCanonicalTokens();
  const allCssFiles = getAllCssFiles(SRC_DIR);

  it('verifies 100% of var(--*) usages across all CSS files resolve to canonical tokens', () => {
    const undefinedUsages: { file: string; token: string }[] = [];
    const varRegex = /var\(\s*(--[a-zA-Z0-9_-]+)/g;

    for (const cssFile of allCssFiles) {
      const relPath = path.relative(SRC_DIR, cssFile);
      const content = fs.readFileSync(cssFile, 'utf8');
      const matches = content.matchAll(varRegex);
      for (const match of matches) {
        const tokenName = match[1];
        if (tokenName && !canonicalTokens.has(tokenName)) {
          undefinedUsages.push({ file: relPath, token: tokenName });
        }
      }
    }

    expect(
      undefinedUsages,
      `Found ${String(undefinedUsages.length)} undefined CSS variables across codebase:\n` +
        undefinedUsages.map((u) => `  ${u.file}: var(${u.token})`).join('\n')
    ).toEqual([]);
  });

  it('verifies all static auth-* classes in AuthStudioPage.tsx and AuthCardEditorDrawer.tsx exist in adminAuth.css', () => {
    const adminAuthCssPath = path.join(SRC_DIR, 'features/admin-auth/adminAuth.css');
    expect(fs.existsSync(adminAuthCssPath)).toBe(true);
    const adminAuthCss = fs.readFileSync(adminAuthCssPath, 'utf8');

    const definedClasses = new Set<string>();
    for (const m of adminAuthCss.matchAll(/\.([a-zA-Z0-9_-]+)/g)) {
      if (m[1]) {
        definedClasses.add(m[1]);
      }
    }

    const tsxFiles = [
      path.join(SRC_DIR, 'features/admin-auth/AuthStudioPage.tsx'),
      path.join(SRC_DIR, 'features/admin-auth/AuthCardEditorDrawer.tsx')
    ];

    const usedAuthClasses = new Set<string>();
    for (const tsxFile of tsxFiles) {
      if (fs.existsSync(tsxFile)) {
        const content = fs.readFileSync(tsxFile, 'utf8');
        for (const m of content.matchAll(/className=(?:\{`([^`]+)`\}|"([^"]+)")/g)) {
          const raw = m[1] ?? m[2] ?? '';
          const parts = raw.replace(/\$\{[^}]+\}/g, ' ').split(/\s+/);
          for (const p of parts) {
            if (p.startsWith('auth-')) {
              usedAuthClasses.add(p);
            }
          }
        }
      }
    }

    const missingClasses: string[] = [];
    for (const cls of usedAuthClasses) {
      if (!definedClasses.has(cls)) {
        missingClasses.push(cls);
      }
    }

    expect(
      missingClasses,
      `Missing auth-* classes in adminAuth.css:\n${missingClasses.join('\n')}`
    ).toEqual([]);
  });

  it('verifies base.css defines color-scheme and button/input/select/textarea color inheritance', () => {
    const baseCssPath = path.join(STYLES_DIR, 'base.css');
    expect(fs.existsSync(baseCssPath)).toBe(true);
    const baseCss = fs.readFileSync(baseCssPath, 'utf8');

    expect(baseCss).toContain('color-scheme: light');
    expect(baseCss).toContain('color-scheme: dark');
    expect(baseCss).toMatch(/button,\s*input,\s*select,\s*textarea\s*\{[^}]*color:\s*inherit/);
    expect(baseCss).toMatch(/button,\s*input,\s*select,\s*textarea\s*\{[^}]*font-family:\s*inherit/);
  });

  it('ensures simulated undefined token reference is caught by audit scanner', () => {
    const sampleInvalidCss = '.bad-class { color: var(--fg-default); background: var(--bg-surface-elevated); }';
    const foundTokens: string[] = [];
    const varRegex = /var\(\s*(--[a-zA-Z0-9_-]+)/g;
    for (const m of sampleInvalidCss.matchAll(varRegex)) {
      if (m[1] && !canonicalTokens.has(m[1])) {
        foundTokens.push(m[1]);
      }
    }
    expect(foundTokens).toContain('--fg-default');
    expect(foundTokens).toContain('--bg-surface-elevated');
  });

  it('verifies mobile media query rules (font-size: 16px, 100dvh, max-height: calc(100dvh - ...), --tap-min: 44px)', () => {
    const baseCss = fs.readFileSync(path.join(STYLES_DIR, 'base.css'), 'utf8');
    expect(baseCss).toContain('font-size: 16px');
    expect(baseCss).toContain('@media (max-width: 767px), (pointer: coarse)');

    const topbarCss = fs.readFileSync(path.join(SRC_DIR, 'app/Topbar.css'), 'utf8');
    expect(topbarCss).toContain('max-height: calc(100dvh - var(--topbar-h, 52px) - 16px)');
    expect(topbarCss).toContain('overflow-y: auto');
    expect(topbarCss).toContain('min-width: 44px');
    expect(topbarCss).toContain('min-height: 44px');

    const notifCss = fs.readFileSync(path.join(SRC_DIR, 'features/notifications/NotificationsBell.css'), 'utf8');
    expect(notifCss).toContain('max-height: calc(100dvh - var(--topbar-h, 52px) - 16px)');
    expect(notifCss).toContain('width: min(360px, calc(100vw - 24px))');
    expect(notifCss).toContain('min-width: 44px');
    expect(notifCss).toContain('min-height: 44px');

    const commandPaletteCss = fs.readFileSync(path.join(SRC_DIR, 'app/CommandPalette.css'), 'utf8');
    expect(commandPaletteCss).toContain('min-width: 44px');
    expect(commandPaletteCss).toContain('min-height: 44px');
    expect(commandPaletteCss).toContain('max-height: calc(100dvh - 32px)');
    expect(commandPaletteCss).toContain('font-size: 16px');
  });

  it('verifies DocsWorkspaceView mobile drawers do not overlap kb-topbar and expose action buttons under coarse pointer', () => {
    const docsCss = fs.readFileSync(path.join(SRC_DIR, 'features/docs/DocsWorkspaceView.css'), 'utf8');
    expect(docsCss).toContain('top: var(--topbar-h, 52px)');
    expect(docsCss).toContain('height: calc(100dvh - var(--topbar-h, 52px))');
    expect(docsCss).toContain('.docs-tree-item__action-btn');
    expect(docsCss).toContain('min-width: 44px');
    expect(docsCss).toContain('min-height: 44px');
    expect(docsCss).toContain('@media (pointer: coarse)');
  });

  it('verifies desktop board vertical and horizontal flex containment and scroll rules (KAN-380)', () => {
    const appShellCss = fs.readFileSync(path.join(SRC_DIR, 'app/AppShell.css'), 'utf8');
    expect(appShellCss).toContain('grid-template-columns: auto minmax(0, 1fr);');
    expect(appShellCss).toMatch(/\.kb-main-canvas\s*\{[^}]*min-width:\s*0;/);
    expect(appShellCss).toMatch(/\.kb-main-canvas\s*\{[^}]*min-height:\s*0;/);

    const boardCss = fs.readFileSync(path.join(SRC_DIR, 'features/board/board.css'), 'utf8');
    expect(boardCss).toContain('.kb-main-canvas:has(.board-canvas) > [data-testid="route-placeholder"]');
    expect(boardCss).toContain('.issues-workspace:has(.board-canvas)');
    expect(boardCss).toContain('.issues-workspace-route:has(.board-canvas)');
    expect(boardCss).toContain('overscroll-behavior-y: contain;');

    // Verify .board-canvas flex containment
    expect(boardCss).toMatch(/\.board-canvas\s*\{[^}]*flex:\s*1 1 0%;/);
    expect(boardCss).toMatch(/\.board-canvas\s*\{[^}]*min-height:\s*0;/);
    expect(boardCss).toMatch(/\.board-canvas\s*\{[^}]*min-width:\s*0;/);

    // Verify .board-lanes flex and scroll containment
    expect(boardCss).toMatch(/\.board-lanes\s*\{[^}]*flex:\s*1 1 0%;/);
    expect(boardCss).toMatch(/\.board-lanes\s*\{[^}]*overflow-x:\s*auto;/);
    expect(boardCss).toMatch(/\.board-lanes\s*\{[^}]*overflow-y:\s*hidden;/);

    // Verify .board-column height containment
    expect(boardCss).toMatch(/\.board-column\s*\{[^}]*min-height:\s*0;/);
    expect(boardCss).toMatch(/\.board-column\s*\{[^}]*height:\s*100%;/);
    expect(boardCss).toMatch(/\.board-column\s*\{[^}]*max-height:\s*100%;/);

    // Verify .board-column-scroll-area flex and vertical scroll containment
    expect(boardCss).toMatch(/\.board-column-scroll-area\s*\{[^}]*flex:\s*1 1 0%;/);
    expect(boardCss).toMatch(/\.board-column-scroll-area\s*\{[^}]*overflow-y:\s*auto;/);
    expect(boardCss).toMatch(/\.board-column-scroll-area\s*\{[^}]*overflow-x:\s*hidden;/);

    const filterBulkCss = fs.readFileSync(path.join(SRC_DIR, 'features/views/filterBulk.css'), 'utf8');
    expect(filterBulkCss).toContain('.issues-workspace-route:has(.swimlane-board-grid)');
    expect(filterBulkCss).toMatch(/\.swimlane-board-grid\s*\{[^}]*min-width:\s*0;/);
    expect(filterBulkCss).toMatch(/\.swimlane-board-grid\s*\{[^}]*overflow-x:\s*auto;/);
  });
});
