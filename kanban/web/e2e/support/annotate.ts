import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import type { Page, TestInfo } from '@playwright/test';

export interface Annotation {
  selector: string;
  label: string;
  note?: string | undefined;
  /** Shifts the numbered badge (px) so it can sit outside the annotated box and not occlude text. */
  badgeOffset?: { dx: number; dy: number } | undefined;
  /** 'right' places the badge just outside the right edge of the box. Default 'left' (top-left corner). */
  badgeAnchor?: 'left' | 'right' | undefined;
}

/**
 * Validates screenshot name and ticket ID format to avoid directory traversal.
 */
export function validateScreenshotParams(
  name: string,
  qaTicketId?: string,
): { validName: string; validTicketId?: string | undefined } {
  if (!/^[0-9]{2}-[a-z0-9-]+$/.test(name)) {
    throw new Error(`Invalid screenshot name: "${name}". Must match ^[0-9]{2}-[a-z0-9-]+$`);
  }
  if (qaTicketId !== undefined && qaTicketId !== '') {
    if (!/^[A-Z][A-Z0-9]+-[0-9A-Za-z-]+$/.test(qaTicketId)) {
      throw new Error(`Invalid QA_TICKET_ID: "${qaTicketId}". Must match ^[A-Z][A-Z0-9]+-[0-9A-Za-z-]+$`);
    }
  }
  return { validName: name, validTicketId: qaTicketId };
}

/**
 * Resolves output relative or absolute path for the screenshot.
 */
export function resolveOutputPath(name: string, projectName: string, qaTicketId?: string): string {
  validateScreenshotParams(name, qaTicketId);
  if (qaTicketId) {
    return `docs/qa/${qaTicketId}/screenshots/${name}-${projectName}.png`;
  }
  return `test-results/screenshots/${name}-${projectName}.png`;
}

/**
 * Pure helper calculating badge position clamped inside [0, viewport - 22].
 */
export function computeBadgePosition(
  boxX: number,
  boxY: number,
  viewportWidth: number,
  viewportHeight: number,
): { x: number; y: number } {
  const x = Math.max(0, Math.min(boxX, viewportWidth - 22));
  const y = Math.max(0, Math.min(boxY, viewportHeight - 22));
  return { x, y };
}

/**
 * Pure helper computing legend grid layout based on annotation count.
 */
export function computeLegendLayout(
  annotationCount: number,
  viewportWidth: number,
): { columns: number; columnWidth: number } {
  const columns = annotationCount > 8 ? 2 : 1;
  const padding = 24; // 12px left + 12px right
  const gap = columns > 1 ? 12 : 0;
  const availableWidth = viewportWidth - padding - gap;
  const columnWidth = Math.floor(availableWidth / columns);
  return { columns, columnWidth };
}

/**
 * Captures an annotated screenshot with visual overlays and legend.
 * Uses DOM and CSSOM property mutation (no style tags or style attributes)
 * to comply strictly with Content-Security-Policy style-src 'self'.
 */
export async function annotatedScreenshot(
  page: Page,
  testInfo: TestInfo,
  opts: { name: string; annotations: Annotation[]; fullPage?: boolean },
): Promise<string> {
  const qaTicketId = process.env.QA_TICKET_ID;
  validateScreenshotParams(opts.name, qaTicketId);

  const relPath = resolveOutputPath(opts.name, testInfo.project.name, qaTicketId);
  const repoRoot = resolve(import.meta.dirname, '../../../..');
  const fullPath = resolve(repoRoot, relPath);

  mkdirSync(dirname(fullPath), { recursive: true });

  const viewport = page.viewportSize() ?? { width: 1280, height: 720 };
  const evaluatedBoxes: {
    x: number;
    y: number;
    width: number;
    height: number;
    badgeX: number;
    badgeY: number;
    index: number;
  }[] = [];

  for (const [i, ann] of opts.annotations.entries()) {
    const locator = page.locator(ann.selector).first();
    const count = await locator.count();
    if (count === 0) {
      throw new Error(`Annotation element not found: selector "${ann.selector}"`);
    }

    let box: { x: number; y: number; width: number; height: number } | null = null;
    if (typeof locator.evaluate === 'function') {
      try {
        box = await locator.evaluate((el) => {
          const r = el.getBoundingClientRect();
          return { x: r.x, y: r.y, width: r.width, height: r.height };
        });
      } catch {
        box = null;
      }
    }
    if (!box && typeof locator.boundingBox === 'function') {
      box = await locator.boundingBox();
    }

    if (!box || box.width === 0 || box.height === 0) {
      throw new Error(`Annotation element has zero dimensions: selector "${ann.selector}"`);
    }

    const badgePos = computeBadgePosition(
      (ann.badgeAnchor === 'right' ? box.x + box.width + 4 : box.x) + (ann.badgeOffset?.dx ?? 0),
      box.y + (ann.badgeOffset?.dy ?? 0),
      viewport.width,
      viewport.height,
    );
    evaluatedBoxes.push({
      x: box.x,
      y: box.y,
      width: box.width,
      height: box.height,
      badgeX: badgePos.x,
      badgeY: badgePos.y,
      index: i + 1,
    });
  }

  const legendLayout = computeLegendLayout(opts.annotations.length, viewport.width);
  const ticketLabel = qaTicketId ?? 'LOCAL';
  const headerText = `${ticketLabel} | ${testInfo.project.name} | ${String(viewport.width)}x${String(viewport.height)}`;

  const overlayId = `playwright-annotated-overlay-${String(Date.now())}`;

  await page.evaluate(
    ({ overlayId, evaluatedBoxes, annotations, headerText, legendLayout }) => {
      const container = document.createElement('div');
      container.id = overlayId;
      container.style.setProperty('position', 'fixed');
      container.style.setProperty('top', '0');
      container.style.setProperty('left', '0');
      container.style.setProperty('width', '100%');
      container.style.setProperty('height', '100%');
      container.style.setProperty('pointer-events', 'none');
      container.style.setProperty('z-index', '2147483647');

      for (const b of evaluatedBoxes) {
        // Outline box
        const outline = document.createElement('div');
        outline.style.setProperty('position', 'absolute');
        outline.style.setProperty('left', `${String(b.x)}px`);
        outline.style.setProperty('top', `${String(b.y)}px`);
        outline.style.setProperty('width', `${String(b.width)}px`);
        outline.style.setProperty('height', `${String(b.height)}px`);
        outline.style.setProperty('border', '2px solid #e11d48');
        outline.style.setProperty('box-sizing', 'border-box');
        container.appendChild(outline);

        // Circular badge
        const badge = document.createElement('div');
        badge.style.setProperty('position', 'absolute');
        badge.style.setProperty('left', `${String(b.badgeX)}px`);
        badge.style.setProperty('top', `${String(b.badgeY)}px`);
        badge.style.setProperty('width', '22px');
        badge.style.setProperty('height', '22px');
        badge.style.setProperty('border-radius', '50%');
        badge.style.setProperty('background-color', '#e11d48');
        badge.style.setProperty('color', '#ffffff');
        badge.style.setProperty('font-size', '12px');
        badge.style.setProperty('font-weight', '700');
        badge.style.setProperty('font-family', 'sans-serif');
        badge.style.setProperty('display', 'flex');
        badge.style.setProperty('align-items', 'center');
        badge.style.setProperty('justify-content', 'center');
        badge.textContent = String(b.index);
        container.appendChild(badge);
      }

      // Legend strip fixed at the bottom
      const legend = document.createElement('div');
      legend.style.setProperty('position', 'absolute');
      legend.style.setProperty('bottom', '0');
      legend.style.setProperty('left', '0');
      legend.style.setProperty('width', '100%');
      legend.style.setProperty('background-color', '#111827');
      legend.style.setProperty('color', '#ffffff');
      legend.style.setProperty('font-family', 'sans-serif');
      legend.style.setProperty('font-size', '13px');
      legend.style.setProperty('padding', '8px 12px');
      legend.style.setProperty('box-sizing', 'border-box');

      const titleLine = document.createElement('div');
      titleLine.style.setProperty('font-weight', '600');
      titleLine.style.setProperty('margin-bottom', '4px');
      titleLine.textContent = headerText;
      legend.appendChild(titleLine);

      const itemsContainer = document.createElement('div');
      itemsContainer.style.setProperty('display', 'grid');
      itemsContainer.style.setProperty(
        'grid-template-columns',
        legendLayout.columns > 1 ? '1fr 1fr' : '1fr',
      );
      itemsContainer.style.setProperty('gap', '4px 12px');

      for (const [i, item] of annotations.entries()) {
        const row = document.createElement('div');
        const noteSuffix = item.note ? ` - ${item.note}` : '';
        row.textContent = `${String(i + 1)}. ${item.label}${noteSuffix}`;
        itemsContainer.appendChild(row);
      }
      legend.appendChild(itemsContainer);
      container.appendChild(legend);

      document.body.appendChild(container);
    },
    { overlayId, evaluatedBoxes, annotations: opts.annotations, headerText, legendLayout },
  );

  await page.screenshot({
    path: fullPath,
    animations: 'disabled',
    caret: 'hide',
    fullPage: opts.fullPage ?? false,
  });

  await page.evaluate((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.remove();
    }
  }, overlayId);

  await testInfo.attach(opts.name, {
    path: fullPath,
    contentType: 'image/png',
  });

  return fullPath;
}
