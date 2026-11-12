import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  validateProbeParams,
  resolveStyleProbePath,
  mergeStyleData,
  writeJsonAtomic,
  probeStyles,
} from './styleProbe';
import type { Page, TestInfo } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

describe('styleProbe support module', () => {
  describe('validateProbeParams', () => {
    it('accepts valid alphanumeric names and QA ticket IDs', () => {
      expect(() => {
        validateProbeParams('app-smoke', 'KANBA-27');
      }).not.toThrow();
      expect(() => {
        validateProbeParams('smoke', undefined);
      }).not.toThrow();
      expect(() => {
        validateProbeParams('test-1', '');
      }).not.toThrow();
    });

    it('rejects invalid names or invalid QA ticket IDs', () => {
      expect(() => {
        validateProbeParams('AppSmoke');
      }).toThrow('Invalid probe name');
      expect(() => {
        validateProbeParams('smoke test');
      }).toThrow('Invalid probe name');
      expect(() => {
        validateProbeParams('smoke', 'invalid_id');
      }).toThrow('Invalid QA_TICKET_ID');
    });
  });

  describe('resolveStyleProbePath', () => {
    it('resolves qa directory when QA_TICKET_ID is set', () => {
      expect(resolveStyleProbePath('desktop', 'KANBA-27')).toBe(
        'docs/qa/KANBA-27/computed-styles-desktop.json',
      );
    });

    it('resolves test-results when QA_TICKET_ID is unset', () => {
      expect(resolveStyleProbePath('tablet', undefined)).toBe(
        'test-results/computed-styles-tablet.json',
      );
    });
  });

  describe('mergeStyleData', () => {
    it('merges new probe data and sorts top-level keys alphabetically', () => {
      const existing = { zebra: { color: 'black' }, apple: { color: 'red' } };
      const merged = mergeStyleData(existing, 'banana', { color: 'yellow' });
      expect(Object.keys(merged)).toEqual(['apple', 'banana', 'zebra']);
      expect(merged.banana).toEqual({ color: 'yellow' });
    });
  });

  describe('writeJsonAtomic', () => {
    const testOutPath = resolve(
      import.meta.dirname,
      '../../../../test-results/style-probe-test/output.json',
    );

    beforeEach(() => {
      if (existsSync(dirname(testOutPath))) {
        rmSync(dirname(testOutPath), { recursive: true, force: true });
      }
    });

    afterEach(() => {
      if (existsSync(dirname(testOutPath))) {
        rmSync(dirname(testOutPath), { recursive: true, force: true });
      }
    });

    it('writes valid JSON with atomic temp file rename', () => {
      writeJsonAtomic(testOutPath, { key: 'value' });
      expect(existsSync(testOutPath)).toBe(true);
      const content = JSON.parse(readFileSync(testOutPath, 'utf-8')) as { key: string };
      expect(content.key).toBe('value');
    });
  });

  describe('probeStyles', () => {
    const originalEnv = process.env.QA_TICKET_ID;
    const testArtifactPath = resolve(
      import.meta.dirname,
      '../../../../docs/qa/KANBA-TEST-PROBE/computed-styles-desktop.json',
    );

    beforeEach(() => {
      process.env.QA_TICKET_ID = 'KANBA-TEST-PROBE';
      if (existsSync(dirname(testArtifactPath))) {
        rmSync(dirname(testArtifactPath), { recursive: true, force: true });
      }
    });

    afterEach(() => {
      if (originalEnv === undefined) {
        delete process.env.QA_TICKET_ID;
      } else {
        process.env.QA_TICKET_ID = originalEnv;
      }
      if (existsSync(dirname(testArtifactPath))) {
        rmSync(dirname(testArtifactPath), { recursive: true, force: true });
      }
    });

    it('extracts computed styles and writes new JSON artifact when file does not exist', async () => {
      const fakePage = {
        evaluate: vi.fn().mockImplementation((fn: (arg: unknown) => unknown, arg: unknown) => {
          // Simulate browser evaluate callback
          const div = document.createElement('div');
          div.id = 'app-root';
          div.style.setProperty('font-family', 'sans-serif');
          document.body.appendChild(div);
          try {
            return Promise.resolve(fn(arg));
          } finally {
            div.remove();
          }
        }),
      } as unknown as Page;

      const fakeTestInfo = {
        project: { name: 'desktop' },
      } as unknown as TestInfo;

      const result = await probeStyles(fakePage, fakeTestInfo, {
        name: 'app-root',
        probes: [{ selector: '#app-root', props: ['font-family'] }],
      });

      expect(result['#app-root']).toBeDefined();
      expect(existsSync(testArtifactPath)).toBe(true);
      const saved = JSON.parse(readFileSync(testArtifactPath, 'utf-8')) as Record<
        string,
        unknown
      >;
      expect(saved['app-root']).toBeDefined();
    });

    it('merges with existing JSON when artifact already exists', async () => {
      mkdirSync(dirname(testArtifactPath), { recursive: true });
      writeFileSync(
        testArtifactPath,
        JSON.stringify({ 'prior-entry': { width: '10px' } }, null, 2),
      );

      const fakePage = {
        evaluate: vi.fn().mockResolvedValue({ width: '20px', height: '30px' }),
      } as unknown as Page;

      const fakeTestInfo = {
        project: { name: 'desktop' },
      } as unknown as TestInfo;

      await probeStyles(fakePage, fakeTestInfo, {
        name: 'second-entry',
        probes: [{ selector: '#header', props: ['width'] }],
      });

      const saved = JSON.parse(readFileSync(testArtifactPath, 'utf-8')) as Record<
        string,
        unknown
      >;
      expect(saved['prior-entry']).toBeDefined();
      expect(saved['second-entry']).toBeDefined();
    });

    it('falls back to empty object when existing artifact has corrupt JSON', async () => {
      mkdirSync(dirname(testArtifactPath), { recursive: true });
      writeFileSync(testArtifactPath, 'INVALID_CORRUPT_JSON{{{');

      const fakePage = {
        evaluate: vi.fn().mockResolvedValue({ width: '20px' }),
      } as unknown as Page;

      const fakeTestInfo = {
        project: { name: 'desktop' },
      } as unknown as TestInfo;

      await probeStyles(fakePage, fakeTestInfo, {
        name: 'recovered-entry',
        probes: [{ selector: '#header', props: ['width'] }],
      });

      const saved = JSON.parse(readFileSync(testArtifactPath, 'utf-8')) as Record<
        string,
        unknown
      >;
      expect(saved['recovered-entry']).toBeDefined();
    });

    it('throws when probe element is not found in document', async () => {
      const fakePage = {
        evaluate: vi.fn().mockImplementation((fn: (arg: unknown) => unknown, arg: unknown) => {
          return Promise.resolve(fn(arg));
        }),
      } as unknown as Page;

      const fakeTestInfo = {
        project: { name: 'desktop' },
      } as unknown as TestInfo;

      await expect(
        probeStyles(fakePage, fakeTestInfo, {
          name: 'missing-probe',
          probes: [{ selector: '#does-not-exist', props: ['display'] }],
        }),
      ).rejects.toThrow('probeStyles element not found: "#does-not-exist"');
    });
  });
});
