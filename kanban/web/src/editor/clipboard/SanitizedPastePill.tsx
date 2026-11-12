/**
 * Sanitized Paste Status Pill Component (KB-P3-46, S5.2, S6.2).
 * Displays a 24x24 🧼 status pill with auto-dismiss, hover pause, and Escape dismiss.
 */

import {
  useEffect,
  useRef,
  useCallback,
  type JSX,
  type KeyboardEvent,
} from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import './SanitizedPastePill.css';

export interface SanitizedPastePillProps {
  prunedHiddenNodes?: number;
  onDismiss: () => void;
  autoDismissMs?: number;
  testId?: string;
}

export const BASE_SANITIZED_HINT =
  'Converted pasted HTML to clean Markdown - Cmd+Z to paste plain text';

export function getSanitizedTooltipText(prunedHiddenNodes?: number): string {
  if (prunedHiddenNodes && prunedHiddenNodes > 0) {
    return `${BASE_SANITIZED_HINT} (stripped ${String(prunedHiddenNodes)} hidden element(s))`;
  }
  return BASE_SANITIZED_HINT;
}

export function SanitizedPastePill({
  prunedHiddenNodes = 0,
  onDismiss,
  autoDismissMs = 4000,
  testId = 'sanitized-paste-pill',
}: SanitizedPastePillProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const remainingMsRef = useRef<number>(autoDismissMs);
  const startTimestampRef = useRef<number>(0);
  const isHoveredOrFocusedRef = useRef<boolean>(false);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startTimer = useCallback(
    (duration: number) => {
      clearTimer();
      startTimestampRef.current = Date.now();
      timerRef.current = setTimeout(() => {
        onDismiss();
      }, duration);
    },
    [clearTimer, onDismiss],
  );

  const pauseTimer = useCallback(() => {
    if (isHoveredOrFocusedRef.current) {
      return;
    }
    isHoveredOrFocusedRef.current = true;
    const elapsed = Date.now() - startTimestampRef.current;
    remainingMsRef.current = Math.max(0, remainingMsRef.current - elapsed);
    clearTimer();
  }, [clearTimer]);

  const resumeTimer = useCallback(() => {
    isHoveredOrFocusedRef.current = false;
    startTimer(remainingMsRef.current);
  }, [startTimer]);

  // Initialize auto-dismiss timer
  useEffect(() => {
    startTimer(autoDismissMs);
    return () => {
      clearTimer();
    };
  }, [autoDismissMs, startTimer, clearTimer]);

  // Global Escape key listener
  useEffect(() => {
    const handleKeyDown = (e: globalThis.KeyboardEvent): void => {
      if (e.key === 'Escape') {
        onDismiss();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onDismiss]);

  const handleContainerKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onDismiss();
    }
  };

  const tooltipText = getSanitizedTooltipText(prunedHiddenNodes);

  return (
    <div className="sanitized-paste-pill-slot" data-testid={`${testId}-slot`}>
      <div
        ref={containerRef}
        className="sanitized-paste-pill"
        data-testid={testId}
        onMouseEnter={pauseTimer}
        onMouseLeave={resumeTimer}
        onFocus={pauseTimer}
        onBlur={resumeTimer}
        onKeyDown={handleContainerKeyDown}
        role="status"
        aria-live="polite"
      >
        <span className="sanitized-paste-pill__label" data-testid={`${testId}-label`}>
          Converted to Markdown
        </span>
        <EmojiHint
          kind="sanitized"
          label="Converted to Markdown"
          content={tooltipText}
          variant="tooltip"
          testId={`${testId}-emoji-hint`}
        />
      </div>
    </div>
  );
}
