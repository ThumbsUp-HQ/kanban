/**
 * Global Keyboard Shortcut Dispatcher (KB-P3-34, S6.4).
 * Single global listener with composing and input boundary guards.
 */

export interface ShortcutOptions {
  readonly allowInInputs?: boolean;
}

export type ShortcutHandler = (event: KeyboardEvent) => void;

interface RegisteredShortcut {
  readonly combo: string;
  readonly handler: ShortcutHandler;
  readonly allowInInputs: boolean;
}

const registry = new Set<RegisteredShortcut>();
let globalListenerAttached = false;

/**
 * Checks whether an element is an input, textarea, select, or contenteditable.
 */
export function isEditableElement(element: Element | null): boolean {
  if (!element || !(element instanceof HTMLElement)) {
    return false;
  }
  const tag = element.tagName.toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    return true;
  }
  return (
    element.isContentEditable ||
    element.contentEditable === 'true' ||
    element.getAttribute('contenteditable') === 'true'
  );
}

/**
 * Normalizes keyboard event to compare against combo string.
 */
export function matchesCombo(event: KeyboardEvent, combo: string): boolean {
  const isMac =
    typeof navigator !== 'undefined' &&
    /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);

  const parts = combo
    .split('+')
    .map((p) => p.trim().toLowerCase());

  let reqMod = false;
  let reqCtrl = false;
  let reqMeta = false;
  let reqShift = false;
  let reqAlt = false;
  let targetKey = '';

  for (const part of parts) {
    if (part === 'mod' || part === 'cmd/ctrl') {
      reqMod = true;
    } else if (part === 'ctrl' || part === 'control') {
      reqCtrl = true;
    } else if (part === 'cmd' || part === 'meta') {
      reqMeta = true;
    } else if (part === 'shift') {
      reqShift = true;
    } else if (part === 'alt') {
      reqAlt = true;
    } else {
      targetKey = part;
    }
  }

  if (reqMod) {
    const hasMod = isMac ? event.metaKey : event.ctrlKey;
    if (!hasMod) {
      return false;
    }
  } else {
    if (reqCtrl && !event.ctrlKey) return false;
    if (reqMeta && !event.metaKey) return false;
  }

  if (reqShift && !event.shiftKey) return false;
  if (reqAlt && !event.altKey) return false;

  // Compare key
  const eventKey = event.key.toLowerCase();
  if (targetKey && eventKey !== targetKey) {
    return false;
  }

  return true;
}

function handleGlobalKeydown(event: KeyboardEvent): void {
  if (event.isComposing) {
    return;
  }

  const active = typeof document !== 'undefined' ? document.activeElement : null;
  const inInput = isEditableElement(active);

  for (const item of registry) {
    if (inInput && !item.allowInInputs) {
      continue;
    }
    if (matchesCombo(event, item.combo)) {
      item.handler(event);
      break;
    }
  }
}

function ensureListener(): void {
  if (!globalListenerAttached && typeof window !== 'undefined') {
    window.addEventListener('keydown', handleGlobalKeydown);
    globalListenerAttached = true;
  }
}

function teardownListenerIfEmpty(): void {
  if (registry.size === 0 && globalListenerAttached && typeof window !== 'undefined') {
    window.removeEventListener('keydown', handleGlobalKeydown);
    globalListenerAttached = false;
  }
}

/**
 * Registers a keyboard shortcut handler. Returns an unregister function.
 */
export function registerShortcut(
  combo: string,
  handler: ShortcutHandler,
  options?: ShortcutOptions,
): () => void {
  const item: RegisteredShortcut = {
    combo,
    handler,
    allowInInputs: options?.allowInInputs ?? false,
  };
  registry.add(item);
  ensureListener();

  return () => {
    registry.delete(item);
    teardownListenerIfEmpty();
  };
}
