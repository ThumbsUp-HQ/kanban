import { type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export const HINT_ROOT_ID = 'kb-hint-root';

/**
 * Returns or creates the singleton hint portal root element in document.body.
 */
export function getOrCreateHintRoot(customDoc?: Document | null): HTMLElement | null {
  const doc =
    customDoc !== undefined
      ? customDoc
      : typeof document !== 'undefined'
        ? document
        : null;

  if (!doc) {
    return null;
  }

  let root = doc.getElementById(HINT_ROOT_ID);
  if (!root) {
    root = doc.createElement('div');
    root.id = HINT_ROOT_ID;
    doc.body.appendChild(root);
  }
  return root;
}

export interface HintPortalProps {
  children: ReactNode;
  containerOverride?: HTMLElement | null;
}

/**
 * Singleton portal rendering children into #kb-hint-root.
 */
export function HintPortal({ children, containerOverride }: HintPortalProps) {
  const container = containerOverride !== undefined ? containerOverride : getOrCreateHintRoot();
  if (!container) {
    return null;
  }
  return createPortal(children, container);
}
