import { useCallback, useRef, useState, type TouchEvent as ReactTouchEvent } from 'react';

export interface UseTouchDragSensorOptions {
  delay?: number; // default: 200ms
  tolerance?: number; // default: 8px
  onLongPress?: () => void;
  onCancel?: () => void;
}

export interface TouchCoords {
  x: number;
  y: number;
}

export interface UseTouchDragSensorResult {
  isTouchLifted: boolean;
  isScrolling: boolean;
  isScrollingRef: React.RefObject<boolean>;
  touchHandlers: {
    onTouchStart: (e: ReactTouchEvent<HTMLElement>) => void;
    onTouchMove: (e: ReactTouchEvent<HTMLElement>) => void;
    onTouchEnd: (e: ReactTouchEvent<HTMLElement>) => void;
    onTouchCancel: (e: ReactTouchEvent<HTMLElement>) => void;
  };
  cancelTouch: () => void;
}

/**
 * Tuned touch gesture sensor for Pragmatic DnD mobile ergonomics (KAN-342).
 *
 * Threshold:
 * - delay: 200ms
 * - tolerance: 8px
 *
 * If movement delta exceeds 8px within 200ms, gesture is classified as a standard
 * touch scroll and drag activation is cancelled.
 * If finger remains stationary within 8px for >= 200ms, long-press activates visual
 * lift and haptic feedback.
 */
export function useTouchDragSensor({
  delay = 200,
  tolerance = 8,
  onLongPress,
  onCancel,
}: UseTouchDragSensorOptions = {}): UseTouchDragSensorResult {
  const [isTouchLifted, setIsTouchLifted] = useState(false);
  const [isScrolling, setIsScrolling] = useState(false);

  const startCoordsRef = useRef<TouchCoords | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isScrollingRef = useRef<boolean>(false);
  const isLiftedRef = useRef<boolean>(false);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const cancelTouch = useCallback(() => {
    clearTimer();
    startCoordsRef.current = null;
    isScrollingRef.current = false;
    isLiftedRef.current = false;
    setIsTouchLifted(false);
    setIsScrolling(false);
    onCancel?.();
  }, [clearTimer, onCancel]);

  const onTouchStart = useCallback(
    (e: ReactTouchEvent<HTMLElement>) => {
      const touch = e.touches[0];
      if (e.touches.length !== 1 || !touch) {
        cancelTouch();
        return;
      }

      startCoordsRef.current = { x: touch.clientX, y: touch.clientY };
      isScrollingRef.current = false;
      setIsScrolling(false);

      clearTimer();
      timerRef.current = setTimeout(() => {
        isLiftedRef.current = true;
        setIsTouchLifted(true);
        if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
          try {
            navigator.vibrate(50);
          } catch {
            // Ignore unsupported platform errors
          }
        }
        onLongPress?.();
      }, delay);
    },
    [delay, clearTimer, cancelTouch, onLongPress],
  );

  const onTouchMove = useCallback(
    (e: ReactTouchEvent<HTMLElement>) => {
      const touch = e.touches[0];
      if (!startCoordsRef.current || !touch) return;

      const deltaX = Math.abs(touch.clientX - startCoordsRef.current.x);
      const deltaY = Math.abs(touch.clientY - startCoordsRef.current.y);
      const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);

      if (distance > tolerance) {
        // Standard touch scroll gesture detected: cancel long-press activation
        clearTimer();
        isScrollingRef.current = true;
        setIsScrolling(true);
        if (isLiftedRef.current) {
          isLiftedRef.current = false;
          setIsTouchLifted(false);
        }
        onCancel?.();
      }
    },
    [tolerance, clearTimer, onCancel],
  );

  const onTouchEnd = useCallback(() => {
    clearTimer();
    startCoordsRef.current = null;
    isScrollingRef.current = false;
    isLiftedRef.current = false;
    setIsTouchLifted(false);
    setIsScrolling(false);
  }, [clearTimer]);

  const onTouchCancel = useCallback(() => {
    cancelTouch();
  }, [cancelTouch]);

  return {
    isTouchLifted,
    isScrolling,
    isScrollingRef,
    touchHandlers: {
      onTouchStart,
      onTouchMove,
      onTouchEnd,
      onTouchCancel,
    },
    cancelTouch,
  };
}
