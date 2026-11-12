/**
 * SparkleOverlayPortal (KB-P5-08, S9.1, S9.3).
 * React portal/overlay for the 18px x 18px blinking caret badge.
 * Positions strictly via CSSOM transform (never setAttribute style) to comply with strict CSP.
 */

import {
  useEffect,
  useRef,
  useState,
  useCallback,
  type JSX,
  type MouseEvent,
} from 'react';
import type { EditorView } from 'prosemirror-view';
import {
  sparklePluginKey,
  acceptSparkleSuggestion,
  type SparklePluginState,
} from './SparkleCompletionPlugin';
import './sparkle.css';

export interface SparkleOverlayPortalProps {
  view: EditorView | null;
  containerRef?: React.RefObject<HTMLElement | null> | undefined;
  onAccept?: (() => void) | undefined;
  testId?: string | undefined;
}

export function SparkleOverlayPortal({
  view,
  containerRef,
  onAccept,
  testId = 'sparkle-badge',
}: SparkleOverlayPortalProps): JSX.Element | null {
  const badgeRef = useRef<HTMLDivElement | null>(null);
  const [pluginState, setPluginState] = useState<SparklePluginState | null>(
    () => {
      if (!view) return null;
      return sparklePluginKey.getState(view.state) ?? null;
    },
  );

  const currentLiveState = view
    ? sparklePluginKey.getState(view.state) ?? null
    : null;
  const activeState = currentLiveState ?? pluginState;

  const updatePosition = useCallback(() => {
    if (!view || !badgeRef.current) return;
    const currentState = sparklePluginKey.getState(view.state);
    setPluginState(currentState ?? null);

    if (
      currentState?.machine.name !== 'READY_BLINKING' ||
      currentState.activePos === null
    ) {
      badgeRef.current.style.display = 'none';
      return;
    }

    try {
      const coords = view.coordsAtPos(currentState.activePos);
      const container =
        containerRef?.current ?? view.dom.parentElement ?? view.dom;
      const containerRect = container.getBoundingClientRect();

      const relX = coords.left - containerRect.left;
      const relY = coords.top - containerRect.top;

      badgeRef.current.style.transform = `translate3d(${String(Math.round(relX))}px, ${String(Math.round(relY))}px, 0)`;
      badgeRef.current.style.display = 'flex';
    } catch {
      badgeRef.current.style.display = 'none';
    }
  }, [view, containerRef]);

  useEffect(() => {
    if (!view) return;

    updatePosition();

    let animId: number;
    const checkState = (): void => {
      updatePosition();
      animId = requestAnimationFrame(checkState);
    };

    animId = requestAnimationFrame(checkState);

    return () => {
      cancelAnimationFrame(animId);
    };
  }, [view, updatePosition]);

  const handleClick = (e: MouseEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    if (onAccept) {
      onAccept();
    } else if (view) {
      acceptSparkleSuggestion(view);
    }
  };

  const isBlinking = activeState?.machine.name === 'READY_BLINKING';

  return (
    <>
      <div
        ref={badgeRef}
        className={`sparkle-badge ${isBlinking ? 'sparkle-badge--visible' : ''}`}
        role="button"
        aria-label="Accept AI suggestion (Tab)"
        tabIndex={-1}
        data-testid={testId}
        onClick={handleClick}
      >
        ✨
      </div>
      <div
        className="sparkle-sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
        data-testid={`${testId}-announcer`}
      >
        {isBlinking ? 'Suggestion available. Press Tab to accept.' : ''}
      </div>
    </>
  );
}
