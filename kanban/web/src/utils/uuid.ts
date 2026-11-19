/**
 * Unified UUID and Clipboard Utilities.
 * Hardened for non-HTTPS and non-Secure Context environments.
 */

/**
 * Generates an RFC 4122 version 4 UUID.
 *
 * In Secure Contexts (HTTPS / localhost), utilizes the native `crypto.randomUUID()`.
 * In non-secure contexts (HTTP / IP addresses) where `crypto.randomUUID` is undefined,
 * falls back to cryptographically strong random values from `crypto.getRandomValues()`.
 * If Web Crypto is entirely unavailable, falls back to `Math.random()`.
 */
export function safeRandomUUID(): string {
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.randomUUID === 'function'
  ) {
    try {
      return crypto.randomUUID();
    } catch {
      // In case randomUUID throws in a non-standard runtime
    }
  }

  const bytes = new Uint8Array(16);
  if (
    typeof crypto !== 'undefined' &&
    typeof crypto.getRandomValues === 'function'
  ) {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i++) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }

  // RFC 4122 v4 variant and version bits
  // byte 6: 0100xxxx (version 4)
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  // byte 8: 10xxxxxx (variant 1: 10x)
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;

  const hex: string[] = [];
  for (const b of bytes) {
    hex.push(b.toString(16).padStart(2, '0'));
  }

  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-');
}

/**
 * Copies text to the system clipboard asynchronously.
 *
 * Uses `navigator.clipboard.writeText()` when available in Secure Contexts.
 * Falls back to creating a hidden `<textarea>` with `document.execCommand('copy')`
 * in non-HTTPS / legacy contexts or if clipboard permissions are restricted.
 * Returns true if the copy succeeded, false if unsupported, or throws the underlying error if rejected.
 */
export async function safeCopyToClipboard(text: string): Promise<boolean> {
  let clipboardError: unknown = null;

  if (
    typeof navigator !== 'undefined' &&
    'clipboard' in navigator &&
    typeof navigator.clipboard.writeText === 'function'
  ) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err: unknown) {
      clipboardError = err;
      // Fallback to execCommand on permission/context error
    }
  }

  if (typeof document !== 'undefined') {
    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.setAttribute('aria-hidden', 'true');
      textarea.style.position = 'fixed';
      textarea.style.top = '0';
      textarea.style.left = '-9999px';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);

      const selection = document.getSelection();
      const originalRange =
        selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

      textarea.select();
      textarea.setSelectionRange(0, textarea.value.length);

      let success = false;
      /* eslint-disable @typescript-eslint/no-deprecated */
      if (typeof document.execCommand === 'function') {
        success = document.execCommand('copy');
      }
      /* eslint-enable @typescript-eslint/no-deprecated */
      document.body.removeChild(textarea);

      if (originalRange && selection) {
        selection.removeAllRanges();
        selection.addRange(originalRange);
      }
      if (success) {
        return true;
      }
    } catch {
      // execCommand failure returns false below unless clipboardError was set
    }
  }

  if (clipboardError !== null && clipboardError !== undefined) {
    // eslint-disable-next-line @typescript-eslint/only-throw-error
    throw clipboardError;
  }

  return false;
}
