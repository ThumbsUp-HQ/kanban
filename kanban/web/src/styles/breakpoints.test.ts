import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { BP, getBreakpoint, useBreakpoint } from './breakpoints';

describe('Responsive Breakpoints (breakpoints.ts)', () => {
  const originalMatchMedia =
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia.bind(window)
      : undefined;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    if (originalMatchMedia) {
      window.matchMedia = originalMatchMedia;
    } else {
      Reflect.deleteProperty(window, 'matchMedia');
    }
  });

  it('exports canonical S6.1 breakpoint constants', () => {
    expect(BP.mobileMax).toBe(767);
    expect(BP.tabletMax).toBe(1279);
  });

  function setupMatchMedia(width: number): {
    listeners: Map<string, Set<(e: MediaQueryListEvent) => void>>;
    triggerChange: (query: string, matches: boolean) => void;
  } {
    const listeners = new Map<string, Set<(e: MediaQueryListEvent) => void>>();

    window.matchMedia = vi.fn().mockImplementation((query: string) => {
      let matches = false;
      if (query === `(max-width: ${String(BP.mobileMax)}px)`) {
        matches = width <= BP.mobileMax;
      } else if (query === `(max-width: ${String(BP.tabletMax)}px)`) {
        matches = width <= BP.tabletMax;
      }

      if (!listeners.has(query)) {
        listeners.set(query, new Set());
      }

      return {
        matches,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn((event: string, handler: (e: MediaQueryListEvent) => void) => {
          if (event === 'change') {
            listeners.get(query)?.add(handler);
          }
        }),
        removeEventListener: vi.fn((event: string, handler: (e: MediaQueryListEvent) => void) => {
          if (event === 'change') {
            listeners.get(query)?.delete(handler);
          }
        }),
        dispatchEvent: vi.fn(),
      };
    });

    return {
      listeners,
      triggerChange: (query: string, matches: boolean) => {
        const queryListeners = listeners.get(query);
        if (queryListeners) {
          const event = { matches, media: query } as MediaQueryListEvent;
          for (const listener of queryListeners) {
            listener(event);
          }
        }
      },
    };
  }

  describe('getBreakpoint() boundary evaluations', () => {
    it('returns mobile at 767px boundary', () => {
      setupMatchMedia(767);
      expect(getBreakpoint()).toBe('mobile');
    });

    it('returns tablet at 768px boundary', () => {
      setupMatchMedia(768);
      expect(getBreakpoint()).toBe('tablet');
    });

    it('returns tablet at 1279px boundary', () => {
      setupMatchMedia(1279);
      expect(getBreakpoint()).toBe('tablet');
    });

    it('returns desktop at 1280px boundary', () => {
      setupMatchMedia(1280);
      expect(getBreakpoint()).toBe('desktop');
    });

    it('falls back safely to desktop when matchMedia is missing', () => {
      // @ts-expect-error simulating missing matchMedia
      window.matchMedia = undefined;
      expect(getBreakpoint()).toBe('desktop');
    });
  });

  describe('useBreakpoint() hook reactivity and cleanup', () => {
    it('returns initial breakpoint matching current viewport', () => {
      setupMatchMedia(390);
      const { result } = renderHook(() => useBreakpoint());
      expect(result.current).toBe('mobile');
    });

    it('updates breakpoint when viewport query changes', () => {
      const { triggerChange } = setupMatchMedia(767);
      const { result } = renderHook(() => useBreakpoint());
      expect(result.current).toBe('mobile');

      // Resize to desktop (neither mobile nor tablet matches)
      act(() => {
        setupMatchMedia(1440);
        triggerChange(`(max-width: ${String(BP.mobileMax)}px)`, false);
      });

      expect(result.current).toBe('desktop');
    });

    it('registers and removes change event listeners cleanly on unmount', () => {
      const { listeners } = setupMatchMedia(1024);
      const { unmount } = renderHook(() => useBreakpoint());

      const mobileListeners = listeners.get(`(max-width: ${String(BP.mobileMax)}px)`);
      const tabletListeners = listeners.get(`(max-width: ${String(BP.tabletMax)}px)`);

      expect(mobileListeners?.size).toBe(1);
      expect(tabletListeners?.size).toBe(1);

      unmount();

      expect(mobileListeners?.size).toBe(0);
      expect(tabletListeners?.size).toBe(0);
    });

    it('falls back safely to desktop when matchMedia is missing', () => {
      // @ts-expect-error simulating missing matchMedia
      window.matchMedia = undefined;
      const { result } = renderHook(() => useBreakpoint());
      expect(result.current).toBe('desktop');
    });
  });
});
