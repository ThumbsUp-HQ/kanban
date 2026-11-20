/**
 * Dedicated Mermaid Web Worker (KB-P3-47, S5.3).
 * Offloads beautiful-mermaid pure TypeScript SVG rendering from the main thread.
 * Defense-in-depth firewall validation ensures oversized or hostile inputs are
 * rejected before layout execution.
 */

import './elkWorkerShim';
import { renderMermaidSVG } from 'beautiful-mermaid';
import { sanitizeAndValidateMermaid } from './mermaidFirewall';
import type { MermaidThemeTokens } from './mermaidTheme';

export interface MermaidWorkerRequest {
  readonly requestId: string;
  readonly source: string;
  readonly theme: MermaidThemeTokens;
}

export interface MermaidWorkerSuccessResponse {
  readonly requestId: string;
  readonly ok: true;
  readonly svg: string;
}

export interface MermaidWorkerFailureResponse {
  readonly requestId: string;
  readonly ok: false;
  readonly code: string;
  readonly message: string;
}

export type MermaidWorkerResponse =
  | MermaidWorkerSuccessResponse
  | MermaidWorkerFailureResponse;

export function inlineThemeColors(rawSvg: string, theme: MermaidThemeTokens): string {
  const isDark = theme.bgSurface.toLowerCase() === '#16181d';
  const nodeFill = isDark ? '#1f242d' : '#f8fafc';
  const nodeStroke = theme.borderStrong;
  const line = theme.borderStrong;
  const arrow = theme.accentPrimary;
  const text = theme.fgPrimary;
  const textSec = isDark ? '#9ca3af' : '#4b5563';
  const groupHdr = isDark ? '#1e222b' : '#f1f5f9';
  const innerStroke = theme.borderStrong;

  const replacements: Record<string, string> = {
    'var(--bg)': theme.bgSurface,
    'var(--fg)': theme.fgPrimary,
    'var(--surface)': nodeFill,
    'var(--border)': nodeStroke,
    'var(--line)': line,
    'var(--accent)': arrow,
    'var(--muted)': textSec,
    'var(--_arrow)': arrow,
    'var(--_line)': line,
    'var(--_text)': text,
    'var(--_text-sec)': textSec,
    'var(--_text-muted)': textSec,
    'var(--_text-faint)': textSec,
    'var(--_node-fill)': nodeFill,
    'var(--_node-stroke)': nodeStroke,
    'var(--_group-hdr)': groupHdr,
    'var(--_group-fill)': theme.bgSurface,
    'var(--_inner-stroke)': innerStroke,
    'var(--_key-badge)': innerStroke,
  };

  let inlined = rawSvg;
  for (const [v, c] of Object.entries(replacements)) {
    inlined = inlined.replaceAll(v, c);
  }

  // 1. Convert presentation properties from style="..." attributes into pure SVG XML attributes
  const presentationProps = [
    'font-family',
    'font-size',
    'font-weight',
    'fill',
    'stroke',
    'stroke-width',
    'stroke-dasharray',
    'opacity',
    'text-anchor',
    'dominant-baseline',
    'letter-spacing',
  ];

  inlined = inlined.replace(/<([a-zA-Z0-9:-]+)(\s[^>]*)>/g, (fullTag, tagName: string, attrs: string) => {
    const styleMatch = /(?:^|\s)style=(?:"([^"]*)"|'([^']*)')/.exec(attrs);
    if (!styleMatch) {
      return fullTag;
    }
    const styleContent = styleMatch[1] ?? styleMatch[2] ?? '';
    const decls = styleContent.split(';');
    const newAttrs: string[] = [];
    for (const decl of decls) {
      const colonIdx = decl.indexOf(':');
      if (colonIdx === -1) continue;
      const prop = decl.slice(0, colonIdx).trim().toLowerCase();
      const val = decl.slice(colonIdx + 1).trim();
      if (!prop || !val) continue;
      if (presentationProps.includes(prop)) {
        const attrRegex = new RegExp(`(?:^|\\s)${prop}=`, 'i');
        if (!attrRegex.test(attrs)) {
          newAttrs.push(`${prop}="${val}"`);
        }
      }
    }
    const cleanAttrs = attrs.replace(/(?:^|\s)style=(?:"[^"]*"|'[^']*')\s*/g, ' ').replace(/\s{2,}/g, ' ');
    const added = newAttrs.length > 0 ? ' ' + newAttrs.join(' ') : '';
    return `<${tagName}${cleanAttrs}${added}>`;
  });

  // 2. Strip all <style> blocks and any remaining inline style="..." attributes
  // to eliminate Chromium CSP style-src 'self' console violation errors on main thread.
  inlined = inlined.replace(/<style[\s\S]*?<\/style>/gi, '');
  inlined = inlined.replace(/(?:^|\s)style=(?:"[^"]*"|'[^']*')\s*/g, ' ').replace(/\s{2,}/g, ' ');

  // 3. Ensure crisp Inter/system-ui font-family on root <svg> and on <text> elements
  if (!/(?:^|\s)font-family=/i.test(inlined)) {
    inlined = inlined.replace(/(<svg\b[^>]*)/i, `$1 font-family="Inter, system-ui, sans-serif"`);
  }
  inlined = inlined.replace(/<text\b((?:(?!font-family=)[^>])*)>/gi, '<text font-family="Inter, system-ui, sans-serif"$1>');

  return inlined.replace(
    /(<svg\b[^>]*>)/i,
    `$1\n  <rect width="100%" height="100%" fill="${theme.bgSurface}" rx="6" ry="6" data-mermaid-bg="true"/>`,
  );
}

self.onmessage = (event: MessageEvent<MermaidWorkerRequest>): void => {
  const { requestId, source, theme } = event.data;

  // 1. Defense-in-depth firewall validation in worker thread
  const firewall = sanitizeAndValidateMermaid(source);
  if (!firewall.ok) {
    const failure: MermaidWorkerFailureResponse = {
      requestId,
      ok: false,
      code: firewall.code,
      message: firewall.message,
    };
    self.postMessage(failure);
    return;
  }

  // 2. Render SVG via beautiful-mermaid with theme tokens
  try {
    const rawSvg = renderMermaidSVG(firewall.sanitizedSource, {
      bg: theme.bgSurface,
      fg: theme.fgPrimary,
      border: theme.borderStrong,
      accent: theme.accentPrimary,
      line: theme.borderStrong,
      surface: theme.bgSurface,
      transparent: false,
    });

    const svg = inlineThemeColors(rawSvg, theme);

    const success: MermaidWorkerSuccessResponse = {
      requestId,
      ok: true,
      svg,
    };
    self.postMessage(success);
  } catch (err: unknown) {
    const failure: MermaidWorkerFailureResponse = {
      requestId,
      ok: false,
      code: 'RENDER_ERROR',
      message: `Mermaid rendering failed: ${String(err)}`,
    };
    self.postMessage(failure);
  }
};
