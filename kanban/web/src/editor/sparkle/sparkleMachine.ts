/**
 * Pure State Machine for Sparkle Completion (KB-P5-08, S9.1, S9.3).
 * States: IDLE, TYPING, FETCHING, READY_BLINKING, ACCEPTED, DISMISSED.
 * Pure reducer without DOM, timers, or network calls for deterministic table testing.
 */

export type SparkleStateName =
  | 'IDLE'
  | 'TYPING'
  | 'FETCHING'
  | 'READY_BLINKING'
  | 'ACCEPTED'
  | 'DISMISSED';

export interface SparkleContext {
  typedCount: number;
  suggestion: string;
  requestId: string | null;
  error: string | null;
}

export interface SparkleState {
  name: SparkleStateName;
  context: SparkleContext;
}

export type SparkleDoneStatus =
  | 'ok'
  | 'empty'
  | 'timeout'
  | 'secret_scrubbed'
  | 'unavailable'
  | 'budget';

export type SparkleEvent =
  | {
      type: 'TYPE_CHAR';
      char?: string;
      isPrintable?: boolean;
      isCollapsed: boolean;
    }
  | { type: 'DEBOUNCE_PAUSE' }
  | {
      type: 'FETCH_COMPLETION';
      text: string;
      requestId?: string;
    }
  | {
      type: 'FETCH_FAIL';
      status?: SparkleDoneStatus | 'error';
      error?: string;
    }
  | { type: 'ACCEPT' }
  | {
      type: 'DISMISS';
      reason?: 'escape' | 'cursor_move' | 'selection_expanded' | 'typing_mismatch';
    }
  | { type: 'RESET' };

export const INITIAL_SPARKLE_CONTEXT: SparkleContext = {
  typedCount: 0,
  suggestion: '',
  requestId: null,
  error: null,
};

export const INITIAL_SPARKLE_STATE: SparkleState = {
  name: 'IDLE',
  context: INITIAL_SPARKLE_CONTEXT,
};

/**
 * Checks whether a single character is a printable character.
 */
export function isPrintableChar(char: string): boolean {
  if (char.length !== 1) return false;
  const code = char.charCodeAt(0);
  return code >= 32 && code !== 127;
}

/**
 * Pure reducer implementing the S9.1 zero-reflow Sparkle completion state machine.
 */
export function sparkleReducer(
  state: SparkleState,
  event: SparkleEvent,
): SparkleState {
  switch (state.name) {
    case 'IDLE': {
      if (event.type === 'TYPE_CHAR') {
        if (!event.isCollapsed || event.isPrintable === false) {
          return {
            name: 'IDLE',
            context: { ...INITIAL_SPARKLE_CONTEXT, typedCount: 0 },
          };
        }
        const nextCount = state.context.typedCount + 1;
        if (nextCount >= 4) {
          return {
            name: 'TYPING',
            context: { ...INITIAL_SPARKLE_CONTEXT, typedCount: nextCount },
          };
        }
        return {
          name: 'IDLE',
          context: { ...INITIAL_SPARKLE_CONTEXT, typedCount: nextCount },
        };
      }
      if (event.type === 'RESET') {
        return INITIAL_SPARKLE_STATE;
      }
      return state;
    }

    case 'TYPING': {
      if (event.type === 'TYPE_CHAR') {
        if (!event.isCollapsed) {
          return { name: 'IDLE', context: INITIAL_SPARKLE_CONTEXT };
        }
        if (event.isPrintable === false) {
          return state;
        }
        return {
          name: 'TYPING',
          context: {
            ...state.context,
            typedCount: state.context.typedCount + 1,
          },
        };
      }
      if (event.type === 'DEBOUNCE_PAUSE') {
        return {
          name: 'FETCHING',
          context: { ...state.context },
        };
      }
      if (event.type === 'DISMISS' || event.type === 'RESET') {
        return { name: 'IDLE', context: INITIAL_SPARKLE_CONTEXT };
      }
      return state;
    }

    case 'FETCHING': {
      if (event.type === 'FETCH_COMPLETION') {
        if (event.text && event.text.length > 0) {
          return {
            name: 'READY_BLINKING',
            context: {
              ...state.context,
              suggestion: event.text,
              requestId: event.requestId ?? null,
              error: null,
            },
          };
        }
        return { name: 'IDLE', context: INITIAL_SPARKLE_CONTEXT };
      }
      if (event.type === 'FETCH_FAIL') {
        return {
          name: 'IDLE',
          context: {
            ...INITIAL_SPARKLE_CONTEXT,
            error: event.error ?? event.status ?? null,
          },
        };
      }
      if (event.type === 'TYPE_CHAR') {
        if (event.isCollapsed && event.isPrintable !== false) {
          return {
            name: 'TYPING',
            context: {
              ...state.context,
              typedCount: state.context.typedCount + 1,
            },
          };
        }
        return { name: 'IDLE', context: INITIAL_SPARKLE_CONTEXT };
      }
      if (event.type === 'DISMISS' || event.type === 'RESET') {
        return { name: 'IDLE', context: INITIAL_SPARKLE_CONTEXT };
      }
      return state;
    }

    case 'READY_BLINKING': {
      if (event.type === 'ACCEPT') {
        return {
          name: 'ACCEPTED',
          context: { ...state.context },
        };
      }
      if (event.type === 'DISMISS') {
        return {
          name: 'DISMISSED',
          context: { ...state.context },
        };
      }
      if (event.type === 'TYPE_CHAR') {
        if (!event.isCollapsed || event.isPrintable === false) {
          return {
            name: 'DISMISSED',
            context: { ...state.context },
          };
        }
        if (
          event.char !== undefined &&
          event.char.length > 0 &&
          state.context.suggestion.startsWith(event.char)
        ) {
          const nextSuggestion = state.context.suggestion.slice(
            event.char.length,
          );
          if (nextSuggestion.length === 0) {
            return {
              name: 'ACCEPTED',
              context: { ...state.context, suggestion: '' },
            };
          }
          return {
            name: 'READY_BLINKING',
            context: { ...state.context, suggestion: nextSuggestion },
          };
        }
        return {
          name: 'DISMISSED',
          context: { ...state.context },
        };
      }
      if (event.type === 'RESET') {
        return { name: 'IDLE', context: INITIAL_SPARKLE_CONTEXT };
      }
      return state;
    }

    case 'ACCEPTED': {
      return { name: 'IDLE', context: INITIAL_SPARKLE_CONTEXT };
    }

    case 'DISMISSED': {
      return { name: 'IDLE', context: INITIAL_SPARKLE_CONTEXT };
    }
  }
}
