import { describe, it, expect, vi, afterEach } from 'vitest';
import { safeRandomUUID, safeCopyToClipboard } from './uuid';

describe('uuid and clipboard utilities', () => {
  const originalCrypto = globalThis.crypto;
  const originalNavigator = globalThis.navigator;

  afterEach(() => {
    Object.defineProperty(globalThis, 'crypto', {
      value: originalCrypto,
      writable: true,
      configurable: true,
    });
    Object.defineProperty(globalThis, 'navigator', {
      value: originalNavigator,
      writable: true,
      configurable: true,
    });
    vi.restoreAllMocks();
  });

  describe('safeRandomUUID', () => {
    const UUID_V4_REGEX =
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

    it('generates a valid UUIDv4 when crypto.randomUUID is available', () => {
      const uuid = safeRandomUUID();
      expect(uuid).toMatch(UUID_V4_REGEX);
    });

    it('falls back to crypto.getRandomValues when crypto.randomUUID is undefined (HTTP non-secure context)', () => {
      const mockGetRandomValues = vi.fn((arr: Uint8Array) => {
        for (let i = 0; i < arr.length; i++) {
          arr[i] = i * 16;
        }
        return arr;
      });

      Object.defineProperty(globalThis, 'crypto', {
        value: {
          getRandomValues: mockGetRandomValues,
        },
        writable: true,
        configurable: true,
      });

      const uuid = safeRandomUUID();
      expect(mockGetRandomValues).toHaveBeenCalled();
      expect(uuid).toMatch(UUID_V4_REGEX);
    });

    it('falls back to getRandomValues if crypto.randomUUID throws an exception', () => {
      const mockGetRandomValues = vi.fn((arr: Uint8Array) => {
        for (let i = 0; i < arr.length; i++) {
          arr[i] = i * 8;
        }
        return arr;
      });

      Object.defineProperty(globalThis, 'crypto', {
        value: {
          randomUUID: () => {
            throw new Error('Not allowed in this context');
          },
          getRandomValues: mockGetRandomValues,
        },
        writable: true,
        configurable: true,
      });

      const uuid = safeRandomUUID();
      expect(mockGetRandomValues).toHaveBeenCalled();
      expect(uuid).toMatch(UUID_V4_REGEX);
    });

    it('falls back to Math.random when Web Crypto API is unavailable', () => {
      Object.defineProperty(globalThis, 'crypto', {
        value: undefined,
        writable: true,
        configurable: true,
      });

      const uuid = safeRandomUUID();
      expect(uuid).toMatch(UUID_V4_REGEX);
    });
  });

  describe('safeCopyToClipboard', () => {
    it('uses navigator.clipboard.writeText when available', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(globalThis, 'navigator', {
        value: {
          clipboard: {
            writeText: writeTextMock,
          },
        },
        writable: true,
        configurable: true,
      });

      const success = await safeCopyToClipboard('test-token');
      expect(success).toBe(true);
      expect(writeTextMock).toHaveBeenCalledWith('test-token');
    });

    it('falls back to execCommand when navigator.clipboard is missing', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {},
        writable: true,
        configurable: true,
      });

      /* eslint-disable @typescript-eslint/no-deprecated */
      const execCommandMock = vi.fn().mockReturnValue(true);
      document.execCommand = execCommandMock;

      const success = await safeCopyToClipboard('fallback-text');
      expect(success).toBe(true);
      expect(execCommandMock).toHaveBeenCalledWith('copy');
      /* eslint-enable @typescript-eslint/no-deprecated */
    });

    it('falls back to execCommand when navigator.clipboard.writeText rejects', async () => {
      const writeTextMock = vi
        .fn()
        .mockRejectedValue(new Error('Permission denied'));
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

      const success = await safeCopyToClipboard('fallback-on-rejection');
      expect(success).toBe(true);
      expect(writeTextMock).toHaveBeenCalledWith('fallback-on-rejection');
      expect(execCommandMock).toHaveBeenCalledWith('copy');
      /* eslint-enable @typescript-eslint/no-deprecated */
    });

    it('returns false if execCommand copy fails', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {},
        writable: true,
        configurable: true,
      });

      /* eslint-disable @typescript-eslint/no-deprecated */
      document.execCommand = vi.fn().mockImplementation(() => {
        throw new Error('Command failed');
      });

      const success = await safeCopyToClipboard('failed-text');
      expect(success).toBe(false);
      /* eslint-enable @typescript-eslint/no-deprecated */
    });

    it('restores selection range when rangeCount > 0 and execCommand succeeds', async () => {
      Object.defineProperty(globalThis, 'navigator', {
        value: {},
        writable: true,
        configurable: true,
      });

      const mockRange = {} as Range;
      const removeAllRangesSpy = vi.fn();
      const addRangeSpy = vi.fn();
      const getSelectionSpy = vi.spyOn(document, 'getSelection').mockReturnValue({
        rangeCount: 1,
        getRangeAt: vi.fn().mockReturnValue(mockRange),
        removeAllRanges: removeAllRangesSpy,
        addRange: addRangeSpy,
      } as unknown as Selection);

      /* eslint-disable @typescript-eslint/no-deprecated */
      const execCommandMock = vi.fn().mockReturnValue(true);
      document.execCommand = execCommandMock;

      const success = await safeCopyToClipboard('preserved-selection');
      expect(success).toBe(true);
      expect(removeAllRangesSpy).toHaveBeenCalled();
      expect(addRangeSpy).toHaveBeenCalledWith(mockRange);
      getSelectionSpy.mockRestore();
      /* eslint-enable @typescript-eslint/no-deprecated */
    });

    it('rethrows clipboardError if navigator.clipboard.writeText rejects and execCommand fails', async () => {
      const originalErr = new Error('Clipboard rejected');
      const writeTextMock = vi.fn().mockRejectedValue(originalErr);
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
      document.execCommand = vi.fn().mockReturnValue(false);

      await expect(safeCopyToClipboard('failing-clipboard')).rejects.toThrow('Clipboard rejected');
      /* eslint-enable @typescript-eslint/no-deprecated */
    });

    it('handles clipboard failure when document is undefined', async () => {
      const originalDoc = globalThis.document;
      const originalErr = new Error('No clipboard in worker');
      Object.defineProperty(globalThis, 'navigator', {
        value: {
          clipboard: {
            writeText: vi.fn().mockRejectedValue(originalErr),
          },
        },
        writable: true,
        configurable: true,
      });

      try {
        // @ts-expect-error test undefined document in worker/node environment
        delete globalThis.document;
        await expect(safeCopyToClipboard('worker-text')).rejects.toThrow('No clipboard in worker');
      } finally {
        globalThis.document = originalDoc;
      }
    });
  });
});
