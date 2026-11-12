/**
 * 100% Branch and Line Coverage Completion Suite for Sparkle (KB-P5-08).
 * Targets all remaining edge branches across sparkleMachine, sparkleClient,
 * SparkleCompletionPlugin, SparkleOverlayPortal, and index.ts.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { EditorState, TextSelection } from 'prosemirror-state';
import { EditorView, DecorationSet } from 'prosemirror-view';
import { history } from 'prosemirror-history';
import { editorSchema } from '../../schema';
import * as SparkleModule from '../index';
import {
  sparkleReducer,
  INITIAL_SPARKLE_STATE,
  INITIAL_SPARKLE_CONTEXT,
} from '../sparkleMachine';
import {
  fetchSparkle,
  getCsrfToken,
  generateClientRequestId,
  type SparkleClientOptions,
  type SparkleResponse,
} from '../sparkleClient';
import {
  createSparkleCompletionPlugin,
  sparklePluginKey,
  acceptSparkleSuggestion,
  type SparklePluginState,
} from '../SparkleCompletionPlugin';
import { SparkleOverlayPortal } from '../SparkleOverlayPortal';

describe('Sparkle 100% Branch Coverage Suite', () => {
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

  it('verifies index.ts re-exports all public symbols', () => {
    expect(SparkleModule.sparkleReducer).toBeDefined();
    expect(SparkleModule.isPrintableChar).toBeDefined();
    expect(SparkleModule.INITIAL_SPARKLE_STATE).toBeDefined();
    expect(SparkleModule.INITIAL_SPARKLE_CONTEXT).toBeDefined();
    expect(SparkleModule.fetchSparkle).toBeDefined();
    expect(SparkleModule.getCsrfToken).toBeDefined();
    expect(SparkleModule.parseSseEvents).toBeDefined();
    expect(SparkleModule.DEFAULT_SPARKLE_TIMEOUT_MS).toBe(200);
    expect(SparkleModule.MAX_SPARKLE_RESPONSE_BYTES).toBe(8192);
    expect(SparkleModule.sparklePluginKey).toBeDefined();
    expect(SparkleModule.sparkleCompletionPlugin).toBeDefined();
    expect(SparkleModule.createSparkleCompletionPlugin).toBeDefined();
    expect(SparkleModule.acceptSparkleSuggestion).toBeDefined();
    expect(SparkleModule.dismissSparkleSuggestion).toBeDefined();
    expect(SparkleModule.SparkleOverlayPortal).toBeDefined();
  });

  it('covers remaining edge branches in sparkleMachine', () => {
    // 1. IDLE + RESET
    const resetFromIdle = sparkleReducer(INITIAL_SPARKLE_STATE, { type: 'RESET' });
    expect(resetFromIdle.name).toBe('IDLE');

    // 2. TYPING + non-printable char
    const typingState: SparkleModule.SparkleState = {
      name: 'TYPING',
      context: { typedCount: 4, suggestion: '', requestId: null, error: null },
    };
    const nonPrintableInTyping = sparkleReducer(typingState, {
      type: 'TYPE_CHAR',
      isCollapsed: true,
      isPrintable: false,
    });
    expect(nonPrintableInTyping.name).toBe('TYPING');

    // 3. TYPING + DISMISS
    const dismissInTyping = sparkleReducer(typingState, { type: 'DISMISS' });
    expect(dismissInTyping.name).toBe('IDLE');

    // 4. FETCHING + non-collapsed TYPE_CHAR
    const fetchingState: SparkleModule.SparkleState = {
      name: 'FETCHING',
      context: { typedCount: 4, suggestion: '', requestId: null, error: null },
    };
    const nonCollapsedInFetching = sparkleReducer(fetchingState, {
      type: 'TYPE_CHAR',
      isCollapsed: false,
      isPrintable: true,
    });
    expect(nonCollapsedInFetching.name).toBe('IDLE');

    // 5. FETCHING + DISMISS
    const dismissInFetching = sparkleReducer(fetchingState, { type: 'DISMISS' });
    expect(dismissInFetching.name).toBe('IDLE');

    // 6. READY_BLINKING + RESET
    const blinkingState: SparkleModule.SparkleState = {
      name: 'READY_BLINKING',
      context: { typedCount: 4, suggestion: 'test', requestId: null, error: null },
    };
    const resetInBlinking = sparkleReducer(blinkingState, { type: 'RESET' });
    expect(resetInBlinking.name).toBe('IDLE');

    // 7. ACCEPTED / DISMISSED fallback event
    const acceptedState: SparkleModule.SparkleState = {
      name: 'ACCEPTED',
      context: { typedCount: 4, suggestion: '', requestId: null, error: null },
    };
    expect(sparkleReducer(acceptedState, { type: 'ACCEPT' }).name).toBe('IDLE');

    const dismissedState: SparkleModule.SparkleState = {
      name: 'DISMISSED',
      context: { typedCount: 4, suggestion: '', requestId: null, error: null },
    };
    expect(sparkleReducer(dismissedState, { type: 'ACCEPT' }).name).toBe('IDLE');
  });

  it('covers SparkleCompletionPlugin edge branches', () => {
    let capturedPluginState: SparklePluginState | null = null;
    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [editorSchema.text('First line')]),
    ]);

    const plugin = createSparkleCompletionPlugin({
      surface: 'doc',
      onStateChange: (state) => {
        capturedPluginState = state;
      },
    });

    const state = EditorState.create({
      doc,
      schema: editorSchema,
      plugins: [plugin, history()],
    });

    const activeView = new EditorView(container, { state });
    view = activeView;
    activeView.dispatch(activeView.state.tr);
    expect(capturedPluginState).not.toBeNull();

    // 1. handleKeyDown when NOT in READY_BLINKING returns false
    const keyEvent = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true });
    const handled = activeView.someProp('handleKeyDown', (f) => f(activeView, keyEvent));
    expect(handled).toBeFalsy();

    // 2. handleTextInput when NOT in READY_BLINKING returns false
    const inputHandled = activeView.someProp('handleTextInput', (f) => f(activeView, 1, 1, 'x', () => activeView.state.tr));
    expect(inputHandled).toBeFalsy();

    // 3. acceptSparkleSuggestion with null activePos returns false
    const tr = activeView.state.tr;
    tr.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: 'abc', requestId: null, error: null },
      },
      activeSuggestion: 'abc',
      activePos: null,
    });
    activeView.dispatch(tr);
    expect(acceptSparkleSuggestion(activeView)).toBe(false);

    // 4. handleTextInput matching final character of suggestion completes suggestion
    const currentPos = activeView.state.selection.from;
    const tr2 = activeView.state.tr;
    tr2.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: 'z', requestId: null, error: null },
      },
      activeSuggestion: 'z',
      activePos: currentPos,
      coords: { top: 20, left: 30 },
    });
    activeView.dispatch(tr2);

    activeView.someProp('handleTextInput', (f) => f(activeView, currentPos, currentPos, 'z', () => activeView.state.tr));
    const afterFinalChar = sparklePluginKey.getState(activeView.state);
    expect(afterFinalChar?.machine.name).toBe('IDLE');

    // 5. Cursor movement in READY_BLINKING dismisses suggestion
    const tr3 = view.state.tr;
    tr3.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: 'hello', requestId: null, error: null },
      },
      activeSuggestion: 'hello',
      activePos: 2,
      coords: { top: 20, left: 30 },
    });
    view.dispatch(tr3);

    // Dispatch a transaction changing selection away from activePos (2 -> 5)
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 5)));
    const postMoveState = sparklePluginKey.getState(view.state);
    expect(postMoveState?.machine.name).toBe('IDLE');

    // 6. Expanding selection from empty to non-empty clears debounce and aborts
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 1, 4)));

    // 7. Document change maps decorations
    const trDecorated = view.state.tr;
    trDecorated.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: 'more', requestId: null, error: null },
      },
      activeSuggestion: 'more',
      activePos: 1,
      coords: { top: 10, left: 10 },
    });
    view.dispatch(trDecorated);

    const docChangeTr = view.state.tr.insertText('Inserted ', 1);
    view.dispatch(docChangeTr);

    // 8. Clicking DOM badge element
    const domBadge = container.querySelector<HTMLDivElement>('.sparkle-badge');
    if (domBadge) {
      domBadge.click();
    }
  });

  it('covers SparkleOverlayPortal branches including null view, fallback accept, and catch blocks', () => {
    // 1. Render portal with view = null
    const { unmount } = render(<SparkleOverlayPortal view={null} testId="portal-null" />);
    expect(screen.getByTestId('portal-null')).toBeDefined();
    unmount();

    // 2. Render with active editor and test fallback onAccept (calling acceptSparkleSuggestion)
    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [editorSchema.text('Portal test')]),
    ]);
    const plugin = createSparkleCompletionPlugin({ surface: 'doc' });
    const state = EditorState.create({ doc, schema: editorSchema, plugins: [plugin] });
    const portalEditorView = new EditorView(container, { state });
    view = portalEditorView;

    const currentPos = portalEditorView.state.selection.from;
    act(() => {
      const tr = portalEditorView.state.tr;
      tr.setMeta(sparklePluginKey, {
        type: 'SET_MACHINE_STATE',
        machine: {
          name: 'READY_BLINKING',
          context: { typedCount: 4, suggestion: ' accepted', requestId: null, error: null },
        },
        activeSuggestion: ' accepted',
        activePos: currentPos,
        coords: { top: 10, left: 20 },
      });
      portalEditorView.dispatch(tr);
    });

    const { unmount: unmountActive } = render(
      <SparkleOverlayPortal view={portalEditorView} testId="portal-fallback-accept" />,
    );

    const badge = screen.getByTestId('portal-fallback-accept');
    fireEvent.click(badge);
    expect(view.state.doc.textContent).toBe(' acceptedPortal test');
    unmountActive();

    // 3. Test coordsAtPos error catch in updatePosition
    const badView = {
      state: view.state,
      dom: document.createElement('div'),
      coordsAtPos: () => {
        throw new Error('Coordinates calculation error');
      },
    } as unknown as EditorView;

    const { unmount: unmountBad } = render(
      <SparkleOverlayPortal view={badView} testId="portal-bad-coords" />,
    );
    unmountBad();
  });

  it('covers sparkleClient stream buffer edge cases and text fallback without done', async () => {
    // 1. Stream buffer with leftover text after stream ends (without trailing \n\n)
    const sseWithTrailingBuffer =
      'event: completion\ndata: {"text": "trailing", "tokens": 2}\n\nevent: done\ndata: {"status": "ok", "ttft_ms": 10, "total_ms": 25}';

    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(ctrl) {
        ctrl.enqueue(encoder.encode(sseWithTrailingBuffer));
        ctrl.close();
      },
    });

    const mockFetch = vi.fn().mockResolvedValue(
      new Response(stream, {
        status: 200,
        headers: { 'content-type': 'text/event-stream' },
      }),
    );

    const baseOpts: SparkleClientOptions = {
      projectId: '11111111-1111-1111-1111-111111111111',
      surface: 'doc',
      prefix: 'a',
      suffix: 'b',
      csrfToken: 'test-csrf-token',
      fetchFn: mockFetch,
    };

    const res = await fetchSparkle(baseOpts);
    expect(res.status).toBe('ok');
    expect(res.text).toBe('trailing');
    expect(res.tokens).toBe(2);

    // 2. Stream with unknown event in trailing buffer
    const badTrailingStream = new ReadableStream<Uint8Array>({
      start(ctrl) {
        ctrl.enqueue(encoder.encode('event: unknown_trailing\ndata: 123'));
        ctrl.close();
      },
    });
    const mockBadFetch = vi.fn().mockResolvedValue(new Response(badTrailingStream, { status: 200 }));
    await expect(fetchSparkle({ ...baseOpts, fetchFn: mockBadFetch })).rejects.toThrow(/Unknown SSE event/);

    // 3. Text response fallback without done event throws
    const mockNoDoneFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: null,
      text: () => Promise.resolve('event: completion\ndata: {"text": "nodone"}\n\n'),
    });

    await expect(
      fetchSparkle({
        ...baseOpts,
        fetchFn: mockNoDoneFetch,
      }),
    ).rejects.toThrow(/Sparkle stream ended without done event/);

    // 4. Text fallback with unknown event throws
    const mockUnknownTextFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: null,
      text: () => Promise.resolve('event: weird\ndata: 123\n\n'),
    });
    await expect(
      fetchSparkle({
        ...baseOpts,
        fetchFn: mockUnknownTextFetch,
      }),
    ).rejects.toThrow(/Unknown SSE event/);

    // 5. In-flight abort signal listener
    const abortCtrl = new AbortController();
    const mockSlowFetch = vi.fn().mockImplementation((_url, init: RequestInit) => {
      return new Promise((_, reject) => {
        init.signal?.addEventListener('abort', () => {
          reject(new Error('User aborted mid-stream'));
        });
      });
    });

    const slowPromise = fetchSparkle({
      ...baseOpts,
      signal: abortCtrl.signal,
      fetchFn: mockSlowFetch,
    });
    abortCtrl.abort(new Error('User aborted mid-stream'));
    await expect(slowPromise).rejects.toThrow(/User aborted mid-stream/);

    // 6. Caller signal already aborted with no reason
    const preAborted = new AbortController();
    preAborted.abort();
    await expect(
      fetchSparkle({
        ...baseOpts,
        signal: preAborted.signal,
      }),
    ).rejects.toThrow(/aborted/i);

    // 7. getCsrfToken when document is undefined
    const origDoc = globalThis.document;
    // @ts-expect-error test undefined document
    delete globalThis.document;
    expect(getCsrfToken()).toBeNull();
    globalThis.document = origDoc;

    // 8. generateClientRequestId when crypto is undefined
    const origCrypto = globalThis.crypto;
    // @ts-expect-error test undefined crypto
    delete globalThis.crypto;
    expect(generateClientRequestId()).toBe('00000000-0000-4000-8000-000000000000');
    globalThis.crypto = origCrypto;
  });

  it('covers triggerFetch rejection, non-empty selection typing, and key capture in SparkleCompletionPlugin', async () => {
    vi.useFakeTimers();

    // 1. triggerFetch catch block when fetcher throws
    const failingFetch = vi.fn().mockRejectedValue(new Error('Backend offline'));
    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [editorSchema.text('hello')]),
    ]);

    const plugin = createSparkleCompletionPlugin({
      surface: 'doc',
      debounceMs: 50,
      fetchFn: failingFetch,
    });

    const state = EditorState.create({ doc, schema: editorSchema, plugins: [plugin] });
    view = new EditorView(container, { state });

    const keyEvent = new KeyboardEvent('keydown', { key: 'a', bubbles: true, cancelable: true });
    view.dom.dispatchEvent(keyEvent);
    view.dom.dispatchEvent(keyEvent);
    view.dom.dispatchEvent(keyEvent);
    view.dom.dispatchEvent(keyEvent);

    vi.advanceTimersByTime(50);
    await Promise.resolve();
    await Promise.resolve();

    const postErrState = sparklePluginKey.getState(view.state);
    expect(postErrState?.machine.name).toBe('IDLE');

    // 2. Typing while selection is non-empty
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 1, 3)));
    view.dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', bubbles: true }));

    // 3. Tab and Escape key events in onKeyDownCapture (which ignore them early)
    view.dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    view.dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

    vi.useRealTimers();
  });

  it('covers decoration mapping on docChanged without sparkle meta, handleKeyDown other keys, and updateBadgePosition null parent', () => {
    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [editorSchema.text('hello world')]),
    ]);

    const plugin = createSparkleCompletionPlugin({
      surface: 'doc',
      debounceMs: 50,
    });

    const state = EditorState.create({ doc, schema: editorSchema, plugins: [plugin] });
    view = new EditorView(container, { state });

    // 1. Dispatch SET_MACHINE_STATE with activeSuggestion to create decorations
    const currentPos = view.state.selection.from;
    const tr1 = view.state.tr;
    tr1.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: ' extension', requestId: null, error: null },
      },
      activeSuggestion: ' extension',
      activePos: currentPos,
      coords: { top: 10, left: 20 },
    });
    view.dispatch(tr1);

    const readyState = sparklePluginKey.getState(view.state);
    expect(readyState?.machine.name).toBe('READY_BLINKING');
    expect(readyState?.decorations).toBeDefined();

    // 2. Test handleKeyDown with non-Tab non-Escape key in READY_BLINKING
    const handledOtherKey = plugin.props.handleKeyDown?.call(
      plugin,
      view,
      new KeyboardEvent('keydown', { key: 'ArrowDown' }),
    );
    expect(handledOtherKey).toBe(false);

    // 3. Dispatch doc change without sparkle meta -> triggers decoration mapping
    const tr2 = view.state.tr.insertText('!', 1);
    view.dispatch(tr2);

    // 4. Detach editorView.dom from parent and test updateBadgePosition null parent
    const detachedDom = view.dom;
    detachedDom.remove();
    // Dispatch READY_BLINKING with coords matching current selection while dom has null parent
    const detachedPos = view.state.selection.from;
    const tr3 = view.state.tr;
    tr3.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: ' detached', requestId: null, error: null },
      },
      activeSuggestion: ' detached',
      activePos: detachedPos,
      coords: { top: 20, left: 30 },
    });
    view.dispatch(tr3);
  });

  it('covers SparkleOverlayPortal catch block and requestAnimationFrame callback loop', () => {
    // 1. view whose coordsAtPos throws during READY_BLINKING
    const throwingView = {
      dom: document.createElement('div'),
      state: {
        selection: { from: 1, to: 1, empty: true },
      },
      coordsAtPos: () => {
        throw new Error('Node not found');
      },
    } as unknown as EditorView;

    const getStateSpy = vi.spyOn(sparklePluginKey, 'getState').mockReturnValue({
      machine: { name: 'READY_BLINKING', context: INITIAL_SPARKLE_CONTEXT },
      decorations: DecorationSet.empty,
      activeSuggestion: 'hello',
      activePos: 1,
      coords: { top: 10, left: 20 },
    });

    const { unmount } = render(<SparkleOverlayPortal view={throwingView} />);
    unmount();
    getStateSpy.mockRestore();

    // 2. requestAnimationFrame execution
    let capturedRafCb: FrameRequestCallback = () => undefined;
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      capturedRafCb = cb;
      return 999;
    });

    const validView = {
      dom: document.createElement('div'),
      state: {
        selection: { from: 1, to: 1, empty: true },
      },
      coordsAtPos: () => ({ top: 100, left: 200 }),
    } as unknown as EditorView;

    const portal = render(<SparkleOverlayPortal view={validView} />);
    capturedRafCb(performance.now());
    portal.unmount();
  });

  it('covers sparkleClient processSseBlock with tokens, ttft, totalMs, and trailing buffer', async () => {
    const baseOpts: SparkleClientOptions = {
      projectId: '11111111-1111-1111-1111-111111111111',
      surface: 'doc',
      prefix: 'test',
      suffix: '',
    };

    // 1. Non-streaming body with tokens, ttft_ms, total_ms
    const mockNonStreamingFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: null,
      text: () =>
        Promise.resolve(
          'event: completion\ndata: {"text":" completed","tokens":7}\n\nevent: done\ndata: {"status":"ok","ttft_ms":35,"total_ms":80}\n\n',
        ),
    });

    const nonStreamRes = await fetchSparkle({
      ...baseOpts,
      fetchFn: mockNonStreamingFetch,
    });
    expect(nonStreamRes.status).toBe('ok');
    expect(nonStreamRes.text).toBe(' completed');
    expect(nonStreamRes.tokens).toBe(7);
    expect(nonStreamRes.ttft_ms).toBe(35);
    expect(nonStreamRes.total_ms).toBe(80);

    // 2. Trailing buffer without double newline at end of stream
    const encoder = new TextEncoder();
    const trailingChunk1 = encoder.encode('event: completion\ndata: {"text":" stream"}\n\n');
    const trailingChunk2 = encoder.encode('event: done\ndata: {"status":"ok","ttft_ms":20,"total_ms":50}');
    let chunkIndex = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (chunkIndex === 0) {
          controller.enqueue(trailingChunk1);
          chunkIndex++;
        } else if (chunkIndex === 1) {
          controller.enqueue(trailingChunk2);
          chunkIndex++;
        } else {
          controller.close();
        }
      },
    });

    const mockTrailingStreamFetch = vi.fn().mockResolvedValue(
      new Response(stream, {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    );

    const trailingRes = await fetchSparkle({
      ...baseOpts,
      fetchFn: mockTrailingStreamFetch,
    });
    expect(trailingRes.status).toBe('ok');
    expect(trailingRes.text).toBe(' stream');
    expect(trailingRes.ttft_ms).toBe(20);
    expect(trailingRes.total_ms).toBe(50);

    // 3. parseSseEvents edge branches: comment only, non-event non-data line, default message event
    const commentOnly = SparkleModule.parseSseEvents(': comment only\n\n');
    expect(commentOnly).toEqual([]);

    const defaultMsg = SparkleModule.parseSseEvents('id: 99\nretry: 500\ndata: payload\n\n');
    expect(defaultMsg).toEqual([{ event: 'message', data: 'payload' }]);

    // 4. Pre-aborted signal with undefined reason
    const abortNoReason = {
      aborted: true,
      reason: undefined,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as AbortSignal;
    await expect(fetchSparkle({ ...baseOpts, signal: abortNoReason })).rejects.toThrow(/Aborted/);
  });

  it('covers sparkleMachine TYPE_CHAR with isPrintable false', () => {
    const fetchingState: SparkleModule.SparkleState = {
      name: 'FETCHING',
      context: { typedCount: 4, suggestion: '', requestId: null, error: null },
    };
    const nonPrintableInFetching = sparkleReducer(fetchingState, {
      type: 'TYPE_CHAR',
      isCollapsed: true,
      isPrintable: false,
    });
    expect(nonPrintableInFetching.name).toBe('IDLE');

    const nonPrintableInIdle = sparkleReducer(INITIAL_SPARKLE_STATE, {
      type: 'TYPE_CHAR',
      isCollapsed: true,
      isPrintable: false,
    });
    expect(nonPrintableInIdle.name).toBe('IDLE');
  });

  it('covers SparkleCompletionPlugin with renderOverlay false and destroy cleanup', () => {
    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [editorSchema.text('sample text')]),
    ]);

    const pluginNoOverlay = createSparkleCompletionPlugin({
      surface: 'doc',
      renderOverlay: false,
    });

    const state = EditorState.create({ doc, schema: editorSchema, plugins: [pluginNoOverlay] });
    const localView = new EditorView(container, { state });

    // READY_BLINKING with coords null to test false branch of pluginState.coords
    const tr = localView.state.tr;
    tr.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: ' more', requestId: null, error: null },
      },
      activeSuggestion: ' more',
      activePos: 1,
      coords: null,
    });
    localView.dispatch(tr);

    // Destroy localView where renderOverlay was false (badgeEl is null)
    localView.destroy();
  });

  it('covers SparkleOverlayPortal containerRef, detached view dom fallback, and null view click', () => {
    // 1. Explicit containerRef
    const customContainer = document.createElement('div');
    document.body.appendChild(customContainer);
    const customRef = { current: customContainer };

    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [editorSchema.text('text')]),
    ]);
    const plugin = createSparkleCompletionPlugin({ surface: 'doc' });
    const state = EditorState.create({ doc, schema: editorSchema, plugins: [plugin] });
    const testView = new EditorView(container, { state });

    const portalWithRef = render(
      <SparkleOverlayPortal view={testView} containerRef={customRef} />,
    );
    portalWithRef.unmount();
    customContainer.remove();

    // 2. Click with no view and no onAccept
    const noViewPortal = render(<SparkleOverlayPortal view={null} />);
    const badge = noViewPortal.container.querySelector('.sparkle-badge');
    expect(badge).not.toBeNull();
    if (badge) {
      fireEvent.click(badge);
    }
    noViewPortal.unmount();

    // 3. Detached view in SparkleOverlayPortal falling back to view.dom
    const detachedDom = testView.dom;
    detachedDom.remove();
    const detachedPortal = render(<SparkleOverlayPortal view={testView} />);
    detachedPortal.unmount();
    testView.destroy();
  });

  it('covers caret move during fetch, empty completion response, and destroyed view on error', async () => {
    vi.useFakeTimers();

    const doc = editorSchema.nodes.doc.create(null, [
      editorSchema.nodes.paragraph.create(null, [editorSchema.text('hello world')]),
    ]);

    // 1. Caret moved before fetch resolves
    let resolveSlowFetch: (val: SparkleResponse) => void = () => undefined;
    const slowFetcher = vi.fn().mockImplementation(() => {
      return new Promise<SparkleResponse>((res) => {
        resolveSlowFetch = res;
      });
    });

    const plugin = createSparkleCompletionPlugin({
      surface: 'doc',
      debounceMs: 50,
      fetchFn: slowFetcher,
    });

    const state = EditorState.create({ doc, schema: editorSchema, plugins: [plugin] });
    const localView = new EditorView(container, { state });

    // Type 4 characters to trigger fetch
    const keyEvent = new KeyboardEvent('keydown', { key: 'a', bubbles: true });
    localView.dom.dispatchEvent(keyEvent);
    localView.dom.dispatchEvent(keyEvent);
    localView.dom.dispatchEvent(keyEvent);
    localView.dom.dispatchEvent(keyEvent);

    vi.advanceTimersByTime(50);
    expect(slowFetcher).toHaveBeenCalledTimes(1);

    // Now move caret away before fetch resolves
    localView.dispatch(localView.state.tr.setSelection(TextSelection.create(localView.state.doc, 5, 5)));

    // Resolve fetch with ok response
    resolveSlowFetch({
      status: 'ok',
      text: ' suggestion',
    });
    await Promise.resolve();
    await Promise.resolve();

    // State should reset to IDLE because selection moved away
    const postMoveState = sparklePluginKey.getState(localView.state);
    expect(postMoveState?.machine.name).toBe('IDLE');

    // 2. Empty completion response (status ok but empty text)
    const emptyFetcher = vi.fn().mockResolvedValue({
      status: 'ok',
      text: '',
    });
    const emptyPlugin = createSparkleCompletionPlugin({
      surface: 'doc',
      debounceMs: 50,
      fetchFn: emptyFetcher,
    });
    const emptyState = EditorState.create({ doc, schema: editorSchema, plugins: [emptyPlugin] });
    const emptyView = new EditorView(container, { state: emptyState });

    emptyView.dom.dispatchEvent(keyEvent);
    emptyView.dom.dispatchEvent(keyEvent);
    emptyView.dom.dispatchEvent(keyEvent);
    emptyView.dom.dispatchEvent(keyEvent);

    vi.advanceTimersByTime(50);
    await Promise.resolve();
    await Promise.resolve();

    const postEmptyState = sparklePluginKey.getState(emptyView.state);
    expect(postEmptyState?.machine.name).toBe('IDLE');
    emptyView.destroy();

    // 3. Destroyed view before error caught
    let rejectErrorFetch: (err: Error) => void = () => undefined;
    const errorFetcher = vi.fn().mockImplementation(() => {
      return new Promise<SparkleResponse>((_, rej) => {
        rejectErrorFetch = rej;
      });
    });
    const errPlugin = createSparkleCompletionPlugin({
      surface: 'doc',
      debounceMs: 50,
      fetchFn: errorFetcher,
    });
    const errState = EditorState.create({ doc, schema: editorSchema, plugins: [errPlugin] });
    const errView = new EditorView(container, { state: errState });

    errView.dom.dispatchEvent(keyEvent);
    errView.dom.dispatchEvent(keyEvent);
    errView.dom.dispatchEvent(keyEvent);
    errView.dom.dispatchEvent(keyEvent);

    vi.advanceTimersByTime(50);
    // Destroy errView while request is in flight
    errView.destroy();

    // Reject fetch now
    rejectErrorFetch(new Error('Offline'));
    await Promise.resolve();
    await Promise.resolve();

    // 4. Keystroke while view is in READY_BLINKING
    const readyPlugin = createSparkleCompletionPlugin({ surface: 'doc' });
    const readyStateInit = EditorState.create({ doc, schema: editorSchema, plugins: [readyPlugin] });
    const readyView = new EditorView(container, { state: readyStateInit });
    const readyTr = readyView.state.tr;
    readyTr.setMeta(sparklePluginKey, {
      type: 'SET_MACHINE_STATE',
      machine: { name: 'READY_BLINKING', context: { ...INITIAL_SPARKLE_CONTEXT, suggestion: 'hello' } },
      activeSuggestion: 'hello',
      activePos: 1,
    });
    readyView.dispatch(readyTr);
    readyView.dom.dispatchEvent(keyEvent);
    readyView.destroy();

    localView.destroy();
    vi.useRealTimers();
  });
});
