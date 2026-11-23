// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi } from 'vitest';
import type { Page } from '@playwright/test';
import {
  FORBIDDEN_MOCK_TOKENS,
  scanForMockTokens,
  assertZeroMockData,
  calculateLuminance,
  calculateContrastRatio,
  parseRgb,
  ROLE_DISALLOWED_SELECTORS,
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
  });
});
