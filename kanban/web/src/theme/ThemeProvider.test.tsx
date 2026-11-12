import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, renderHook } from '@testing-library/react';
import React from 'react';
import {
  ThemeProvider,
  useTheme,
  sanitizeTheme,
  getSystemResolvedTheme,
  THEME_STORAGE_KEY,
} from './ThemeProvider';

function TestConsumer(): React.JSX.Element {
  const { theme, resolvedTheme, setTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolvedTheme">{resolvedTheme}</span>
      <button data-testid="btn-light" type="button" onClick={() => { setTheme('light'); }}>
        Set Light
      </button>
      <button data-testid="btn-dark" type="button" onClick={() => { setTheme('dark'); }}>
        Set Dark
      </button>
      <button data-testid="btn-system" type="button" onClick={() => { setTheme('system'); }}>
        Set System
      </button>
    </div>
  );
}

describe('ThemeProvider and useTheme', () => {
  const originalMatchMedia =
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia.bind(window)
      : undefined;

  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    vi.restoreAllMocks();
  });

  afterEach(() => {
    if (originalMatchMedia) {
      window.matchMedia = originalMatchMedia;
    } else {
      Reflect.deleteProperty(window, 'matchMedia');
    }
  });

  function setupMatchMedia(prefersDark: boolean): {
    triggerChange: (matches: boolean) => void;
    listeners: Set<(e: MediaQueryListEvent) => void>;
  } {
    const listeners = new Set<(e: MediaQueryListEvent) => void>();

    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-color-scheme: dark)' ? prefersDark : false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn((event: string, handler: (e: MediaQueryListEvent) => void) => {
        if (event === 'change') {
          listeners.add(handler);
        }
      }),
      removeEventListener: vi.fn((event: string, handler: (e: MediaQueryListEvent) => void) => {
        if (event === 'change') {
          listeners.delete(handler);
        }
      }),
      dispatchEvent: vi.fn(),
    }));

    return {
      listeners,
      triggerChange: (matches: boolean) => {
        const event = { matches, media: '(prefers-color-scheme: dark)' } as MediaQueryListEvent;
        for (const listener of listeners) {
          listener(event);
        }
      },
    };
  }

  describe('sanitizeTheme helper', () => {
    it('accepts valid theme literals', () => {
      expect(sanitizeTheme('light')).toBe('light');
      expect(sanitizeTheme('dark')).toBe('dark');
      expect(sanitizeTheme('system')).toBe('system');
    });

    it('falls back to system on null, undefined, or hostile injections', () => {
      expect(sanitizeTheme(null)).toBe('system');
      expect(sanitizeTheme('"><script>alert(1)</script>')).toBe('system');
      expect(sanitizeTheme('HIGH_CONTRAST')).toBe('system');
      expect(sanitizeTheme('')).toBe('system');
    });
  });

  describe('getSystemResolvedTheme helper', () => {
    it('returns dark when prefers-color-scheme matches dark', () => {
      setupMatchMedia(true);
      expect(getSystemResolvedTheme()).toBe('dark');
    });

    it('returns light when prefers-color-scheme is light or unsupported', () => {
      setupMatchMedia(false);
      expect(getSystemResolvedTheme()).toBe('light');

      // @ts-expect-error simulating missing matchMedia
      window.matchMedia = undefined;
      expect(getSystemResolvedTheme()).toBe('light');
    });
  });

  describe('ThemeProvider lifecycle and DOM dataset mutations', () => {
    it('defaults to system theme and removes data-theme attribute', () => {
      setupMatchMedia(false);
      render(
        <ThemeProvider>
          <TestConsumer />
        </ThemeProvider>,
      );

      expect(screen.getByTestId('theme').textContent).toBe('system');
      expect(screen.getByTestId('resolvedTheme').textContent).toBe('light');
      expect(document.documentElement.dataset.theme).toBeUndefined();
    });

    it('sets data-theme="dark" when dark is chosen', () => {
      setupMatchMedia(false);
      render(
        <ThemeProvider>
          <TestConsumer />
        </ThemeProvider>,
      );

      act(() => {
        screen.getByTestId('btn-dark').click();
      });

      expect(screen.getByTestId('theme').textContent).toBe('dark');
      expect(screen.getByTestId('resolvedTheme').textContent).toBe('dark');
      expect(document.documentElement.dataset.theme).toBe('dark');
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    });

    it('sets data-theme="light" when light is chosen', () => {
      setupMatchMedia(false);
      render(
        <ThemeProvider>
          <TestConsumer />
        </ThemeProvider>,
      );

      act(() => {
        screen.getByTestId('btn-light').click();
      });

      expect(screen.getByTestId('theme').textContent).toBe('light');
      expect(screen.getByTestId('resolvedTheme').textContent).toBe('light');
      expect(document.documentElement.dataset.theme).toBe('light');
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    });

    it('removes data-theme when returning from dark to system', () => {
      setupMatchMedia(false);
      render(
        <ThemeProvider>
          <TestConsumer />
        </ThemeProvider>,
      );

      act(() => {
        screen.getByTestId('btn-dark').click();
      });
      expect(document.documentElement.dataset.theme).toBe('dark');

      act(() => {
        screen.getByTestId('btn-system').click();
      });
      expect(document.documentElement.dataset.theme).toBeUndefined();
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system');
    });

    it('follows system dark preference changes when theme is system', () => {
      const { triggerChange } = setupMatchMedia(false);
      render(
        <ThemeProvider>
          <TestConsumer />
        </ThemeProvider>,
      );

      expect(screen.getByTestId('resolvedTheme').textContent).toBe('light');

      act(() => {
        triggerChange(true);
      });

      expect(screen.getByTestId('resolvedTheme').textContent).toBe('dark');
    });

    it('handles hostile storage contents by resetting to system without throwing', () => {
      setupMatchMedia(false);
      localStorage.setItem(THEME_STORAGE_KEY, '"><script>xss()</script>');

      render(
        <ThemeProvider>
          <TestConsumer />
        </ThemeProvider>,
      );

      expect(screen.getByTestId('theme').textContent).toBe('system');
      expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system');
      expect(document.documentElement.dataset.theme).toBeUndefined();
    });

    it('handles localStorage exceptions gracefully', () => {
      setupMatchMedia(false);
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new Error('QuotaExceeded');
      });

      render(
        <ThemeProvider>
          <TestConsumer />
        </ThemeProvider>,
      );

      // Should not throw even when storage throws
      expect(() => {
        act(() => {
          screen.getByTestId('btn-dark').click();
        });
      }).not.toThrow();

      expect(screen.getByTestId('theme').textContent).toBe('dark');
    });

    it('handles localStorage getItem throwing by falling back to system', () => {
      vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
        throw new Error('Blocked');
      });

      render(
        <ThemeProvider>
          <TestConsumer />
        </ThemeProvider>,
      );

      expect(screen.getByTestId('theme').textContent).toBe('system');
    });

    it('unregisters media query listener on unmount', () => {
      const { listeners } = setupMatchMedia(false);
      const { unmount } = render(
        <ThemeProvider>
          <TestConsumer />
        </ThemeProvider>,
      );

      expect(listeners.size).toBe(1);
      unmount();
      expect(listeners.size).toBe(0);
    });

    it('throws error when useTheme is called outside ThemeProvider', () => {
      expect(() => renderHook(() => useTheme())).toThrow(
        'useTheme must be used within a ThemeProvider',
      );
    });
  });
});
