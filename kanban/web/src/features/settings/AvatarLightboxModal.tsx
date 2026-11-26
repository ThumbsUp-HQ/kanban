// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useRef, type JSX } from 'react';
import { StudioDocLink } from '../../components/help/StudioDocLink';

export interface AvatarLightboxModalProps {
  avatarUrl: string;
  displayName: string;
  onClose: () => void;
}

const LIGHTBOX_SIZE = 440;

export function AvatarLightboxModal({
  avatarUrl,
  displayName,
  onClose,
}: AvatarLightboxModalProps): JSX.Element {
  const [zoom, setZoom] = useState<number>(1.0);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [imageLoaded, setImageLoaded] = useState<boolean>(false);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const activePointers = useRef<Map<number, { x: number; y: number }>>(new Map());
  const dragStart = useRef<{ panX: number; panY: number; clientX: number; clientY: number } | null>(null);
  const pinchStart = useRef<{ dist: number; zoom: number } | null>(null);

  // Load avatar image
  useEffect(() => {
    let active = true;
    const img = new Image();
    img.crossOrigin = 'anonymous';

    img.onload = () => {
      if (!active) return;
      imageRef.current = img;
      setImageLoaded(true);
      setPan({ x: 0, y: 0 });
      setZoom(1.0);
    };

    img.onerror = () => {
      if (!active) return;
      setImageLoaded(false);
    };

    img.src = avatarUrl;

    return () => {
      active = false;
    };
  }, [avatarUrl]);

  // Escape key handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  // Clamp pan so image does not drift out of view when zoomed in
  const getClampedPan = (
    x: number,
    y: number,
    currentZoom: number,
    img: HTMLImageElement,
  ): { x: number; y: number } => {
    const baseScale = Math.min(LIGHTBOX_SIZE / img.width, LIGHTBOX_SIZE / img.height);
    const renderWidth = img.width * baseScale * currentZoom;
    const renderHeight = img.height * baseScale * currentZoom;
    const maxPanX = Math.max(0, (renderWidth - LIGHTBOX_SIZE) / 2);
    const maxPanY = Math.max(0, (renderHeight - LIGHTBOX_SIZE) / 2);
    return {
      x: Math.min(Math.max(x, -maxPanX), maxPanX),
      y: Math.min(Math.max(y, -maxPanY), maxPanY),
    };
  };

  // Render to canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img || !imageLoaded) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, LIGHTBOX_SIZE, LIGHTBOX_SIZE);

    const baseScale = Math.min(LIGHTBOX_SIZE / img.width, LIGHTBOX_SIZE / img.height);
    const renderWidth = img.width * baseScale * zoom;
    const renderHeight = img.height * baseScale * zoom;

    const clamped = getClampedPan(pan.x, pan.y, zoom, img);
    const centerX = LIGHTBOX_SIZE / 2 + clamped.x;
    const centerY = LIGHTBOX_SIZE / 2 + clamped.y;

    ctx.drawImage(
      img,
      centerX - renderWidth / 2,
      centerY - renderHeight / 2,
      renderWidth,
      renderHeight,
    );
  }, [zoom, pan, imageLoaded]);

  // Zoom button helper
  const handleZoomStep = (direction: 'in' | 'out'): void => {
    const delta = direction === 'in' ? 0.2 : -0.2;
    setZoom((prev) => {
      const next = Math.min(4.0, Math.max(1.0, Number((prev + delta).toFixed(2))));
      const img = imageRef.current;
      if (img) {
        setPan((p) => getClampedPan(p.x, p.y, next, img));
      }
      return next;
    });
  };

  // Reset zoom helper
  const handleResetZoom = (): void => {
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
  };

  // Mouse wheel zoom
  const handleWheel = (e: React.WheelEvent): void => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.1 : -0.1;
    setZoom((prev) => {
      const next = Math.min(4.0, Math.max(1.0, Number((prev + delta).toFixed(2))));
      const img = imageRef.current;
      if (img) {
        setPan((p) => getClampedPan(p.x, p.y, next, img));
      }
      return next;
    });
  };

  // Keyboard arrow pan
  const handleKeyDownOnLightbox = (e: React.KeyboardEvent): void => {
    if (!imageRef.current) return;
    const step = 14;
    let newX = pan.x;
    let newY = pan.y;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      newX -= step;
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      newX += step;
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      newY -= step;
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      newY += step;
    } else {
      return;
    }
    setPan(getClampedPan(newX, newY, zoom, imageRef.current));
  };

  // Pointer drag and 2-pointer pinch
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>): void => {
    if (typeof (e.currentTarget as HTMLElement).setPointerCapture === "function") {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    }
    activePointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (activePointers.current.size === 1) {
      dragStart.current = {
        panX: pan.x,
        panY: pan.y,
        clientX: e.clientX,
        clientY: e.clientY,
      };
      pinchStart.current = null;
    } else if (activePointers.current.size === 2) {
      const [p1, p2] = Array.from(activePointers.current.values()) as [
        { x: number; y: number },
        { x: number; y: number },
      ];
      const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
      pinchStart.current = { dist: Math.max(1, dist), zoom };
      dragStart.current = null;
    }
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>): void => {
    if (!activePointers.current.has(e.pointerId)) return;
    activePointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (activePointers.current.size === 2 && pinchStart.current) {
      const [p1, p2] = Array.from(activePointers.current.values()) as [
        { x: number; y: number },
        { x: number; y: number },
      ];
      const currentDist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
      const factor = currentDist / pinchStart.current.dist;
      const nextZoom = Math.min(
        4.0,
        Math.max(1.0, Number((pinchStart.current.zoom * factor).toFixed(2))),
      );
      setZoom(nextZoom);
      const img = imageRef.current;
      if (img) {
        setPan((p) => getClampedPan(p.x, p.y, nextZoom, img));
      }
    } else if (activePointers.current.size === 1 && dragStart.current && imageRef.current) {
      const dx = e.clientX - dragStart.current.clientX;
      const dy = e.clientY - dragStart.current.clientY;
      const candidateX = dragStart.current.panX + dx;
      const candidateY = dragStart.current.panY + dy;
      setPan(getClampedPan(candidateX, candidateY, zoom, imageRef.current));
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>): void => {
    activePointers.current.delete(e.pointerId);
    if (activePointers.current.size === 0) {
      dragStart.current = null;
      pinchStart.current = null;
    } else if (activePointers.current.size === 1) {
      pinchStart.current = null;
      const [remaining] = Array.from(activePointers.current.values()) as [
        { x: number; y: number },
      ];
      dragStart.current = {
        panX: pan.x,
        panY: pan.y,
        clientX: remaining.x,
        clientY: remaining.y,
      };
    }
  };

  return (
    <div
      className="kb-avatar-lightbox-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="avatar-lightbox-title"
      data-testid="avatar-lightbox-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="kb-avatar-lightbox-card">
        <div className="kb-avatar-lightbox-header">
          <h2 id="avatar-lightbox-title" className="kb-avatar-lightbox-title">
            {displayName || 'User'} Picture
          </h2>
          <div className="kb-avatar-lightbox-header-actions">
            <StudioDocLink
              href="/docs/studio-configuration-reference#user-avatars-profile-media"
              title="User Avatars & Profile Media Documentation"
              testId="avatar-lightbox-doc-link"
            />
            <button
              type="button"
              className="kb-avatar-lightbox-close-btn"
              aria-label="Close"
              data-testid="avatar-lightbox-close-btn"
              onClick={onClose}
            >
              ✕
            </button>
          </div>
        </div>

        <div
          className="kb-avatar-lightbox-viewport"
          tabIndex={0}
          role="application"
          aria-label="Avatar full-size lightbox viewport. Use arrow keys to pan, mouse wheel or pinch to zoom"
          data-testid="avatar-lightbox-viewport"
          onWheel={handleWheel}
          onKeyDown={handleKeyDownOnLightbox}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          <canvas
            ref={canvasRef}
            width={LIGHTBOX_SIZE}
            height={LIGHTBOX_SIZE}
            className="kb-avatar-lightbox-canvas"
            data-testid="avatar-lightbox-canvas"
          />
        </div>

        <div className="kb-avatar-lightbox-controls">
          <button
            type="button"
            className="kb-avatar-lightbox-zoom-btn"
            aria-label="Zoom out"
            data-testid="avatar-lightbox-zoom-out"
            onClick={() => { handleZoomStep('out'); }}
            disabled={zoom <= 1.0}
          >
            -
          </button>
          <input
            type="range"
            className="kb-avatar-lightbox-zoom-slider"
            min={1.0}
            max={4.0}
            step={0.05}
            value={zoom}
            aria-label="Zoom level"
            data-testid="avatar-lightbox-zoom-slider"
            onChange={(e) => {
              const next = parseFloat(e.target.value);
              setZoom(next);
              const img = imageRef.current;
              if (img) {
                setPan((p) => getClampedPan(p.x, p.y, next, img));
              }
            }}
          />
          <button
            type="button"
            className="kb-avatar-lightbox-zoom-btn"
            aria-label="Zoom in"
            data-testid="avatar-lightbox-zoom-in"
            onClick={() => { handleZoomStep('in'); }}
            disabled={zoom >= 4.0}
          >
            +
          </button>
          <span
            className="kb-avatar-lightbox-zoom-value"
            data-testid="avatar-lightbox-zoom-value"
          >
            {zoom.toFixed(1)}x
          </span>
          <button
            type="button"
            className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
            aria-label="Reset zoom"
            data-testid="avatar-lightbox-reset-btn"
            onClick={handleResetZoom}
          >
            Reset
          </button>
        </div>
      </div>
    </div>
  );
}
