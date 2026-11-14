// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  animateCardSnapBack,
  isReducedMotionPreferred,
  useCardSnapBackAnimation,
  SNAPBACK_DURATION_MS,
} from '../useCardSnapBackAnimation';

describe('useCardSnapBackAnimation & animateCardSnapBack (KB-P5-25)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe('isReducedMotionPreferred', () => {
    it('returns true when media query matches', () => {
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('prefers-reduced-motion: reduce'),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));

      expect(isReducedMotionPreferred()).toBe(true);
    });

    it('returns false when media query does not match', () => {
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));

      expect(isReducedMotionPreferred()).toBe(false);
    });

    it('returns false when window.matchMedia is undefined', () => {
      // @ts-expect-error simulating environment without matchMedia
      delete window.matchMedia;
      expect(isReducedMotionPreferred()).toBe(false);
    });
  });

  describe('animateCardSnapBack', () => {
    it('returns 0 when element or firstRect is null', () => {
      const onComplete = vi.fn();
      expect(animateCardSnapBack(null, { left: 10, top: 10 }, { onComplete })).toBe(0);
      expect(onComplete).toHaveBeenCalledTimes(1);

      const div = document.createElement('div');
      expect(animateCardSnapBack(div, null, { onComplete })).toBe(0);
      expect(onComplete).toHaveBeenCalledTimes(2);
    });

    it('executes in 0ms under prefers-reduced-motion: reduce', () => {
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('prefers-reduced-motion: reduce'),
        media: query,
      }));

      const div = document.createElement('div');
      const onComplete = vi.fn();
      const duration = animateCardSnapBack(div, { left: 200, top: 100 }, { onComplete });

      expect(duration).toBe(0);
      expect(onComplete).toHaveBeenCalledTimes(1);
      expect(div.style.transform).toBe('');
    });

    it('returns 0 and calls onComplete when displacement is negligible (< 1px)', () => {
      window.matchMedia = vi.fn().mockReturnValue({ matches: false });
      const div = document.createElement('div');
      div.getBoundingClientRect = vi.fn().mockReturnValue({
        left: 100,
        top: 100,
        width: 300,
        height: 120,
      });

      const onComplete = vi.fn();
      const duration = animateCardSnapBack(div, { left: 100.2, top: 100.4 }, { onComplete });

      expect(duration).toBe(0);
      expect(onComplete).toHaveBeenCalledTimes(1);
    });

    it('applies 240ms FLIP transform and cleans up upon transitionend', () => {
      window.matchMedia = vi.fn().mockReturnValue({ matches: false });
      const div = document.createElement('div');
      div.getBoundingClientRect = vi.fn().mockReturnValue({
        left: 100,
        top: 200,
        width: 320,
        height: 140,
      });

      const onComplete = vi.fn();
      const duration = animateCardSnapBack(div, { left: 450, top: 250 }, { onComplete });

      expect(duration).toBe(SNAPBACK_DURATION_MS);

      // Inverted starting position
      expect(div.style.transform).toBe('translate3d(350px, 50px, 0)');

      // Advance requestAnimationFrame
      act(() => {
        vi.advanceTimersByTime(16);
      });

      expect(div.style.transform).toBe('translate3d(0, 0, 0)');
      expect(div.style.transition).toContain('240ms cubic-bezier(0.2, 0, 0, 1)');

      // Non-matching transitionend (e.g. wrong property or wrong target) does not clean up
      div.dispatchEvent(new TransitionEvent('transitionend', { propertyName: 'opacity' }));
      expect(onComplete).not.toHaveBeenCalled();

      // Simulate transitionend
      div.dispatchEvent(new TransitionEvent('transitionend', { propertyName: 'transform' }));

      expect(div.style.transform).toBe('');
      expect(div.style.transition).toBe('');
      expect(onComplete).toHaveBeenCalledTimes(1);
    });

    it('triggers layout reflow with offsetHeight and custom timing/duration', () => {
      window.matchMedia = vi.fn().mockReturnValue({ matches: false });
      const div = document.createElement('div');
      Object.defineProperty(div, 'offsetHeight', { value: 120, configurable: true });
      div.getBoundingClientRect = vi.fn().mockReturnValue({
        left: 100,
        top: 200,
        width: 100,
        height: 100,
      });

      const onComplete = vi.fn();
      const dur = animateCardSnapBack(
        div,
        { left: 50, top: 150 },
        { durationMs: 300, timingFunction: 'ease-out', onComplete },
      );

      expect(dur).toBe(300);
    });

    it('cleans up via safety timeout if transitionend is not fired', () => {
      window.matchMedia = vi.fn().mockReturnValue({ matches: false });
      const div = document.createElement('div');
      div.getBoundingClientRect = vi.fn().mockReturnValue({
        left: 100,
        top: 100,
        width: 300,
        height: 120,
      });

      const onComplete = vi.fn();
      animateCardSnapBack(div, { left: 500, top: 300 }, { onComplete });

      act(() => {
        vi.advanceTimersByTime(SNAPBACK_DURATION_MS + 60);
      });

      expect(div.style.transform).toBe('');
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
  });

  describe('useCardSnapBackAnimation Hook', () => {
    it('records position and triggers snap-back animation', () => {
      const { result } = renderHook(() => useCardSnapBackAnimation());

      const div = document.createElement('div');
      div.getBoundingClientRect = vi.fn().mockReturnValue({
        left: 300,
        top: 150,
        width: 320,
        height: 120,
      });

      // Record target column position
      act(() => {
        result.current.recordPosition('KAN-8', div);
      });

      // Layout reverts back to origin
      div.getBoundingClientRect = vi.fn().mockReturnValue({
        left: 50,
        top: 150,
        width: 320,
        height: 120,
      });

      const onComplete = vi.fn();
      let duration = 0;
      act(() => {
        duration = result.current.triggerSnapBack('KAN-8', div, { onComplete });
      });

      expect(duration).toBe(SNAPBACK_DURATION_MS);
      expect(div.style.transform).toBe('translate3d(250px, 0px, 0)');
    });

    it('cleans up recorded rect when passing null element', () => {
      const { result } = renderHook(() => useCardSnapBackAnimation());
      const div = document.createElement('div');
      div.getBoundingClientRect = vi.fn().mockReturnValue({ left: 100, top: 100 });

      act(() => {
        result.current.recordPosition('KAN-8', div);
        result.current.recordPosition('KAN-8', null);
      });

      const onComplete = vi.fn();
      const duration = result.current.triggerSnapBack('KAN-8', div, { onComplete });
      expect(duration).toBe(0);
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
  });
});
