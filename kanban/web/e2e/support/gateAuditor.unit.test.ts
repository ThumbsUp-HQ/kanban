// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi } from 'vitest';
import type { Page } from '@playwright/test';
import {
  FORBIDDEN_MOCK_TOKENS,
  scanForMockTokens,
  assertZeroMockData,
  scanDomForMockData,
  scanHorizontalOverflow,
  scanModalFooterVisibility,
  calculateLuminance,
  calculateContrastRatio,
  parseRgb,
  scanElementContrast,
  ROLE_DISALLOWED_SELECTORS,
  assertDisallowedControls,
  scanLandmarksAndHeadings,
  scanAccessibleNamesAndAria,
  scanFocusVisibleIndicators,
  scanMobileTouchTargets,
  scanMobileInputFontSizes,
  scanTopbarOcclusion,
} from './gateAuditor';

describe('gateAuditor Meta-Assertion Harness (KANBA-223)', () => {
  describe('Zero-Mock-Data Gate', () => {
    it('detects every single forbidden mock token in strings', () => {
      for (const token of FORBIDDEN_MOCK_TOKENS) {
        const payload = `User payload containing ${token} as a value`;
        const violations = scanForMockTokens(payload);
        expect(violations.length).toBeGreaterThan(0);
        expect(violations[0]).toContain(token);
      }
    });

    it('detects forbidden mock tokens nested inside objects and arrays', () => {
      const nestedPayload = {
        data: {
          items: [
            { id: 1, title: 'Clean title' },
            { id: 2, assignee: 'Alice Cooper' },
          ],
          metadata: {
            board_type: 'Kanban Board',
          },
        },
      };

      const violations = scanForMockTokens(nestedPayload);
      expect(violations).toHaveLength(2);
      expect(violations.some((v) => v.includes('Alice Cooper'))).toBe(true);
      expect(violations.some((v) => v.includes('Kanban Board'))).toBe(true);
    });

    it('detects forbidden mock token in object keys', () => {
      const payloadWithKey = {
        'state-todo': { count: 5 },
      };
      const violations = scanForMockTokens(payloadWithKey);
      expect(violations.length).toBe(1);
      expect(violations[0]).toContain('state-todo');
    });

    it('assertZeroMockData throws on forbidden tokens and succeeds on clean data', () => {
      expect(() => {
        assertZeroMockData({ name: 'Adam Outler' }, 'user payload');
      }).toThrow('Zero-Mock-Data Gate failure in user payload');

      expect(() => {
        assertZeroMockData({ route: '/undefined/' }, 'navigation');
      }).toThrow('Zero-Mock-Data Gate failure in navigation');

      expect(() => {
        assertZeroMockData(
          {
            user: 'Elena Vance',
            project: 'PRJ',
            cycle: 'Sprint Alpha',
            state: 'st-inprogress',
            module: 'mod-core',
          },
          'clean payload',
        );
      }).not.toThrow();
    });
  });

  describe('WCAG AA Contrast Calculator & Meta-Evaluator', () => {
    it('correctly calculates relative luminance for standard colors', () => {
      // Pure black L = 0
      expect(calculateLuminance(0, 0, 0)).toBe(0);
      // Pure white L = 1
      expect(calculateLuminance(255, 255, 255)).toBeCloseTo(1.0, 4);
    });

    it('correctly parses RGB and RGBA strings', () => {
      expect(parseRgb('rgb(255, 0, 128)')).toEqual({ r: 255, g: 0, b: 128, a: 1 });
      expect(parseRgb('rgba(10, 20, 30, 0.5)')).toEqual({ r: 10, g: 20, b: 30, a: 0.5 });
      expect(parseRgb('#ffffff')).toEqual({ r: 255, g: 255, b: 255, a: 1 });
      expect(parseRgb('#000')).toEqual({ r: 0, g: 0, b: 0, a: 1 });
    });

    it('computes contrast ratios matching WCAG 2.1 specifications', () => {
      // Black on White: 21:1
      const blackOnWhite = calculateContrastRatio('rgb(0, 0, 0)', 'rgb(255, 255, 255)');
      expect(blackOnWhite).toBeCloseTo(21.0, 1);

      // White on Black: 21:1
      const whiteOnBlack = calculateContrastRatio('rgb(255, 255, 255)', 'rgb(0, 0, 0)');
      expect(whiteOnBlack).toBeCloseTo(21.0, 1);

      // Identical colors: 1:1
      const sameColor = calculateContrastRatio('rgb(100, 100, 100)', 'rgb(100, 100, 100)');
      expect(sameColor).toBeCloseTo(1.0, 1);
    });

    it('detects injected contrast violations (fails below 4.5:1 for regular text)', () => {
      // Light gray on white (#999999 on #ffffff is ~2.8:1, fails WCAG AA)
      const lowContrast = calculateContrastRatio('rgb(153, 153, 153)', 'rgb(255, 255, 255)');
      expect(lowContrast).toBeLessThan(4.5);

      // Dark gray on black (#444444 on #121418 is ~1.8:1, fails WCAG AA)
      const darkOnDark = calculateContrastRatio('rgb(68, 68, 68)', 'rgb(18, 20, 24)');
      expect(darkOnDark).toBeLessThan(4.5);

      // High contrast accessible dark mode (#e2e8f0 on #121418 is ~12.5:1, passes)
      const accessibleDark = calculateContrastRatio('rgb(226, 232, 240)', 'rgb(18, 20, 24)');
      expect(accessibleDark).toBeGreaterThan(4.5);
    });
  });

  describe('6-Role Missing-Control Configuration', () => {
    it('defines distinct disallowed controls across guest, viewer, member, projadmin, wsadmin', () => {
      expect(ROLE_DISALLOWED_SELECTORS.guest.length).toBeGreaterThan(5);
      expect(ROLE_DISALLOWED_SELECTORS.viewer.length).toBeGreaterThan(5);
      expect(ROLE_DISALLOWED_SELECTORS.member.length).toBeGreaterThan(2);
      expect(ROLE_DISALLOWED_SELECTORS.projadmin.length).toBeGreaterThan(0);
      expect(ROLE_DISALLOWED_SELECTORS.wsadmin.length).toBeGreaterThan(0);
      expect(ROLE_DISALLOWED_SELECTORS.admin).toEqual([]);

      // Viewer disallowed selectors include write buttons
      expect(ROLE_DISALLOWED_SELECTORS.viewer).toContain('[data-testid="home-create-issue-btn"]');
      expect(ROLE_DISALLOWED_SELECTORS.viewer).toContain('[data-testid="create-cycle-form"]');

      // Member disallowed selectors include project creation
      expect(ROLE_DISALLOWED_SELECTORS.member).toContain('[data-testid="home-create-project-btn"]');
      expect(ROLE_DISALLOWED_SELECTORS.member).toContain('button:has-text("+ Workflow")');
    });
  });

  describe('Mobile Gate Auditors (KAN-314)', () => {
    it('scanMobileTouchTargets delegates to page.evaluate with target bounds', async () => {
      const mockPage = {
        evaluate: vi.fn().mockResolvedValue([
          { selector: 'button:nth-of-type(1)', text: 'Tiny', width: 24, height: 24, minAllowed: 44 }
        ]),
      } as unknown as Page;

      const violations = await scanMobileTouchTargets(mockPage, { minTargetSize: 44 });
      expect(violations).toHaveLength(1);
      expect(violations[0]?.width).toBe(24);
      expect(violations[0]?.minAllowed).toBe(44);
    });

    it('scanMobileInputFontSizes delegates to page.evaluate with 16px requirement', async () => {
      const mockPage = {
        evaluate: vi.fn().mockResolvedValue([
          { selector: 'input:nth-of-type(1)', tagName: 'input', fontSize: 13, requiredSize: 16 }
        ]),
      } as unknown as Page;

      const violations = await scanMobileInputFontSizes(mockPage, { minFontSize: 16 });
      expect(violations).toHaveLength(1);
      expect(violations[0]?.fontSize).toBe(13);
      expect(violations[0]?.requiredSize).toBe(16);
    });

    it('scanTopbarOcclusion delegates to page.evaluate detecting topbar overlay', async () => {
      const mockPage = {
        evaluate: vi.fn().mockResolvedValue([
          { selector: '.docs-tree-pane', topbarBottom: 52, elementTop: 0, occludedPixels: 52 }
        ]),
      } as unknown as Page;

      const violations = await scanTopbarOcclusion(mockPage, '.kb-topbar');
      expect(violations).toHaveLength(1);
      expect(violations[0]?.occludedPixels).toBe(52);
    });

    it('executes all DOM scanners inside jsdom via page.evaluate', async () => {
      const evalPage = {
        evaluate: vi.fn((fn: (arg?: unknown) => unknown, arg?: unknown) =>
          Promise.resolve(fn(arg)),
        ),
        locator: vi.fn((sel: string) => ({
          count: vi.fn(() => Promise.resolve(sel.includes('home-create-issue-btn') ? 1 : 0)),
          first: vi.fn(() => {
            const el = document.querySelector(sel);
            return {
              count: vi.fn(() => Promise.resolve(el ? 1 : 0)),
              focus: vi.fn(() => Promise.resolve()),
              evaluate: vi.fn((fn: (e: Element) => unknown) =>
                Promise.resolve(el ? fn(el) : null),
              ),
            };
          }),
        })),
      } as unknown as Page;

      // 1. scanDomForMockData & scanForMockTokens branches
      expect(scanForMockTokens(null)).toEqual([]);
      expect(scanForMockTokens(42)).toEqual([]);
      expect(scanForMockTokens(true)).toEqual([]);
      expect(parseRgb('')).toBeNull();
      expect(parseRgb('invalid')).toBeNull();
      expect(calculateContrastRatio('invalid', 'rgb(0,0,0)')).toBe(21);

      document.body.innerText = 'Welcome Alice Cooper';
      document.body.innerHTML = `
        <div id="state-todo" data-testid="mod-1">
          <a href="/undefined/page">Link</a>
          <input value="Adam Outler" />
        </div>
      `;
      const mockHits = await scanDomForMockData(evalPage);
      expect(mockHits.length).toBeGreaterThan(0);

      // 2. scanHorizontalOverflow
      Object.defineProperty(document.documentElement, 'scrollWidth', { value: 1200, configurable: true });
      Object.defineProperty(window, 'innerWidth', { value: 390, configurable: true });
      const wideEl = document.createElement('div');
      wideEl.id = 'wide';
      wideEl.className = 'wide-box extra';
      wideEl.getBoundingClientRect = () => ({ right: 500, left: 0, top: 0, bottom: 50, width: 500, height: 50, x: 0, y: 0, toJSON: () => ({}) });
      document.body.appendChild(wideEl);
      const overflowRes = await scanHorizontalOverflow(evalPage, 390);
      expect(overflowRes.overflows).toBe(true);
      expect(overflowRes.offendingElements.length).toBeGreaterThan(0);
      const overflowNoLimit = await scanHorizontalOverflow(evalPage);
      expect(overflowNoLimit.overflows).toBe(true);

      // 3. scanModalFooterVisibility
      Object.defineProperty(window, 'innerHeight', { value: 400, configurable: true });
      document.body.innerHTML = `
        <div role="dialog" id="m-hidden"></div>
        <div role="dialog" id="m-nofooter"></div>
        <div role="dialog" id="m-visible">
          <footer class="modal-footer">
            <button id="b-hidden">Hidden</button>
            <button id="b-oob">Save</button>
            <button id="b-ok">Cancel</button>
          </footer>
        </div>
      `;
      const mVisible = document.getElementById('m-visible');
      const mNoFooter = document.getElementById('m-nofooter');
      if (mNoFooter) {
        mNoFooter.getBoundingClientRect = () => ({ width: 200, height: 200, top: 0, left: 0, right: 200, bottom: 200, x: 0, y: 0, toJSON: () => ({}) });
      }
      if (mVisible) {
        mVisible.getBoundingClientRect = () => ({ width: 300, height: 300, top: 0, left: 0, right: 300, bottom: 300, x: 0, y: 0, toJSON: () => ({}) });
      }
      const bOob = document.getElementById('b-oob');
      if (bOob) {
        bOob.getBoundingClientRect = () => ({ width: 80, height: 36, top: -10, left: -10, right: 500, bottom: 500, x: -10, y: -10, toJSON: () => ({}) });
      }
      const bOk = document.getElementById('b-ok');
      if (bOk) {
        bOk.getBoundingClientRect = () => ({ width: 80, height: 36, top: 10, left: 10, right: 90, bottom: 46, x: 10, y: 10, toJSON: () => ({}) });
      }
      const modalViolations = await scanModalFooterVisibility(evalPage);
      expect(modalViolations.length).toBe(1);

      // 4. scanElementContrast
      document.documentElement.setAttribute('data-theme', 'dark');
      document.body.innerHTML = `
        <div id="contrast-root" style="background-color: rgba(0, 0, 0, 0);">
          <button id="c-low" style="color: rgb(30, 30, 30); font-size: 14px; font-weight: 400;">Low Contrast</button>
          <h1 id="c-large" style="color: rgb(255, 255, 255); background-color: rgb(10, 10, 10); font-size: 20px; font-weight: 700;">High Contrast</h1>
          <button id="c-emoji" style="color: rgb(30, 30, 30);">🛡️</button>
          <button id="c-hidden" style="display: none;">Hidden</button>
          <div aria-hidden="true"><button id="c-aria-hidden">Ignored</button></div>
        </div>
      `;
      for (const id of ['c-low', 'c-large', 'c-emoji']) {
        const el = document.getElementById(id);
        if (el) {
          el.getBoundingClientRect = () => ({ width: 100, height: 30, top: 0, left: 0, right: 100, bottom: 30, x: 0, y: 0, toJSON: () => ({}) });
        }
      }
      const contrastViolations = await scanElementContrast(evalPage, ['button', 'h1'], '#contrast-root');
      expect(contrastViolations.length).toBe(1);
      document.documentElement.removeAttribute('data-theme');

      // 5. assertDisallowedControls
      const roleViolations = await assertDisallowedControls(evalPage, 'viewer');
      expect(roleViolations.length).toBe(1);

      // 6. scanLandmarksAndHeadings
      document.body.innerHTML = `
        <nav></nav>
        <nav aria-label="Secondary"></nav>
        <h2>Skipped H1</h2>
        <h4>Skipped H3</h4>
      `;
      const h2 = document.querySelector('h2');
      const h4 = document.querySelector('h4');
      if (h2) {
        Object.defineProperty(h2, 'offsetParent', { value: document.body, configurable: true });
      }
      if (h4) {
        Object.defineProperty(h4, 'offsetParent', { value: document.body, configurable: true });
      }
      const landmarkViolations = await scanLandmarksAndHeadings(evalPage);
      expect(landmarkViolations.some((v) => v.kind === 'missing-main')).toBe(true);
      expect(landmarkViolations.some((v) => v.kind === 'unlabelled-nav')).toBe(true);
      expect(landmarkViolations.some((v) => v.kind === 'missing-h1')).toBe(true);
      expect(landmarkViolations.some((v) => v.kind === 'skipped-heading')).toBe(true);

      document.body.innerHTML = `<main><h1>Title</h1></main><main></main>`;
      const multiMainViolations = await scanLandmarksAndHeadings(evalPage);
      expect(multiMainViolations.some((v) => v.kind === 'multiple-mains')).toBe(true);

      // 7. scanAccessibleNamesAndAria
      document.body.innerHTML = `
        <button id="unnamed-btn" class="sr-only"></button>
        <button id="named-btn" class="sr-only" aria-label="Named"></button>
        <div role="menu"><button role="radio">Bad Radio</button></div>
        <div aria-labelledby="missing-id" aria-controls="missing-ctrl" aria-activedescendant="missing-act"></div>
      `;
      const ariaViolations = await scanAccessibleNamesAndAria(evalPage);
      expect(ariaViolations.some((v) => v.kind === 'missing-name')).toBe(true);
      expect(ariaViolations.some((v) => v.kind === 'invalid-parent-child')).toBe(true);
      expect(ariaViolations.filter((v) => v.kind === 'broken-reference').length).toBe(3);

      // 8. scanFocusVisibleIndicators
      document.body.innerHTML = `
        <input class="kb-palette-input" style="outline-style: none; outline-width: 0px; box-shadow: none;" />
        <input class="navigator-search-input" style="outline-style: solid; outline-width: 2px;" />
      `;
      const focusViolations = await scanFocusVisibleIndicators(evalPage, ['.kb-palette-input', '.navigator-search-input', '.missing']);
      expect(focusViolations.length).toBe(1);

      // 9. scanMobileTouchTargets, scanMobileInputFontSizes, scanTopbarOcclusion
      document.body.innerHTML = `
        <header class="kb-topbar" style="z-index: 100;"></header>
        <aside class="docs-tree-pane" style="position: fixed; z-index: 50;"></aside>
        <button id="small-btn">Tiny</button>
        <button id="ignored-btn" class="ignore-me">Ignored</button>
        <button id="hidden-btn" style="display: none;">Hidden</button>
        <div style="display: block;"><a id="inline-link" href="/test" style="display: inline;">Inline</a></div>
        <input id="small-input" type="text" style="font-size: 12px;" />
        <input id="hidden-input" type="text" style="display: none; font-size: 12px;" />
      `;
      const topbar = document.querySelector('.kb-topbar');
      if (topbar) {
        topbar.getBoundingClientRect = () => ({ top: 0, bottom: 52, left: 0, right: 390, width: 390, height: 52, x: 0, y: 0, toJSON: () => ({}) });
      }
      const pane = document.querySelector('.docs-tree-pane');
      if (pane) {
        pane.getBoundingClientRect = () => ({ top: 10, bottom: 400, left: 0, right: 250, width: 250, height: 390, x: 0, y: 10, toJSON: () => ({}) });
      }
      const smallBtn = document.getElementById('small-btn');
      if (smallBtn) {
        smallBtn.getBoundingClientRect = () => ({ top: 0, bottom: 20, left: 0, right: 20, width: 20, height: 20, x: 0, y: 0, toJSON: () => ({}) });
      }
      const inlineLink = document.getElementById('inline-link');
      if (inlineLink) {
        inlineLink.getBoundingClientRect = () => ({ top: 0, bottom: 16, left: 0, right: 40, width: 40, height: 16, x: 0, y: 0, toJSON: () => ({}) });
      }
      const smallInput = document.getElementById('small-input');
      if (smallInput) {
        smallInput.getBoundingClientRect = () => ({ top: 0, bottom: 30, left: 0, right: 100, width: 100, height: 30, x: 0, y: 0, toJSON: () => ({}) });
      }

      const touchRes = await scanMobileTouchTargets(evalPage, { minTargetSize: 44, ignoreSelectors: ['.ignore-me'] });
      expect(touchRes.length).toBe(2);
      const fontRes = await scanMobileInputFontSizes(evalPage, { minFontSize: 16 });
      expect(fontRes.length).toBe(1);
      const occRes = await scanTopbarOcclusion(evalPage);
      expect(occRes.length).toBe(1);
    });
  });
});
