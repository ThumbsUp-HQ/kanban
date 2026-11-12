import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  validateScreenshotParams,
  resolveOutputPath,
  computeBadgePosition,
  computeLegendLayout,
  annotatedScreenshot,
} from './annotate';
import {
  validateProbeParams,
  resolveStyleProbePath,
  mergeStyleData,
  writeJsonAtomic,
  probeStyles,
} from './styleProbe';
import { mkdtempSync, rmSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import type { Page, TestInfo, Locator } from '@playwright/test';

describe('annotate and styleProbe support modules', () => {
  describe('resolveOutputPath', () => {
    it('returns docs/qa/KANBA-77/screenshots/03-board-desktop.png for QA_TICKET_ID=KANBA-77, name 03-board, project desktop', () => {
      const result = resolveOutputPath('03-board', 'desktop', 'KANBA-77');
      expect(result).toBe('docs/qa/KANBA-77/screenshots/03-board-desktop.png');
    });

    it('returns test-results/screenshots/ path when QA_TICKET_ID is unset', () => {
      const result = resolveOutputPath('01-smoke', 'mobile', undefined);
      expect(result).toBe('test-results/screenshots/01-smoke-mobile.png');
    });
  });

  describe('validateScreenshotParams security validations', () => {
    it('throws on path traversal in QA_TICKET_ID', () => {
      expect(() => validateScreenshotParams('01-smoke', '../../etc')).toThrow('Invalid QA_TICKET_ID');
    });

    it('throws on path traversal in name', () => {
      expect(() => validateScreenshotParams('../x', 'KANBA-77')).toThrow('Invalid screenshot name');
    });

    it('throws on names without 2-digit prefix', () => {
      expect(() => validateScreenshotParams('1-x', 'KANBA-77')).toThrow('Invalid screenshot name');
      expect(() => validateScreenshotParams('board', 'KANBA-77')).toThrow('Invalid screenshot name');
    });
  });

  describe('computeBadgePosition boundary clamping', () => {
    it('clamps badge position into [0, viewport - 22] for negative coordinates', () => {
      const pos = computeBadgePosition(-50, -20, 1440, 900);
      expect(pos.x).toBe(0);
      expect(pos.y).toBe(0);
    });

    it('clamps badge position when coordinates exceed viewport boundary', () => {
      const pos = computeBadgePosition(1500, 1000, 1440, 900);
      expect(pos.x).toBe(1440 - 22);
      expect(pos.y).toBe(900 - 22);
    });
  });

  describe('computeLegendLayout wrapping', () => {
    it('wraps more than 8 annotations into 2 columns without exceeding viewport width 390', () => {
      const layout = computeLegendLayout(9, 390);
      expect(layout.columns).toBe(2);
      expect(layout.columnWidth * layout.columns).toBeLessThanOrEqual(390);
      expect(layout.columnWidth).toBeGreaterThan(100);
    });

    it('uses single column for <= 8 annotations', () => {
      const layout = computeLegendLayout(5, 390);
      expect(layout.columns).toBe(1);
    });
  });

  describe('annotatedScreenshot execution', () => {
    it('successfully processes annotations and captures screenshot with overlay', async () => {
      const fakeLocator = {
        first: () => fakeLocator,
        count: vi.fn().mockResolvedValue(1),
        evaluate: vi.fn().mockImplementation((fn: (el: unknown) => unknown) => {
          return Promise.resolve(
            fn({
              getBoundingClientRect: () => ({ x: 100, y: 100, width: 200, height: 50 }),
            }),
          );
        }),
        boundingBox: vi.fn().mockResolvedValue({ x: 100, y: 100, width: 200, height: 50 }),
      } as unknown as Locator;

      const fakePage = {
        viewportSize: vi.fn().mockReturnValue({ width: 1440, height: 900 }),
        locator: vi.fn().mockReturnValue(fakeLocator),
        evaluate: vi.fn().mockImplementation((fn: (arg?: unknown) => unknown, arg?: unknown) => {
          return Promise.resolve(typeof fn === 'function' ? fn(arg) : fn);
        }),
        screenshot: vi.fn().mockImplementation((opts: { path: string }) => {
          writeFileSync(opts.path, Buffer.from('fake-png-bytes'));
          return Promise.resolve();
        }),
      } as unknown as Page;

      const attachMock = vi.fn().mockResolvedValue(undefined);
      const fakeTestInfo = {
        project: { name: 'desktop' },
        attach: attachMock,
      } as unknown as TestInfo;

      const oldEnv = process.env.QA_TICKET_ID;
      process.env.QA_TICKET_ID = 'KANBA-UNIT';
      try {
        const outPath = await annotatedScreenshot(fakePage, fakeTestInfo, {
          name: '01-smoke',
          annotations: [
            { selector: '[data-testid="app-root"]', label: 'App Root', note: 'test note' },
            { selector: '[data-testid="app-root"]', label: 'Item 2' },
          ],
          fullPage: true,
        });
        expect(outPath).toContain('docs/qa/KANBA-UNIT/screenshots/01-smoke-desktop.png');
        expect(attachMock).toHaveBeenCalled();
      } finally {
        if (oldEnv === undefined) {
          delete process.env.QA_TICKET_ID;
        } else {
          process.env.QA_TICKET_ID = oldEnv;
        }
        rmSync(resolve(import.meta.dirname, '../../../../docs/qa/KANBA-UNIT'), {
          recursive: true,
          force: true,
        });
      }

      // Test with QA_TICKET_ID unset
      const oldEnv2 = process.env.QA_TICKET_ID;
      delete process.env.QA_TICKET_ID;
      try {
        const outPathLocal = await annotatedScreenshot(fakePage, fakeTestInfo, {
          name: '02-local',
          annotations: [{ selector: '[data-testid="app-root"]', label: 'Local' }],
        });
        expect(outPathLocal).toContain('test-results/screenshots/02-local-desktop.png');

        // Test with null viewportSize fallback
        const nullViewportPage = {
          ...fakePage,
          viewportSize: vi.fn().mockReturnValue(null),
        } as unknown as Page;
        const outNull = await annotatedScreenshot(nullViewportPage, fakeTestInfo, {
          name: '03-nullvp',
          annotations: [{ selector: '[data-testid="app-root"]', label: 'NullVP' }],
        });
        expect(outNull).toContain('test-results/screenshots/03-nullvp-desktop.png');
      } finally {
        if (oldEnv2 !== undefined) {
          process.env.QA_TICKET_ID = oldEnv2;
        }
      }
    });

    it('supports 9 or more annotations triggering multi-column legend and handles pre-removed overlay', async () => {
      const fakeLocator = {
        first: () => fakeLocator,
        count: vi.fn().mockResolvedValue(1),
        boundingBox: vi.fn().mockResolvedValue({ x: 10, y: 20, width: 100, height: 40 }),
      } as unknown as Locator;

      const fakePage = {
        viewportSize: vi.fn().mockReturnValue({ width: 1440, height: 900 }),
        locator: vi.fn().mockReturnValue(fakeLocator),
        evaluate: vi.fn().mockImplementation((fn: (arg?: unknown) => unknown, arg?: unknown) => {
          return Promise.resolve(typeof fn === 'function' ? fn(arg) : fn);
        }),
        screenshot: vi.fn().mockImplementation((opts: { path: string }) => {
          // Pre-remove overlay from DOM so cleanup evaluate hits `if (el)` false branch
          document.querySelectorAll('[id^="qa-annotation-overlay-"]').forEach((el) => {
            el.remove();
          });
          writeFileSync(opts.path, Buffer.from('fake-png-bytes'));
          return Promise.resolve();
        }),
      } as unknown as Page;

      const fakeTestInfo = {
        project: { name: 'desktop' },
        attach: vi.fn().mockResolvedValue(undefined),
      } as unknown as TestInfo;

      const annotations = Array.from({ length: 9 }, (_, i) => ({
        selector: '[data-testid="app-root"]',
        label: `Item ${String(i + 1)}`,
        note: i % 2 === 0 ? `Note ${String(i + 1)}` : undefined,
      }));

      const outPath = await annotatedScreenshot(fakePage, fakeTestInfo, {
        name: '04-multicol',
        annotations,
      });
      expect(outPath).toContain('test-results/screenshots/04-multicol-desktop.png');
    });

    it('throws if annotation element is not found or has zero dimensions', async () => {
      const missingLocator = {
        first: () => missingLocator,
        count: vi.fn().mockResolvedValue(0),
      } as unknown as Locator;

      const fakePage = {
        viewportSize: vi.fn().mockReturnValue({ width: 1440, height: 900 }),
        locator: vi.fn().mockReturnValue(missingLocator),
      } as unknown as Page;

      const fakeTestInfo = { project: { name: 'desktop' } } as unknown as TestInfo;

      await expect(
        annotatedScreenshot(fakePage, fakeTestInfo, {
          name: '01-missing',
          annotations: [{ selector: '.missing', label: 'Missing' }],
        }),
      ).rejects.toThrow('Annotation element not found');

      const zeroBoxLocator = {
        first: () => zeroBoxLocator,
        count: vi.fn().mockResolvedValue(1),
        boundingBox: vi.fn().mockResolvedValue({ x: 0, y: 0, width: 0, height: 0 }),
      } as unknown as Locator;

      const fakePage2 = {
        viewportSize: vi.fn().mockReturnValue({ width: 1440, height: 900 }),
        locator: vi.fn().mockReturnValue(zeroBoxLocator),
      } as unknown as Page;

      await expect(
        annotatedScreenshot(fakePage2, fakeTestInfo, {
          name: '01-zero',
          annotations: [{ selector: '.zero', label: 'Zero' }],
        }),
      ).rejects.toThrow('zero dimensions');
    });
  });

  describe('styleProbe merge and atomic write', () => {
    let tmpDir: string;

    beforeEach(() => {
      tmpDir = mkdtempSync(join(tmpdir(), 'style-probe-test-'));
    });

    afterEach(() => {
      if (existsSync(tmpDir)) {
        rmSync(tmpDir, { recursive: true, force: true });
      }
    });

    it('throws on invalid probe names or ticket ids', () => {
      expect(() => {
        validateProbeParams('../secret');
      }).toThrow('Invalid probe name');
      expect(() => {
        validateProbeParams('valid-name', '../../etc');
      }).toThrow('Invalid QA_TICKET_ID');
    });

    it('resolves correct style probe path', () => {
      expect(resolveStyleProbePath('desktop', 'KANBA-27')).toBe(
        'docs/qa/KANBA-27/computed-styles-desktop.json',
      );
      expect(resolveStyleProbePath('mobile', undefined)).toBe(
        'test-results/computed-styles-mobile.json',
      );
    });

    it('merges two probe calls with different names into one sorted JSON file', () => {
      const initial: Record<string, unknown> = {};
      const step1 = mergeStyleData(initial, 'header', { color: 'rgb(0, 0, 0)' });
      const step2 = mergeStyleData(step1, 'app-root', { margin: '0px auto' });

      // Verify keys are sorted alphabetically: 'app-root' before 'header'
      expect(Object.keys(step2)).toEqual(['app-root', 'header']);
    });

    it('writes JSON atomically via temp file and rename', () => {
      const targetPath = join(tmpDir, 'computed-styles.json');
      const testData = { 'app-root': { width: '1280px' } };

      writeJsonAtomic(targetPath, testData);

      expect(existsSync(targetPath)).toBe(true);
      const readBack = JSON.parse(readFileSync(targetPath, 'utf-8')) as Record<string, unknown>;
      expect(readBack).toEqual(testData);
    });

    it('executes probeStyles against page and writes to file', async () => {
      document.body.innerHTML = '<main class="app-main" style="width: 1280px; height: 600px;"><h1>Title</h1></main>';

      const fakePage = {
        evaluate: vi.fn().mockImplementation((fn: (arg: unknown) => unknown, arg: unknown) => {
          return Promise.resolve(fn(arg));
        }),
      } as unknown as Page;

      const fakeTestInfo = {
        project: { name: 'tablet' },
      } as unknown as TestInfo;

      const oldEnv = process.env.QA_TICKET_ID;
      process.env.QA_TICKET_ID = 'KANBA-UNIT';
      try {
        const res = await probeStyles(fakePage, fakeTestInfo, {
          name: 'app-root',
          probes: [{ selector: '.app-main', props: ['width'] }],
        });
        expect(res['.app-main']).toBeDefined();

        // Second call to test merge into existing file and invalid json recovery
        const targetPath = join(
          resolve(import.meta.dirname, '../../../..'),
          resolveStyleProbePath('tablet', 'KANBA-UNIT'),
        );
        writeFileSync(targetPath, 'corrupted-json{');
        await probeStyles(fakePage, fakeTestInfo, {
          name: 'header',
          probes: [{ selector: '.app-main', props: ['height'] }],
        });
      } finally {
        if (oldEnv === undefined) {
          delete process.env.QA_TICKET_ID;
        } else {
          process.env.QA_TICKET_ID = oldEnv;
        }
        rmSync(resolve(import.meta.dirname, '../../../../docs/qa/KANBA-UNIT'), {
          recursive: true,
          force: true,
        });
      }

      // Test element not found error
      await expect(
        probeStyles(fakePage, fakeTestInfo, {
          name: 'missing',
          probes: [{ selector: '.non-existent-selector', props: ['width'] }],
        }),
      ).rejects.toThrow('probeStyles element not found');
    });
  });
});
