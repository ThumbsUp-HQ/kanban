// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import type { Page } from '@playwright/test';

/**
 * Forbidden mock tokens mandated by KANBA-223.
 * The gate fails immediately if any of these tokens appear in DOM or API responses.
 */
export const FORBIDDEN_MOCK_TOKENS = [
  'Alice Cooper',
  'Adam Outler',
  'Cycle 1',
  'Kanban Board',
  'state-todo',
  'mod-1',
  'QAADM-NEW',
  '/undefined/',
] as const;

export type ForbiddenMockToken = (typeof FORBIDDEN_MOCK_TOKENS)[number];

export interface ContrastViolation {
  selector: string;
  text: string;
  fgColor: string;
  bgColor: string;
  contrastRatio: number;
  requiredRatio: number;
  isLargeText: boolean;
}

export interface OverflowViolation {
  scrollWidth: number;
  innerWidth: number;
  offendingElements: string[];
}

export interface ModalFooterViolation {
  modalSelector: string;
  buttonSelector: string;
  buttonText: string;
  bounds: { top: number; left: number; right: number; bottom: number };
  viewport: { width: number; height: number };
  reason: string;
}

export interface DisallowedControlViolation {
  role: string;
  selector: string;
  count: number;
}

/**
 * Recursively scans a string or data object for forbidden mock tokens.
 */
export function scanForMockTokens(data: unknown): string[] {
  const violations: string[] = [];

  function checkString(str: string): void {
    for (const token of FORBIDDEN_MOCK_TOKENS) {
      if (str.includes(token)) {
        violations.push(`Forbidden mock token detected: "${token}" in string "${str.slice(0, 100)}"`);
      }
    }
  }

  function traverse(item: unknown): void {
    if (item === null || item === undefined) {
      return;
    }
    if (typeof item === 'string') {
      checkString(item);
    } else if (typeof item === 'number' || typeof item === 'boolean') {
      // safe primitives
    } else if (Array.isArray(item)) {
      for (const entry of item) {
        traverse(entry);
      }
    } else if (typeof item === 'object') {
      for (const [key, val] of Object.entries(item)) {
        checkString(key);
        traverse(val);
      }
    }
  }

  traverse(data);
  return violations;
}

/**
 * Asserts zero forbidden mock tokens in the given data object or string.
 */
export function assertZeroMockData(data: unknown, contextName = 'data'): void {
  const violations = scanForMockTokens(data);
  if (violations.length > 0) {
    throw new Error(`Zero-Mock-Data Gate failure in ${contextName}:\n${violations.join('\n')}`);
  }
}

/**
 * Scans page DOM for forbidden mock tokens in rendered text and attributes.
 */
export async function scanDomForMockData(page: Page): Promise<string[]> {
  const found = await page.evaluate((tokens) => {
    const hits: string[] = [];
    const fullText = document.body.innerText;
    for (const tok of tokens) {
      if (fullText.includes(tok)) {
        hits.push(`DOM innerText contains forbidden token: "${tok}"`);
      }
    }

    // Check all elements attributes (e.g. href, data-testid, id, value)
    const elements = document.querySelectorAll('*');
    for (const el of Array.from(elements)) {
      const testId = el.getAttribute('data-testid');
      const href = el.getAttribute('href');
      const val = typeof (el as HTMLInputElement).value === 'string' ? (el as HTMLInputElement).value : '';
      const id = el.id;

      for (const tok of tokens) {
        if (
          testId?.includes(tok) ||
          href?.includes(tok) ||
          val.includes(tok) ||
          id.includes(tok)
        ) {
          hits.push(`Element <${el.tagName.toLowerCase()}> contains forbidden token "${tok}"`);
        }
      }
    }
    return hits;
  }, FORBIDDEN_MOCK_TOKENS as unknown as string[]);

  return found;
}

/**
 * Validates document scrollWidth <= window.innerWidth on mobile or desktop.
 */
export async function scanHorizontalOverflow(
  page: Page,
  expectedMaxWidth?: number,
): Promise<{ scrollWidth: number; innerWidth: number; overflows: boolean; offendingElements: string[] }> {
  return page.evaluate((maxW) => {
    const docElem = document.documentElement;
    const scrollWidth = Math.max(docElem.scrollWidth, document.body.scrollWidth);
    const innerWidth = window.innerWidth;
    const limit = maxW !== undefined ? Math.min(innerWidth, maxW) : innerWidth;

    const offending: string[] = [];
    if (scrollWidth > limit) {
      const all = document.querySelectorAll('body *');
      for (const el of Array.from(all)) {
        const rect = el.getBoundingClientRect();
        if (rect.right > limit + 1) {
          const id = el.id ? `#${el.id}` : '';
          const cls = el.className && typeof el.className === 'string' ? `.${el.className.split(' ').join('.')}` : '';
          offending.push(`<${el.tagName.toLowerCase()}${id}${cls}> rect.right=${String(Math.round(rect.right))}px exceeds ${String(limit)}px`);
          if (offending.length >= 5) break;
        }
      }
    }

    return {
      scrollWidth,
      innerWidth,
      overflows: scrollWidth > limit,
      offendingElements: offending,
    };
  }, expectedMaxWidth);
}

/**
 * Validates modal dialog footer action buttons are fully within viewport bounds.
 */
export async function scanModalFooterVisibility(
  page: Page,
  dialogSelector = '[role="dialog"]',
): Promise<ModalFooterViolation[]> {
  return page.evaluate((sel) => {
    const violations: {
      modalSelector: string;
      buttonSelector: string;
      buttonText: string;
      bounds: { top: number; left: number; right: number; bottom: number };
      viewport: { width: number; height: number };
      reason: string;
    }[] = [];

    const modals = document.querySelectorAll(sel);
    const vp = { width: window.innerWidth, height: window.innerHeight };

    modals.forEach((modal, mIdx) => {
      const modalRect = modal.getBoundingClientRect();
      // Skip if modal is hidden
      if (modalRect.width === 0 || modalRect.height === 0) return;

      // Scope to modal footer action container(s)
      const footers = modal.querySelectorAll('footer, [class*="footer"], [class*="__footer"], [class*="-footer"]');
      if (footers.length === 0) return;

      footers.forEach((footer) => {
        const buttons = footer.querySelectorAll('button, [role="button"], input[type="submit"]');
        buttons.forEach((btn, bIdx) => {
          const rect = btn.getBoundingClientRect();
          if (rect.width === 0 || rect.height === 0) return;

          const reasons: string[] = [];
          if (rect.bottom > vp.height) {
            reasons.push(`bottom (${String(Math.round(rect.bottom))}px) exceeds viewport height (${String(vp.height)}px)`);
          }
          if (rect.right > vp.width) {
            reasons.push(`right (${String(Math.round(rect.right))}px) exceeds viewport width (${String(vp.width)}px)`);
          }
          if (rect.top < 0) {
            reasons.push(`top (${String(Math.round(rect.top))}px) is above viewport top (0px)`);
          }
          if (rect.left < 0) {
            reasons.push(`left (${String(Math.round(rect.left))}px) is left of viewport (0px)`);
          }

          if (reasons.length > 0) {
            violations.push({
              modalSelector: `${sel}:nth-of-type(${String(mIdx + 1)})`,
              buttonSelector: `button:nth-of-type(${String(bIdx + 1)})`,
              buttonText: btn.textContent.trim().slice(0, 30),
              bounds: {
                top: Math.round(rect.top),
                left: Math.round(rect.left),
                right: Math.round(rect.right),
                bottom: Math.round(rect.bottom),
              },
              viewport: vp,
              reason: reasons.join('; '),
            });
          }
        });
      });
    });

    return violations;
  }, dialogSelector);
}

/**
 * Parses RGB or RGBA string into normalized [0..255] channels.
 */
export function parseRgb(color: string): { r: number; g: number; b: number; a: number } | null {
  if (!color || typeof color !== 'string') return null;
  const trimmed = color.trim().toLowerCase();

  // Hex format #rgb, #rgba, #rrggbb, #rrggbbaa
  if (trimmed.startsWith('#')) {
    const hex = trimmed.slice(1);
    if (hex.length === 3) {
      const c0 = hex[0] ?? '0';
      const c1 = hex[1] ?? '0';
      const c2 = hex[2] ?? '0';
      return {
        r: parseInt(c0 + c0, 16),
        g: parseInt(c1 + c1, 16),
        b: parseInt(c2 + c2, 16),
        a: 1,
      };
    }
    if (hex.length === 6) {
      return {
        r: parseInt(hex.slice(0, 2), 16),
        g: parseInt(hex.slice(2, 4), 16),
        b: parseInt(hex.slice(4, 6), 16),
        a: 1,
      };
    }
  }

  // rgb(r, g, b) or rgba(r, g, b, a)
  const match = /rgba?\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/.exec(trimmed);
  if (match?.[1] && match[2] && match[3]) {
    return {
      r: Math.round(parseFloat(match[1])),
      g: Math.round(parseFloat(match[2])),
      b: Math.round(parseFloat(match[3])),
      a: match[4] !== undefined ? parseFloat(match[4]) : 1,
    };
  }

  return null;
}

/**
 * Calculates WCAG 2.1 relative luminance for sRGB channels.
 */
export function calculateLuminance(r: number, g: number, b: number): number {
  const a = [r, g, b].map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  const rLum = a[0] ?? 0;
  const gLum = a[1] ?? 0;
  const bLum = a[2] ?? 0;
  return 0.2126 * rLum + 0.7152 * gLum + 0.0722 * bLum;
}

/**
 * Calculates contrast ratio between foreground and background.
 * Returns a ratio >= 1.0 (e.g. 4.5 for 4.5:1).
 */
export function calculateContrastRatio(fgRgb: string, bgRgb: string): number {
  const fg = parseRgb(fgRgb);
  const bg = parseRgb(bgRgb);
  if (!fg || !bg) return 21; // fallback if unparseable

  // Alpha blend foreground over background if foreground is translucent
  const effectiveFg = {
    r: Math.round(fg.r * fg.a + bg.r * (1 - fg.a)),
    g: Math.round(fg.g * fg.a + bg.g * (1 - fg.a)),
    b: Math.round(fg.b * fg.a + bg.b * (1 - fg.a)),
  };

  const lum1 = calculateLuminance(effectiveFg.r, effectiveFg.g, effectiveFg.b);
  const lum2 = calculateLuminance(bg.r, bg.g, bg.b);

  const lighter = Math.max(lum1, lum2);
  const darker = Math.min(lum1, lum2);
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * Sweeps key text and button elements on page and asserts WCAG AA contrast.
 */
export async function scanElementContrast(
  page: Page,
  selectors: string[] = ['button', 'a', 'h1', 'h2', 'h3', 'p', 'label', 'input', '.kb-btn', '.badge'],
  containerSelector?: string,
): Promise<ContrastViolation[]> {
  return page.evaluate(({ sels, containerSel }) => {
    function parseRgbLocal(color: string): { r: number; g: number; b: number; a: number } | null {
      if (!color || typeof color !== 'string') return null;
      const match = /rgba?\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/.exec(color);
      if (match?.[1] && match[2] && match[3]) {
        return {
          r: Math.round(parseFloat(match[1])),
          g: Math.round(parseFloat(match[2])),
          b: Math.round(parseFloat(match[3])),
          a: match[4] !== undefined ? parseFloat(match[4]) : 1,
        };
      }
      return null;
    }

    function calculateLumLocal(r: number, g: number, b: number): number {
      const a = [r, g, b].map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      });
      const rLum = a[0] ?? 0;
      const gLum = a[1] ?? 0;
      const bLum = a[2] ?? 0;
      return 0.2126 * rLum + 0.7152 * gLum + 0.0722 * bLum;
    }

    function getEffectiveBg(el: Element): string {
      let current: Element | null = el;
      while (current) {
        const bg = window.getComputedStyle(current).backgroundColor;
        const parsed = parseRgbLocal(bg);
        if (parsed && parsed.a > 0.05) {
          return bg;
        }
        current = current.parentElement;
      }
      // default page background based on theme
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      return isDark ? 'rgb(18, 20, 24)' : 'rgb(255, 255, 255)';
    }

    const violations: {
      selector: string;
      text: string;
      fgColor: string;
      bgColor: string;
      contrastRatio: number;
      requiredRatio: number;
      isLargeText: boolean;
    }[] = [];

    const root = containerSel ? document.querySelector(containerSel) ?? document : document;
    const elements = root.querySelectorAll(sels.join(', '));
    elements.forEach((el, idx) => {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;

      const style = window.getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none' || parseFloat(style.opacity) < 0.1) return;
      if (el.closest('[aria-hidden="true"], [inert]') && !el.closest('[role="dialog"]')) return;
      const text = el.textContent.trim();
      if (!text || text.length === 0) return;
      // Skip pure icon/symbol glyphs (e.g. 🛡️, ▾, ✕) where color contrast does not apply to text
      const hasAlphaNumeric = /[\p{L}\p{N}]/u.test(text);
      if (!hasAlphaNumeric) return;

      const fgColor = style.color;
      const bgColor = getEffectiveBg(el);

      const fg = parseRgbLocal(fgColor);
      const bg = parseRgbLocal(bgColor);
      if (!fg || !bg) return;

      const effectiveFg = {
        r: Math.round(fg.r * fg.a + bg.r * (1 - fg.a)),
        g: Math.round(fg.g * fg.a + bg.g * (1 - fg.a)),
        b: Math.round(fg.b * fg.a + bg.b * (1 - fg.a)),
      };

      const lum1 = calculateLumLocal(effectiveFg.r, effectiveFg.g, effectiveFg.b);
      const lum2 = calculateLumLocal(bg.r, bg.g, bg.b);
      const lighter = Math.max(lum1, lum2);
      const darker = Math.min(lum1, lum2);
      const ratio = Math.round(((lighter + 0.05) / (darker + 0.05)) * 100) / 100;

      const fontSize = parseFloat(style.fontSize) || 14;
      const fontWeight = parseInt(style.fontWeight, 10) || 400;
      const isLargeText = fontSize >= 18 || (fontSize >= 14 && fontWeight >= 700);
      const requiredRatio = isLargeText ? 3.0 : 4.5;

      if (ratio < requiredRatio) {
        violations.push({
          selector: `${el.tagName.toLowerCase()}:nth-of-type(${String(idx + 1)})`,
          text: text.slice(0, 30),
          fgColor,
          bgColor,
          contrastRatio: ratio,
          requiredRatio,
          isLargeText,
        });
      }
    });

    return violations;
  }, { sels: selectors, containerSel: containerSelector });
}

export type AuditRole = 'guest' | 'viewer' | 'member' | 'projadmin' | 'wsadmin' | 'admin';

/**
 * 6-Role Missing-Control definitions per KANBA-209 and KANBA-223.
 */
export const ROLE_DISALLOWED_SELECTORS: Record<AuditRole, string[]> = {
  guest: [
    '[data-testid="project-card-KAN"]',
    '[data-testid="home-create-issue-btn"]',
    '[data-testid="home-create-project-btn"]',
    '[data-testid="sidebar-add-project-btn"]',
    '[data-testid="view-empty-create-btn"]',
    '[data-testid="list-new-btn"]',
    '.kb-new-item-btn',
    '[data-testid="create-cycle-form"]',
    'button:has-text("+ Workflow")',
  ],
  viewer: [
    '[data-testid="home-create-issue-btn"]',
    '[data-testid="view-empty-create-btn"]',
    '[data-testid="list-new-btn"]',
    '.kb-new-item-btn',
    '[data-testid="create-cycle-form"]',
    'button:has-text("Create New Cycle")',
    'button:has-text("+ Module")',
    'button:has-text("+ Workflow")',
    '[data-testid="home-create-project-btn"]',
    '[data-testid="sidebar-add-project-btn"]',
  ],
  member: [
    '[data-testid="home-create-project-btn"]',
    '[data-testid="sidebar-add-project-btn"]',
    'button:has-text("+ Workflow")',
    '[data-testid="settings-danger-delete-workspace"]',
  ],
  projadmin: [
    '[data-testid="settings-danger-delete-workspace"]',
    'a[href="/admin/standalone"]',
  ],
  wsadmin: [
    'a[href="/admin/standalone"]',
    'button:has-text("Standalone Server Backup")',
  ],
  admin: [],
};

/**
 * Asserts exact DOM count() === 0 for disallowed controls for a given role.
 */
export async function assertDisallowedControls(
  page: Page,
  role: AuditRole,
): Promise<DisallowedControlViolation[]> {
  const selectors = ROLE_DISALLOWED_SELECTORS[role];
  const violations: DisallowedControlViolation[] = [];

  for (const sel of selectors) {
    const count = await page.locator(sel).count();
    if (count > 0) {
      violations.push({ role, selector: sel, count });
    }
  }

  return violations;
}

export interface TouchTargetViolation {
  selector: string;
  text: string;
  width: number;
  height: number;
  minAllowed: number;
}

/**
 * Scans page for interactive elements failing minimum touch target bounds (>=44x44px).
 */
export async function scanMobileTouchTargets(
  page: Page,
  options: {
    minTargetSize?: number;
    ignoreSelectors?: string[];
    containerSelector?: string;
  } = {}
): Promise<TouchTargetViolation[]> {
  const minTarget = options.minTargetSize ?? 44;
  const ignore = options.ignoreSelectors ?? [];
  const container = options.containerSelector ?? 'body';

  return page.evaluate(
    ({ minSize, ignoreList, containerSel }) => {
      const violations: {
        selector: string;
        text: string;
        width: number;
        height: number;
        minAllowed: number;
      }[] = [];

      const root = document.querySelector(containerSel) || document.body;
      const interactiveElements = root.querySelectorAll<HTMLElement>(
        'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="menuitem"], [role="tab"]'
      );

      interactiveElements.forEach((el, idx) => {
        const style = window.getComputedStyle(el);
        if (
          style.display === 'none' ||
          style.visibility === 'hidden' ||
          style.opacity === '0' ||
          el.hasAttribute('hidden') ||
          el.getAttribute('aria-hidden') === 'true'
        ) {
          return;
        }

        for (const ig of ignoreList) {
          if (el.matches(ig)) return;
        }

        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;

        if (el.tagName === 'A' && el.parentElement && window.getComputedStyle(el.parentElement).display === 'block') {
          if (style.display === 'inline') return;
        }

        if (rect.width < minSize - 1 || rect.height < minSize - 1) {
          const text = (el.textContent || el.getAttribute('aria-label') || el.tagName).trim().slice(0, 30);
          const selector = el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}:nth-of-type(${String(idx + 1)})`;
          violations.push({
            selector,
            text,
            width: Math.round(rect.width * 10) / 10,
            height: Math.round(rect.height * 10) / 10,
            minAllowed: minSize,
          });
        }
      });

      return violations;
    },
    { minSize: minTarget, ignoreList: ignore, containerSel: container }
  );
}

export interface InputFontSizeViolation {
  selector: string;
  tagName: string;
  fontSize: number;
  requiredSize: number;
}

/**
 * Scans page for text inputs/selects/textareas rendering with font-size < 16px.
 */
export async function scanMobileInputFontSizes(
  page: Page,
  options: {
    minFontSize?: number;
    containerSelector?: string;
  } = {}
): Promise<InputFontSizeViolation[]> {
  const minFont = options.minFontSize ?? 16;
  const container = options.containerSelector ?? 'body';

  return page.evaluate(
    ({ minSize, containerSel }) => {
      const violations: {
        selector: string;
        tagName: string;
        fontSize: number;
        requiredSize: number;
      }[] = [];

      const root = document.querySelector(containerSel) || document.body;
      const inputs = root.querySelectorAll<HTMLElement>(
        'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="color"]), select, textarea'
      );

      inputs.forEach((el, idx) => {
        const style = window.getComputedStyle(el);
        if (
          style.display === 'none' ||
          style.visibility === 'hidden' ||
          style.opacity === '0' ||
          el.hasAttribute('hidden')
        ) {
          return;
        }

        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return;

        const size = parseFloat(style.fontSize) || 0;
        if (size < minSize - 0.1) {
          const selector = el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}:nth-of-type(${String(idx + 1)})`;
          violations.push({
            selector,
            tagName: el.tagName.toLowerCase(),
            fontSize: Math.round(size * 10) / 10,
            requiredSize: minSize,
          });
        }
      });

      return violations;
    },
    { minSize: minFont, containerSel: container }
  );
}

export interface TopbarOcclusionViolation {
  selector: string;
  topbarBottom: number;
  elementTop: number;
  occludedPixels: number;
}

/**
 * Scans for sticky or drawer containers occluded by the fixed Topbar.
 */
export async function scanTopbarOcclusion(
  page: Page,
  topbarSelector = '.kb-topbar',
  targetSelectors: string[] = ['.docs-tree-pane', '.docs-rail-pane', '.docs-sheet-backdrop']
): Promise<TopbarOcclusionViolation[]> {
  return page.evaluate(
    ({ topbarSel, targets }) => {
      const violations: {
        selector: string;
        topbarBottom: number;
        elementTop: number;
        occludedPixels: number;
      }[] = [];

      const topbar = document.querySelector<HTMLElement>(topbarSel);
      if (!topbar) return violations;

      const topbarRect = topbar.getBoundingClientRect();
      const topbarBottom = topbarRect.bottom;

      for (const sel of targets) {
        const el = document.querySelector<HTMLElement>(sel);
        if (!el) continue;

        const style = window.getComputedStyle(el);
        if (
          style.display === 'none' ||
          style.visibility === 'hidden' ||
          style.opacity === '0' ||
          style.position !== 'fixed'
        ) {
          continue;
        }

        const rect = el.getBoundingClientRect();
        const topbarZ = parseInt(window.getComputedStyle(topbar).zIndex, 10) || 0;
        const elZ = parseInt(style.zIndex, 10) || 0;

        if (rect.top < topbarBottom && topbarZ > elZ) {
          violations.push({
            selector: sel,
            topbarBottom: Math.round(topbarBottom),
            elementTop: Math.round(rect.top),
            occludedPixels: Math.round(topbarBottom - rect.top),
          });
        }
      }

      return violations;
    },
    { topbarSel: topbarSelector, targets: targetSelectors }
  );
}
