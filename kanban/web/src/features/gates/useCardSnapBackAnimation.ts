// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { useRef, useCallback, useEffect } from 'react';

export const SNAPBACK_DURATION_MS = 240;
export const SNAPBACK_TIMING_FUNCTION = 'cubic-bezier(0.2, 0, 0, 1)';

export function isReducedMotionPreferred(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export interface SnapBackOptions {
  durationMs?: number | undefined;
  timingFunction?: string | undefined;
  onComplete?: (() => void) | undefined;
}

/**
 * Runs a GPU-accelerated 240ms FLIP animation returning an element from firstRect back to its current layout position.
 * If prefers-reduced-motion: reduce is active, skips transform and executes in 0ms.
 */
export function animateCardSnapBack(
  element: HTMLElement | null,
  firstRect: { left: number; top: number } | null | undefined,
  options: SnapBackOptions = {},
): number {
  if (!element || !firstRect) {
    options.onComplete?.();
    return 0;
  }

  if (isReducedMotionPreferred()) {
    element.style.transform = '';
    element.style.transition = '';
    options.onComplete?.();
    return 0;
  }

  const lastRect = element.getBoundingClientRect();
  const dx = firstRect.left - lastRect.left;
  const dy = firstRect.top - lastRect.top;

  // If displacement is negligible, skip
  if (Math.abs(dx) < 1 && Math.abs(dy) < 1) {
    options.onComplete?.();
    return 0;
  }

  const duration = options.durationMs ?? SNAPBACK_DURATION_MS;
  const timing = options.timingFunction ?? SNAPBACK_TIMING_FUNCTION;

  // Invert
  element.style.transition = 'none';
  element.style.transform = `translate3d(${String(dx)}px, ${String(dy)}px, 0)`;

  // Force layout reflow so the browser registers inverted starting position
  if (element.offsetHeight) {
    // reflow triggered
  }

  // Play
  requestAnimationFrame(() => {
    element.style.transition = `transform ${String(duration)}ms ${timing}`;
    element.style.transform = 'translate3d(0, 0, 0)';
  });

  let safetyTimeout: ReturnType<typeof setTimeout> | null = null;

  const cleanup = (): void => {
    if (safetyTimeout !== null) {
      clearTimeout(safetyTimeout);
      safetyTimeout = null;
    }
    element.removeEventListener('transitionend', handleTransitionEnd);
    element.style.transition = '';
    element.style.transform = '';
    options.onComplete?.();
  };

  const handleTransitionEnd = (e: TransitionEvent): void => {
    if (e.target === element && e.propertyName === 'transform') {
      cleanup();
    }
  };

  element.addEventListener('transitionend', handleTransitionEnd);

  // Safety timer in case transitionend is canceled or does not fire
  safetyTimeout = setTimeout(cleanup, duration + 50);

  return duration;
}

/**
 * Hook providing card position tracking and snap-back invocation for Kanban cards.
 */
export function useCardSnapBackAnimation() {
  const cardRectsRef = useRef<Map<string, { left: number; top: number }>>(new Map());

  const recordPosition = useCallback((issueKey: string, element: HTMLElement | null): void => {
    if (!element) {
      cardRectsRef.current.delete(issueKey);
      return;
    }
    const rect = element.getBoundingClientRect();
    cardRectsRef.current.set(issueKey, { left: rect.left, top: rect.top });
  }, []);

  const triggerSnapBack = useCallback(
    (issueKey: string, element: HTMLElement | null, options: SnapBackOptions = {}): number => {
      const recorded = cardRectsRef.current.get(issueKey);
      cardRectsRef.current.delete(issueKey);
      return animateCardSnapBack(element, recorded, options);
    },
    [],
  );

  useEffect(() => {
    const rects = cardRectsRef.current;
    return () => {
      rects.clear();
    };
  }, []);

  return {
    recordPosition,
    triggerSnapBack,
    animateCardSnapBack,
  };
}
