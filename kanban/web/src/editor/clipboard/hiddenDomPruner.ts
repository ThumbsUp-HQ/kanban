/**
 * Hidden-DOM Paste-Jacking Pruner & Invisible Unicode Stripper (KB-P3-46, S5.2, S3.5).
 * Executes Step A client-side sanitization BEFORE stripping inline style attributes.
 */

import { ensureTrustedTypesPolicies } from './trustedTypes';

export const MAX_PASTE_HTML_BYTES = 2_097_152; // 2 MiB

/**
 * Invisible prompt-injection Unicode characters across all text outputs:
 * - U+200B..U+200F (Zero-width spaces, directional marks)
 * - U+202A..U+202E (Bidirectional overrides)
 * - U+2060..U+206F (Word joiners and invisible operators)
 * - U+FEFF (BOM / Zero-width no-break space)
 * - U+E0000..U+E007F (Unicode Tag block)
 */
export const INVISIBLE_UNICODE_REGEX =
  /[\u200B-\u200F\u202A-\u202E\u2060-\u206F\uFEFF]|[\u{E0000}-\u{E007F}]/gu;

/**
 * Strips invisible Unicode characters from text.
 */
export function stripInvisibleUnicode(text: string): string {
  return text.replace(INVISIBLE_UNICODE_REGEX, '');
}

export interface PruneResult {
  prunedHtml: string;
  prunedHiddenNodes: number;
}

interface RgbColor {
  r: number;
  g: number;
  b: number;
}

const NAMED_COLORS: Record<string, RgbColor> = {
  white: { r: 255, g: 255, b: 255 },
  black: { r: 0, g: 0, b: 0 },
  red: { r: 255, g: 0, b: 0 },
  green: { r: 0, g: 128, b: 0 },
  blue: { r: 0, g: 0, b: 255 },
  yellow: { r: 255, g: 255, b: 0 },
  gray: { r: 128, g: 128, b: 128 },
  grey: { r: 128, g: 128, b: 128 },
};

export function parseColor(colorStr: string | null | undefined): RgbColor | null {
  if (!colorStr) {
    return null;
  }
  const str = colorStr.trim().toLowerCase();
  if (str === 'transparent' || str === 'inherit' || str === 'initial' || str === 'unset') {
    return null;
  }

  if (NAMED_COLORS[str]) {
    return NAMED_COLORS[str];
  }

  // Hex: #rgb, #rgba, #rrggbb, #rrggbbaa
  if (str.startsWith('#')) {
    const hex = str.slice(1);
    if (!/^[0-9a-f]+$/i.test(hex)) {
      return null;
    }
    if (hex.length === 3 || hex.length === 4) {
      const r = parseInt(hex.slice(0, 1).repeat(2), 16);
      const g = parseInt(hex.slice(1, 2).repeat(2), 16);
      const b = parseInt(hex.slice(2, 3).repeat(2), 16);
      return { r, g, b };
    }
    if (hex.length === 6 || hex.length === 8) {
      const r = parseInt(hex.slice(0, 2), 16);
      const g = parseInt(hex.slice(2, 4), 16);
      const b = parseInt(hex.slice(4, 6), 16);
      return { r, g, b };
    }
    return null;
  }

  // rgb(...) or rgba(...)
  const rgbMatch = /^rgba?\(\s*([0-9.]+)\s*[, ]\s*([0-9.]+)\s*[, ]\s*([0-9.]+)/.exec(str);
  if (rgbMatch) {
    const r = Math.min(255, Math.max(0, Math.round(Number(rgbMatch[1]))));
    const g = Math.min(255, Math.max(0, Math.round(Number(rgbMatch[2]))));
    const b = Math.min(255, Math.max(0, Math.round(Number(rgbMatch[3]))));
    return { r, g, b };
  }

  return null;
}

function sRgbToLinear(c: number): number {
  const norm = c / 255;
  return norm <= 0.04045 ? norm / 12.92 : Math.pow((norm + 0.055) / 1.055, 2.4);
}

function relativeLuminance(rgb: RgbColor): number {
  return 0.2126 * sRgbToLinear(rgb.r) + 0.7152 * sRgbToLinear(rgb.g) + 0.0722 * sRgbToLinear(rgb.b);
}

export function computeContrastRatio(c1: RgbColor, c2: RgbColor): number {
  const l1 = relativeLuminance(c1);
  const l2 = relativeLuminance(c2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

const NON_CONTENT_TAGS = new Set([
  'SCRIPT',
  'STYLE',
  'TEMPLATE',
  'NOSCRIPT',
  'IFRAME',
  'OBJECT',
  'EMBED',
  'META',
]);

function parseCssLength(val: string | null | undefined): number | null {
  if (!val) {
    return null;
  }
  const match = /^(-?[0-9.]+)(px|pt|em|rem|%)?$/.exec(val.trim());
  if (match) {
    /* v8 ignore next */
    return parseFloat(match[1] ?? '0');
  }
  return null;
}

function isZeroBoxClipping(style: string): boolean {
  const widthZero = /width\s*:\s*0([a-z%]+)?\b/i.test(style) || /max-width\s*:\s*0([a-z%]+)?\b/i.test(style);
  const heightZero = /height\s*:\s*0([a-z%]+)?\b/i.test(style) || /max-height\s*:\s*0([a-z%]+)?\b/i.test(style);
  const overflowHidden = /overflow\s*:\s*hidden/i.test(style);

  if (widthZero && (heightZero || overflowHidden)) {
    return true;
  }
  if (/clip\s*:\s*rect\(\s*0/i.test(style)) {
    return true;
  }
  if (/clip-path\s*:\s*inset\(\s*100%/i.test(style)) {
    return true;
  }
  return false;
}

function isOffScreen(style: string): boolean {
  const isPos = /position\s*:\s*(absolute|fixed)/i.test(style);
  if (isPos) {
    const leftMatch = /\bleft\s*:\s*(-?[0-9.]+)/i.exec(style);
    if (leftMatch && Number(leftMatch[1]) <= -1000) {
      return true;
    }
    const topMatch = /\btop\s*:\s*(-?[0-9.]+)/i.exec(style);
    if (topMatch && Number(topMatch[1]) <= -1000) {
      return true;
    }
  }
  const indentMatch = /\btext-indent\s*:\s*(-?[0-9.]+)/i.exec(style);
  if (indentMatch && Number(indentMatch[1]) <= -1000) {
    return true;
  }
  return false;
}

function extractStyleProperty(style: string, prop: string): string | null {
  const regex = new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`, 'i');
  const match = regex.exec(style);
  return match?.[1] ? match[1].trim() : null;
}

function shouldPruneElement(el: HTMLElement, ancestorBackground: RgbColor | null): boolean {
  // 1. Non-content tags
  if (NON_CONTENT_TAGS.has(el.tagName)) {
    return true;
  }

  // 2. HTML attribute hidden or aria-hidden="true"
  if (el.hasAttribute('hidden') || el.getAttribute('aria-hidden') === 'true') {
    return true;
  }

  const rawStyle = el.getAttribute('style') ?? '';

  // 3. Inline style display:none, visibility:hidden/collapse
  if (/display\s*:\s*none/i.test(rawStyle)) {
    return true;
  }
  if (/visibility\s*:\s*(hidden|collapse)/i.test(rawStyle)) {
    return true;
  }

  // 4. opacity <= 0.02
  const opacityVal = extractStyleProperty(rawStyle, 'opacity');
  if (opacityVal !== null) {
    const parsed = parseFloat(opacityVal);
    if (!isNaN(parsed) && parsed <= 0.02) {
      return true;
    }
  }

  // 5. font-size: 0 or < 1px
  const fontSizeVal = extractStyleProperty(rawStyle, 'font-size');
  if (fontSizeVal !== null) {
    const parsed = parseCssLength(fontSizeVal);
    if (parsed !== null && parsed < 1) {
      return true;
    }
  }

  // 6. Zero-box clipping
  if (isZeroBoxClipping(rawStyle)) {
    return true;
  }

  // 7. Off-screen positioning
  if (isOffScreen(rawStyle)) {
    return true;
  }

  // 8. Near-zero contrast (< 1.15)
  const colorVal = extractStyleProperty(rawStyle, 'color');
  const bgVal = extractStyleProperty(rawStyle, 'background-color') ?? extractStyleProperty(rawStyle, 'background');

  const textColor = parseColor(colorVal);
  const bgColor = parseColor(bgVal) ?? ancestorBackground;

  if (textColor && bgColor) {
    const contrast = computeContrastRatio(textColor, bgColor);
    if (contrast < 1.15) {
      return true;
    }
  }

  return false;
}

/**
 * Step A - Client Hidden-DOM Paste-Jacking Pruner.
 * Walks the parsed DOM fragment and deletes hidden subtrees before DOMPurify strips style.
 */
export function pruneHiddenDom(rawHtml: string): PruneResult {
  if (!rawHtml || rawHtml.trim() === '') {
    return { prunedHtml: '', prunedHiddenNodes: 0 };
  }

  // Enforce 2 MiB cap
  let safeHtml = rawHtml;
  const byteLen = new TextEncoder().encode(safeHtml).length;
  if (byteLen > MAX_PASTE_HTML_BYTES) {
    // Truncate to safe byte limit
    const bytes = new TextEncoder().encode(safeHtml).slice(0, MAX_PASTE_HTML_BYTES);
    safeHtml = new TextDecoder('utf-8', { fatal: false }).decode(bytes);
  }

  const { sanitizerPolicy } = ensureTrustedTypesPolicies();
  /* v8 ignore next */
  const policyInput = sanitizerPolicy ? sanitizerPolicy.createHTML(safeHtml) : safeHtml;

  const parser = new DOMParser();
  const doc = parser.parseFromString(policyInput, 'text/html');

  let prunedHiddenNodes = 0;

  function traverse(node: Node, currentBg: RgbColor | null): void {
    const children = Array.from(node.childNodes);
    for (const child of children) {
      if (child.nodeType === Node.COMMENT_NODE) {
        // Strip HTML comment nodes unconditionally
        child.remove();
        continue;
      }

      if (child.nodeType === Node.ELEMENT_NODE) {
        const el = child as HTMLElement;
        const rawStyle = el.getAttribute('style') ?? '';
        const ownBg = parseColor(
          extractStyleProperty(rawStyle, 'background-color') ??
          extractStyleProperty(rawStyle, 'background'),
        );
        const effectiveBg = ownBg ?? currentBg;

        if (shouldPruneElement(el, effectiveBg)) {
          el.remove();
          prunedHiddenNodes++;
          continue;
        }

        traverse(el, effectiveBg);
      }
    }
  }

  traverse(doc.body, null);

  // Strip invisible Unicode from the resulting HTML
  const serialized = doc.body.innerHTML;
  const prunedHtml = stripInvisibleUnicode(serialized);

  return {
    prunedHtml,
    prunedHiddenNodes,
  };
}
