/**
 * Pure Math Engine for Media Pan and Cursor-Centered Zoom (KB-P3-48, S5.4).
 * Enforces zoom bounds (10% - 800%), cursor-centered coordinate invariance,
 * and drag pan translation.
 */

export const MIN_ZOOM = 0.10; // 10%
export const MAX_ZOOM = 8.00; // 800%
export const ZOOM_STEP = 1.25;

export interface TransformState {
  readonly scale: number;
  readonly tx: number;
  readonly ty: number;
}

export interface Point {
  readonly x: number;
  readonly y: number;
}

export const INITIAL_TRANSFORM: TransformState = Object.freeze({
  scale: 1,
  tx: 0,
  ty: 0,
});

/**
 * Clamps zoom scale to the [MIN_ZOOM, MAX_ZOOM] interval.
 */
export function clampZoom(scale: number): number {
  if (Number.isNaN(scale) || !Number.isFinite(scale)) {
    return 1;
  }
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, scale));
}

/**
 * Computes updated transform keeping the world point under focalPoint invariant.
 */
export function zoomAtPoint(
  current: TransformState,
  focalPoint: Point,
  zoomFactor: number,
): TransformState {
  const nextScale = clampZoom(current.scale * zoomFactor);
  if (Math.abs(nextScale - current.scale) < 0.0001) {
    return current;
  }

  // World coordinates of the focal point before zoom
  const worldX = (focalPoint.x - current.tx) / current.scale;
  const worldY = (focalPoint.y - current.ty) / current.scale;

  // New translation to keep world coordinates anchored under focalPoint
  const nextTx = focalPoint.x - worldX * nextScale;
  const nextTy = focalPoint.y - worldY * nextScale;

  return {
    scale: nextScale,
    tx: nextTx,
    ty: nextTy,
  };
}

/**
 * Applies drag delta to current translation.
 */
export function panBy(
  current: TransformState,
  dx: number,
  dy: number,
): TransformState {
  return {
    scale: current.scale,
    tx: current.tx + dx,
    ty: current.ty + dy,
  };
}

/**
 * Resets transform back to 100% zoom and centered translation.
 */
export function resetTransform(): TransformState {
  return INITIAL_TRANSFORM;
}

/**
 * Formats zoom scale as integer percentage (e.g. 1.25 -> "125%").
 */
export function formatZoomPercentage(scale: number): string {
  return `${String(Math.round(scale * 100))}%`;
}

/**
 * Builds CSSOM transform string strictly avoiding JSX inline attribute strings.
 */
export function buildCssomTransform(state: TransformState): string {
  return `translate3d(${String(state.tx)}px, ${String(state.ty)}px, 0) scale(${String(state.scale)})`;
}
