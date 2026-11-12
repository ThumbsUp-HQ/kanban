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
});
