/**
 * Safe SVG Blob Sanitizer & Acyclic Local <use> DAG Guard (KB-P3-48, S5.4).
 * Dual-layer client sanitization: DOMPurify SVG profile + local <use> DAG
 * cycle/depth/expansion guard emitting sandboxed blob: URLs for <img>.
 */

import DOMPurifyFactory from 'dompurify';

export const MAX_CLIENT_SVG_BYTES = 2097152; // 2 MiB
export const MAX_SVG_USE_DEPTH = 4;
export const MAX_SVG_EXPANDED_NODES = 500;

export const ALLOWED_SVG_TAGS: readonly string[] = Object.freeze([
  'svg',
  'g',
  'path',
  'rect',
  'circle',
  'ellipse',
  'line',
  'polyline',
  'polygon',
  'text',
  'tspan',
  'defs',
  'linearGradient',
  'radialGradient',
  'stop',
  'clipPath',
  'marker',
  'use',
  'title',
  'desc',
]);

export const FORBIDDEN_SVG_TAGS: readonly string[] = Object.freeze([
  'script',
  'foreignObject',
  'iframe',
  'image',
  'style',
  'animate',
  'animateTransform',
  'animateMotion',
  'set',
  'feImage',
  'filter',
]);

export type SafeSvgErrorCode =
  | 'SVG_TOO_LARGE'
  | 'SVG_EMPTY'
  | 'SVG_PARSE_ERROR'
  | 'SVG_USE_CYCLE'
  | 'SVG_USE_MAX_DEPTH'
  | 'SVG_EXPANSION_LIMIT_EXCEEDED';

export interface SafeSvgSuccess {
  readonly ok: true;
  readonly blobUrl: string;
  readonly cleanSvg: string;
  readonly revoke: () => void;
}

export interface SafeSvgFailure {
  readonly ok: false;
  readonly error: SafeSvgErrorCode;
  readonly message: string;
}

export type SafeSvgResult = SafeSvgSuccess | SafeSvgFailure;

interface TrustedHTMLInstance {
  readonly __brand?: unique symbol;
}

interface TrustedTypePolicy {
  createHTML(input: string): TrustedHTMLInstance;
}

interface TrustedTypePolicyFactory {
  createPolicy(
    name: string,
    rules: { createHTML: (input: string) => string },
  ): TrustedTypePolicy;
}

interface WindowWithTrustedTypes extends Window {
  trustedTypes?: TrustedTypePolicyFactory | undefined;
}

let cachedSanitizerPolicy: TrustedTypePolicy | null = null;
let policyResolutionAttempted = false;

export function _resetPolicyForTesting(): void {
  cachedSanitizerPolicy = null;
  policyResolutionAttempted = false;
}

function getSanitizerPolicy(): TrustedTypePolicy | null {
  if (policyResolutionAttempted) {
    return cachedSanitizerPolicy;
  }
  policyResolutionAttempted = true;
  if (typeof window !== 'undefined') {
    const win = window as WindowWithTrustedTypes;
    if (win.trustedTypes && typeof win.trustedTypes.createPolicy === 'function') {
      try {
        cachedSanitizerPolicy = win.trustedTypes.createPolicy('kanban-sanitizer', {
          createHTML: (html: string): string => html,
        });
      } catch {
        cachedSanitizerPolicy = null;
      }
    }
  }
  return cachedSanitizerPolicy;
}

function toTrustedHtml(markup: string): string {
  const policy = getSanitizerPolicy();
  if (policy) {
    return policy.createHTML(markup) as unknown as string;
  }
  return markup;
}

const DOMPurify = DOMPurifyFactory(window);

function countSubtreeNodes(el: Element): number {
  let count = 1;
  for (const child of Array.from(el.children)) {
    count += countSubtreeNodes(child);
  }
  return count;
}

function safeCreateObjectURL(blob: Blob): string {
  if (typeof URL.createObjectURL === 'function') {
    return URL.createObjectURL(blob);
  }
  return `blob:http://localhost/${Math.random().toString(36).substring(2)}`;
}

function safeRevokeObjectURL(url: string): void {
  if (typeof URL.revokeObjectURL === 'function') {
    URL.revokeObjectURL(url);
  }
}

/**
 * Sanitizes an untrusted raw SVG string and produces a sandboxed blob URL.
 */
export function createSafeSvgBlobUrl(rawSvg: string): SafeSvgResult {
  if (!rawSvg || rawSvg.trim().length === 0) {
    return {
      ok: false,
      error: 'SVG_EMPTY',
      message: 'SVG content is empty.',
    };
  }

  // 1. Enforce 2 MiB byte limit
  const utf8Bytes = new TextEncoder().encode(rawSvg).length;
  if (utf8Bytes > MAX_CLIENT_SVG_BYTES) {
    return {
      ok: false,
      error: 'SVG_TOO_LARGE',
      message: `SVG size (${String(utf8Bytes)} bytes) exceeds maximum allowed ${String(MAX_CLIENT_SVG_BYTES)} bytes.`,
    };
  }

  // 2. Validate raw XML syntax with DOMParser before sanitization
  let xmlToValidate = rawSvg;
  if (xmlToValidate.includes('xlink:') && !xmlToValidate.includes('xmlns:xlink')) {
    xmlToValidate = xmlToValidate.replace(/<svg\b/i, '<svg xmlns:xlink="http://www.w3.org/1999/xlink"');
  }

  const parser = new DOMParser();
  const rawDoc = parser.parseFromString(toTrustedHtml(xmlToValidate), 'image/svg+xml');
  const rawParserError = rawDoc.querySelector('parsererror');
  if (rawParserError) {
    return {
      ok: false,
      error: 'SVG_PARSE_ERROR',
      message: rawParserError.textContent || 'Failed to parse SVG XML.',
    };
  }

  // 3. DOMPurify sanitize under strict SVG profile, retaining local <use>
  const sanitizedMarkup = DOMPurify.sanitize(rawSvg, {
    USE_PROFILES: { svg: true, svgFilters: false },
    ALLOWED_TAGS: ALLOWED_SVG_TAGS as unknown as string[],
    FORBID_TAGS: FORBIDDEN_SVG_TAGS as unknown as string[],
    FORBID_ATTR: ['style'],
    ADD_TAGS: ['use'],
    ADD_ATTR: ['href', 'xlink:href'],
    RETURN_DOM_FRAGMENT: false,
    RETURN_TRUSTED_TYPE: false,
  });

  if (!sanitizedMarkup || sanitizedMarkup.trim().length === 0) {
    return {
      ok: false,
      error: 'SVG_EMPTY',
      message: 'Sanitized SVG content is empty.',
    };
  }

  // 4. XML Parsing with DOMParser
  let markupToParse = sanitizedMarkup;
  if (markupToParse.includes('xlink:') && !markupToParse.includes('xmlns:xlink')) {
    markupToParse = markupToParse.replace(/<svg\b/i, '<svg xmlns:xlink="http://www.w3.org/1999/xlink"');
  }
  const doc = parser.parseFromString(toTrustedHtml(markupToParse), 'image/svg+xml');

  const parserError = doc.querySelector('parsererror');
  if (parserError) {
    return {
      ok: false,
      error: 'SVG_PARSE_ERROR',
      message: parserError.textContent || 'Failed to parse sanitized SVG XML.',
    };
  }

  const svgEl = doc.querySelector('svg');
  if (!svgEl) {
    return {
      ok: false,
      error: 'SVG_EMPTY',
      message: 'No root <svg> element found.',
    };
  }

  // 4. Scrub attributes: on* handlers and foreign/non-fragment hrefs
  const allElements = Array.from(doc.querySelectorAll('*'));
  for (const el of allElements) {
    // Strip on* event attributes
    const attrNames = el.getAttributeNames();
    for (const name of attrNames) {
      if (name.toLowerCase().startsWith('on')) {
        el.removeAttribute(name);
      }
    }

    // Strip href or xlink:href if not a purely local fragment identifier
    const href = el.getAttribute('href');
    if (href !== null) {
      if (!/^#[A-Za-z0-9_.:-]+$/.test(href)) {
        el.removeAttribute('href');
      }
    }
    const xlinkHref = el.getAttribute('xlink:href');
    if (xlinkHref !== null) {
      if (!/^#[A-Za-z0-9_.:-]+$/.test(xlinkHref)) {
        el.removeAttribute('xlink:href');
      }
    }
  }

  // 5. Build ID map for <use> element reference inspection
  const idMap = new Map<string, Element>();
  for (const el of allElements) {
    const id = el.getAttribute('id');
    if (id) {
      idMap.set(id, el);
    }
  }

  // 6. Inspect <use> reference graph for cycles, max depth, and node expansion
  const useElements = Array.from(doc.querySelectorAll('use'));

  function evaluateUseTarget(
    targetId: string,
    ancestors: Set<string>,
    depth: number,
  ):
    | { depth: number; expandedNodes: number }
    | { error: SafeSvgErrorCode; message: string } {
    if (ancestors.has(targetId)) {
      return {
        error: 'SVG_USE_CYCLE',
        message: `Cyclic <use> reference detected: #${targetId}`,
      };
    }

    if (depth > MAX_SVG_USE_DEPTH) {
      return {
        error: 'SVG_USE_MAX_DEPTH',
        message: `Maximum <use> chain depth (${String(MAX_SVG_USE_DEPTH)}) exceeded.`,
      };
    }

    const targetEl = idMap.get(targetId);
    if (!targetEl) {
      return { depth, expandedNodes: 0 };
    }

    const nextAncestors = new Set(ancestors);
    nextAncestors.add(targetId);

    let maxDepth = depth;
    let targetNodes = countSubtreeNodes(targetEl);

    const childUses = Array.from(targetEl.querySelectorAll('use'));
    for (const childUse of childUses) {
      const ref = (childUse.getAttribute('href') ?? childUse.getAttribute('xlink:href') ?? '').replace(/^#/, '');
      if (ref) {
        const result = evaluateUseTarget(ref, nextAncestors, depth + 1);
        if ('error' in result) {
          return result;
        }
        maxDepth = Math.max(maxDepth, result.depth);
        targetNodes += result.expandedNodes;
      }
    }

    return { depth: maxDepth, expandedNodes: targetNodes };
  }

  let totalExpandedNodes = 0;

  for (const useEl of useElements) {
    const ref = (useEl.getAttribute('href') ?? useEl.getAttribute('xlink:href') ?? '').replace(/^#/, '');
    if (!ref) {
      continue;
    }

    const evaluation = evaluateUseTarget(ref, new Set(), 1);
    if ('error' in evaluation) {
      return {
        ok: false,
        error: evaluation.error,
        message: evaluation.message,
      };
    }

    totalExpandedNodes += evaluation.expandedNodes;
    if (totalExpandedNodes > MAX_SVG_EXPANDED_NODES) {
      return {
        ok: false,
        error: 'SVG_EXPANSION_LIMIT_EXCEEDED',
        message: `Expanded <use> node count (${String(totalExpandedNodes)}) exceeds limit of ${String(MAX_SVG_EXPANDED_NODES)}.`,
      };
    }
  }

  // 7. Enforce xmlns attribute on <svg>
  if (!svgEl.getAttribute('xmlns')) {
    svgEl.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  }

  // 8. Serialize and create blob URL
  const serializer = new XMLSerializer();
  const cleanSvg = serializer.serializeToString(svgEl);
  const blob = new Blob([cleanSvg], { type: 'image/svg+xml;charset=utf-8' });
  const blobUrl = safeCreateObjectURL(blob);

  return {
    ok: true,
    blobUrl,
    cleanSvg,
    revoke: () => {
      safeRevokeObjectURL(blobUrl);
    },
  };
}
