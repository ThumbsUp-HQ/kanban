/**
 * Unit Tests for MermaidBlockView and MermaidNodeView (KB-P3-47, S5.3).
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { renderMermaidSVG } from 'beautiful-mermaid';
import type { Node as ProsemirrorNode } from 'prosemirror-model';
import type { EditorView, NodeView } from 'prosemirror-view';
import {
  MermaidBlockView,
  MermaidNodeView,
  registerMermaidExtension,
  formatHumanReason,
} from './MermaidBlockView';
import { MermaidWorkerClient } from './mermaidClient';
import type { MermaidWorkerRequest } from './mermaid.worker';
import { getRegisteredExtensions, clearEditorExtensions } from '../editorSurfaceFactory';
import * as safeSvgModule from '../media/safeSvg';

class FakeWorker implements Worker {
  public postMessage = vi.fn();
  public terminate = vi.fn();
  public onmessage: ((event: MessageEvent) => void) | null = null;
  public onerror: ((event: ErrorEvent) => void) | null = null;
  public onmessageerror: ((event: MessageEvent) => void) | null = null;
  public addEventListener = vi.fn();
  public removeEventListener = vi.fn();
  public dispatchEvent = vi.fn(() => true);
}

function createRealWorkerClient(): MermaidWorkerClient {
  return new MermaidWorkerClient({
    workerFactory: () => {
      const worker = new FakeWorker();
      worker.postMessage = vi.fn((req: MermaidWorkerRequest) => {
        try {
          const svg = renderMermaidSVG(req.source, {
            bg: req.theme.bgSurface,
            fg: req.theme.fgPrimary,
          });
          setTimeout(() => {
            worker.onmessage?.({
              data: { requestId: req.requestId, ok: true, svg },
            } as MessageEvent);
          }, 0);
        } catch (err: unknown) {
          worker.onmessage?.({
            data: {
              requestId: req.requestId,
              ok: false,
              code: 'RENDER_ERROR',
              message: err instanceof Error ? err.message : String(err),
            },
          } as MessageEvent);
        }
      });
      return worker;
    },
  });
}

const realCreateObjectURL = URL.createObjectURL.bind(URL);
const realRevokeObjectURL = URL.revokeObjectURL.bind(URL);

describe('MermaidBlockView', () => {
  let createdBlobUrls: string[] = [];
  let revokedBlobUrls: string[] = [];

  beforeEach(() => {
    createdBlobUrls = [];
    revokedBlobUrls = [];

    let blobCounter = 0;
    URL.createObjectURL = vi.fn(() => {
      blobCounter += 1;
      const url = `blob:http://localhost/mock-blob-${String(blobCounter)}`;
      createdBlobUrls.push(url);
      return url;
    });

    URL.revokeObjectURL = vi.fn((url: string) => {
      revokedBlobUrls.push(url);
    });
  });

  afterEach(() => {
    URL.createObjectURL = realCreateObjectURL;
    URL.revokeObjectURL = realRevokeObjectURL;
    clearEditorExtensions();
    vi.clearAllMocks();
  });

  it('renders all 6 supported diagram types strictly as <img src="blob:..."> with zero inline <svg>', async () => {
    const diagrams = [
      'flowchart TD\n  A[Start] --> B[End]',
      'sequenceDiagram\n  Alice->>Bob: Hello',
      'stateDiagram-v2\n  [*] --> State1',
      'classDiagram\n  class Vehicle',
      'erDiagram\n  USER ||--o{ POST : writes',
      'xychart-beta\n  x-axis [1, 2]\n  y-axis "Y" 0 --> 10\n  bar [1, 2]',
    ];

    const client = createRealWorkerClient();

    for (const source of diagrams) {
      const { container, unmount } = render(
        <MermaidBlockView source={source} client={client} />,
      );

      await waitFor(
        () => {
          const img = container.querySelector('img');
          expect(img).not.toBeNull();
          expect(img?.getAttribute('src')).toMatch(/^blob:/);
        },
        { timeout: 3000 },
      );

      // Strict requirement: zero inline <svg> in document DOM
      expect(container.querySelector('svg')).toBeNull();

      unmount();
    }
  });

  it('syncs with dark theme, re-renders with dark tokens, and revokes prior blob URL', async () => {
    const client = createRealWorkerClient();
    const source = 'graph TD\n  Light --> Dark';

    const { container, unmount } = render(
      <MermaidBlockView source={source} client={client} />,
    );

    await waitFor(() => {
      expect(container.querySelector('img')).not.toBeNull();
    });

    const initialBlob = container.querySelector('img')?.getAttribute('src');
    expect(initialBlob).toBeTruthy();

    // Flip document theme to dark
    act(() => {
      document.documentElement.setAttribute('data-theme', 'dark');
    });

    await waitFor(() => {
      const nextBlob = container.querySelector('img')?.getAttribute('src');
      expect(nextBlob).not.toBeNull();
      // Prior blob should have been revoked
      if (initialBlob) {
        expect(revokedBlobUrls).toContain(initialBlob);
      }
    });

    // Reset document attribute
    document.documentElement.removeAttribute('data-theme');
    unmount();
  });

  it('handles 1,500ms watchdog timeout and displays calm fallback banner with source', async () => {
    const hangingWorker = new FakeWorker();
    const client = new MermaidWorkerClient({
      workerFactory: () => hangingWorker,
      watchdogMs: 1500,
    });

    vi.useFakeTimers();

    const { container } = render(
      <MermaidBlockView source="graph TD\n  Hang --> Forever" client={client} />,
    );

    // Start executeRender
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(hangingWorker.postMessage).toHaveBeenCalled();

    // Advance to 1499ms
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1498);
    });
    expect(hangingWorker.terminate).not.toHaveBeenCalled();

    // Advance 1ms more to 1500ms: watchdog fires
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(hangingWorker.terminate).toHaveBeenCalledTimes(1);

    vi.useRealTimers();

    await waitFor(() => {
      const banner = container.querySelector('.mermaid-fallback-banner');
      expect(banner).not.toBeNull();
      expect(banner?.textContent).toContain(
        'Diagram rendered as source: exceeded 1,500ms render budget',
      );
      // Source code is visible below fallback banner
      const sourceCode = container.querySelector('.mermaid-block__source-pre');
      expect(sourceCode).not.toBeNull();
      expect(sourceCode?.textContent).toContain('Hang --> Forever');
    });
  });

  it('renders calm fallback banner for unsupported diagram types without unhandled errors', async () => {
    const client = createRealWorkerClient();
    const { container } = render(
      <MermaidBlockView source="gantt\n  title Project Schedule" client={client} />,
    );

    await waitFor(() => {
      const banner = container.querySelector('.mermaid-fallback-banner');
      expect(banner).not.toBeNull();
      expect(banner?.textContent).toContain('Diagram rendered as source: unsupported diagram type');
      expect(container.querySelector('.mermaid-block__source-pre')?.textContent).toContain('gantt');
    });
  });

  it('renders calm fallback banner for 401-node limit exceeded', async () => {
    let overNodes = 'graph TD\n';
    for (let i = 0; i <= 400; i++) {
      overNodes += `  N${String(i)}["Node ${String(i)}"]\n`;
    }

    const client = createRealWorkerClient();
    const { container } = render(
      <MermaidBlockView source={overNodes} client={client} />,
    );

    await waitFor(() => {
      const banner = container.querySelector('.mermaid-fallback-banner');
      expect(banner).not.toBeNull();
      expect(banner?.textContent).toContain('Diagram rendered as source: exceeded 400 node limit');
    });
  });

  it('revokes active blob URL on unmount (memory hygiene)', async () => {
    const client = createRealWorkerClient();
    const { container, unmount } = render(
      <MermaidBlockView source={'graph TD\n  Mem --> Clean'} client={client} />,
    );

    await waitFor(() => {
      expect(container.querySelector('img')).not.toBeNull();
    });

    const activeBlob = container.querySelector('img')?.getAttribute('src');
    expect(activeBlob).toBeTruthy();

    unmount();

    if (activeBlob) {
      expect(revokedBlobUrls).toContain(activeBlob);
    }
  });

  it('toggles between Preview and Edit mode via toolbar toggle button', async () => {
    const client = createRealWorkerClient();
    const onSourceChange = vi.fn();

    const { container } = render(
      <MermaidBlockView
        source={'graph TD\n  A --> B'}
        client={client}
        onSourceChange={onSourceChange}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('img')).not.toBeNull();
    });

    const toggleBtn = screen.getByTestId('mermaid-block-toggle-btn');
    expect(toggleBtn.textContent).toBe('Edit Mermaid');

    // Switch to edit mode
    fireEvent.click(toggleBtn);
    expect(toggleBtn.textContent).toBe('Preview');

    const textarea = screen.getByTestId<HTMLTextAreaElement>('mermaid-block-textarea');
    expect(textarea.value).toContain('A --> B');

    // Modify text in textarea
    fireEvent.change(textarea, { target: { value: 'graph TD\n  A --> C' } });
    expect(onSourceChange).toHaveBeenCalledWith('graph TD\n  A --> C');

    // Switch back to preview
    fireEvent.click(toggleBtn);
    expect(toggleBtn.textContent).toBe('Edit Mermaid');

    await waitFor(() => {
      expect(container.querySelector('img')).not.toBeNull();
    });
  });

  it('formats human reason codes accurately', () => {
    expect(formatHumanReason('RENDER_TIMEOUT', '')).toBe('exceeded 1,500ms render budget');
    expect(formatHumanReason('NODE_LIMIT_EXCEEDED', '')).toBe('exceeded 400 node limit');
    expect(formatHumanReason('EDGE_LIMIT_EXCEEDED', '')).toBe('exceeded 1,000 edge limit');
    expect(formatHumanReason('SOURCE_TOO_LARGE', '')).toBe('source exceeds 64 KB limit');
    expect(formatHumanReason('UNSUPPORTED_DIAGRAM_TYPE', '')).toBe('unsupported diagram type');
    expect(formatHumanReason('EMPTY_SOURCE', '')).toBe('empty diagram source');
    expect(formatHumanReason('CUSTOM_CODE', 'Custom reason')).toBe('Custom reason');
    expect(formatHumanReason('UNKNOWN', '')).toBe('syntax or rendering error');
  });

  it('updates when source prop changes and resets editedSource', async () => {
    const client = createRealWorkerClient();
    const { container, rerender } = render(
      <MermaidBlockView source="graph TD\n  Initial --> Node" client={client} />,
    );
    await waitFor(() => {
      expect(container.querySelector('img')).not.toBeNull();
    });

    // Enter edit mode and type something
    const toggleBtn = screen.getByTestId('mermaid-block-toggle-btn');
    fireEvent.click(toggleBtn);
    const textarea = screen.getByTestId<HTMLTextAreaElement>('mermaid-block-textarea');
    fireEvent.change(textarea, { target: { value: 'graph TD\n  Edited' } });
    expect(textarea.value).toBe('graph TD\n  Edited');

    // Change source prop
    rerender(<MermaidBlockView source={'graph TD\n  NewProp --> Node'} client={client} />);
    // Swapping source prop resets editedSource while staying in edit mode
    const updatedTextarea = screen.getByTestId<HTMLTextAreaElement>('mermaid-block-textarea');
    expect(updatedTextarea.value).toBe('graph TD\n  NewProp --> Node');
  });

  it('handles unmount while render is in flight cleanly', async () => {
    let resolvePromise: (val: unknown) => void = vi.fn();
    const renderMock = vi.fn(
      () =>
        new Promise((resolve) => {
          resolvePromise = resolve;
        }),
    );
    const slowClient = {
      render: renderMock,
    } as unknown as MermaidWorkerClient;

    const { unmount } = render(
      <MermaidBlockView source="graph TD\n  Slow --> InFlight" client={slowClient} />,
    );
    await waitFor(() => {
      expect(renderMock).toHaveBeenCalled();
    });
    unmount();
    resolvePromise({ ok: true, svg: '<svg></svg>' });
    await new Promise((r) => setTimeout(r, 10));
  });

  it('handles unmount while render throws cleanly', async () => {
    let rejectPromise: (err: unknown) => void = vi.fn();
    const renderFailingMock = vi.fn(
      () =>
        new Promise((_, reject) => {
          rejectPromise = reject;
        }),
    );
    const slowFailingClient = {
      render: renderFailingMock,
    } as unknown as MermaidWorkerClient;

    const { unmount } = render(
      <MermaidBlockView source="graph TD\n  Slow --> Crash" client={slowFailingClient} />,
    );
    await waitFor(() => {
      expect(renderFailingMock).toHaveBeenCalled();
    });
    unmount();
    rejectPromise(new Error('late crash'));
    await new Promise((r) => setTimeout(r, 10));
  });

  it('allows textarea typing when onSourceChange is omitted', () => {
    const client = createRealWorkerClient();
    render(<MermaidBlockView source="graph TD\n  No --> Handler" client={client} />);
    const toggleBtn = screen.getByTestId('mermaid-block-toggle-btn');
    fireEvent.click(toggleBtn);
    const textarea = screen.getByTestId<HTMLTextAreaElement>('mermaid-block-textarea');
    fireEvent.change(textarea, { target: { value: 'graph TD\n  NoHandlerTyping' } });
    expect(textarea.value).toBe('graph TD\n  NoHandlerTyping');
  });

  it('handles safeSvg blob creation failure gracefully with fallback banner', async () => {
    const spy = vi.spyOn(safeSvgModule, 'createSafeSvgBlobUrl').mockReturnValueOnce({
      ok: false,
      error: 'SVG_PARSE_ERROR',
      message: 'Malformed SVG output',
    });
    const client = createRealWorkerClient();
    const { container } = render(
      <MermaidBlockView source="graph TD\n  A --> B" client={client} />,
    );
    await waitFor(() => {
      const banner = container.querySelector('.mermaid-fallback-banner');
      expect(banner).not.toBeNull();
      expect(banner?.textContent).toContain('Diagram rendered as source: Malformed SVG output');
    });
    spy.mockRestore();
  });

  it('handles client.render rejection gracefully with fallback banner', async () => {
    const failingClient = {
      render: vi.fn().mockRejectedValue(new Error('Unexpected worker crash')),
    } as unknown as MermaidWorkerClient;
    const { container } = render(
      <MermaidBlockView source="graph TD\n  Crash --> Test" client={failingClient} />,
    );
    await waitFor(() => {
      const banner = container.querySelector('.mermaid-fallback-banner');
      expect(banner).not.toBeNull();
      expect(banner?.textContent).toContain('Unexpected worker crash');
    });
  });

  it('omits Edit Mermaid button in readOnly mode', async () => {
    const client = createRealWorkerClient();
    const { container } = render(
      <MermaidBlockView source="graph TD\n  RO1 --> RO2" client={client} readOnly={true} />,
    );
    await waitFor(() => {
      expect(container.querySelector('img')).not.toBeNull();
    });
    expect(container.querySelector('.mermaid-block__toggle-btn')).toBeNull();
  });

  describe('MermaidNodeView (ProseMirror Integration)', () => {
    it('initializes NodeView, handles updates, stopEvent, ignoreMutation, and destroy', async () => {
      const mockNode = {
        type: { name: 'code_block' },
        attrs: { lang: 'mermaid' },
        textContent: 'graph TD\n  PM1 --> PM2',
        nodeSize: 30,
      } as unknown as ProsemirrorNode;

      const mockView = {
        editable: true,
        state: {
          tr: {
            insertText: vi.fn().mockReturnThis(),
          },
          doc: {
            nodeAt: vi.fn(() => mockNode),
          },
        },
        dispatch: vi.fn(),
      } as unknown as EditorView;

      const getPos = () => 0;

      let nodeView!: MermaidNodeView;
      act(() => {
        nodeView = new MermaidNodeView(mockNode, mockView, getPos);
      });
      expect(nodeView.dom.className).toBe('kb-mermaid-nodeview');

      // Test stopEvent
      const clickEvent = new MouseEvent('click', { bubbles: true });
      nodeView.dom.dispatchEvent(clickEvent);
      expect(nodeView.stopEvent(clickEvent)).toBe(true);

      // Test ignoreMutation
      expect(nodeView.ignoreMutation()).toBe(true);

      // Test update with matching node
      const updatedNode = {
        type: mockNode.type,
        attrs: mockNode.attrs,
        textContent: 'graph TD\n  PM1 --> PM3',
        nodeSize: 30,
      } as unknown as ProsemirrorNode;
      act(() => {
        expect(nodeView.update(updatedNode)).toBe(true);
      });

      // Test update with non-matching node type
      const nonMatchingNode = {
        type: { name: 'paragraph' },
        attrs: {},
        textContent: 'test',
      } as unknown as ProsemirrorNode;
      expect(nodeView.update(nonMatchingNode)).toBe(false);

      // Test update with code_block but non-mermaid lang
      const nonMermaidLang = {
        type: { name: 'code_block' },
        attrs: { lang: 'python' },
        textContent: 'test',
      } as unknown as ProsemirrorNode;
      expect(nodeView.update(nonMermaidLang)).toBe(false);

      // Test destroy
      await act(async () => {
        nodeView.destroy();
        await new Promise((r) => setTimeout(r, 10));
      });
    });

    it('executes handleSourceChange and dispatches transaction to EditorView', async () => {
      const mockNode = {
        type: { name: 'code_block' },
        attrs: { lang: 'mermaid' },
        textContent: 'graph TD\n  Original',
        nodeSize: 20,
      } as unknown as ProsemirrorNode;

      const mockTr = {
        insertText: vi.fn().mockReturnThis(),
      };
      const mockView = {
        editable: true,
        state: {
          tr: mockTr,
          doc: {
            nodeAt: vi.fn(() => mockNode),
          },
        },
        dispatch: vi.fn(),
      } as unknown as EditorView;

      let nodeView!: MermaidNodeView;
      let nodeViewNoPos!: MermaidNodeView;
      let nodeViewNullNode!: MermaidNodeView;

      act(() => {
        nodeView = new MermaidNodeView(mockNode, mockView, () => 5);
        nodeViewNoPos = new MermaidNodeView(mockNode, mockView, () => undefined);
      });

      const exposed = nodeView as unknown as { handleSourceChange: (s: string) => void };
      act(() => {
        exposed.handleSourceChange('graph TD\n  Modified');
      });

      expect(mockTr.insertText).toHaveBeenCalledWith('graph TD\n  Modified', 6, 24);
      expect(mockView.dispatch).toHaveBeenCalledWith(mockTr);

      // Pos is undefined
      (nodeViewNoPos as unknown as { handleSourceChange: (s: string) => void }).handleSourceChange('test');

      // nodeAt returns null
      const mockViewNoNode = {
        editable: true,
        state: {
          tr: mockTr,
          doc: { nodeAt: vi.fn(() => null) },
        },
        dispatch: vi.fn(),
      } as unknown as EditorView;
      act(() => {
        nodeViewNullNode = new MermaidNodeView(mockNode, mockViewNoNode, () => 5);
      });
      (nodeViewNullNode as unknown as { handleSourceChange: (s: string) => void }).handleSourceChange('test');

      // Update with identical text
      expect(nodeView.update(mockNode)).toBe(true);

      // Destroy all node views
      await act(async () => {
        nodeView.destroy();
        nodeViewNoPos.destroy();
        nodeViewNullNode.destroy();
        await new Promise((r) => setTimeout(r, 10));
      });
    });

    it('registers extension and handles non-mermaid code blocks in nodeViews', async () => {
      const unregister = registerMermaidExtension();
      const extensions = getRegisteredExtensions('description');
      const mermaidExt = extensions.find((e) => e.name === 'mermaidNodeView');
      expect(mermaidExt).toBeDefined();

      if (mermaidExt?.nodeViews) {
        const views = mermaidExt.nodeViews({ surface: 'description' });
        expect(views.code_block).toBeDefined();

        const mockView = { editable: true } as unknown as EditorView;
        const nonMermaid = {
          type: { name: 'code_block' },
          attrs: { lang: 'python' },
          textContent: 'x = 1',
        } as unknown as ProsemirrorNode;

        if (views.code_block) {
          const result = views.code_block(nonMermaid, mockView, () => 0, [], {} as never);
          expect(result).toBeDefined();
          expect(result.dom).toBeInstanceOf(HTMLElement);
          expect((result as { contentDOM?: HTMLElement }).contentDOM).toBeInstanceOf(HTMLElement);

          const mermaidNode = {
            type: { name: 'code_block' },
            attrs: { lang: 'mermaid' },
            textContent: 'graph TD\n  A --> B',
          } as unknown as ProsemirrorNode;

          let mermaidResult!: NodeView;
          act(() => {
            if (views.code_block) {
              mermaidResult = views.code_block(mermaidNode, mockView, () => 0, [], {} as never);
            }
          });
          expect(mermaidResult).toBeInstanceOf(MermaidNodeView);

          await act(async () => {
            (mermaidResult as MermaidNodeView).destroy();
            await new Promise((r) => setTimeout(r, 10));
          });
        }
      }

      unregister();
    });
  });
});
