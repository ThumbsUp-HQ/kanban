import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import type { Page, TestInfo } from '@playwright/test';

export interface StyleProbeConfig {
  selector: string;
  props: string[];
}

/**
 * Validates style probe name and QA_TICKET_ID.
 */
export function validateProbeParams(name: string, qaTicketId?: string): void {
  if (!/^[a-z0-9-]+$/.test(name)) {
    throw new Error(`Invalid probe name: "${name}". Must match ^[a-z0-9-]+$`);
  }
  if (qaTicketId !== undefined && qaTicketId !== '') {
    if (!/^[A-Z][A-Z0-9]+-[0-9A-Za-z-]+$/.test(qaTicketId)) {
      throw new Error(`Invalid QA_TICKET_ID: "${qaTicketId}". Must match ^[A-Z][A-Z0-9]+-[0-9A-Za-z-]+$`);
    }
  }
}

/**
 * Resolves destination JSON file path for computed styles.
 */
export function resolveStyleProbePath(projectName: string, qaTicketId?: string): string {
  if (qaTicketId) {
    return `docs/qa/${qaTicketId}/computed-styles-${projectName}.json`;
  }
  return `test-results/computed-styles-${projectName}.json`;
}

/**
 * Merges probed style records into an existing JSON object with sorted keys.
 */
export function mergeStyleData(
  existing: Record<string, unknown>,
  probeName: string,
  data: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...existing, [probeName]: data };
  const sorted: Record<string, unknown> = {};
  for (const key of Object.keys(merged).sort()) {
    sorted[key] = merged[key];
  }
  return sorted;
}

/**
 * Atomically writes JSON content via temp file and rename.
 */
export function writeJsonAtomic(filePath: string, data: unknown): void {
  mkdirSync(dirname(filePath), { recursive: true });
  const tempPath = `${filePath}.tmp.${String(Date.now())}-${Math.random().toString(36).slice(2)}`;
  writeFileSync(tempPath, JSON.stringify(data, null, 2) + '\n', 'utf-8');
  renameSync(tempPath, filePath);
}

/**
 * Probes getComputedStyle values and bounding client rect for configured selectors,
 * merging the resulting measurements into a versioned JSON artifact.
 */
export async function probeStyles(
  page: Page,
  testInfo: TestInfo,
  opts: { name: string; probes: StyleProbeConfig[] },
): Promise<Record<string, Record<string, string>>> {
  const qaTicketId = process.env.QA_TICKET_ID;
  validateProbeParams(opts.name, qaTicketId);

  const probedResults: Record<string, Record<string, string>> = {};

  for (const probe of opts.probes) {
    const values = await page.evaluate(
      ({ selector, props }) => {
        const el = document.querySelector(selector);
        if (!el) {
          throw new Error(`probeStyles element not found: "${selector}"`);
        }
        const computed = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        const measurements: Record<string, string> = {
          width: `${String(rect.width)}px`,
          height: `${String(rect.height)}px`,
        };
        for (const p of props) {
          measurements[p] = computed.getPropertyValue(p);
        }
        return measurements;
      },
      { selector: probe.selector, props: probe.props },
    );
    probedResults[probe.selector] = values;
  }

  const relPath = resolveStyleProbePath(testInfo.project.name, qaTicketId);
  const repoRoot = resolve(import.meta.dirname, '../../../..');
  const fullPath = resolve(repoRoot, relPath);

  let existingData: Record<string, unknown> = {};
  if (existsSync(fullPath)) {
    try {
      existingData = JSON.parse(readFileSync(fullPath, 'utf-8')) as Record<string, unknown>;
    } catch {
      existingData = {};
    }
  }

  const merged = mergeStyleData(existingData, opts.name, probedResults);
  writeJsonAtomic(fullPath, merged);

  return probedResults;
}
