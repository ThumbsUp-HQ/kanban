// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Mobile Touch Pan and Pinch-to-Zoom Diagram Viewer (KB-MOBILE-DOCS-PAN-ZOOM, KAN-346).
 * Full-screen accessible interactive overlay dialog for embedded Mermaid diagrams and media.
 * Supports:
 * - 2-finger touch pinch-to-zoom (scaling 25% to 500%)
 * - 1-finger touch pan / pointer drag translation
 * - Swipe-down dismiss gesture (downward touch drag > 70px)
 * - Accessible >=44x44px Close button with Escape key dismissal and focus restoration
 * - Zoom in (+), Zoom out (-), and Reset zoom (100%) controls
 * - Strictly compliant with CSP style-src 'self' (zero inline style attributes; CSSOM transform)
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type JSX,
  type ReactNode,
  type TouchEvent as ReactTouchEvent,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react';
import { createPortal } from 'react-dom';
import './DocsMobileDiagramViewer.css';

export interface DocsMobileDiagramViewerProps {
  isOpen: boolean;
  onClose: () => void;
  src?: string | undefined;
  blobUrl?: string | undefined;
  svgContent?: string | undefined;
  rawSource?: string | undefined;
  title?: string | undefined;
  alt?: string | undefined;
  testId?: string | undefined;
}

export interface DocsMobileDiagramTriggerProps {
  onExpand: () => void;
  label?: string | undefined;
  testId?: string | undefined;
  className?: string | undefined;
  children: ReactNode;
}

const MIN_SCALE = 0.25;
const MAX_SCALE = 5.0;
const ZOOM_STEP = 1.25;
const SWIPE_DISMISS_THRESHOLD_PX = 70;

export function formatZoomPercent(scale: number): string {
  return `${String(Math.round(scale * 100))}%`;
}

/**
 * Affordance wrapper for embedded diagrams on touch devices.
 * Provides tap-to-expand touch action trigger and visual affordance hint.
 */
export function DocsMobileDiagramTrigger({
  onExpand,
  label = 'Tap to expand diagram',
  testId = 'docs-mobile-diagram-trigger',
  className = '',
  children,
}: DocsMobileDiagramTriggerProps): JSX.Element {
  return (
    <div
      className={`docs-mobile-diagram-trigger-wrap ${className}`.trim()}
      data-testid={testId}
      onClick={onExpand}
      role="button"
      tabIndex={0}
      aria-label={label}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onExpand();
        }
      }}
    >
      {children}
      <button
        type="button"
        className="docs-mobile-diagram-tap-hint"
        data-testid={`${testId}-hint`}
        onClick={(e) => {
          e.stopPropagation();
          onExpand();
        }}
        aria-label="Tap to expand diagram in full screen"
      >
        <span className="docs-mobile-diagram-tap-icon" aria-hidden="true">
          ⤢
        </span>
        <span className="docs-mobile-diagram-tap-text">Tap to pan & zoom</span>
      </button>
    </div>
  );
}

/**
 * Full-screen interactive diagram viewer overlay with pinch-to-zoom,
 * touch panning, and swipe-down dismiss.
 */
interface DocsMobileDiagramModalProps {
  onClose: () => void;
  src?: string | undefined;
  blobUrl?: string | undefined;
  svgContent?: string | undefined;
  rawSource?: string | undefined;
  title: string;
  alt: string;
  testId: string;
}

function DocsMobileDiagramModal({
  onClose,
  src,
  blobUrl,
  svgContent,
  rawSource,
  title,
  alt,
  testId,
}: DocsMobileDiagramModalProps): JSX.Element {
  const [scale, setScale] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [swipeOffset, setSwipeOffset] = useState(0);

  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);

  // Gesture tracking refs
  const initialPinchDistRef = useRef<number>(0);
  const startScaleRef = useRef<number>(1.0);
  const touchStartPosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const lastTouchPosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const isDraggingRef = useRef<boolean>(false);
  const touchCountRef = useRef<number>(0);

  // Focus management and Escape key dismissal
  useEffect(() => {
    const prevActiveElement = document.activeElement as HTMLElement | null;
    requestAnimationFrame(() => {
      closeButtonRef.current?.focus();
    });

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      prevActiveElement?.focus();
    };
  }, [onClose]);

  // Apply CSSOM transform directly to satisfy CSP style-src 'self' (zero inline style attributes)
  useEffect(() => {
    if (contentRef.current) {
      const translateY = pan.y + swipeOffset;
      contentRef.current.style.transform = `translate(${String(pan.x)}px, ${String(translateY)}px) scale(${String(scale)})`;
    }
  }, [pan, scale, swipeOffset]);

  const handleZoomIn = useCallback(() => {
    setScale((prev) => Math.min(MAX_SCALE, Number((prev * ZOOM_STEP).toFixed(2))));
  }, []);

  const handleZoomOut = useCallback(() => {
    setScale((prev) => Math.max(MIN_SCALE, Number((prev / ZOOM_STEP).toFixed(2))));
  }, []);

  const handleZoomReset = useCallback(() => {
    setScale(1.0);
    setPan({ x: 0, y: 0 });
    setSwipeOffset(0);
  }, []);

  const handleWheel = useCallback((e: ReactWheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
    setScale((prev) => {
      const next = prev * factor;
      return Math.min(MAX_SCALE, Math.max(MIN_SCALE, Number(next.toFixed(2))));
    });
  }, []);

  // Multi-touch gestures (pinch-to-zoom, pan, and swipe-down dismiss)
  const handleTouchStart = useCallback((e: ReactTouchEvent<HTMLDivElement>) => {
    touchCountRef.current = e.touches.length;

    if (e.touches.length === 2) {
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      /* v8 ignore next */
      if (!t1 || !t2) return;
      initialPinchDistRef.current = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
      startScaleRef.current = scale;
    } else if (e.touches.length === 1) {
      const t = e.touches[0];
      /* v8 ignore next */
      if (!t) return;
      touchStartPosRef.current = { x: t.clientX, y: t.clientY };
      lastTouchPosRef.current = { x: t.clientX, y: t.clientY };
      isDraggingRef.current = true;
    }
  }, [scale]);

  const handleTouchMove = useCallback((e: ReactTouchEvent<HTMLDivElement>) => {
    touchCountRef.current = e.touches.length;

    if (e.touches.length === 2 && initialPinchDistRef.current > 0) {
      const t1 = e.touches[0];
      const t2 = e.touches[1];
      /* v8 ignore next */
      if (!t1 || !t2) return;
      const currentDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
      const factor = currentDist / initialPinchDistRef.current;
      const nextScale = Math.min(
        MAX_SCALE,
        Math.max(MIN_SCALE, Number((startScaleRef.current * factor).toFixed(2)))
      );
      setScale(nextScale);
    } else if (e.touches.length === 1 && isDraggingRef.current) {
      const t = e.touches[0];
      /* v8 ignore next */
      if (!t) return;
      const dx = t.clientX - lastTouchPosRef.current.x;
      const dy = t.clientY - lastTouchPosRef.current.y;
      lastTouchPosRef.current = { x: t.clientX, y: t.clientY };

      const totalDy = t.clientY - touchStartPosRef.current.y;
      const totalDx = Math.abs(t.clientX - touchStartPosRef.current.x);

      // When diagram is at default scale and moving downward, show swipe dismiss feedback
      if (scale <= 1.05 && totalDy > 0 && totalDy > totalDx * 1.1) {
        setSwipeOffset(totalDy * 0.6);
      } else {
        setPan((prev) => ({ x: prev.x + dx, y: prev.y + dy }));
      }
    }
  }, [scale]);

  const handleTouchEnd = useCallback((e: ReactTouchEvent<HTMLDivElement>) => {
    touchCountRef.current = e.touches.length;

    if (e.touches.length === 0) {
      isDraggingRef.current = false;
      initialPinchDistRef.current = 0;

      const totalDy = lastTouchPosRef.current.y - touchStartPosRef.current.y;
      const totalDx = Math.abs(lastTouchPosRef.current.x - touchStartPosRef.current.x);

      // Trigger swipe-down dismiss if downward drag threshold is exceeded
      if (totalDy >= SWIPE_DISMISS_THRESHOLD_PX && totalDy > totalDx * 1.1 && scale <= 1.2) {
        setSwipeOffset(0);
        onClose();
        return;
      }

      setSwipeOffset(0);
    }
  }, [scale, onClose]);

  // Pointer events fallback for desktop click-drag and synthetic tests
  const handlePointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'touch') return; // Handled by touch events
    if (e.button !== 0) return;
    isDraggingRef.current = true;
    lastTouchPosRef.current = { x: e.clientX, y: e.clientY };
    touchStartPosRef.current = { x: e.clientX, y: e.clientY };
    try {
      /* v8 ignore next 3 */
      if ('setPointerCapture' in e.currentTarget) {
        e.currentTarget.setPointerCapture(e.pointerId);
      }
    } catch {
      // Ignored if capture unsupported
    }
  }, []);

  const handlePointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'touch') return;
    if (!isDraggingRef.current) return;
    const dx = e.clientX - lastTouchPosRef.current.x;
    const dy = e.clientY - lastTouchPosRef.current.y;
    lastTouchPosRef.current = { x: e.clientX, y: e.clientY };

    const totalDy = e.clientY - touchStartPosRef.current.y;
    const totalDx = Math.abs(e.clientX - touchStartPosRef.current.x);

    if (scale <= 1.05 && totalDy > 0 && totalDy > totalDx * 1.1) {
      setSwipeOffset(totalDy * 0.6);
    } else {
      setPan((prev) => ({ x: prev.x + dx, y: prev.y + dy }));
    }
  }, [scale]);

  const handlePointerUp = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.pointerType === 'touch') return;
    if (!isDraggingRef.current) return;
    isDraggingRef.current = false;
    try {
      /* v8 ignore next 3 */
      if ('releasePointerCapture' in e.currentTarget) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    } catch {
      // Ignored if release unsupported
    }

    const totalDy = lastTouchPosRef.current.y - touchStartPosRef.current.y;
    const totalDx = Math.abs(lastTouchPosRef.current.x - touchStartPosRef.current.x);

    if (totalDy >= SWIPE_DISMISS_THRESHOLD_PX && totalDy > totalDx * 1.1 && scale <= 1.2) {
      setSwipeOffset(0);
      onClose();
      return;
    }

    setSwipeOffset(0);
  }, [scale, onClose]);

  const effectiveMediaSrc = blobUrl ?? src ?? '';

  const modalNode = (
    <div
      ref={overlayRef}
      className="docs-mobile-diagram-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Interactive Diagram Viewer"
      data-testid={testId}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      {/* Top Header Bar */}
      <header className="docs-mobile-diagram-header" data-testid={`${testId}-header`}>
        <div className="docs-mobile-diagram-title-wrap">
          <span className="docs-mobile-diagram-title">{title}</span>
          <span className="docs-mobile-diagram-swipe-badge" data-testid={`${testId}-swipe-hint`}>
            Swipe down to close
          </span>
        </div>

        <div className="docs-mobile-diagram-actions">
          {/* Zoom Out Button */}
          <button
            type="button"
            className="docs-mobile-diagram-btn"
            aria-label="Zoom out"
            onClick={handleZoomOut}
            data-testid={`${testId}-zoom-out`}
          >
            -
          </button>

          {/* Reset Zoom Button */}
          <button
            type="button"
            className="docs-mobile-diagram-btn docs-mobile-diagram-btn--readout"
            aria-label="Reset zoom"
            onClick={handleZoomReset}
            data-testid={`${testId}-zoom-reset`}
          >
            {formatZoomPercent(scale)}
          </button>

          {/* Zoom In Button */}
          <button
            type="button"
            className="docs-mobile-diagram-btn"
            aria-label="Zoom in"
            onClick={handleZoomIn}
            data-testid={`${testId}-zoom-in`}
          >
            +
          </button>

          {/* Close Button */}
          <button
            ref={closeButtonRef}
            type="button"
            className="docs-mobile-diagram-btn docs-mobile-diagram-close-btn"
            aria-label="Close diagram viewer"
            onClick={onClose}
            data-testid={`${testId}-close-btn`}
          >
            ✕
          </button>
        </div>
      </header>

      {/* Interactive Touch Canvas Area */}
      <div
        ref={canvasRef}
        className="docs-mobile-diagram-canvas"
        data-testid={`${testId}-canvas`}
        onWheel={handleWheel}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onTouchCancel={handleTouchEnd}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <div
          ref={contentRef}
          className="docs-mobile-diagram-content"
          data-testid={`${testId}-content`}
        >
          {svgContent ? (
            <div
              className="docs-mobile-diagram-svg"
              dangerouslySetInnerHTML={{ __html: svgContent }}
            />
          ) : effectiveMediaSrc ? (
            <img
              src={effectiveMediaSrc}
              alt={alt}
              className="docs-mobile-diagram-img"
              data-testid={`${testId}-img`}
              draggable={false}
            />
          ) : rawSource ? (
            <pre className="docs-mobile-diagram-source">
              <code>{rawSource}</code>
            </pre>
          ) : null}
        </div>
      </div>
    </div>
  );

  /* v8 ignore next */
  return typeof document !== 'undefined' ? createPortal(modalNode, document.body) : modalNode;
}

/**
 * Full-screen interactive diagram viewer overlay with pinch-to-zoom,
 * touch panning, and swipe-down dismiss.
 */
export function DocsMobileDiagramViewer({
  isOpen,
  onClose,
  src,
  blobUrl,
  svgContent,
  rawSource,
  title = 'Diagram Viewer',
  alt = 'Mermaid diagram',
  testId = 'docs-mobile-diagram-viewer',
}: DocsMobileDiagramViewerProps): JSX.Element | null {
  if (!isOpen) return null;

  return (
    <DocsMobileDiagramModal
      onClose={onClose}
      src={src}
      blobUrl={blobUrl}
      svgContent={svgContent}
      rawSource={rawSource}
      title={title}
      alt={alt}
      testId={testId}
    />
  );
}
