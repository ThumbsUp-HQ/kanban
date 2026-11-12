/**
 * Media Viewport Component (KB-P3-48, S5.4, S6.2).
 * Interactive viewport for vector SVGs and raster pictures with 10% - 800%
 * pan/zoom, contrast backdrop cycle, external media shield badge, and lightbox.
 * Strictly compliant with CSP style-src 'self' (zero inline style attributes).
 */

import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
  type JSX,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react';
import { EmojiHint } from '../../components/emoji/EmojiHint';
import {
  zoomAtPoint,
  panBy,
  resetTransform,
  formatZoomPercentage,
  buildCssomTransform,
  ZOOM_STEP,
  type TransformState,
  INITIAL_TRANSFORM,
} from './panZoomMath';
import { resolveMediaUrl } from './mediaUrlResolver';
import { MediaLightbox } from './MediaLightbox';
import './MediaViewport.css';

export type MediaBackdropKind = 'theme' | 'light' | 'dark' | 'checkerboard';

const BACKDROP_CYCLE: readonly MediaBackdropKind[] = Object.freeze([
  'theme',
  'light',
  'dark',
  'checkerboard',
]);

export interface MediaViewportProps {
  src: string;
  alt?: string | undefined;
  rawSource?: string | undefined;
  safeFilename?: string | undefined;
  isLightbox?: boolean | undefined;
  initialBackdrop?: MediaBackdropKind | undefined;
  onBackdropChange?: ((next: MediaBackdropKind) => void) | undefined;
  airGapMode?: boolean | undefined;
  resolveAttachmentUrl?: ((attachmentId: string) => string) | undefined;
  testId?: string | undefined;
}

export function MediaViewport({
  src,
  alt = '',
  rawSource,
  safeFilename = 'media.svg',
  isLightbox = false,
  initialBackdrop = 'theme',
  onBackdropChange,
  airGapMode = false,
  resolveAttachmentUrl,
  testId = 'media-viewport',
}: MediaViewportProps): JSX.Element {
  const [backdrop, setBackdrop] = useState<MediaBackdropKind>(initialBackdrop);
  const [prevInitial, setPrevInitial] = useState(initialBackdrop);
  if (initialBackdrop !== prevInitial) {
    setPrevInitial(initialBackdrop);
    setBackdrop(initialBackdrop);
  }

  const [transform, setTransform] = useState<TransformState>(INITIAL_TRANSFORM);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);
  const [copyAnnounce, setCopyAnnounce] = useState('');

  const canvasRef = useRef<HTMLDivElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  // Drag pan pointer state
  const isDraggingRef = useRef(false);
  const lastPointerPosRef = useRef({ x: 0, y: 0 });
  const hasMovedRef = useRef(false);

  const resolved = resolveMediaUrl(src, { airGapMode, resolveAttachmentUrl });

  // Apply CSSOM transform strictly to maintain CSP style-src 'self'
  useEffect(() => {
    if (imgRef.current) {
      imgRef.current.style.transform = buildCssomTransform(transform);
    }
  }, [transform]);

  const handleBackdropCycle = useCallback(() => {
    const currentIndex = BACKDROP_CYCLE.indexOf(backdrop);
    const nextIndex = (currentIndex + 1) % BACKDROP_CYCLE.length;
    const nextBackdrop = BACKDROP_CYCLE[nextIndex] ?? 'theme';
    setBackdrop(nextBackdrop);
    onBackdropChange?.(nextBackdrop);
  }, [backdrop, onBackdropChange]);

  const handleZoomIn = useCallback(() => {
    const rect = canvasRef.current?.getBoundingClientRect() ?? { width: 400, height: 300 };
    const focalPoint = { x: rect.width / 2, y: rect.height / 2 };
    setTransform((prev) => zoomAtPoint(prev, focalPoint, ZOOM_STEP));
  }, []);

  const handleZoomOut = useCallback(() => {
    const rect = canvasRef.current?.getBoundingClientRect() ?? { width: 400, height: 300 };
    const focalPoint = { x: rect.width / 2, y: rect.height / 2 };
    setTransform((prev) => zoomAtPoint(prev, focalPoint, 1 / ZOOM_STEP));
  }, []);

  const handleZoomReset = useCallback(() => {
    setTransform(resetTransform());
  }, []);

  const handleWheel = useCallback(
    (e: ReactWheelEvent<HTMLDivElement>) => {
      // Support Ctrl/Cmd+Wheel or general wheel inside lightbox
      if (e.ctrlKey || e.metaKey || isLightbox) {
        e.preventDefault();
        const rect = canvasRef.current?.getBoundingClientRect() ?? { left: 0, top: 0 };
        const focalPoint = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
        setTransform((prev) => zoomAtPoint(prev, focalPoint, factor));
      }
    },
    [isLightbox],
  );

  const handlePointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return; // Main button only
    isDraggingRef.current = true;
    hasMovedRef.current = false;
    lastPointerPosRef.current = { x: e.clientX, y: e.clientY };
    try {
      if ('setPointerCapture' in e.currentTarget) {
        e.currentTarget.setPointerCapture(e.pointerId);
      }
    } catch {
      // Ignored if pointer capture not supported
    }
  }, []);

  const handlePointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!isDraggingRef.current) return;
    const dx = e.clientX - lastPointerPosRef.current.x;
    const dy = e.clientY - lastPointerPosRef.current.y;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
      hasMovedRef.current = true;
    }
    lastPointerPosRef.current = { x: e.clientX, y: e.clientY };
    setTransform((prev) => panBy(prev, dx, dy));
  }, []);

  const handlePointerUp = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
      try {
        if ('releasePointerCapture' in e.currentTarget) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        // Ignored if pointer capture already lost
      }
      // If pointer didn't drag and image was clicked in inline mode, expand to lightbox
      if (!hasMovedRef.current && !isLightbox) {
        setIsLightboxOpen(true);
      }
    },
    [isLightbox],
  );

  const handleCopyRaw = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(rawSource ?? '');
      setCopyAnnounce('Copied source');
      setTimeout(() => {
        setCopyAnnounce('');
      }, 2500);
    } catch {
      setCopyAnnounce('Copy failed');
    }
  }, [rawSource]);

  // Clean filename for download attribute
  const cleanedFilename = safeFilename.replace(/[^a-zA-Z0-9._-]/g, '_') || 'media.svg';

  // Render air-gap offline placeholder card if blocked
  if (resolved.isAirGapBlocked) {
    return (
      <div className="media-airgap-placeholder" data-testid={`${testId}-airgap`}>
        <div className="media-airgap-placeholder__badge">
          <EmojiHint kind="airGap" />
          <span>External image blocked in Air-Gap Local-Only Mode</span>
        </div>
        <div className="media-airgap-placeholder__host">
          Host: {resolved.originalHost}
        </div>
      </div>
    );
  }

  const containerClasses = [
    'media-viewport',
    isLightbox ? 'media-viewport--lightbox' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const canvasClasses = [
    'media-viewport__canvas',
    `media-bg--${backdrop}`,
  ].join(' ');

  const imgClasses = [
    'media-viewport__img',
    isLoaded ? 'media-viewport__img--loaded' : 'media-viewport__img--loading',
  ].join(' ');

  return (
    <div className={containerClasses} data-testid={testId}>
      {/* Canvas Area */}
      <div
        ref={canvasRef}
        className={canvasClasses}
        data-testid={`${testId}-canvas`}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {!isLoaded && (
          <div className="media-viewport__skeleton" data-testid={`${testId}-skeleton`}>
            Loading media...
          </div>
        )}

        <img
          ref={imgRef}
          src={resolved.url}
          alt={alt}
          loading="lazy"
          decoding="async"
          className={imgClasses}
          data-testid={`${testId}-img`}
          onLoad={() => {
            setIsLoaded(true);
          }}
        />
      </div>

      {/* Optional Alt text badge */}
      {alt && alt.trim().length > 0 && (
        <div className="media-alt-badge" title={alt} data-testid={`${testId}-alt-badge`}>
          Alt: {alt.length > 24 ? `${alt.slice(0, 24)}...` : alt}
        </div>
      )}

      {/* Floating Controls Bar */}
      <div className="media-viewport__controls" data-testid={`${testId}-controls`}>
        {/* Contrast Backdrop Toggle */}
        <EmojiHint
          kind="mediaBackdrop"
          variant="interactive"
          onActivate={handleBackdropCycle}
          testId={`${testId}-backdrop-toggle`}
        />

        {/* Zoom Out Button */}
        <button
          type="button"
          className="media-btn"
          aria-label="Zoom out"
          onClick={handleZoomOut}
          data-testid={`${testId}-zoom-out`}
        >
          -
        </button>

        {/* Zoom Level Indicator / Reset Button */}
        <button
          type="button"
          className="media-btn media-btn--zoom-readout"
          aria-label="Reset zoom to 100%"
          onClick={handleZoomReset}
          data-testid={`${testId}-zoom-readout`}
        >
          {formatZoomPercentage(transform.scale)}
        </button>

        {/* Zoom In Button */}
        <button
          type="button"
          className="media-btn"
          aria-label="Zoom in"
          onClick={handleZoomIn}
          data-testid={`${testId}-zoom-in`}
        >
          +
        </button>

        {/* Proxied External Media Badge */}
        {resolved.isExternalProxied && (
          <EmojiHint
            kind="externalMedia"
            testId={`${testId}-proxied-badge`}
          />
        )}

        {/* Copy Raw Source Button (if SVG / text source available) */}
        {rawSource && (
          <button
            type="button"
            className="media-btn"
            aria-label="Copy raw source"
            onClick={() => {
              void handleCopyRaw();
            }}
            data-testid={`${testId}-copy-source`}
          >
            {copyAnnounce || 'Copy'}
          </button>
        )}

        {/* Download Media Asset Button */}
        <a
          download={cleanedFilename}
          href={resolved.url}
          className="media-btn"
          aria-label="Download media asset"
          data-testid={`${testId}-download`}
        >
          ⬇
        </a>

        {/* Expand in Lightbox Button */}
        {!isLightbox && (
          <button
            ref={triggerRef}
            type="button"
            className="media-btn media-btn--icon"
            aria-label="Expand in lightbox"
            onClick={() => {
              setIsLightboxOpen(true);
            }}
            data-testid={`${testId}-expand`}
          >
            ⤢
          </button>
        )}
      </div>

      {/* Screen Reader Announcement for Copy */}
      <span className="sr-only" aria-live="polite">
        {copyAnnounce}
      </span>

      {/* Lightbox Dialog Portal */}
      {!isLightbox && (
        <MediaLightbox
          isOpen={isLightboxOpen}
          onClose={() => {
            setIsLightboxOpen(false);
          }}
          src={resolved.url}
          alt={alt}
          rawSource={rawSource}
          backdrop={backdrop}
          onBackdropChange={(next) => {
            setBackdrop(next);
          }}
          safeFilename={cleanedFilename}
          triggerRef={triggerRef}
        />
      )}
    </div>
  );
}
