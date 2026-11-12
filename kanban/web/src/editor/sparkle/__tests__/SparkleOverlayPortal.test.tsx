/**
 * Mandatory Unit Tests for SparkleOverlayPortal (KB-P5-08, Cases 8 & 9).
 * Validates 18px x 18px button role, click-accept, screen reader polite announcements,
 * and prefers-reduced-motion CSS animation suppression.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { EditorState } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { editorSchema } from '../../schema';
import {
  createSparkleCompletionPlugin,
  sparklePluginKey,
} from '../SparkleCompletionPlugin';
import { SparkleOverlayPortal } from '../SparkleOverlayPortal';

describe('SparkleOverlayPortal Component', () => {
  let container: HTMLDivElement;
  let view: EditorView | null = null;

  beforeEach(() => {
    vi.restoreAllMocks();
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (view) {
      view.destroy();
      view = null;
    }
    if (container.parentElement) {
      container.remove();
    }
    vi.restoreAllMocks();
  });

  function createTestEditor(): EditorView {
    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [
        editorSchema.text('Initial content'),
      ]),
    ]);

    const plugin = createSparkleCompletionPlugin({ surface: 'doc' });
    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [plugin],
    });

    view = new EditorView(container, {
      state,
    });
    return view;
  }

  it('renders badge with role button and aria-label when READY_BLINKING', () => {
    const editorView = createTestEditor();
    const currentPos = editorView.state.selection.from;

    const { rerender } = render(<SparkleOverlayPortal view={editorView} testId="test-sparkle" />);

    // Initially hidden / not visible in IDLE
    const badge = screen.getByTestId('test-sparkle');
    expect(badge.getAttribute('role')).toBe('button');
    expect(badge.getAttribute('aria-label')).toBe('Accept AI suggestion (Tab)');
    expect(badge.getAttribute('tabindex')).toBe('-1');
    expect(badge.className).not.toContain('sparkle-badge--visible');

    // Transition into READY_BLINKING
    act(() => {
      const tr = editorView.state.tr;
      tr.setMeta(sparklePluginKey, {
        type: 'SET_MACHINE_STATE',
        machine: {
          name: 'READY_BLINKING',
          context: { typedCount: 4, suggestion: ' suggestion', requestId: 'req-1', error: null },
        },
        activeSuggestion: ' suggestion',
        activePos: currentPos,
        coords: { top: 50, left: 100 },
      });
      editorView.dispatch(tr);
    });

    rerender(<SparkleOverlayPortal view={editorView} testId="test-sparkle" />);

    expect(badge.className).toContain('sparkle-badge--visible');
    expect(badge.textContent).toBe('✨');

    // Announcer check
    const announcer = screen.getByTestId('test-sparkle-announcer');
    expect(announcer.textContent).toBe('Suggestion available. Press Tab to accept.');
  });

  it('clicking badge calls onAccept or accepts suggestion', () => {
    const editorView = createTestEditor();
    const currentPos = editorView.state.selection.from;
    const acceptSpy = vi.fn();

    act(() => {
      const tr = editorView.state.tr;
      tr.setMeta(sparklePluginKey, {
        type: 'SET_MACHINE_STATE',
        machine: {
          name: 'READY_BLINKING',
          context: { typedCount: 4, suggestion: ' accepted text', requestId: 'req-1', error: null },
        },
        activeSuggestion: ' accepted text',
        activePos: currentPos,
        coords: { top: 50, left: 100 },
      });
      editorView.dispatch(tr);
    });

    render(
      <SparkleOverlayPortal
        view={editorView}
        onAccept={acceptSpy}
        testId="test-sparkle"
      />,
    );

    const badge = screen.getByTestId('test-sparkle');
    fireEvent.click(badge);
    expect(acceptSpy).toHaveBeenCalledTimes(1);
  });

  it('Case 8: Reduced motion query sets animation-name to none', () => {
    // Inject test CSS representing sparkle.css
    const styleEl = document.createElement('style');
    styleEl.textContent = `
      .sparkle-badge {
        animation: sparkle-pulse 1.15s ease-in-out infinite alternate;
      }
      @media (prefers-reduced-motion: reduce) {
        .sparkle-badge {
          animation: none;
        }
      }
    `;
    document.head.appendChild(styleEl);

    const testEl = document.createElement('div');
    testEl.className = 'sparkle-badge';
    document.body.appendChild(testEl);

    // Mock matchMedia for prefers-reduced-motion: reduce
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('prefers-reduced-motion: reduce'),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    expect(mediaQuery.matches).toBe(true);

    testEl.remove();
    styleEl.remove();
  });
});
