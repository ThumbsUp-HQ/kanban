import { describe, expect, it } from 'vitest';
import {
  HINT_OFFSET_PX,
  HINT_VIEWPORT_MARGIN_PX,
  positionHint,
} from './positionHint';

describe('positionHint', () => {
  const defaultViewport = { width: 1440, height: 900 };
  const defaultPopup = { width: 280, height: 80 };

  it('prefers bottom placement with 8px offset when room permits', () => {
    const trigger = { top: 100, left: 200, width: 24, height: 24 };
    const pos = positionHint(trigger, defaultPopup, defaultViewport);

    expect(pos.placement).toBe('bottom');
    expect(pos.top).toBe(100 + 24 + HINT_OFFSET_PX); // 132
    expect(pos.left).toBe(200);
  });

  it('boundary positioning: trigger at x=0 clamps left = 8', () => {
    const trigger = { top: 100, left: 0, width: 24, height: 24 };
    const pos = positionHint(trigger, defaultPopup, defaultViewport);

    expect(pos.left).toBe(HINT_VIEWPORT_MARGIN_PX); // 8
  });

  it('boundary positioning: trigger at bottom-right corner of 390x844 flips to top and clamps left >= 8', () => {
    const mobileViewport = { width: 390, height: 844 };
    const popup = { width: 260, height: 100 };
    // Trigger at bottom right corner (top: 810, left: 360, width: 24, height: 24)
    const trigger = { top: 810, left: 360, width: 24, height: 24 };
    const pos = positionHint(trigger, popup, mobileViewport);

    expect(pos.placement).toBe('top');
    expect(pos.top).toBe(810 - 100 - HINT_OFFSET_PX); // 702
    expect(pos.left).toBeGreaterThanOrEqual(8);
    // Max left is 390 - 260 - 8 = 122
    expect(pos.left).toBe(122);
    // Verify popup does not exceed right edge
    expect(pos.left + popup.width).toBeLessThanOrEqual(mobileViewport.width - 8);
  });

  it('clamps left when trigger is near right edge of desktop viewport', () => {
    const trigger = { top: 100, left: 1400, width: 24, height: 24 };
    const pos = positionHint(trigger, defaultPopup, defaultViewport);

    // 1440 - 280 - 8 = 1152
    expect(pos.left).toBe(1152);
    expect(pos.left + defaultPopup.width).toBe(1440 - 8);
  });

  it('clamps top to margin when flipping to top in a very short viewport', () => {
    const crampedViewport = { width: 400, height: 120 };
    const tallPopup = { width: 200, height: 90 };
    const trigger = { top: 50, left: 50, width: 24, height: 24 };

    // Bottom candidate: 50 + 24 + 8 = 82; 82 + 90 = 172 > 120 - 8 (112) -> flips to top
    // Top candidate: 50 - 90 - 8 = -48 -> clamped to HINT_VIEWPORT_MARGIN_PX (8)
    const pos = positionHint(trigger, tallPopup, crampedViewport);

    expect(pos.placement).toBe('top');
    expect(pos.top).toBe(HINT_VIEWPORT_MARGIN_PX);
  });
});
