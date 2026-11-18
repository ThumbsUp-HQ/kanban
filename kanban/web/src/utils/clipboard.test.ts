import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { copyToClipboard, useClipboard } from './clipboard';

describe('Universal Clipboard Utility (clipboard.ts)', () => {
  const originalNavigator = globalThis.navigator;
  const originalIsSecureContext = window.isSecureContext;

  beforeEach(() => {
    vi.restoreAllMocks();
    /* eslint-disable @typescript-eslint/no-deprecated */
    document.execCommand = vi.fn().mockReturnValue(true);
    /* eslint-enable @typescript-eslint/no-deprecated */
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'navigator', {
      value: originalNavigator,
      writable: true,
      configurable: true,
    });
    Object.defineProperty(window, 'isSecureContext', {
      value: originalIsSecureContext,
      writable: true,
      configurable: true,
    });
  });

  describe('copyToClipboard', () => {
    it('uses navigator.clipboard.writeText when available in a secure context', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
      Object.defineProperty(globalThis, 'navigator', {
        value: {
          clipboard: {
            writeText: writeTextMock,
          },
        },
        writable: true,
        configurable: true,
      });

      const result = await copyToClipboard('secure-token-123');
      expect(result).toBe(true);
      expect(writeTextMock).toHaveBeenCalledWith('secure-token-123');
    });

    it('falls back to execCommand when navigator.clipboard.writeText rejects', async () => {
      const writeTextMock = vi.fn().mockRejectedValue(new Error('Permission denied'));
      Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
      Object.defineProperty(globalThis, 'navigator', {
        value: {
          clipboard: {
            writeText: writeTextMock,
          },
        },
        writable: true,
        configurable: true,
      });

      /* eslint-disable @typescript-eslint/no-deprecated */
      const execCommandMock = vi.fn().mockReturnValue(true);
      document.execCommand = execCommandMock;

      const result = await copyToClipboard('fallback-token-456');
      expect(result).toBe(true);
      expect(writeTextMock).toHaveBeenCalledWith('fallback-token-456');
      expect(execCommandMock).toHaveBeenCalledWith('copy');
      /* eslint-enable @typescript-eslint/no-deprecated */
    });

    it('falls back to execCommand on plain HTTP (isSecureContext === false)', async () => {
      const writeTextMock = vi.fn();
      Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
      Object.defineProperty(globalThis, 'navigator', {
        value: {
          clipboard: {
            writeText: writeTextMock,
          },
        },
        writable: true,
        configurable: true,
      });

      /* eslint-disable @typescript-eslint/no-deprecated */
      const execCommandMock = vi.fn().mockReturnValue(true);
      document.execCommand = execCommandMock;

      const result = await copyToClipboard('http-lan-token-789');
      expect(result).toBe(true);
      expect(writeTextMock).not.toHaveBeenCalled();
      expect(execCommandMock).toHaveBeenCalledWith('copy');
      /* eslint-enable @typescript-eslint/no-deprecated */
    });

    it('falls back to execCommand when navigator.clipboard is undefined', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {},
        writable: true,
        configurable: true,
      });

      /* eslint-disable @typescript-eslint/no-deprecated */
      const execCommandMock = vi.fn().mockReturnValue(true);
      document.execCommand = execCommandMock;

      const result = await copyToClipboard('no-clipboard-api-text');
      expect(result).toBe(true);
      expect(execCommandMock).toHaveBeenCalledWith('copy');
      /* eslint-enable @typescript-eslint/no-deprecated */
    });

    it('returns false when both clipboard API and execCommand fail', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {},
        writable: true,
        configurable: true,
      });

      /* eslint-disable @typescript-eslint/no-deprecated */
      document.execCommand = vi.fn().mockReturnValue(false);
      /* eslint-enable @typescript-eslint/no-deprecated */

      const result = await copyToClipboard('failing-text');
      expect(result).toBe(false);
    });

    it('returns false when document throws during fallback', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {},
        writable: true,
        configurable: true,
      });

      vi.spyOn(document.body, 'appendChild').mockImplementation(() => {
        throw new Error('DOM attachment failed');
      });

      const result = await copyToClipboard('dom-error-text');
      expect(result).toBe(false);
    });

    it('returns false when document is undefined', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {},
        writable: true,
        configurable: true,
      });
      const originalDoc = globalThis.document;
      // @ts-expect-error simulating non-DOM / SSR
      delete globalThis.document;

      const result = await copyToClipboard('no-dom-text');
      expect(result).toBe(false);

      globalThis.document = originalDoc;
    });

    it('preserves existing user text selection after copying via execCommand', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {},
        writable: true,
        configurable: true,
      });

      /* eslint-disable @typescript-eslint/no-deprecated */
      document.execCommand = vi.fn().mockReturnValue(true);
      /* eslint-enable @typescript-eslint/no-deprecated */

      const mockRange = {} as Range;
      const removeAllRanges = vi.fn();
      const addRange = vi.fn();

      vi.spyOn(document, 'getSelection').mockReturnValue({
        rangeCount: 1,
        getRangeAt: () => mockRange,
        removeAllRanges,
        addRange,
      } as unknown as Selection);

      const result = await copyToClipboard('selection-preserved-text');
      expect(result).toBe(true);
      expect(removeAllRanges).toHaveBeenCalled();
      expect(addRange).toHaveBeenCalledWith(mockRange);
    });
  });

  describe('useClipboard hook', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('manages copied state transitions and auto-resets after timeout', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {
          clipboard: {
            writeText: vi.fn().mockResolvedValue(undefined),
          },
        },
        writable: true,
        configurable: true,
      });

      const { result } = renderHook(() => useClipboard({ timeoutMs: 1500 }));
      expect(result.current.copied).toBe(false);

      let success = false;
      await act(async () => {
        success = await result.current.copy('test-string');
      });

      expect(success).toBe(true);
      expect(result.current.copied).toBe(true);

      // Fast-forward halfway
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(result.current.copied).toBe(true);

      // Fast-forward past timeout
      act(() => {
        vi.advanceTimersByTime(600);
      });
      expect(result.current.copied).toBe(false);
    });

    it('allows immediate manual reset', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {
          clipboard: {
            writeText: vi.fn().mockResolvedValue(undefined),
          },
        },
        writable: true,
        configurable: true,
      });

      const { result } = renderHook(() => useClipboard());

      await act(async () => {
        await result.current.copy('manual-reset-text');
      });
      expect(result.current.copied).toBe(true);

      act(() => {
        result.current.reset();
      });
      expect(result.current.copied).toBe(false);
    });

    it('clears pending timer on rapid consecutive copy calls and unmount', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {
          clipboard: {
            writeText: vi.fn().mockResolvedValue(undefined),
          },
        },
        writable: true,
        configurable: true,
      });

      const { result, unmount } = renderHook(() => useClipboard({ timeoutMs: 2000 }));

      await act(async () => {
        await result.current.copy('first-copy');
      });
      expect(result.current.copied).toBe(true);

      // Second rapid copy before timer finishes
      await act(async () => {
        await result.current.copy('second-copy');
      });
      expect(result.current.copied).toBe(true);

      // Unmount while active to trigger cleanup
      unmount();
    });

    it('does not set copied to true when copy fails', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {},
        writable: true,
        configurable: true,
      });
      /* eslint-disable @typescript-eslint/no-deprecated */
      document.execCommand = vi.fn().mockReturnValue(false);
      /* eslint-enable @typescript-eslint/no-deprecated */

      const { result } = renderHook(() => useClipboard());

      let success = true;
      await act(async () => {
        success = await result.current.copy('failing-text');
      });

      expect(success).toBe(false);
      expect(result.current.copied).toBe(false);
    });

    it('resets copied state and clears timer on reset()', async () => {
      /* eslint-disable @typescript-eslint/no-deprecated */
      document.execCommand = vi.fn().mockReturnValue(true);
      /* eslint-enable @typescript-eslint/no-deprecated */
      const { result } = renderHook(() => useClipboard());
      await act(async () => {
        await result.current.copy('test-reset');
      });
      expect(result.current.copied).toBe(true);
      act(() => {
        result.current.reset();
      });
      expect(result.current.copied).toBe(false);
      // Call reset again when timer is null
      act(() => {
        result.current.reset();
      });
      expect(result.current.copied).toBe(false);
    });
  });
});
