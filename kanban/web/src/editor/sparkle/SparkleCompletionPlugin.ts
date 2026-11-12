/**
 * ProseMirror SparkleCompletionPlugin (KB-P5-08, S9.1, S9.3, S15.2).
 * Integrates S9.1 state machine, Decoration.widget ghost-text preview,
 * 320ms typing debounce, Tab/click accept, and Escape/cursor dismiss.
 */

import {
  Plugin,
  PluginKey,
  type EditorState,
  type Transaction,
} from 'prosemirror-state';
import { type EditorView } from 'prosemirror-view';
import { Decoration, DecorationSet } from 'prosemirror-view';
import { closeHistory } from 'prosemirror-history';
import {
  sparkleReducer,
  INITIAL_SPARKLE_STATE,
  isPrintableChar,
  type SparkleState,
} from './sparkleMachine';
import {
  fetchSparkle,
  type SparkleClientOptions,
  type EditorSurfaceKind,
} from './sparkleClient';
import './sparkle.css';

export interface SparklePluginState {
  machine: SparkleState;
  decorations: DecorationSet;
  activeSuggestion: string;
  activePos: number | null;
  coords: { top: number; left: number } | null;
}

export interface CreateSparklePluginOptions {
  surface?: EditorSurfaceKind | undefined;
  projectId?: string | undefined;
  objectId?: string | null | undefined;
  debounceMs?: number | undefined;
  timeoutMs?: number | undefined;
  fetchFn?: ((options: SparkleClientOptions) => ReturnType<typeof fetchSparkle>) | undefined;
  onStateChange?: ((state: SparklePluginState) => void) | undefined;
  renderOverlay?: boolean | undefined;
}

export const sparklePluginKey = new PluginKey<SparklePluginState>(
  'sparkleCompletion',
);

export type SparklePluginMeta =
  | {
      type: 'SET_MACHINE_STATE';
      machine: SparkleState;
      activeSuggestion?: string;
      activePos?: number | null;
      coords?: { top: number; left: number } | null;
    }
  | { type: 'ACCEPT_SUGGESTION' }
  | { type: 'DISMISS_SUGGESTION'; reason?: string };

/**
 * Accepts the currently active Sparkle completion suggestion in the editor.
 */
export function acceptSparkleSuggestion(view: EditorView): boolean {
  const pluginState = sparklePluginKey.getState(view.state);
  if (pluginState?.machine.name !== 'READY_BLINKING') {
    return false;
  }
  const suggestion = pluginState.activeSuggestion;
  const pos = pluginState.activePos;
  if (!suggestion || pos === null) return false;

  const tr = view.state.tr;
  closeHistory(tr);
  tr.insertText(suggestion, pos);
  tr.setMeta(sparklePluginKey, { type: 'ACCEPT_SUGGESTION' });
  view.dispatch(tr);
  return true;
}

/**
 * Dismisses the active Sparkle suggestion.
 */
export function dismissSparkleSuggestion(
  view: EditorView,
  reason = 'manual',
): boolean {
  const pluginState = sparklePluginKey.getState(view.state);
  if (pluginState?.machine.name !== 'READY_BLINKING') {
    return false;
  }
  const tr = view.state.tr;
  tr.setMeta(sparklePluginKey, { type: 'DISMISS_SUGGESTION', reason });
  view.dispatch(tr);
  return true;
}

/**
 * Creates the ghost-text decoration widget.
 */
function createGhostDecoration(
  pos: number,
  suggestion: string,
  doc: EditorState['doc'],
): DecorationSet {
  const widget = Decoration.widget(
    pos,
    () => {
      const span = document.createElement('span');
      span.className = 'sparkle-ghost';
      span.textContent = suggestion;
      span.setAttribute('aria-hidden', 'true');
      return span;
    },
    { side: 1, key: 'sparkle-ghost-widget' },
  );
  return DecorationSet.create(doc, [widget]);
}

/**
 * Creates the ProseMirror SparkleCompletionPlugin instance.
 */
export function createSparkleCompletionPlugin(
  options: CreateSparklePluginOptions = {},
): Plugin<SparklePluginState> {
  const surface: EditorSurfaceKind = options.surface ?? 'doc';
  const projectId = options.projectId ?? '00000000-0000-0000-0000-000000000000';
  const objectId = options.objectId ?? null;
  const debounceMs = options.debounceMs ?? 320;
  const timeoutMs = options.timeoutMs ?? 200;
  const fetcher = options.fetchFn ?? fetchSparkle;
  const shouldRenderOverlay = options.renderOverlay !== false;

  return new Plugin<SparklePluginState>({
    key: sparklePluginKey,

    state: {
      init(): SparklePluginState {
        return {
          machine: INITIAL_SPARKLE_STATE,
          decorations: DecorationSet.empty,
          activeSuggestion: '',
          activePos: null,
          coords: null,
        };
      },

      apply(tr: Transaction, prevState, _oldEditorState, newEditorState): SparklePluginState {
        const meta = tr.getMeta(sparklePluginKey) as
          | SparklePluginMeta
          | undefined;

        if (meta) {
          if (meta.type === 'SET_MACHINE_STATE') {
            const nextMachine = meta.machine;
            const nextSuggestion =
              meta.activeSuggestion ?? prevState.activeSuggestion;
            const nextPos = meta.activePos ?? prevState.activePos;
            const nextCoords = meta.coords ?? prevState.coords;

            let nextDecos = DecorationSet.empty;
            if (
              nextMachine.name === 'READY_BLINKING' &&
              nextPos !== null &&
              nextSuggestion.length > 0
            ) {
              nextDecos = createGhostDecoration(
                nextPos,
                nextSuggestion,
                newEditorState.doc,
              );
            }

            return {
              machine: nextMachine,
              decorations: nextDecos,
              activeSuggestion: nextSuggestion,
              activePos: nextPos,
              coords: nextCoords,
            };
          }

          if (meta.type === 'ACCEPT_SUGGESTION') {
            const nextMachine = sparkleReducer(prevState.machine, {
              type: 'ACCEPT',
            });
            const idleMachine = sparkleReducer(nextMachine, { type: 'RESET' });
            return {
              machine: idleMachine,
              decorations: DecorationSet.empty,
              activeSuggestion: '',
              activePos: null,
              coords: null,
            };
          }

          {
            const nextMachine = sparkleReducer(prevState.machine, {
              type: 'DISMISS',
            });
            const idleMachine = sparkleReducer(nextMachine, { type: 'RESET' });
            return {
              machine: idleMachine,
              decorations: DecorationSet.empty,
              activeSuggestion: '',
              activePos: null,
              coords: null,
            };
          }
        }

        // Map decorations if document changed without sparkle meta
        if (tr.docChanged && prevState.decorations !== DecorationSet.empty) {
          const mappedDecos = prevState.decorations.map(
            tr.mapping,
            newEditorState.doc,
          );
          return {
            ...prevState,
            decorations: mappedDecos,
          };
        }

        return prevState;
      },
    },

    props: {
      decorations(state) {
        return sparklePluginKey.getState(state)?.decorations;
      },

      handleKeyDown(view, event) {
        const pluginState = sparklePluginKey.getState(view.state);
        if (pluginState?.machine.name !== 'READY_BLINKING') {
          return false;
        }

        if (event.key === 'Tab') {
          event.preventDefault();
          return acceptSparkleSuggestion(view);
        }

        if (event.key === 'Escape') {
          event.preventDefault();
          return dismissSparkleSuggestion(view, 'escape');
        }

        return false;
      },

      handleTextInput(view, _from, _to, text) {
        const pluginState = sparklePluginKey.getState(view.state);
        if (!pluginState) return false;

        if (pluginState.machine.name === 'READY_BLINKING') {
          const suggestion = pluginState.activeSuggestion;
          if (text.length > 0 && suggestion.startsWith(text)) {
            const remaining = suggestion.slice(text.length);
            if (remaining.length === 0) {
              // Entire suggestion typed out
              const tr = view.state.tr;
              tr.setMeta(sparklePluginKey, {
                type: 'ACCEPT_SUGGESTION',
              });
              view.dispatch(tr);
            } else {
              // Advance ghost text
              const tr = view.state.tr;
              tr.setMeta(sparklePluginKey, {
                type: 'SET_MACHINE_STATE',
                machine: {
                  ...pluginState.machine,
                  context: {
                    ...pluginState.machine.context,
                    suggestion: remaining,
                  },
                },
                activeSuggestion: remaining,
              });
              view.dispatch(tr);
            }
            return false;
          }

          // Mismatched char -> dismiss
          dismissSparkleSuggestion(view, 'typing_mismatch');
          return false;
        }

        return false;
      },
    },

    view(editorView: EditorView) {
      let debounceTimer: ReturnType<typeof setTimeout> | null = null;
      let abortController: AbortController | null = null;
      let badgeEl: HTMLDivElement | null = null;
      let liveRegionEl: HTMLDivElement | null = null;

      const clearDebounce = (): void => {
        if (debounceTimer) {
          clearTimeout(debounceTimer);
          debounceTimer = null;
        }
      };

      const abortPriorRequest = (): void => {
        if (abortController) {
          abortController.abort(new Error('Sparkle request superseded by new typing'));
          abortController = null;
        }
      };

      const ensureOverlayElements = (): void => {
        if (!shouldRenderOverlay) return;
        const parent = editorView.dom.parentElement;
        if (!parent) return;

        if (!badgeEl) {
          badgeEl = parent.querySelector('.sparkle-badge');
          if (!badgeEl) {
            badgeEl = document.createElement('div');
            badgeEl.className = 'sparkle-badge';
            badgeEl.setAttribute('role', 'button');
            badgeEl.setAttribute('aria-label', 'Accept AI suggestion (Tab)');
            badgeEl.setAttribute('tabindex', '-1');
            badgeEl.textContent = '✨';
            badgeEl.style.display = 'none';

            badgeEl.addEventListener('click', (e) => {
              e.preventDefault();
              e.stopPropagation();
              acceptSparkleSuggestion(editorView);
            });

            parent.appendChild(badgeEl);
          }
        }

        if (!liveRegionEl) {
          liveRegionEl = parent.querySelector('.sparkle-sr-only');
          if (!liveRegionEl) {
            liveRegionEl = document.createElement('div');
            liveRegionEl.className = 'sparkle-sr-only';
            liveRegionEl.setAttribute('role', 'status');
            liveRegionEl.setAttribute('aria-live', 'polite');
            liveRegionEl.setAttribute('aria-atomic', 'true');
            parent.appendChild(liveRegionEl);
          }
        }
      };

      const updateBadgePosition = (coords: { top: number; left: number } | null): void => {
        if (!badgeEl) return;
        if (!coords) {
          badgeEl.style.display = 'none';
          return;
        }

        const parent = editorView.dom.parentElement;
        if (!parent) {
          badgeEl.style.display = 'none';
          return;
        }

        const parentRect = parent.getBoundingClientRect();
        const relX = coords.left - parentRect.left;
        const relY = coords.top - parentRect.top;

        badgeEl.style.transform = `translate3d(${String(Math.round(relX))}px, ${String(Math.round(relY))}px, 0)`;
        badgeEl.style.display = 'flex';
      };

      ensureOverlayElements();

      let localMachine = INITIAL_SPARKLE_STATE;

      const triggerFetch = async (targetPos?: number): Promise<void> => {
        const state = editorView.state;
        const currentSel = state.selection;
        if (!currentSel.empty) return;
        const pos = targetPos ?? currentSel.from;
        const doc = state.doc;
        const prefix = doc.textBetween(0, pos, '\n', '\n');
        const suffix = doc.textBetween(pos, doc.content.size, '\n', '\n');

        abortPriorRequest();
        abortController = new AbortController();

        const tr = editorView.state.tr;
        const currentPluginState = sparklePluginKey.getState(editorView.state);
        const nextMachine = sparkleReducer(
          localMachine.name === 'TYPING' ? localMachine : (currentPluginState?.machine ?? INITIAL_SPARKLE_STATE),
          { type: 'DEBOUNCE_PAUSE' },
        );
        localMachine = nextMachine;
        tr.setMeta(sparklePluginKey, {
          type: 'SET_MACHINE_STATE',
          machine: nextMachine,
        });
        editorView.dispatch(tr);

        try {
          const response = await fetcher({
            projectId,
            objectId,
            surface,
            prefix,
            suffix,
            timeoutMs,
            signal: abortController.signal,
          });

          if (response.status === 'ok' && response.text.length > 0) {
            const currentSelection = editorView.state.selection;
            if (currentSelection.empty && currentSelection.from === pos) {
              const coords = editorView.coordsAtPos(pos);
              const readyMachine = sparkleReducer(
                localMachine,
                {
                  type: 'FETCH_COMPLETION',
                  text: response.text,
                },
              );
              localMachine = readyMachine;

              const updateTr = editorView.state.tr;
              updateTr.setMeta(sparklePluginKey, {
                type: 'SET_MACHINE_STATE',
                machine: readyMachine,
                activeSuggestion: response.text,
                activePos: pos,
                coords: { top: coords.top, left: coords.left },
              });
              editorView.dispatch(updateTr);

              updateBadgePosition({ top: coords.top, left: coords.left });
              if (liveRegionEl) {
                liveRegionEl.textContent =
                  'Suggestion available. Press Tab to accept.';
              }
              return;
            }
          }

          // Non-ok or empty response -> reset to IDLE
          const failTr = editorView.state.tr;
          const failMachine = sparkleReducer(
            localMachine,
            { type: 'FETCH_FAIL', status: response.status },
          );
          localMachine = failMachine;
          failTr.setMeta(sparklePluginKey, {
            type: 'SET_MACHINE_STATE',
            machine: failMachine,
            activeSuggestion: '',
            activePos: null,
            coords: null,
          });
          editorView.dispatch(failTr);
          updateBadgePosition(null);
        } catch {
          if (!editorView.isDestroyed) {
            const errTr = editorView.state.tr;
            const errMachine = sparkleReducer(
              localMachine,
              { type: 'FETCH_FAIL', status: 'error' },
            );
            localMachine = errMachine;
            errTr.setMeta(sparklePluginKey, {
              type: 'SET_MACHINE_STATE',
              machine: errMachine,
              activeSuggestion: '',
              activePos: null,
              coords: null,
            });
            editorView.dispatch(errTr);
            updateBadgePosition(null);
          }
        }
      };

      const handleKeystrokeOrInput = (view: EditorView): void => {
        const sel = view.state.selection;
        if (!sel.empty) {
          clearDebounce();
          abortPriorRequest();
          localMachine = INITIAL_SPARKLE_STATE;
          return;
        }

        const currentPluginState = sparklePluginKey.getState(view.state);
        if (currentPluginState?.machine.name === 'READY_BLINKING') {
          localMachine = currentPluginState.machine;
        }

        if (localMachine.name === 'FETCHING') {
          abortPriorRequest();
        }

        const nextMachine = sparkleReducer(localMachine, {
          type: 'TYPE_CHAR',
          isCollapsed: true,
          isPrintable: true,
        });

        localMachine = nextMachine;

        if (nextMachine.name === 'TYPING') {
          clearDebounce();
          debounceTimer = setTimeout(() => {
            void triggerFetch();
          }, debounceMs);
        }
      };

      const onKeyDownCapture = (e: KeyboardEvent): void => {
        if (e.key === 'Tab' || e.key === 'Escape') {
          return;
        }
        if (isPrintableChar(e.key)) {
          handleKeystrokeOrInput(editorView);
        }
      };

      editorView.dom.addEventListener('keydown', onKeyDownCapture, true);

      return {
        update(view: EditorView, prevState: EditorState) {
          ensureOverlayElements();

          const pluginState = sparklePluginKey.getState(view.state);
          if (options.onStateChange && pluginState) {
            options.onStateChange(pluginState);
          }

          if (pluginState?.machine.name === 'READY_BLINKING') {
            const currentSel = view.state.selection;
            if (
              !currentSel.empty ||
              currentSel.from !== pluginState.activePos
            ) {
              // Cursor moved away from suggestion anchor -> dismiss
              dismissSparkleSuggestion(view, 'cursor_move');
              updateBadgePosition(null);
              return;
            }
            if (pluginState.coords) {
              updateBadgePosition(pluginState.coords);
            }
          } else {
            updateBadgePosition(null);
          }

          // If selection became non-empty, abort in-flight fetch and clear debounce
          if (!view.state.selection.empty && prevState.selection.empty) {
            clearDebounce();
            abortPriorRequest();
          }
        },

        destroy() {
          clearDebounce();
          abortPriorRequest();
          editorView.dom.removeEventListener(
            'keydown',
            onKeyDownCapture,
            true,
          );
          if (badgeEl?.parentElement) {
            badgeEl.remove();
            badgeEl = null;
          }
          if (liveRegionEl?.parentElement) {
            liveRegionEl.remove();
            liveRegionEl = null;
          }
        },
      };
    },
  });
}

export const sparkleCompletionPlugin = createSparkleCompletionPlugin;
