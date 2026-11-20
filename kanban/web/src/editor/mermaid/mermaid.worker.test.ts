/**
 * Unit Tests for Dedicated Mermaid Web Worker (KB-P3-47, S5.3).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DEFAULT_LIGHT_THEME_TOKENS, DEFAULT_DARK_THEME_TOKENS } from './mermaidTheme';
import type { inlineThemeColors as InlineThemeColorsFn } from './mermaid.worker';

describe('mermaid.worker', () => {
  let postedMessages: unknown[] = [];
  let workerHandler: ((e: MessageEvent) => void) | null = null;
  let inlineThemeColors: typeof InlineThemeColorsFn;

  beforeEach(async () => {
    postedMessages = [];
    if (!workerHandler) {
      vi.stubGlobal('self', {
        postMessage: vi.fn((msg: unknown) => {
          postedMessages.push(msg);
        }),
        onmessage: null,
      });

      const mod = await import('./mermaid.worker');
      inlineThemeColors = mod.inlineThemeColors;
      workerHandler = (self as unknown as { onmessage: (e: MessageEvent) => void }).onmessage;
    } else {
      (self as unknown as { postMessage: (msg: unknown) => void }).postMessage = vi.fn((msg: unknown) => {
        postedMessages.push(msg);
      });
    }
  });

  it('handles valid diagram request and posts SVG success response', () => {
    expect(workerHandler).toBeTypeOf('function');

    workerHandler?.({
      data: {
        requestId: 'req_1',
        source: 'flowchart TD\n  A --> B',
        theme: DEFAULT_LIGHT_THEME_TOKENS,
      },
    } as MessageEvent);

    expect(postedMessages).toHaveLength(1);
    const response = postedMessages[0] as {
      requestId: string;
      ok: boolean;
      svg?: string;
    };
    expect(response.requestId).toBe('req_1');
    expect(response.ok).toBe(true);
    expect(response.svg).toContain('<svg');
    expect(response.svg).not.toContain('<style');
    expect(response.svg).not.toMatch(/(?:^|\s)style=/);
    expect(response.svg).toContain('font-family="Inter, system-ui, sans-serif"');
  });

  it('handles firewall rejection in worker and posts failure response', () => {
    workerHandler?.({
      data: {
        requestId: 'req_2',
        source: 'gantt\n  title Unsupported',
        theme: DEFAULT_LIGHT_THEME_TOKENS,
      },
    } as MessageEvent);

    expect(postedMessages).toHaveLength(1);
    const response = postedMessages[0] as {
      requestId: string;
      ok: boolean;
      code?: string;
    };
    expect(response.requestId).toBe('req_2');
    expect(response.ok).toBe(false);
    expect(response.code).toBe('UNSUPPORTED_DIAGRAM_TYPE');
  });

  it('handles beautiful-mermaid syntax/render errors gracefully', () => {
    workerHandler?.({
      data: {
        requestId: 'req_3',
        source: 'flowchart INVALID_DIRECTION\n  A --> B',
        theme: DEFAULT_LIGHT_THEME_TOKENS,
      },
    } as MessageEvent);

    expect(postedMessages).toHaveLength(1);
    const response = postedMessages[0] as {
      requestId: string;
      ok: boolean;
      code?: string;
    };
    expect(response.requestId).toBe('req_3');
    expect(response.ok).toBe(false);
    expect(response.code).toBe('RENDER_ERROR');
  });

  it('renders with dark theme tokens and applies dark surface colors', () => {
    workerHandler?.({
      data: {
        requestId: 'req_4',
        source: 'flowchart TD\n  DarkA --> DarkB',
        theme: DEFAULT_DARK_THEME_TOKENS,
      },
    } as MessageEvent);

    expect(postedMessages).toHaveLength(1);
    const response = postedMessages[0] as {
      requestId: string;
      ok: boolean;
      svg?: string;
    };
    expect(response.requestId).toBe('req_4');
    expect(response.ok).toBe(true);
    expect(response.svg).toContain('fill="#16181d"');
  });

  it('covers inlineThemeColors presentation conversion branches and edge cases', () => {
    // 1. Single-quoted style with presentation props + non-presentation prop + malformed declarations
    const svgWithMixedStyle = `<svg xmlns="http://www.w3.org/2000/svg" font-family="CustomFont">
      <g style='font-size: 14px; display: none; ; invalidColon; :emptyProp; fill: #123456'>
        <rect width="10" height="10" fill="#000" style="fill: #fff; opacity: 0.8" />
        <text style="cursor: pointer;">No presentation</text>
      </g>
    </svg>`;

    const inlined = inlineThemeColors(svgWithMixedStyle, DEFAULT_LIGHT_THEME_TOKENS);
    expect(inlined).not.toContain('<style');
    expect(inlined).not.toMatch(/(?:^|\s)style=/);
    expect(inlined).toContain('font-size="14px"');
    expect(inlined).toContain('opacity="0.8"');
    // fill="#000" was already on rect, so attrRegex prevents duplicate attribute
    expect(inlined).toContain('fill="#000"');
    expect(inlined).toContain('data-mermaid-bg="true"');
  });
});
