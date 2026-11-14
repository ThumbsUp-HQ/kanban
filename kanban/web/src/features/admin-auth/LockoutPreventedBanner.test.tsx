import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { LockoutPreventedBanner } from './LockoutPreventedBanner';

describe('LockoutPreventedBanner (KB-P3-36)', () => {
  it('renders ZERO_ADMIN_CARDS reason copy and copies CLI command (Mandatory Test Case 4)', async () => {
    const onDismiss = vi.fn();
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      writable: true,
      value: { writeText: writeTextSpy },
    });

    render(
      <LockoutPreventedBanner
        reasonCode="ZERO_ADMIN_CARDS"
        onDismiss={onDismiss}
      />,
    );

    const banner = screen.getByRole('alert');
    expect(banner).toBeDefined();
    expect(
      screen.getByText(
        /disabling or deleting this card would leave zero enabled sign-in cards/i,
      ),
    ).toBeDefined();

    expect(
      screen.getByText('kanban-ctl auth emergency-unlock --enable-local-admin'),
    ).toBeDefined();

    const copyBtn = screen.getByRole('button', { name: /Copy command/i });
    await act(async () => {
      fireEvent.click(copyBtn);
      await Promise.resolve();
    });
    expect(writeTextSpy).toHaveBeenCalledWith(
      'kanban-ctl auth emergency-unlock --enable-local-admin',
    );
  });

  it('resets copied state after timeout and handles clipboard errors', async () => {
    vi.useFakeTimers();
    const writeTextSpy = vi.fn().mockRejectedValue(new Error('Clipboard denied'));
    Object.defineProperty(navigator, 'clipboard', {
      writable: true,
      value: { writeText: writeTextSpy },
    });

    const { rerender } = render(<LockoutPreventedBanner />);
    const copyBtn = screen.getByRole('button', { name: /Copy command/i });
    fireEvent.click(copyBtn);

    // Verify error was gracefully caught
    expect(writeTextSpy).toHaveBeenCalled();

    // Now test successful copy with timer advancement
    const successSpy = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      writable: true,
      value: { writeText: successSpy },
    });

    rerender(<LockoutPreventedBanner />);
    const copyBtn2 = screen.getByRole('button', { name: /Copy command/i });
    await act(async () => {
      fireEvent.click(copyBtn2);
      await Promise.resolve();
    });

    expect(screen.getByText('Copied!')).toBeDefined();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });

    expect(screen.queryByText('Copied!')).toBeNull();

    vi.useRealTimers();
  });

  it('renders HANDSHAKE_STALE_FOR_LOCAL_DISABLE reason copy', () => {
    render(
      <LockoutPreventedBanner
        reasonCode="HANDSHAKE_STALE_FOR_LOCAL_DISABLE"
        onDismiss={vi.fn()}
      />,
    );

    expect(
      screen.getByText(
        /Local Administrator cannot be disabled until at least one external Server-Admin identity provider card completes a verified login handshake within the past 15 minutes/i,
      ),
    ).toBeDefined();
  });

  it('falls back to generic message or detail when reasonCode is unknown', () => {
    const { rerender } = render(
      <LockoutPreventedBanner
        detail="Custom lockout explanation"
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByText('Custom lockout explanation')).toBeDefined();

    rerender(<LockoutPreventedBanner onDismiss={vi.fn()} />);
    expect(
      screen.getByText(
        'Lockout prevented: this change would block Server Administrator sign-in.',
      ),
    ).toBeDefined();
  });

  it('dismisses banner on close button click', () => {
    const onDismiss = vi.fn();
    render(<LockoutPreventedBanner onDismiss={onDismiss} />);

    const closeBtn = screen.getByRole('button', { name: /Dismiss lockout alert/i });
    fireEvent.click(closeBtn);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
