/**
 * Unit Tests for SanitizedPastePill Component (KB-P3-46, S5.2, S6.2).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import {
  SanitizedPastePill,
  getSanitizedTooltipText,
  BASE_SANITIZED_HINT,
} from './SanitizedPastePill';

describe('SanitizedPastePill', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('computes tooltip text with and without stripped hidden elements', () => {
    expect(getSanitizedTooltipText(0)).toBe(BASE_SANITIZED_HINT);
    expect(getSanitizedTooltipText(undefined)).toBe(BASE_SANITIZED_HINT);
    expect(getSanitizedTooltipText(2)).toBe(
      `${BASE_SANITIZED_HINT} (stripped 2 hidden element(s))`,
    );
  });

  it('renders pill with label and 24x24 soap emoji hint', () => {
    const handleDismiss = vi.fn();
    render(
      <SanitizedPastePill
        prunedHiddenNodes={0}
        onDismiss={handleDismiss}
        testId="test-pill"
      />,
    );

    expect(screen.getByTestId('test-pill')).toBeDefined();
    expect(screen.getByTestId('test-pill-label').textContent).toContain('Converted to Markdown');
    expect(screen.getByTestId('test-pill-emoji-hint')).toBeDefined();
    expect(screen.getByText('🧼')).toBeDefined();
  });

  it('auto-dismisses after 4000ms', () => {
    const handleDismiss = vi.fn();
    render(
      <SanitizedPastePill
        prunedHiddenNodes={0}
        onDismiss={handleDismiss}
        autoDismissMs={4000}
        testId="test-pill"
      />,
    );

    expect(handleDismiss).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(3999);
    });
    expect(handleDismiss).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('pauses auto-dismiss timer on mouseenter/focus and resumes on mouseleave/blur', () => {
    const handleDismiss = vi.fn();
    render(
      <SanitizedPastePill
        prunedHiddenNodes={0}
        onDismiss={handleDismiss}
        autoDismissMs={4000}
        testId="test-pill"
      />,
    );

    const pill = screen.getByTestId('test-pill');

    // Advance 2000ms
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(handleDismiss).not.toHaveBeenCalled();

    // Hover to pause
    fireEvent.mouseEnter(pill);

    // Advance 5000ms while hovered
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(handleDismiss).not.toHaveBeenCalled();

    // Leave hover to resume remaining 2000ms
    fireEvent.mouseLeave(pill);

    act(() => {
      vi.advanceTimersByTime(1999);
    });
    expect(handleDismiss).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('dismisses immediately on Escape key', () => {
    const handleDismiss = vi.fn();
    render(
      <SanitizedPastePill
        prunedHiddenNodes={0}
        onDismiss={handleDismiss}
        testId="test-pill"
      />,
    );

    const pill = screen.getByTestId('test-pill');
    fireEvent.keyDown(pill, { key: 'Escape' });
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('dismisses immediately on global Escape key', () => {
    const handleDismiss = vi.fn();
    render(
      <SanitizedPastePill
        prunedHiddenNodes={0}
        onDismiss={handleDismiss}
        testId="test-pill"
      />,
    );

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('ignores non-Escape keys on container and window', () => {
    const handleDismiss = vi.fn();
    render(<SanitizedPastePill onDismiss={handleDismiss} testId="test-pill" />);
    const pill = screen.getByTestId('test-pill');

    fireEvent.keyDown(pill, { key: 'Tab' });
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(handleDismiss).not.toHaveBeenCalled();
  });

  it('ignores duplicate pause calls when already hovered', () => {
    const handleDismiss = vi.fn();
    render(<SanitizedPastePill onDismiss={handleDismiss} testId="test-pill" />);
    const pill = screen.getByTestId('test-pill');
    fireEvent.mouseEnter(pill);
    fireEvent.focus(pill);
  });
});
