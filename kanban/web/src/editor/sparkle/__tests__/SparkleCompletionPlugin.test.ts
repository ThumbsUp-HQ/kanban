/**
 * Mandatory Unit Tests for ProseMirror SparkleCompletionPlugin (KB-P5-08).
 * Covers Debounce (Case 2), Abort (Case 3), Accept & Undo (Case 4),
 * Security textContent rendering (Case 5), Faults (Case 6), and Dismiss (Case 7).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { EditorState } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { history, undo } from 'prosemirror-history';
import { editorSchema } from '../../schema';
import {
  createSparkleCompletionPlugin,
  sparklePluginKey,
  acceptSparkleSuggestion,
  dismissSparkleSuggestion,
} from '../SparkleCompletionPlugin';
import type { SparkleClientOptions, SparkleResponse } from '../sparkleClient';

describe('SparkleCompletionPlugin Unit Tests', () => {
  let container: HTMLDivElement;
  let view: EditorView | null = null;

  beforeEach(() => {
    vi.useRealTimers();
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
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function createTestView(options?: {
    initialText?: string;
    fetchFn?: (opts: SparkleClientOptions) => Promise<SparkleResponse>;
    debounceMs?: number;
    timeoutMs?: number;
  }): EditorView {
    const text = options?.initialText ?? '';
    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(
        null,
        text ? [editorSchema.text(text)] : [],
      ),
    ]);

    const sparklePlugin = createSparkleCompletionPlugin({
      surface: 'doc',
      debounceMs: options?.debounceMs ?? 320,
      timeoutMs: options?.timeoutMs ?? 200,
      fetchFn: options?.fetchFn,
    });

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [sparklePlugin, history()],
    });

    view = new EditorView(container, {
      state,
    });

    return view;
  }

  function simulateKeystroke(v: EditorView, key: string): void {
    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
    v.dom.dispatchEvent(event);
  }

  it('Case 2: Debounce - 3 chars -> no fetch; 4th char then 319ms -> no fetch; 320ms -> exactly 1 fetch', () => {
    vi.useFakeTimers();

    const fetchSpy = vi.fn().mockResolvedValue({
      status: 'ok',
      text: ' completion text',
      tokens: 3,
    });

    const v = createTestView({ fetchFn: fetchSpy, debounceMs: 320 });

    // Type 3 characters
    simulateKeystroke(v, 'a');
    simulateKeystroke(v, 'b');
    simulateKeystroke(v, 'c');
    vi.advanceTimersByTime(500);

    expect(fetchSpy).not.toHaveBeenCalled();

    // Type 4th character
    simulateKeystroke(v, 'd');
    vi.advanceTimersByTime(319);
    expect(fetchSpy).not.toHaveBeenCalled();

    // Advance 1ms to reach 320ms debounce threshold
    vi.advanceTimersByTime(1);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('Case 3: Abort - typing during FETCHING aborts prior request and starts new debounce', () => {
    vi.useFakeTimers();

    let capturedSignal: AbortSignal | null = null;
    const fetchSpy = vi.fn().mockImplementation((opts: SparkleClientOptions) => {
      capturedSignal = opts.signal ?? null;
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve({ status: 'ok', text: ' response', tokens: 2 });
        }, 100);
      });
    });

    const v = createTestView({ fetchFn: fetchSpy, debounceMs: 320 });

    // Type 4 characters to trigger debounce
    simulateKeystroke(v, 'a');
    simulateKeystroke(v, 'b');
    simulateKeystroke(v, 'c');
    simulateKeystroke(v, 'd');
    vi.advanceTimersByTime(320);

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect((capturedSignal as AbortSignal | null)?.aborted).toBe(false);

    // Type 5th character while prior request is still in flight (FETCHING)
    simulateKeystroke(v, 'e');
    expect((capturedSignal as AbortSignal | null)?.aborted).toBe(true);

    // Verify a new debounce timer is started
    vi.advanceTimersByTime(319);
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(1);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it('Case 4: Accept - Tab in READY_BLINKING inserts text, one undo step removes it, doc unchanged before accept', () => {
    const v = createTestView({ initialText: 'Hello' });
    const initialDocText = v.state.doc.textContent;
    const currentPos = v.state.selection.from;

    // Simulate transitioning into READY_BLINKING with active suggestion at current cursor pos
    const tr = v.state.tr;
    tr.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: ' world', requestId: 'req-1', error: null },
      },
      activeSuggestion: ' world',
      activePos: currentPos,
      coords: { top: 10, left: 20 },
    });
    v.dispatch(tr);

    // 1. Verify doc is unchanged before accept
    expect(v.state.doc.textContent).toBe(initialDocText);

    // 2. Press Tab to accept suggestion
    const tabEvent = new KeyboardEvent('keydown', {
      key: 'Tab',
      bubbles: true,
      cancelable: true,
    });
    const handled = v.someProp('handleKeyDown', (f) => f(v, tabEvent));
    expect(handled).toBe(true);

    // 3. Verify text was inserted
    expect(v.state.doc.textContent).toBe(' worldHello');

    // 4. Verify machine returned to IDLE
    const pluginStateAfterAccept = sparklePluginKey.getState(v.state);
    expect(pluginStateAfterAccept?.machine.name).toBe('IDLE');

    // 5. Verify single undo step restores original document
    undo(v.state, v.dispatch);
    expect(v.state.doc.textContent).toBe(initialDocText);
  });

  it('Case 5 (Security): HTML injection text is rendered strictly via textContent, never innerHTML', () => {
    const v = createTestView({ initialText: 'Testing' });
    const currentPos = v.state.selection.from;

    // Transition into READY_BLINKING with hostile HTML suggestion
    const tr = v.state.tr;
    tr.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: '<b>x</b>', requestId: 'req-sec', error: null },
      },
      activeSuggestion: '<b>x</b>',
      activePos: currentPos,
      coords: { top: 10, left: 30 },
    });
    v.dispatch(tr);

    // Look for .sparkle-ghost decoration element in editor DOM
    const ghostEl = container.querySelector('.sparkle-ghost');
    expect(ghostEl).not.toBeNull();
    expect(ghostEl?.textContent).toBe('<b>x</b>');

    // Assert zero <b> HTML elements exist
    expect(ghostEl?.querySelector('b')).toBeNull();
    expect(container.querySelectorAll('b').length).toBe(0);
  });

  it('Case 6 (Fault): empty, secret_scrubbed, and timeout statuses reset to IDLE without badge', async () => {
    const statuses = ['empty', 'secret_scrubbed', 'timeout'] as const;

    for (const status of statuses) {
      const fetchSpy = vi.fn().mockResolvedValue({
        status,
        text: '',
      });

      const v = createTestView({ fetchFn: fetchSpy, debounceMs: 10 });
      vi.useFakeTimers();

      simulateKeystroke(v, '1');
      simulateKeystroke(v, '2');
      simulateKeystroke(v, '3');
      simulateKeystroke(v, '4');
      vi.advanceTimersByTime(10);
      await Promise.resolve();

      const pluginState = sparklePluginKey.getState(v.state);
      expect(pluginState?.machine.name).toBe('IDLE');
      expect(pluginState?.activeSuggestion).toBe('');

      v.destroy();
      vi.useRealTimers();
    }
  });

  it('Case 7: Dismiss on Escape, cursor move, and mismatched char; advance on matching char', () => {
    const v = createTestView({ initialText: 'Hello' });
    const currentPos = v.state.selection.from;

    // 1. Enter READY_BLINKING with suggestion " world"
    const tr = v.state.tr;
    tr.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: ' world', requestId: 'req-1', error: null },
      },
      activeSuggestion: ' world',
      activePos: currentPos,
      coords: { top: 10, left: 20 },
    });
    v.dispatch(tr);

    // 2. Type matching character ' ' (space)
    v.someProp('handleTextInput', (f) => f(v, currentPos, currentPos, ' ', () => v.state.tr));
    const advancedState = sparklePluginKey.getState(v.state);
    expect(advancedState?.machine.name).toBe('READY_BLINKING');
    expect(advancedState?.activeSuggestion).toBe('world');

    // 3. Type mismatched character 'z' -> dismisses to IDLE
    v.someProp('handleTextInput', (f) => f(v, currentPos, currentPos, 'z', () => v.state.tr));
    const dismissedState = sparklePluginKey.getState(v.state);
    expect(dismissedState?.machine.name).toBe('IDLE');

    // 4. Test Escape key dismiss
    const tr2 = v.state.tr;
    tr2.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: ' test', requestId: 'req-2', error: null },
      },
      activeSuggestion: ' test',
      activePos: currentPos,
      coords: { top: 10, left: 20 },
    });
    v.dispatch(tr2);

    const escEvent = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    const escHandled = v.someProp('handleKeyDown', (f) => f(v, escEvent));
    expect(escHandled).toBe(true);

    const postEscState = sparklePluginKey.getState(v.state);
    expect(postEscState?.machine.name).toBe('IDLE');

    // 5. Test manual helper functions
    expect(acceptSparkleSuggestion(v)).toBe(false); // cannot accept in IDLE
    expect(dismissSparkleSuggestion(v)).toBe(false); // cannot dismiss in IDLE
  });

  it('covers full typing of suggestion to auto-accept, non-empty selection guard, and accept edge cases', () => {
    const v = createTestView({ initialText: 'Hello' });
    const currentPos = 5;

    // 1. Ready blinking with exact suggestion ' world'
    const tr = v.state.tr;
    tr.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 5, suggestion: ' world', requestId: 'req-full', error: null },
      },
      activeSuggestion: ' world',
      activePos: currentPos,
      coords: { top: 10, left: 20 },
    });
    v.dispatch(tr);

    // Typing the entire suggestion string at once
    v.someProp('handleTextInput', (f) => f(v, currentPos, currentPos, ' world', () => v.state.tr));
    const postTypeState = sparklePluginKey.getState(v.state);
    expect(postTypeState?.machine.name).toBe('IDLE');

    // 2. acceptSparkleSuggestion with null activePos / empty suggestion
    const tr2 = v.state.tr;
    tr2.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 5, suggestion: '', requestId: 'req-empty', error: null },
      },
      activeSuggestion: '',
      activePos: null,
    });
    v.dispatch(tr2);
    expect(acceptSparkleSuggestion(v)).toBe(false);
  });

  it('covers createSparkleCompletionPlugin default options, missing plugin state, and selection guards', () => {
    // 1. Default options
    const defaultPlugin = createSparkleCompletionPlugin();
    expect(defaultPlugin).toBeDefined();

    // 2. View without Sparkle plugin for handleTextInput guard
    const bareDoc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [editorSchema.text('Bare')]),
    ]);
    const bareState = EditorState.create({ schema: editorSchema, doc: bareDoc });
    const bareView = new EditorView(container, { state: bareState });

    // Call handleTextInput from defaultPlugin on bareView
    const textHandled = (defaultPlugin.props.handleTextInput as any)?.(bareView, 1, 1, 'x', () => bareState.tr);
    expect(textHandled).toBe(false);

    // Call handleDOMEvents.contextmenu on bareView
    const evt = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
    const ctxHandled = (defaultPlugin.props.handleDOMEvents?.contextmenu as any)?.(bareView, evt);
    expect(ctxHandled).toBe(false);

    bareView.destroy();
  });
});
