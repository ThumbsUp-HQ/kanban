/**
 * Pure geometric positioning function for <EmojiHint> popups (KB-P3-31, S6.2).
 * Prefers bottom placement with 8px offset, flips to top if bottom edge exceeds
 * viewport boundary, and clamps left into [8, viewport.width - popupWidth - 8].
 */

export interface RectLike {
  readonly top: number;
  readonly left: number;
  readonly width: number;
  readonly height: number;
  readonly bottom?: number;
  readonly right?: number;
}

export interface SizeLike {
  readonly width: number;
  readonly height: number;
}

export interface ViewportLike {
  readonly width: number;
  readonly height: number;
}

export interface HintPosition {
  readonly top: number;
  readonly left: number;
  readonly placement: 'top' | 'bottom';
}

export const HINT_OFFSET_PX = 8;
export const HINT_VIEWPORT_MARGIN_PX = 8;

/**
 * Calculates clamped viewport coordinates for popup placement.
 */
export function positionHint(
  triggerRect: RectLike,
  popupSize: SizeLike,
  viewport: ViewportLike,
): HintPosition {
  const popupWidth = popupSize.width;
  const popupHeight = popupSize.height;

  let placement: 'top' | 'bottom' = 'bottom';
  let top = triggerRect.top + triggerRect.height + HINT_OFFSET_PX;

  // Flip to top if bottom edge exceeds viewport.height - 8
  if (top + popupHeight > viewport.height - HINT_VIEWPORT_MARGIN_PX) {
    placement = 'top';
    top = triggerRect.top - popupHeight - HINT_OFFSET_PX;
  }

  // Ensure top doesn't fall below margin if viewport is extremely cramped
  if (top < HINT_VIEWPORT_MARGIN_PX) {
    top = HINT_VIEWPORT_MARGIN_PX;
  }

  // Clamp left into [8, viewport.width - popupWidth - 8]
  const minLeft = HINT_VIEWPORT_MARGIN_PX;
  const maxLeft = Math.max(minLeft, viewport.width - popupWidth - HINT_VIEWPORT_MARGIN_PX);
  const left = Math.max(minLeft, Math.min(triggerRect.left, maxLeft));

  return {
    top: Math.round(top),
    left: Math.round(left),
    placement,
  };
}
