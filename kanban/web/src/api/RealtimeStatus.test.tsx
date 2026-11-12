import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RealtimeStatus, announce, type RealtimeState } from './RealtimeStatus.tsx';

describe('RealtimeStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders no chip while open and for connecting', () => {
    const { rerender } = render(<RealtimeStatus state="open" />);
    expect(document.querySelector('.realtime-status-chip')).toBeNull();
    rerender(<RealtimeStatus state="connecting" />);
    expect(document.querySelector('.realtime-status-chip')).toBeNull();
  });

  it('defaults to open (hidden)', () => {
    render(<RealtimeStatus />);
    expect(document.querySelector('.realtime-status-chip')).toBeNull();
  });

  it.each<[RealtimeState, string]>([
    ['reconnecting', 'Reconnecting...'],
    ['sse-fallback', 'Live updates via fallback channel'],
    ['closed', 'Offline - changes will sync when reconnected'],
  ])('shows role=status text for %s', (state, text) => {
    render(<RealtimeStatus state={state} />);
    const chip = document.querySelector('.realtime-status-chip');
    expect(chip?.getAttribute('role')).toBe('status');
    expect(chip?.getAttribute('aria-live')).toBe('polite');
    expect(chip?.textContent).toBe(text);
  });

  it('counts elapsed seconds while reconnecting and resets afterwards', () => {
    const { rerender } = render(<RealtimeStatus state="reconnecting" />);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(document.querySelector('.realtime-status-chip')?.textContent).toBe('Reconnecting... 3s');
    rerender(<RealtimeStatus state="closed" />);
    rerender(<RealtimeStatus state="reconnecting" />);
    expect(document.querySelector('.realtime-status-chip')?.textContent).toBe('Reconnecting...');
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(document.querySelector('.realtime-status-chip')?.textContent).toBe('Reconnecting... 1s');
  });

  it('never receives focus on state change and exposes no tab stop', () => {
    const { rerender } = render(
      <>
        <button data-testid="board-btn">board</button>
        <RealtimeStatus state="open" />
      </>,
    );
    const button = screen.getByTestId('board-btn');
    button.focus();
    rerender(
      <>
        <button data-testid="board-btn">board</button>
        <RealtimeStatus state="closed" />
      </>,
    );
    expect(document.activeElement).toBe(button);
    expect(document.querySelector('.realtime-status-chip')?.hasAttribute('tabindex')).toBe(false);
  });

  it('announce() publishes to the live region and unsubscribes on unmount', () => {
    const { unmount } = render(<RealtimeStatus />);
    act(() => {
      announce('Update failed');
    });
    expect(document.querySelector('.realtime-live-region')?.textContent).toBe('Update failed');
    unmount();
    expect(() => {
      announce('after unmount');
    }).not.toThrow();
  });
});
