import { useEffect, type RefObject } from 'react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

/**
 * Traps Tab and Shift+Tab navigation within containerRef when active.
 * Used exclusively on mobile viewports for modal sheet accessibility.
 */
export function useFocusTrap(active: boolean, containerRef: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    if (!active) {
      return;
    }
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key !== 'Tab') {
        return;
      }
      const focusables = Array.from(
        container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      ).filter(
        (el) =>
          !el.hasAttribute('disabled') &&
          el.getAttribute('aria-hidden') !== 'true' &&
          (el.offsetParent !== null || el.getClientRects().length > 0 || el.tabIndex >= 0),
      );

      if (focusables.length === 0) {
        e.preventDefault();
        return;
      }

      const first = focusables[0];
      const last = focusables[focusables.length - 1];

      if (!first || !last) {
        return;
      }

      if (e.shiftKey) {
        if (document.activeElement === first || !container.contains(document.activeElement)) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last || !container.contains(document.activeElement)) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [active, containerRef]);
}
