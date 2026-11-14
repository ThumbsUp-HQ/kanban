/**
 * Unit Tests for StickyPromotionBanner (KB-P3-51, S8.2).
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StickyPromotionBanner } from './StickyPromotionBanner';

describe('StickyPromotionBanner', () => {
  it('renders label, hint with reasons, and action buttons', () => {
    const onPromote = vi.fn();
    const onSnooze = vi.fn();

    render(
      <StickyPromotionBanner
        reasons={['740 chars (> 600)', '2 headings (>= 2)']}
        onPromote={onPromote}
        onSnooze={onSnooze}
      />,
    );

    expect(screen.getByText('Growing into a spec')).toBeDefined();

    const promoteBtn = screen.getByRole('button', { name: 'Promote to Doc' });
    expect(promoteBtn.textContent).toContain('Promote to Doc ->');

    const snoozeBtn = screen.getByRole('button', { name: 'Snooze promotion' });
    expect(snoozeBtn.textContent).toBe('Snooze');

    fireEvent.click(promoteBtn);
    expect(onPromote).toHaveBeenCalledTimes(1);

    fireEvent.click(snoozeBtn);
    expect(onSnooze).toHaveBeenCalledTimes(1);
  });

  it('renders fallback text when reasons array is empty', () => {
    render(
      <StickyPromotionBanner
        reasons={[]}
        onPromote={vi.fn()}
        onSnooze={vi.fn()}
      />,
    );

    const hint = screen.getByTestId('sticky-promotion-hint');
    expect(hint).toBeDefined();
  });

  it('disables buttons when isPromoting is true', () => {
    render(
      <StickyPromotionBanner
        reasons={['650 chars (> 600)']}
        isPromoting={true}
        onPromote={vi.fn()}
        onSnooze={vi.fn()}
      />,
    );

    const promoteBtn = screen.getByRole('button', { name: 'Promote to Doc' });
    expect(promoteBtn.textContent).toBe('Promoting...');
    expect(promoteBtn.hasAttribute('disabled')).toBe(true);

    const snoozeBtn = screen.getByRole('button', { name: 'Snooze promotion' });
    expect(snoozeBtn.hasAttribute('disabled')).toBe(true);
  });
});
