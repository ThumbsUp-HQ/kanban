/**
 * Mermaid ProseMirror NodeView & React Component (KB-P3-47, S5.3).
 * Renders fenced ```mermaid blocks inside MediaViewport via isolated Web Worker.
 * Supports live theme sync, safe blob: URLs, toggleable Edit/Preview mode,
 * and calm fallback notice banner for invalid or timed-out diagrams.
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type JSX,
} from 'react';
import type { Node as ProsemirrorNode } from 'prosemirror-model';
import type { EditorView, NodeView } from 'prosemirror-view';
import { createRoot, type Root } from 'react-dom/client';
import { MediaViewport } from '../media/MediaViewport';
import { createSafeSvgBlobUrl } from '../media/safeSvg';
import { readMermaidThemeTokens } from './mermaidTheme';
import { mermaidClient, MermaidWorkerClient } from './mermaidClient';
import { registerEditorExtension } from '../editorSurfaceFactory';
import './MermaidBlockView.css';

export interface MermaidBlockViewProps {
  source: string;
  readOnly?: boolean | undefined;
  client?: MermaidWorkerClient | undefined;
  onSourceChange?: ((newSource: string) => void) | undefined;
  testId?: string | undefined;
}

export function formatHumanReason(code: string, message: string): string {
  switch (code) {
    case 'RENDER_TIMEOUT':
      return 'exceeded 1,500ms render budget';
    case 'NODE_LIMIT_EXCEEDED':
      return 'exceeded 400 node limit';
    case 'EDGE_LIMIT_EXCEEDED':
      return 'exceeded 1,000 edge limit';
    case 'SOURCE_TOO_LARGE':
      return 'source exceeds 64 KB limit';
    case 'UNSUPPORTED_DIAGRAM_TYPE':
      return 'unsupported diagram type';
    case 'EMPTY_SOURCE':
      return 'empty diagram source';
    default:
      return message || 'syntax or rendering error';
  }
}

type RenderStatus = 'idle' | 'rendering' | 'success' | 'fallback';

export function MermaidBlockView({
  source,
  readOnly = false,
  client = mermaidClient,
  onSourceChange,
  testId = 'mermaid-block',
}: MermaidBlockViewProps): JSX.Element {
  const [mode, setMode] = useState<'preview' | 'edit'>('preview');
  const [status, setStatus] = useState<RenderStatus>('idle');
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [fallbackReason, setFallbackReason] = useState<string>('');
  const [editedSource, setEditedSource] = useState<string | null>(null);
  const [prevPropSource, setPrevPropSource] = useState<string>(source);

  if (source !== prevPropSource) {
    setPrevPropSource(source);
    setEditedSource(null);
  }

  const currentSource = editedSource ?? source;

  // Keep track of active blob revoker to prevent memory leaks
  const activeRevokeRef = useRef<(() => void) | null>(null);
  const isMountedRef = useRef<boolean>(true);

  // Main render runner
  const executeRender = useCallback(
    async (sourceToRender: string) => {
      setStatus('rendering');
      const theme = readMermaidThemeTokens();

      try {
        const result = await client.render(sourceToRender, theme);
        if (!isMountedRef.current) {
          return;
        }

        if (result.ok) {
          const safeResult = createSafeSvgBlobUrl(result.svg);
          if (safeResult.ok) {
            // Revoke prior blob URL
            if (activeRevokeRef.current) {
              activeRevokeRef.current();
            }
            activeRevokeRef.current = safeResult.revoke;
            setBlobUrl(safeResult.blobUrl);
            setStatus('success');
            setFallbackReason('');
          } else {
            setStatus('fallback');
            setFallbackReason(safeResult.message);
          }
        } else {
          setStatus('fallback');
          setFallbackReason(formatHumanReason(result.code, result.message));
        }
      } catch (err: unknown) {
        if (!isMountedRef.current) {
          return;
        }
        const message = err instanceof Error ? err.message : String(err);
        setStatus('fallback');
        setFallbackReason(formatHumanReason('RENDER_ERROR', message));
      }
    },
    [client],
  );

  // Trigger render on source or client change (deferred to avoid synchronous setState in effect)
  useEffect(() => {
    let isCancelled = false;
    const timer = setTimeout(() => {
      if (!isCancelled) {
        void executeRender(currentSource);
      }
    }, 0);
    return () => {
      isCancelled = true;
      clearTimeout(timer);
    };
  }, [currentSource, executeRender]);

  // Listen for document theme changes (data-theme, class) to trigger live re-render
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (
          mutation.type === 'attributes' &&
          (mutation.attributeName === 'data-theme' || mutation.attributeName === 'class')
        ) {
          void executeRender(currentSource);
          break;
        }
      }
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme', 'class'],
    });

    return () => {
      observer.disconnect();
    };
  }, [currentSource, executeRender]);

  // Memory hygiene on unmount: revoke active blob URL
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (activeRevokeRef.current) {
        activeRevokeRef.current();
        activeRevokeRef.current = null;
      }
    };
  }, []);

  const handleToggleMode = useCallback(() => {
    if (mode === 'preview') {
      setMode('edit');
    } else {
      setMode('preview');
      void executeRender(currentSource);
    }
  }, [mode, currentSource, executeRender]);

  const handleTextareaChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const next = e.target.value;
      setEditedSource(next);
      onSourceChange?.(next);
    },
    [onSourceChange],
  );

  const containerClasses = [
    'mermaid-block',
    `mermaid-block--${mode}`,
    status === 'fallback' ? 'mermaid-block--fallback' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={containerClasses} data-testid={testId} data-lang="mermaid">
      {/* Top Toolbar with Mode Toggle */}
      <div className="mermaid-block__toolbar" data-testid={`${testId}-toolbar`}>
        <span className="mermaid-block__badge">Mermaid</span>
        {!readOnly && (
          <button
            type="button"
            className="mermaid-block__toggle-btn"
            onClick={handleToggleMode}
            data-testid={`${testId}-toggle-btn`}
          >
            {mode === 'preview' ? 'Edit Mermaid' : 'Preview'}
          </button>
        )}
      </div>

      {/* Fallback Banner for invalid or timed-out diagrams */}
      {status === 'fallback' && (
        <div className="mermaid-fallback-banner" data-testid={`${testId}-fallback-banner`}>
          <span className="mermaid-fallback-banner__icon" aria-hidden="true">
            ⚠
          </span>
          <span className="mermaid-fallback-banner__msg">
            Diagram rendered as source: {fallbackReason}
          </span>
        </div>
      )}

      {/* Visual Preview Mode: MediaViewport mounting safe blob: <img> */}
      {mode === 'preview' && status === 'success' && blobUrl && (
        <div className="mermaid-block__preview" data-testid={`${testId}-preview`}>
          <MediaViewport
            kind="mermaid"
            src={blobUrl}
            blobUrl={blobUrl}
            rawSource={currentSource}
            safeFilename="diagram.svg"
            downloadFilename="diagram.svg"
            alt="Mermaid diagram"
            testId={`${testId}-viewport`}
          />
        </div>
      )}

      {/* Loading State */}
      {mode === 'preview' && status === 'rendering' && !blobUrl && (
        <div className="mermaid-block__preview" data-testid={`${testId}-loading`}>
          <div className="media-viewport__skeleton">Rendering Mermaid diagram...</div>
        </div>
      )}

      {/* Fallback Monospace Source Block (always visible in fallback state or edit mode) */}
      {(mode === 'edit' || status === 'fallback') && (
        <div className="mermaid-block__source" data-testid={`${testId}-source-wrapper`}>
          {mode === 'edit' && !readOnly ? (
            <textarea
              className="mermaid-block__textarea"
              value={currentSource}
              onChange={handleTextareaChange}
              rows={Math.max(4, currentSource.split('\n').length + 1)}
              data-testid={`${testId}-textarea`}
              spellCheck={false}
            />
          ) : (
            <pre className="mermaid-block__source-pre" data-testid={`${testId}-source`}>
              <code className="language-mermaid">{currentSource}</code>
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * ProseMirror NodeView for ```mermaid code_blocks.
 */
export class MermaidNodeView implements NodeView {
  dom: HTMLElement;
  private root: Root | null = null;
  private currentSource: string;

  constructor(
    node: ProsemirrorNode,
    private readonly view: EditorView,
    private readonly getPos: () => number | undefined,
  ) {
    this.dom = document.createElement('div');
    this.dom.className = 'kb-mermaid-nodeview';
    this.currentSource = node.textContent;
    this.render();
  }

  private handleSourceChange = (newSource: string): void => {
    this.currentSource = newSource;
    const pos = this.getPos();
    if (typeof pos === 'number') {
      const targetNode = this.view.state.doc.nodeAt(pos);
      if (targetNode) {
        const tr = this.view.state.tr.insertText(
          newSource,
          pos + 1,
          pos + targetNode.nodeSize - 1,
        );
        this.view.dispatch(tr);
      }
    }
  };

  private render(): void {
    this.root ??= createRoot(this.dom);
    this.root.render(
      <MermaidBlockView
        source={this.currentSource}
        readOnly={!this.view.editable}
        onSourceChange={this.handleSourceChange}
      />,
    );
  }

  update(node: ProsemirrorNode): boolean {
    if (node.type.name !== 'code_block' || node.attrs.lang !== 'mermaid') {
      return false;
    }
    if (node.textContent !== this.currentSource) {
      this.currentSource = node.textContent;
      this.render();
    }
    return true;
  }

  stopEvent(event: Event): boolean {
    // Keep events inside the Mermaid component (zoom, copy, toggle) from bubbling to ProseMirror
    return this.dom.contains(event.target as Node);
  }

  ignoreMutation(): boolean {
    // Ignore DOM mutations managed by React
    return true;
  }

  destroy(): void {
    const rootToUnmount = this.root;
    this.root = null;
    if (rootToUnmount) {
      setTimeout(() => {
        rootToUnmount.unmount();
      }, 0);
    }
  }
}

/**
 * Registers Mermaid nodeView extension with the global editor surface registry.
 */
export function registerMermaidExtension(): () => void {
  return registerEditorExtension({
    name: 'mermaidNodeView',
    surfaces: ['description', 'doc', 'sticky', 'comment'],
    nodeViews: () => ({
      code_block: (node, view, getPos) => {
        if (node.attrs.lang === 'mermaid') {
          return new MermaidNodeView(node, view, getPos);
        }
        const dom = document.createElement('pre');
        const code = document.createElement('code');
        dom.appendChild(code);
        return {
          dom,
          contentDOM: code,
        };
      },
    }),
  });
}
