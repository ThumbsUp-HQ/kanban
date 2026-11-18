/**
 * Universal Plain-HTTP & HTTPS Clipboard Utility (KB-P3-16, KANBA-227).
 * Uses navigator.clipboard.writeText when available in secure contexts,
 * and automatically falls back to hidden offscreen <textarea> + document.execCommand('copy')
 * on plain HTTP (http://<LAN-IP>:8921) or restricted browser contexts.
 */

import { useState, useCallback, useEffect, useRef } from 'react';

/**
 * Copies text to the system clipboard across HTTPS, localhost, and plain HTTP (LAN IP).
 * Returns true if the copy operation succeeded, false otherwise.
 * Never throws unhandled exceptions.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  // 1. Try modern Async Clipboard API in secure contexts
  if (
    typeof navigator !== 'undefined' &&
    'clipboard' in navigator &&
    typeof navigator.clipboard.writeText === 'function' &&
    (typeof window === 'undefined' || (window as unknown as { isSecureContext?: boolean }).isSecureContext !== false)
  ) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Rejection (e.g. not focused, permission denied, or plain HTTP) -> fall through to execCommand
    }
  }

  // 2. Fallback to offscreen textarea + document.execCommand('copy')
  if (typeof document !== 'undefined') {
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.setAttribute('aria-hidden', 'true');
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      textarea.style.top = '-9999px';
      textarea.style.opacity = '0';
      textarea.style.pointerEvents = 'none';
      document.body.appendChild(textarea);

      const selection = document.getSelection();
      const originalRange =
        selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

      textarea.select();
      textarea.setSelectionRange(0, textarea.value.length);

      // eslint-disable-next-line @typescript-eslint/no-deprecated
      const successful = document.execCommand('copy');
      document.body.removeChild(textarea);

      if (originalRange && selection) {
        selection.removeAllRanges();
        selection.addRange(originalRange);
      }

      return successful;
    } catch {
      return false;
    }
  }

  return false;
}

export interface UseClipboardOptions {
  timeoutMs?: number;
}

/**
 * React hook that manages copied status with automatic timer cleanup.
 */
export function useClipboard(options: UseClipboardOptions = {}): {
  copied: boolean;
  copy: (text: string) => Promise<boolean>;
  reset: () => void;
} {
  const timeoutMs = options.timeoutMs ?? 2000;
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const reset = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setCopied(false);
  }, []);

  const copy = useCallback(
    async (text: string): Promise<boolean> => {
      const success = await copyToClipboard(text);
      if (success) {
        if (timerRef.current !== null) {
          clearTimeout(timerRef.current);
        }
        setCopied(true);
        timerRef.current = setTimeout(() => {
          setCopied(false);
          timerRef.current = null;
        }, timeoutMs);
      }
      return success;
    },
    [timeoutMs],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  return { copied, copy, reset };
}
