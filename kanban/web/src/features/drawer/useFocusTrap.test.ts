import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useRef } from 'react';
import { useFocusTrap } from './useFocusTrap';

describe('useFocusTrap', () => {
  it('Required Test Case 8: wraps Tab from last to first and Shift+Tab from first to last when active', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);

    const btn1 = document.createElement('button');
    btn1.textContent = 'First';
    const input = document.createElement('input');
    const btn2 = document.createElement('button');
    btn2.textContent = 'Last';

    container.appendChild(btn1);
    container.appendChild(input);
    container.appendChild(btn2);

    const { unmount } = renderHook(() => {
      const ref = useRef<HTMLElement | null>(container);
      useFocusTrap(true, ref);
    });

    // Tab from last element wraps to first
    btn2.focus();
    expect(document.activeElement).toBe(btn2);

    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    const tabPrevented = !document.dispatchEvent(tabEvent);
    expect(tabPrevented).toBe(true);
    expect(document.activeElement).toBe(btn1);

    // Shift+Tab from first element wraps to last
    btn1.focus();
    expect(document.activeElement).toBe(btn1);

    const shiftTabEvent = new KeyboardEvent('keydown', {
      key: 'Tab',
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    });
    const shiftTabPrevented = !document.dispatchEvent(shiftTabEvent);
    expect(shiftTabPrevented).toBe(true);
    expect(document.activeElement).toBe(btn2);

    unmount();
    document.body.removeChild(container);
  });

  it('does not trap focus when active is false', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);

    const btn1 = document.createElement('button');
    const btn2 = document.createElement('button');
    container.appendChild(btn1);
    container.appendChild(btn2);

    const { unmount } = renderHook(() => {
      const ref = useRef<HTMLElement | null>(container);
      useFocusTrap(false, ref);
    });

    btn2.focus();
    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    const tabPrevented = !document.dispatchEvent(tabEvent);

    expect(tabPrevented).toBe(false); // Not intercepted
    expect(document.activeElement).toBe(btn2);

    unmount();
    document.body.removeChild(container);
  });

  it('yields Tab keydown when .kb-help-drawer or .field-help-hint-popover is present', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);

    const btn1 = document.createElement('button');
    const btn2 = document.createElement('button');
    container.appendChild(btn1);
    container.appendChild(btn2);

    const drawer = document.createElement('div');
    drawer.className = 'kb-help-drawer';
    document.body.appendChild(drawer);

    const { unmount } = renderHook(() => {
      const ref = useRef<HTMLElement | null>(container);
      useFocusTrap(true, ref);
    });

    btn2.focus();
    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    const tabPrevented = !document.dispatchEvent(tabEvent);

    expect(tabPrevented).toBe(false); // Yielded, not prevented

    unmount();
    drawer.remove();
    container.remove();
  });

  it('covers null containerRef and non-Tab keys', () => {
    const { unmount } = renderHook(() => {
      const ref = useRef<HTMLElement | null>(null);
      useFocusTrap(true, ref);
    });

    const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    expect(!document.dispatchEvent(enterEvent)).toBe(false);

    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    expect(!document.dispatchEvent(tabEvent)).toBe(false);

    unmount();
  });

  it('prevents default and focuses container when no focusable elements exist', () => {
    const container = document.createElement('div');
    container.tabIndex = -1;
    document.body.appendChild(container);

    const { unmount } = renderHook(() => {
      const ref = useRef<HTMLElement | null>(container);
      useFocusTrap(true, ref);
    });

    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    const prevented = !document.dispatchEvent(tabEvent);
    expect(prevented).toBe(true);
    expect(document.activeElement).toBe(container);

    unmount();
    container.remove();
  });

  it('traps Tab and Shift+Tab when focus is outside the container', () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const btn1 = document.createElement('button');
    const btn2 = document.createElement('button');
    container.appendChild(btn1);
    container.appendChild(btn2);

    const outsideBtn = document.createElement('button');
    document.body.appendChild(outsideBtn);
    outsideBtn.focus();

    const { unmount } = renderHook(() => {
      const ref = useRef<HTMLElement | null>(container);
      useFocusTrap(true, ref);
    });

    // Tab while outside -> focuses first element
    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    const tabPrevented = !document.dispatchEvent(tabEvent);
    expect(tabPrevented).toBe(true);
    expect(document.activeElement).toBe(btn1);

    // Focus outside again
    outsideBtn.focus();
    // Shift+Tab while outside -> focuses last element
    const shiftTabEvent = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true });
    const shiftTabPrevented = !document.dispatchEvent(shiftTabEvent);
    expect(shiftTabPrevented).toBe(true);
    expect(document.activeElement).toBe(btn2);

    // Tab from first element (btn1) when inside -> not prevented, naturally moves
    btn1.focus();
    const naturalTab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    expect(!document.dispatchEvent(naturalTab)).toBe(false);

    // Shift+Tab from last element (btn2) when inside -> not prevented, naturally moves
    btn2.focus();
    const naturalShiftTab = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true });
    expect(!document.dispatchEvent(naturalShiftTab)).toBe(false);

    unmount();
    container.remove();
    outsideBtn.remove();
  });
});
