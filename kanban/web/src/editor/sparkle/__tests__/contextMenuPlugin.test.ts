/**
 * Plugin Integration Tests for Sparkle Context Menu Resolution (KB-P5-09, S9.1, S9.2).
 *
 * Covers:
 * - Test 1: Row 1 - Right-click on badge accepts completion.
 * - Test 2: Row 2 - Right-click within <= 28px of caret accepts completion.
 * - Test 3: Row 3 - Shift + Right-click yields native context menu (defaultPrevented === false).
 * - Test 4: Row 4 - Non-empty selection yields native context menu (Copy/Cut preserved).
 * - Test 5: Row 5 - Spelling node or distance > 28px yields native menu, no stopPropagation.
 * - Test 6: Badge gesture - pointerdown button 2 accepts once, suppresses following contextmenu, second contextmenu is NATIVE.
 * - Test 7: Single-step undo - Right-click accept then undo restores exact pre-accept document.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { EditorState, TextSelection } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { history, undo } from 'prosemirror-history';
import { editorSchema } from '../../schema';
import {
  createSparkleCompletionPlugin,
  sparklePluginKey,
} from '../SparkleCompletionPlugin';
import { resetBadgeContextMenuSuppression } from '../contextMenuMatrix';

describe('SparkleCompletionPlugin Context Menu Integration (KB-P5-09)', () => {
  let container: HTMLDivElement;
  let view: EditorView | null = null;

  beforeEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    resetBadgeContextMenuSuppression();
    container = document.createElement('div');
    document.body.appendChild(container);
  });

  afterEach(() => {
    resetBadgeContextMenuSuppression();
    if (view) {
      view.destroy();
      view = null;
    }
    if (container.parentElement) {
      container.remove();
    }
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function createTestView(options?: {
    initialText?: string;
  }): EditorView {
    const text = options?.initialText ?? 'Hello world';
    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(
        null,
        text ? [editorSchema.text(text)] : [],
      ),
    ]);

    const sparklePlugin = createSparkleCompletionPlugin({
      surface: 'doc',
      renderOverlay: true,
    });

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [sparklePlugin, history()],
    });

    view = new EditorView(container, {
      state,
    });

    // Mock coordsAtPos to return deterministic coordinates for caret at pos
    view.coordsAtPos = vi.fn().mockImplementation(() => ({
      left: 100,
      right: 100,
      top: 50,
      bottom: 70, // Midpoint is (100, 60)
    }));

    return view;
  }

  function setReadyBlinkingState(
    v: EditorView,
    suggestion = ' completion text',
    pos?: number,
  ): void {
    const targetPos = pos ?? v.state.doc.content.size - 1;
    const tr = v.state.tr;
    tr.setSelection(TextSelection.create(tr.doc, targetPos));
    tr.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: {
          typedCount: 4,
          suggestion,
          requestId: 'test-req',
          error: null,
        },
      },
      activeSuggestion: suggestion,
      activePos: targetPos,
      coords: { top: 50, left: 100 },
    });
    v.dispatch(tr);
  }

  it('Row 1: Right-click directly on .sparkle-badge in READY_BLINKING accepts completion immediately', () => {
    const v = createTestView();
    setReadyBlinkingState(v, ' verified');

    // Find the badge element rendered by the plugin overlay
    const badge = container.querySelector('.sparkle-badge');
    expect(badge).not.toBeNull();

    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 500, // Distance is ignored when target is badge
      clientY: 500,
    });

    badge?.dispatchEvent(event);

    // Event must be prevented
    expect(event.defaultPrevented).toBe(true);
    // Completion accepted into document
    expect(v.state.doc.textContent).toBe('Hello world verified');

    // Right-click on badge with shiftKey allows native context menu
    const shiftEvent = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      shiftKey: true,
    });
    badge?.dispatchEvent(shiftEvent);
    expect(shiftEvent.defaultPrevented).toBe(false);

    // Pointerdown button 0 on badge does not accept
    const normalPointerEvent = new PointerEvent('pointerdown', {
      bubbles: true,
      cancelable: true,
      button: 0,
    });
    badge?.dispatchEvent(normalPointerEvent);
    expect(normalPointerEvent.defaultPrevented).toBe(false);
  });

  it('Row 2: Right-click within <= 28px of caret & not over spelling accepts completion', () => {
    const v = createTestView();
    setReadyBlinkingState(v, ' verified');

    // Caret midpoint is (100, 60). Point (115, 60) is dx = 15, dy = 0 -> distance = 15px <= 28px
    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 115,
      clientY: 60,
    });

    v.dom.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(v.state.doc.textContent).toBe('Hello world verified');
  });

  it('Row 3: Shift + Right-click is native user escape hatch (never calls preventDefault or stopPropagation)', () => {
    const v = createTestView();
    setReadyBlinkingState(v, ' verified');

    // Within 5px of caret, but holding Shift
    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 105,
      clientY: 60,
      shiftKey: true,
    });

    const stopPropagationSpy = vi.spyOn(event, 'stopPropagation');

    v.dom.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    expect(stopPropagationSpy).not.toHaveBeenCalled();
    // Document not changed
    expect(v.state.doc.textContent).toBe('Hello world');
  });

  it('Row 4: Non-empty selection yields native context menu to preserve Copy/Cut', () => {
    const v = createTestView();
    setReadyBlinkingState(v, ' verified');

    // Expand selection to cover 'world' (pos 6 to 11)
    const tr = v.state.tr;
    tr.setSelection(TextSelection.create(tr.doc, 6, 11));
    v.dispatch(tr);

    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 105,
      clientY: 60,
    });

    const stopPropagationSpy = vi.spyOn(event, 'stopPropagation');
    v.dom.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    expect(stopPropagationSpy).not.toHaveBeenCalled();
    expect(v.state.doc.textContent).toBe('Hello world');
  });

  it('Row 5a: Over spelling node (.cm-lint-spelling) within 10px of caret preserves native spellcheck menu', () => {
    const v = createTestView();
    setReadyBlinkingState(v, ' verified');

    // Create a spelling node element inside editor
    const spellingSpan = document.createElement('span');
    spellingSpan.className = 'cm-lint-spelling';
    spellingSpan.textContent = 'mispelled';
    v.dom.appendChild(spellingSpan);

    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 105,
      clientY: 60,
    });

    const stopPropagationSpy = vi.spyOn(event, 'stopPropagation');
    spellingSpan.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    expect(stopPropagationSpy).not.toHaveBeenCalled();
    expect(v.state.doc.textContent).toBe('Hello world');
  });

  it('Row 5b: Right-click > 28px away from caret preserves native context menu', () => {
    const v = createTestView();
    setReadyBlinkingState(v, ' verified');

    // Caret midpoint is (100, 60). Point (135, 60) is dx = 35px > 28px
    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 135,
      clientY: 60,
    });

    const stopPropagationSpy = vi.spyOn(event, 'stopPropagation');
    v.dom.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    expect(stopPropagationSpy).not.toHaveBeenCalled();
    expect(v.state.doc.textContent).toBe('Hello world');

    // When coordsAtPos throws error, distance is treated as Infinity (NATIVE)
    v.coordsAtPos = vi.fn().mockImplementation(() => {
      throw new Error('DOM coords unavailable');
    });
    const errorEvent = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 100,
      clientY: 60,
    });
    v.dom.dispatchEvent(errorEvent);
    expect(errorEvent.defaultPrevented).toBe(false);
  });

  it('Row 6: Right-click when machine is in IDLE state is 100% native behavior', () => {
    const v = createTestView();
    // Do not set READY_BLINKING (state is IDLE)

    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 100,
      clientY: 60,
    });

    const stopPropagationSpy = vi.spyOn(event, 'stopPropagation');
    v.dom.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    expect(stopPropagationSpy).not.toHaveBeenCalled();
  });

  it('Test 6: Badge gesture - pointerdown button 2 accepts once, suppresses following contextmenu, second contextmenu is NATIVE', () => {
    const v = createTestView();
    setReadyBlinkingState(v, ' accepted_by_pointerdown');

    const badge = container.querySelector('.sparkle-badge');
    expect(badge).not.toBeNull();

    // 1. Dispatch pointerdown with button 2 (Right-click) on badge
    const pointerDownEvent = new PointerEvent('pointerdown', {
      bubbles: true,
      cancelable: true,
      button: 2,
    });
    badge?.dispatchEvent(pointerDownEvent);

    // Suggestion is accepted
    expect(pointerDownEvent.defaultPrevented).toBe(true);
    expect(v.state.doc.textContent).toBe('Hello world accepted_by_pointerdown');

    // 2. Dispatch subsequent contextmenu event immediately following pointerdown
    const immediateContextMenu = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      button: 2,
    });
    v.dom.dispatchEvent(immediateContextMenu);

    // Contextmenu is suppressed for this gesture
    expect(immediateContextMenu.defaultPrevented).toBe(true);

    // 3. Dispatch second unrelated contextmenu later
    const secondContextMenu = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      button: 2,
      clientX: 100,
      clientY: 60,
    });
    v.dom.dispatchEvent(secondContextMenu);

    // Suppression was consumed; state is no longer READY_BLINKING; outcome is NATIVE
    expect(secondContextMenu.defaultPrevented).toBe(false);
  });

  it('Test 7: Single-step undo - Right-click accept then Ctrl+Z restores exact pre-accept document', () => {
    const v = createTestView();
    const originalText = v.state.doc.textContent;
    setReadyBlinkingState(v, ' addition');

    // Right-click accept via <= 28px click
    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 105,
      clientY: 60,
    });
    v.dom.dispatchEvent(event);

    expect(v.state.doc.textContent).toBe('Hello world addition');

    // Execute undo step
    const undoResult = undo(v.state, v.dispatch);
    expect(undoResult).toBe(true);

    // Document is restored byte-for-byte to pre-accept text
    expect(v.state.doc.textContent).toBe(originalText);
  });
});
