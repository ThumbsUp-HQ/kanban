/**
 * Unit Tests for Pan/Zoom Math Engine (KB-P3-48, S5.4).
 */

import { describe, it, expect } from 'vitest';
import {
  clampZoom,
  zoomAtPoint,
  panBy,
  resetTransform,
  formatZoomPercentage,
  buildCssomTransform,
  MIN_ZOOM,
  MAX_ZOOM,
  ZOOM_STEP,
  INITIAL_TRANSFORM,
} from './panZoomMath';

describe('panZoomMath', () => {
  it('clamps zoom scales strictly between MIN_ZOOM (10%) and MAX_ZOOM (800%)', () => {
    expect(clampZoom(0.01)).toBe(MIN_ZOOM);
    expect(clampZoom(0.09)).toBe(MIN_ZOOM);
    expect(clampZoom(0.10)).toBe(MIN_ZOOM);
    expect(clampZoom(1.0)).toBe(1.0);
    expect(clampZoom(4.5)).toBe(4.5);
    expect(clampZoom(8.00)).toBe(MAX_ZOOM);
    expect(clampZoom(8.01)).toBe(MAX_ZOOM);
    expect(clampZoom(100.0)).toBe(MAX_ZOOM);

    // Fallbacks for NaN or non-finite inputs
    expect(clampZoom(Number.NaN)).toBe(1);
    expect(clampZoom(Number.POSITIVE_INFINITY)).toBe(1);
  });

  it('keeps world coordinate invariant under cursor during zoomAtPoint within 0.01px', () => {
    const focalPoint = { x: 200, y: 150 };
    const initial = { scale: 1.0, tx: 0, ty: 0 };

    // World coordinates before zoom
    const initialWorldX = (focalPoint.x - initial.tx) / initial.scale;
    const initialWorldY = (focalPoint.y - initial.ty) / initial.scale;

    // Zoom in by factor 1.25
    const zoomedIn = zoomAtPoint(initial, focalPoint, ZOOM_STEP);
    expect(zoomedIn.scale).toBe(1.25);

    // World coordinates after zoom
    const zoomedWorldX = (focalPoint.x - zoomedIn.tx) / zoomedIn.scale;
    const zoomedWorldY = (focalPoint.y - zoomedIn.ty) / zoomedIn.scale;

    expect(Math.abs(zoomedWorldX - initialWorldX)).toBeLessThan(0.001);
    expect(Math.abs(zoomedWorldY - initialWorldY)).toBeLessThan(0.001);

    // Zoom out by factor 0.8
    const zoomedOut = zoomAtPoint(zoomedIn, focalPoint, 1 / ZOOM_STEP);
    const outWorldX = (focalPoint.x - zoomedOut.tx) / zoomedOut.scale;
    const outWorldY = (focalPoint.y - zoomedOut.ty) / zoomedOut.scale;

    expect(Math.abs(outWorldX - initialWorldX)).toBeLessThan(0.001);
    expect(Math.abs(outWorldY - initialWorldY)).toBeLessThan(0.001);

    // When scale does not change (e.g. at boundary), returns current state reference
    const atMax = { scale: MAX_ZOOM, tx: 50, ty: 50 };
    const unchanged = zoomAtPoint(atMax, focalPoint, 2.0);
    expect(unchanged).toBe(atMax);
  });

  it('pans translation by delta offsets', () => {
    const start = { scale: 1.5, tx: 10, ty: 20 };
    const panned = panBy(start, 25, -15);
    expect(panned.scale).toBe(1.5);
    expect(panned.tx).toBe(35);
    expect(panned.ty).toBe(5);
  });

  it('resets transform to 100% scale and 0 translation', () => {
    expect(resetTransform()).toEqual(INITIAL_TRANSFORM);
    expect(resetTransform()).toEqual({ scale: 1, tx: 0, ty: 0 });
  });

  it('formats zoom percentage correctly', () => {
    expect(formatZoomPercentage(1.0)).toBe('100%');
    expect(formatZoomPercentage(1.25)).toBe('125%');
    expect(formatZoomPercentage(0.1)).toBe('10%');
    expect(formatZoomPercentage(8.0)).toBe('800%');
    expect(formatZoomPercentage(2.556)).toBe('256%');
  });

  it('builds CSSOM transform string', () => {
    const transform = { scale: 2.5, tx: 40, ty: -30 };
    expect(buildCssomTransform(transform)).toBe('translate3d(40px, -30px, 0) scale(2.5)');
  });
});
