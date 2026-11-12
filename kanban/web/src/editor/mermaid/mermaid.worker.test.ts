/**
 * Unit Tests for Dedicated Mermaid Web Worker (KB-P3-47, S5.3).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DEFAULT_LIGHT_THEME_TOKENS, DEFAULT_DARK_THEME_TOKENS } from './mermaidTheme';

describe('mermaid.worker', () => {
  let postedMessages: unknown[] = [];
  let workerHandler: ((e: MessageEvent) => void) | null = null;

  beforeEach(async () => {
    postedMessages = [];
    if (!workerHandler) {
      vi.stubGlobal('self', {
        postMessage: vi.fn((msg: unknown) => {
          postedMessages.push(msg);
        }),
        onmessage: null,
      });

      await import('./mermaid.worker');
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
});
