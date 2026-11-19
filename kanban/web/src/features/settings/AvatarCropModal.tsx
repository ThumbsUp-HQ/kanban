// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, useEffect, useRef, type JSX } from 'react';

export interface AvatarCropModalProps {
  file: File;
  onSave: (croppedBlob: Blob) => void | Promise<void>;
  onClose: () => void;
  isSaving?: boolean;
}

const CROP_SIZE = 320;

export function AvatarCropModal({
  file,
  onSave,
  onClose,
  isSaving = false,
}: AvatarCropModalProps): JSX.Element {
  const [zoom, setZoom] = useState<number>(1.0);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [imageLoaded, setImageLoaded] = useState<boolean>(false);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const activePointers = useRef<Map<number, { x: number; y: number }>>(new Map());
  const dragStart = useRef<{ panX: number; panY: number; clientX: number; clientY: number } | null>(null);
  const pinchStart = useRef<{ dist: number; zoom: number } | null>(null);

  // Load image from File
  useEffect(() => {
    let active = true;
    const objectUrl = URL.createObjectURL(file);
    const img = new Image();

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

    img.src = objectUrl;

    return () => {
      active = false;
      URL.revokeObjectURL(objectUrl);
    };
  }, [file]);

  // Escape key handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape' && !isSaving) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose, isSaving]);

  // Clamp pan so image boundary covers crop area
  const getClampedPan = (
    x: number,
    y: number,
    currentZoom: number,
    img: HTMLImageElement,
  ): { x: number; y: number } => {
    const baseScale = Math.max(CROP_SIZE / img.width, CROP_SIZE / img.height);
    const renderWidth = img.width * baseScale * currentZoom;
    const renderHeight = img.height * baseScale * currentZoom;
    const maxPanX = Math.max(0, (renderWidth - CROP_SIZE) / 2);
    const maxPanY = Math.max(0, (renderHeight - CROP_SIZE) / 2);
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

    ctx.clearRect(0, 0, CROP_SIZE, CROP_SIZE);

    const baseScale = Math.max(CROP_SIZE / img.width, CROP_SIZE / img.height);
    const renderWidth = img.width * baseScale * zoom;
    const renderHeight = img.height * baseScale * zoom;

    const clamped = getClampedPan(pan.x, pan.y, zoom, img);
    const centerX = CROP_SIZE / 2 + clamped.x;
    const centerY = CROP_SIZE / 2 + clamped.y;

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
  const handleKeyDownOnCrop = (e: React.KeyboardEvent): void => {
    if (!imageRef.current) return;
    const step = 12;
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

  // Export 512x512 raster Blob
  const handleSave = (): void => {
    if (!imageRef.current) {
      void onSave(file);
      return;
    }
    const img = imageRef.current;
    const exportCanvas = document.createElement('canvas');
    exportCanvas.width = 512;
    exportCanvas.height = 512;
    const exportCtx = exportCanvas.getContext('2d');
    if (!exportCtx) {
      void onSave(file);
      return;
    }

    const baseScale = Math.max(CROP_SIZE / img.width, CROP_SIZE / img.height);
    const renderWidth = img.width * baseScale * zoom;
    const renderHeight = img.height * baseScale * zoom;
    const clamped = getClampedPan(pan.x, pan.y, zoom, img);

    const scaleFactor = 512 / CROP_SIZE;
    const expRenderW = renderWidth * scaleFactor;
    const expRenderH = renderHeight * scaleFactor;
    const expCenterX = (CROP_SIZE / 2 + clamped.x) * scaleFactor;
    const expCenterY = (CROP_SIZE / 2 + clamped.y) * scaleFactor;

    exportCtx.drawImage(
      img,
      expCenterX - expRenderW / 2,
      expCenterY - expRenderH / 2,
      expRenderW,
      expRenderH,
    );

    if (typeof exportCanvas.toBlob === 'function') {
      exportCanvas.toBlob(
        (blob) => {
          if (blob) {
            void onSave(blob);
          } else {
            void onSave(file);
          }
        },
        'image/png',
      );
    } else {
      void onSave(file);
    }
  };

  return (
    <div
      className="kb-avatar-crop-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="avatar-crop-title"
      data-testid="avatar-crop-modal"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSaving) {
          onClose();
        }
      }}
    >
      <div className="kb-avatar-crop-card">
        <div className="kb-avatar-crop-header">
          <h2 id="avatar-crop-title" className="kb-avatar-crop-title">
            Crop Profile Picture
          </h2>
          <button
            type="button"
            className="kb-avatar-crop-close-btn"
            aria-label="Close"
            onClick={onClose}
            disabled={isSaving}
          >
            ✕
          </button>
        </div>

        <div
          className="kb-avatar-crop-viewport"
          tabIndex={0}
          role="application"
          aria-label="Image crop area, use arrow keys to pan, mouse wheel or pinch to zoom"
          data-testid="avatar-crop-viewport"
          onWheel={handleWheel}
          onKeyDown={handleKeyDownOnCrop}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          <canvas
            ref={canvasRef}
            width={CROP_SIZE}
            height={CROP_SIZE}
            className="kb-avatar-crop-canvas"
            data-testid="avatar-crop-canvas"
          />
          <div className="kb-avatar-crop-guide" aria-hidden="true" />
        </div>

        <div className="kb-avatar-crop-controls">
          <button
            type="button"
            className="kb-avatar-crop-zoom-btn"
            aria-label="Zoom out"
            data-testid="avatar-crop-zoom-out"
            onClick={() => { handleZoomStep('out'); }}
            disabled={zoom <= 1.0 || isSaving}
          >
            -
          </button>
          <input
            type="range"
            className="kb-avatar-crop-zoom-slider"
            min={1.0}
            max={4.0}
            step={0.05}
            value={zoom}
            aria-label="Zoom level"
            data-testid="avatar-crop-zoom-slider"
            disabled={isSaving}
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
            className="kb-avatar-crop-zoom-btn"
            aria-label="Zoom in"
            data-testid="avatar-crop-zoom-in"
            onClick={() => { handleZoomStep('in'); }}
            disabled={zoom >= 4.0 || isSaving}
          >
            +
          </button>
          <span className="kb-avatar-crop-zoom-value" data-testid="avatar-crop-zoom-value">
            {zoom.toFixed(1)}x
          </span>
        </div>

        <div className="kb-avatar-crop-actions">
          <button
            type="button"
            className="kb-personal-settings-btn kb-personal-settings-btn-secondary"
            data-testid="avatar-crop-cancel-btn"
            onClick={onClose}
            disabled={isSaving}
          >
            Cancel
          </button>
          <button
            type="button"
            className="kb-personal-settings-btn kb-personal-settings-btn-primary"
            data-testid="avatar-crop-save-btn"
            onClick={handleSave}
            disabled={isSaving}
          >
            {isSaving ? 'Saving...' : 'Save Picture'}
          </button>
        </div>
      </div>
    </div>
  );
}
