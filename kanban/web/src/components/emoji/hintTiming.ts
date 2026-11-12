/**
 * Framework-free timing engine for <EmojiHint> hover and focus interactions (KB-P3-31, S6.2).
 * Supports injectable clock, neighbor warmup, hover-bridge grace period, and instant focus.
 */

export const HOVER_OPEN_DELAY_MS = 180;
export const NEIGHBOR_WARMUP_WINDOW_MS = 400;
export const FOCUS_OPEN_DELAY_MS = 0;
export const BRIDGE_GRACE_MS = 120;

export interface HintClock {
  now(): number;
  setTimer(cb: () => void, ms: number): unknown;
  clearTimer(id: unknown): void;
}

export interface HintState {
  readonly openId: string | null;
  readonly restoreFocusId: string | null;
}

export interface HintController {
  pointerEnterTrigger(id: string): void;
  pointerLeaveTrigger(id: string): void;
  pointerEnterPopup(id: string): void;
  pointerLeavePopup(id: string): void;
  focus(id: string): void;
  blur(id: string): void;
  escape(): void;
  tap(id: string): void;
  close(id?: string): void;
  getState(): HintState;
  subscribe(listener: (state: HintState) => void): () => void;
}

const defaultClock: HintClock = {
  now: () => Date.now(),
  setTimer: (cb, ms) => window.setTimeout(cb, ms),
  clearTimer: (id) => {
    window.clearTimeout(id as number);
  },
};

/**
 * Creates a HintController with timing rules defined in S6.2.
 */
export function createHintController(customClock?: HintClock): HintController {
  const clock = customClock ?? defaultClock;

  let currentState: HintState = { openId: null, restoreFocusId: null };
  let lastCloseTime = -Infinity;

  let pendingOpenTimer: unknown = null;
  let pendingOpenId: string | null = null;

  let pendingCloseTimer: unknown = null;
  let pendingCloseId: string | null = null;

  const listeners = new Set<(state: HintState) => void>();

  function notify(): void {
    for (const listener of listeners) {
      listener(currentState);
    }
  }

  function setOpen(id: string): void {
    if (pendingOpenTimer !== null) {
      clock.clearTimer(pendingOpenTimer);
      pendingOpenTimer = null;
      pendingOpenId = null;
    }
    if (pendingCloseTimer !== null) {
      clock.clearTimer(pendingCloseTimer);
      pendingCloseTimer = null;
      pendingCloseId = null;
    }
    currentState = { openId: id, restoreFocusId: null };
    notify();
  }

  function setClosed(restoreId: string | null = null): void {
    if (pendingCloseTimer !== null) {
      clock.clearTimer(pendingCloseTimer);
      pendingCloseTimer = null;
      pendingCloseId = null;
    }
    currentState = { openId: null, restoreFocusId: restoreId };
    notify();
  }

  function scheduleBridgeClose(id: string): void {
    if (currentState.openId === id) {
      if (pendingCloseTimer !== null) {
        clock.clearTimer(pendingCloseTimer);
      }
      pendingCloseId = id;
      pendingCloseTimer = clock.setTimer(() => {
        pendingCloseTimer = null;
        pendingCloseId = null;
        if (currentState.openId === id) {
          lastCloseTime = clock.now();
          setClosed();
        }
      }, BRIDGE_GRACE_MS);
    }
  }

  return {
    pointerEnterTrigger(id: string): void {
      if (pendingOpenTimer !== null) {
        clock.clearTimer(pendingOpenTimer);
        pendingOpenTimer = null;
        pendingOpenId = null;
      }

      if (pendingCloseTimer !== null) {
        if (pendingCloseId === id) {
          clock.clearTimer(pendingCloseTimer);
          pendingCloseTimer = null;
          pendingCloseId = null;
          return;
        } else {
          clock.clearTimer(pendingCloseTimer);
          pendingCloseTimer = null;
          pendingCloseId = null;
          lastCloseTime = clock.now();
          currentState = { openId: null, restoreFocusId: null };
          notify();
        }
      }

      if (currentState.openId === id) {
        return;
      }

      if (currentState.openId !== null) {
        lastCloseTime = clock.now();
        currentState = { openId: null, restoreFocusId: null };
        notify();
      }

      const elapsed = clock.now() - lastCloseTime;
      if (lastCloseTime > 0 && elapsed < NEIGHBOR_WARMUP_WINDOW_MS) {
        setOpen(id);
      } else {
        pendingOpenId = id;
        pendingOpenTimer = clock.setTimer(() => {
          pendingOpenTimer = null;
          pendingOpenId = null;
          setOpen(id);
        }, HOVER_OPEN_DELAY_MS);
      }
    },

    pointerLeaveTrigger(id: string): void {
      if (pendingOpenId === id && pendingOpenTimer !== null) {
        clock.clearTimer(pendingOpenTimer);
        pendingOpenTimer = null;
        pendingOpenId = null;
      }
      scheduleBridgeClose(id);
    },

    pointerEnterPopup(id: string): void {
      if (currentState.openId === id && pendingCloseTimer !== null) {
        clock.clearTimer(pendingCloseTimer);
        pendingCloseTimer = null;
        pendingCloseId = null;
      }
    },

    pointerLeavePopup(id: string): void {
      scheduleBridgeClose(id);
    },

    focus(id: string): void {
      if (currentState.openId === id) {
        if (pendingCloseTimer !== null) {
          clock.clearTimer(pendingCloseTimer);
          pendingCloseTimer = null;
          pendingCloseId = null;
        }
        return;
      }
      if (currentState.openId !== null) {
        lastCloseTime = clock.now();
      }
      setOpen(id);
    },

    blur(id: string): void {
      if (pendingOpenId === id && pendingOpenTimer !== null) {
        clock.clearTimer(pendingOpenTimer);
        pendingOpenTimer = null;
        pendingOpenId = null;
      }
      if (currentState.openId === id) {
        lastCloseTime = clock.now();
        setClosed();
      }
    },

    escape(): void {
      if (currentState.openId !== null) {
        const prevId = currentState.openId;
        lastCloseTime = clock.now();
        setClosed(prevId);
      }
    },

    tap(id: string): void {
      if (currentState.openId === id) {
        lastCloseTime = clock.now();
        setClosed();
      } else {
        if (currentState.openId !== null) {
          lastCloseTime = clock.now();
        }
        setOpen(id);
      }
    },

    close(id?: string): void {
      if (id === undefined || currentState.openId === id) {
        if (currentState.openId !== null) {
          lastCloseTime = clock.now();
          setClosed();
        } else if (pendingOpenTimer !== null) {
          clock.clearTimer(pendingOpenTimer);
          pendingOpenTimer = null;
          pendingOpenId = null;
        }
      }
    },

    getState(): HintState {
      return currentState;
    },

    subscribe(listener: (state: HintState) => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export const defaultHintController: HintController = createHintController();
