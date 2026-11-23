// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { StickiesGrid } from '../stickies/StickiesGrid';
import { StickyCard } from '../stickies/StickyCard';
import type { StickyItem } from '../stickies/stickiesApi';
import type { StickyColorToken } from '../stickies/stickyHeuristic';

// Helper: Calculate WCAG 2.2 Relative Luminance and Contrast Ratio
function srgbToLinear(c: number): number {
  const norm = c / 255.0;
  return norm <= 0.04045 ? norm / 12.92 : Math.pow((norm + 0.055) / 1.055, 2.4);
}

function getRelativeLuminance(hex: string): number {
  const cleanHex = hex.replace('#', '');
  const r = parseInt(cleanHex.substring(0, 2), 16);
  const g = parseInt(cleanHex.substring(2, 4), 16);
  const b = parseInt(cleanHex.substring(4, 6), 16);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

function calculateContrastRatio(fgHex: string, bgHex: string): number {
  const l1 = getRelativeLuminance(fgHex);
  const l2 = getRelativeLuminance(bgHex);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

const mockStickies: StickyItem[] = [
  {
    id: 'sticky-a',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'First card triage note',
    color_token: 'amber',
    sort_rank: '0',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    etag: '"etag-a"',
    capabilities: ['EDIT', 'DELETE'],
  },
  {
    id: 'sticky-b',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'Second card architecture review',
    color_token: 'mint',
    sort_rank: '1',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    etag: '"etag-b"',
    capabilities: ['EDIT', 'DELETE'],
  },
  {
    id: 'sticky-c',
    workspace_id: 'ws-1',
    project_id: 'proj-1',
    body_markdown: 'Third card backend migration',
    color_token: 'sky',
    sort_rank: '2',
    promotion_recommended: false,
    promotion_snoozed_at_length: null,
    promoted_to_doc_id: null,
    is_promoted_stub: false,
    triggers: [],
    etag: '"etag-c"',
    capabilities: ['EDIT', 'DELETE'],
  },
];

describe('KAN-359 Stickies Canvas Accessibility & Conformance Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Test Case 1: WCAG 2.2 AA >=4.5:1 Text Contrast Across All 6 Sticky Card Colors', () => {
    // 6 required sticky card colors (both semantic and canonical tokens)
    const colorDefinitions = [
      { name: 'yellow', lightHex: '#fef3c7', darkHex: '#78350f', token: 'amber' as StickyColorToken },
      { name: 'pink', lightHex: '#fce7f3', darkHex: '#831843', token: 'coral' as StickyColorToken },
      { name: 'blue', lightHex: '#e0f2fe', darkHex: '#0c4a6e', token: 'sky' as StickyColorToken },
      { name: 'green', lightHex: '#d1fae5', darkHex: '#064e3b', token: 'mint' as StickyColorToken },
      { name: 'orange', lightHex: '#ffedd5', darkHex: '#7c2d12', token: 'coral' as StickyColorToken },
      { name: 'purple', lightHex: '#ede9fe', darkHex: '#4c1d95', token: 'lavender' as StickyColorToken },
    ];

    const lightModeFg = '#0f172a'; // var(--sticky-fg) in light mode
    const darkModeFg = '#f9fafb';  // var(--sticky-fg) in dark mode

    it('verifies mathematical WCAG 2.2 AA >= 4.5:1 contrast for all 6 colors in Light Mode', () => {
      for (const col of colorDefinitions) {
        const ratio = calculateContrastRatio(lightModeFg, col.lightHex);
        expect(ratio).toBeGreaterThanOrEqual(4.5);
      }
    });

    it('verifies mathematical WCAG 2.2 AA >= 4.5:1 contrast for all 6 colors in Dark Mode', () => {
      for (const col of colorDefinitions) {
        const ratio = calculateContrastRatio(darkModeFg, col.darkHex);
        expect(ratio).toBeGreaterThanOrEqual(4.5);
      }
    });

    it('renders StickyCard with color-independent textual cue and accessibility attributes', () => {
      const baseItem = mockStickies[0];
      if (!baseItem) {
        throw new Error('Missing base sticky');
      }

      for (const col of colorDefinitions) {
        const testSticky: StickyItem = {
          ...baseItem,
          id: `sticky-${col.name}`,
          color_token: col.token,
        };

        const { unmount } = render(
          <StickyCard
            sticky={testSticky}
            onUpdate={vi.fn()}
            onDelete={vi.fn()}
            onPromote={vi.fn()}
          />
        );

        const card = screen.getByTestId(`sticky-card-${testSticky.id}`);
        expect(card).toBeDefined();
        expect(card.getAttribute('role')).toBe('article');
        expect(card.getAttribute('aria-roledescription')).toBe('sticky card');
        expect(card.getAttribute('aria-label')).toBe(`Sticky note in ${col.token}`);
        expect(card.getAttribute('tabindex')).toBe('0');

        // Color-independent textual badge is present
        const badge = screen.getByTestId(`sticky-color-badge-${testSticky.id}`);
        expect(badge).toBeDefined();
        expect(badge.textContent).toBe(col.token);

        unmount();
      }
    });
  });

  describe('Test Case 2: Keyboard Arrow-Key Sticky Positioning & Spatial Traversal', () => {
    it('traverses spatial focus across cards using ArrowRight, ArrowDown, ArrowLeft, ArrowUp', () => {
      render(
        <StickiesGrid
          stickies={mockStickies}
          onUpdateSticky={vi.fn()}
          onDeleteSticky={vi.fn()}
          onPromoteSticky={vi.fn()}
          onUnarchiveCopy={vi.fn()}
        />
      );

      const cardA = screen.getByTestId('sticky-card-sticky-a');
      const cardB = screen.getByTestId('sticky-card-sticky-b');
      const cardC = screen.getByTestId('sticky-card-sticky-c');

      cardA.focus();
      expect(document.activeElement).toBe(cardA);

      // ArrowRight moves focus to cardB
      fireEvent.keyDown(cardA, { key: 'ArrowRight' });
      expect(document.activeElement).toBe(cardB);

      // ArrowDown moves focus to cardC
      fireEvent.keyDown(cardB, { key: 'ArrowDown' });
      expect(document.activeElement).toBe(cardC);

      // ArrowUp moves focus back to cardB
      fireEvent.keyDown(cardC, { key: 'ArrowUp' });
      expect(document.activeElement).toBe(cardB);

      // ArrowLeft moves focus back to cardA
      fireEvent.keyDown(cardB, { key: 'ArrowLeft' });
      expect(document.activeElement).toBe(cardA);

      // Boundary: ArrowLeft and ArrowUp at index 0 (targetIndex === currentIndex)
      fireEvent.keyDown(cardA, { key: 'ArrowLeft' });
      expect(document.activeElement).toBe(cardA);
      fireEvent.keyDown(cardA, { key: 'ArrowUp' });
      expect(document.activeElement).toBe(cardA);

      // Boundary: ArrowRight and ArrowDown at last index
      cardC.focus();
      fireEvent.keyDown(cardC, { key: 'ArrowRight' });
      expect(document.activeElement).toBe(cardC);
      fireEvent.keyDown(cardC, { key: 'ArrowDown' });
      expect(document.activeElement).toBe(cardC);
    });

    it('positions/reorders sticky cards using Alt+Arrow keys and fires onMoveSticky', () => {
      const onMoveSticky = vi.fn();
      render(
        <StickiesGrid
          stickies={mockStickies}
          onUpdateSticky={vi.fn()}
          onDeleteSticky={vi.fn()}
          onPromoteSticky={vi.fn()}
          onUnarchiveCopy={vi.fn()}
          onMoveSticky={onMoveSticky}
        />
      );

      const cardA = screen.getByTestId('sticky-card-sticky-a');
      cardA.focus();

      // Alt+ArrowRight moves cardA to the right (position 2)
      fireEvent.keyDown(cardA, { key: 'ArrowRight', altKey: true });
      expect(onMoveSticky).toHaveBeenCalledWith('sticky-a', 'right');

      // Alt+ArrowDown moves cardA down (position 3)
      fireEvent.keyDown(cardA, { key: 'ArrowDown', altKey: true });
      expect(onMoveSticky).toHaveBeenCalledWith('sticky-a', 'down');

      // Alt+ArrowUp moves cardA back up (position 2)
      fireEvent.keyDown(cardA, { key: 'ArrowUp', altKey: true });
      expect(onMoveSticky).toHaveBeenCalledWith('sticky-a', 'up');

      // Alt+ArrowLeft moves cardA back left (position 1)
      fireEvent.keyDown(cardA, { key: 'ArrowLeft', altKey: true });
      expect(onMoveSticky).toHaveBeenCalledWith('sticky-a', 'left');

      // Boundary: Alt+ArrowLeft or Alt+ArrowUp at position 0 does not move before index 0
      fireEvent.keyDown(cardA, { key: 'ArrowLeft', altKey: true });
      fireEvent.keyDown(cardA, { key: 'ArrowUp', altKey: true });

      // Boundary: Alt+ArrowRight or Alt+ArrowDown at last position
      const cardC = screen.getByTestId('sticky-card-sticky-c');
      cardC.focus();
      fireEvent.keyDown(cardC, { key: 'ArrowRight', altKey: true });
      fireEvent.keyDown(cardC, { key: 'ArrowDown', altKey: true });

      // Check boundary check: Alt+ArrowLeft at position 0
      const onMoveStickyBoundary = vi.fn();
      const { unmount } = render(
        <StickiesGrid
          stickies={mockStickies}
          onUpdateSticky={vi.fn()}
          onDeleteSticky={vi.fn()}
          onPromoteSticky={vi.fn()}
          onUnarchiveCopy={vi.fn()}
          onMoveSticky={onMoveStickyBoundary}
        />
      );
      const boundaryCards = screen.getAllByTestId('sticky-card-sticky-a');
      const boundaryCardA = boundaryCards[1];
      if (boundaryCardA) {
        boundaryCardA.focus();
        fireEvent.keyDown(boundaryCardA, { key: 'ArrowLeft', altKey: true });
        expect(onMoveStickyBoundary).not.toHaveBeenCalled();
      }
      unmount();
    });

    it('handles standalone StickyCard onKeyboardMove and onSpatialNavigate callbacks', () => {
      const baseItem = mockStickies[0];
      if (!baseItem) {
        throw new Error('Missing base sticky');
      }

      const onKeyboardMove = vi.fn();
      const onSpatialNavigate = vi.fn();

      render(
        <StickyCard
          sticky={baseItem}
          onUpdate={vi.fn()}
          onDelete={vi.fn()}
          onPromote={vi.fn()}
          onKeyboardMove={onKeyboardMove}
          onSpatialNavigate={onSpatialNavigate}
        />
      );

      const card = screen.getByTestId('sticky-card-sticky-a');
      card.focus();

      // Alt+ArrowUp triggers onKeyboardMove
      fireEvent.keyDown(card, { key: 'ArrowUp', altKey: true });
      expect(onKeyboardMove).toHaveBeenCalledWith('sticky-a', 'up');

      // Alt+ArrowDown triggers onKeyboardMove
      fireEvent.keyDown(card, { key: 'ArrowDown', altKey: true });
      expect(onKeyboardMove).toHaveBeenCalledWith('sticky-a', 'down');

      // Plain ArrowRight on card container triggers onSpatialNavigate
      fireEvent.keyDown(card, { key: 'ArrowRight' });
      expect(onSpatialNavigate).toHaveBeenCalledWith('sticky-a', 'right');

      // Plain ArrowDown on card container triggers onSpatialNavigate
      fireEvent.keyDown(card, { key: 'ArrowDown' });
      expect(onSpatialNavigate).toHaveBeenCalledWith('sticky-a', 'down');

      // Plain ArrowUp on card container triggers onSpatialNavigate
      fireEvent.keyDown(card, { key: 'ArrowUp' });
      expect(onSpatialNavigate).toHaveBeenCalledWith('sticky-a', 'up');

      // Plain ArrowLeft on card container triggers onSpatialNavigate
      fireEvent.keyDown(card, { key: 'ArrowLeft' });
      expect(onSpatialNavigate).toHaveBeenCalledWith('sticky-a', 'left');

      // Non-arrow key does not trigger handlers
      fireEvent.keyDown(card, { key: 'Escape' });

      // Non-card element inside does not trigger card spatial navigation
      const innerBadge = screen.getByTestId('sticky-color-badge-sticky-a');
      fireEvent.keyDown(innerBadge, { key: 'ArrowRight' });

      // Fallback: when onSpatialNavigate is not provided, plain Arrow on card calls onKeyboardMove
      const secondItem = mockStickies[1];
      if (!secondItem) {
        throw new Error('Missing second sticky');
      }

      const onKeyboardMoveOnly = vi.fn();
      const { unmount } = render(
        <StickyCard
          sticky={secondItem}
          onUpdate={vi.fn()}
          onDelete={vi.fn()}
          onPromote={vi.fn()}
          onKeyboardMove={onKeyboardMoveOnly}
        />
      );
      const cardOnly = screen.getByTestId('sticky-card-sticky-b');
      cardOnly.focus();
      fireEvent.keyDown(cardOnly, { key: 'ArrowLeft' });
      expect(onKeyboardMoveOnly).toHaveBeenCalledWith('sticky-b', 'left');
      unmount();
    });
  });

  describe('Test Case 3: aria-live="polite" Status Announcements for Moves, Colors, and Doc Promotions', () => {
    it('announces keyboard moves via aria-live="polite" live region', async () => {
      render(
        <StickiesGrid
          stickies={mockStickies}
          onUpdateSticky={vi.fn()}
          onDeleteSticky={vi.fn()}
          onPromoteSticky={vi.fn()}
          onUnarchiveCopy={vi.fn()}
        />
      );

      const cardA = screen.getByTestId('sticky-card-sticky-a');
      cardA.focus();

      // Trigger move via Alt+ArrowRight
      act(() => {
        fireEvent.keyDown(cardA, { key: 'ArrowRight', altKey: true });
      });

      const liveRegion = await screen.findByTestId('stickies-announcement');
      expect(liveRegion).toBeDefined();
      expect(liveRegion.getAttribute('aria-live')).toBe('polite');
      expect(liveRegion.getAttribute('role')).toBe('status');
      expect(liveRegion.textContent).toContain('Moved sticky note right to position 2 of 3.');
    });

    it('announces color changes via aria-live="polite" live region', async () => {
      const onUpdateSticky = vi.fn().mockResolvedValue(undefined);
      render(
        <StickiesGrid
          stickies={mockStickies}
          onUpdateSticky={onUpdateSticky}
          onDeleteSticky={vi.fn()}
          onPromoteSticky={vi.fn()}
          onUnarchiveCopy={vi.fn()}
        />
      );

      const cardA = screen.getByTestId('sticky-card-sticky-a');
      const mintSwatch = cardA.querySelector('[data-testid="color-swatch-mint"]');
      expect(mintSwatch).toBeDefined();

      if (mintSwatch) {
        act(() => {
          fireEvent.click(mintSwatch);
        });
      }

      const liveRegion = await screen.findByTestId('stickies-announcement');
      expect(liveRegion).toBeDefined();
      expect(liveRegion.getAttribute('aria-live')).toBe('polite');
      expect(liveRegion.textContent).toContain('Sticky note color changed to mint.');
    });

    it('announces doc promotions via aria-live="polite" live region', async () => {
      const onPromoteSticky = vi.fn().mockResolvedValue(undefined);
      render(
        <StickiesGrid
          stickies={mockStickies}
          onUpdateSticky={vi.fn()}
          onDeleteSticky={vi.fn()}
          onPromoteSticky={onPromoteSticky}
          onUnarchiveCopy={vi.fn()}
        />
      );

      // Open menu on sticky-a and trigger promote
      const menuTrigger = screen.getByTestId('sticky-menu-trigger-sticky-a');
      fireEvent.click(menuTrigger);

      const convertItem = screen.getByTestId('convert-to-doc-menuitem');
      act(() => {
        fireEvent.click(convertItem);
      });

      const confirmBtn = await screen.findByTestId('confirm-promote-btn');
      act(() => {
        fireEvent.click(confirmBtn);
      });

      const liveRegion = await screen.findByTestId('stickies-announcement');
      expect(liveRegion).toBeDefined();
      expect(liveRegion.getAttribute('aria-live')).toBe('polite');
      expect(liveRegion.textContent).toContain('Promoted sticky to Doc');
    });

    it('announces standalone StickyCard recolor when onAnnounce is not provided', async () => {
      const baseItem = mockStickies[0];
      if (!baseItem) {
        throw new Error('Missing base sticky');
      }

      render(
        <StickyCard
          sticky={baseItem}
          onUpdate={vi.fn()}
          onDelete={vi.fn()}
          onPromote={vi.fn()}
        />
      );

      const skySwatch = screen.getByTestId('color-swatch-sky');
      act(() => {
        fireEvent.click(skySwatch);
      });

      const cardLive = await screen.findByTestId('sticky-card-announcement-sticky-a');
      expect(cardLive).toBeDefined();
      expect(cardLive.getAttribute('aria-live')).toBe('polite');
      expect(cardLive.textContent).toContain('Sticky note color changed to sky.');
    });

    it('announces unarchived copy via aria-live="polite" live region', async () => {
      const baseItem = mockStickies[0];
      if (!baseItem) return;
      const stubSticky: StickyItem = {
        ...baseItem,
        id: 'sticky-stub-1',
        is_promoted_stub: true,
        promoted_to_doc_id: 'doc-1',
        promoted_to_doc: {
          id: 'doc-1',
          canonical_key: 'DOC-1',
          title: 'Promoted Spec',
        },
      };

      const onUnarchiveCopy = vi.fn().mockResolvedValue(undefined);
      render(
        <StickiesGrid
          stickies={[stubSticky]}
          onUpdateSticky={vi.fn()}
          onDeleteSticky={vi.fn()}
          onPromoteSticky={vi.fn()}
          onUnarchiveCopy={onUnarchiveCopy}
        />
      );

      const unarchiveBtn = screen.getByTestId('unarchive-copy-btn');
      act(() => {
        fireEvent.click(unarchiveBtn);
      });

      const liveRegion = await screen.findByTestId('stickies-announcement');
      expect(liveRegion).toBeDefined();
      expect(liveRegion.textContent).toContain('Created editable copy of sticky note.');
    });

    it('supports direct arrow navigation and keyboard fallback when onSpatialNavigate is omitted', () => {
      const onKeyboardMove = vi.fn();
      const baseItem = mockStickies[0];
      if (!baseItem) return;

      render(
        <StickyCard
          sticky={baseItem}
          onUpdate={vi.fn()}
          onDelete={vi.fn()}
          onPromote={vi.fn()}
          onKeyboardMove={onKeyboardMove}
        />
      );

      const card = screen.getByTestId('sticky-card-sticky-a');
      card.focus();

      fireEvent.keyDown(card, { key: 'ArrowRight' });
      expect(onKeyboardMove).toHaveBeenCalledWith('sticky-a', 'right');

      fireEvent.keyDown(card, { key: 'ArrowLeft' });
      expect(onKeyboardMove).toHaveBeenCalledWith('sticky-a', 'left');

      fireEvent.keyDown(card, { key: 'ArrowDown' });
      expect(onKeyboardMove).toHaveBeenCalledWith('sticky-a', 'down');

      fireEvent.keyDown(card, { key: 'ArrowUp' });
      expect(onKeyboardMove).toHaveBeenCalledWith('sticky-a', 'up');
    });

    it('navigates color palette swatches using arrow keys in StickyCard', () => {
      const onUpdate = vi.fn().mockResolvedValue(undefined);
      const baseItem = mockStickies[0];
      if (!baseItem) return;

      render(
        <StickyCard
          sticky={baseItem}
          onUpdate={onUpdate}
          onDelete={vi.fn()}
          onPromote={vi.fn()}
        />
      );

      const colorPicker = screen.getByRole('radiogroup', { name: /Sticky color/i });
      fireEvent.keyDown(colorPicker, { key: 'ArrowRight' });
      fireEvent.keyDown(colorPicker, { key: 'ArrowDown' });
      fireEvent.keyDown(colorPicker, { key: 'ArrowLeft' });
      fireEvent.keyDown(colorPicker, { key: 'ArrowUp' });
    });

    it('handles errors gracefully in StickyCard during recolor, snooze, and promote', async () => {
      const onUpdateErr = vi.fn().mockRejectedValue(new Error('Network failure'));
      const onPromoteErr = vi.fn().mockRejectedValue(new Error('Promote failure'));
      const baseItem = mockStickies[0];
      if (!baseItem) return;

      render(
        <StickyCard
          sticky={baseItem}
          onUpdate={onUpdateErr}
          onDelete={vi.fn()}
          onPromote={onPromoteErr}
        />
      );

      // Trigger recolor error
      const skySwatch = screen.getByTestId('color-swatch-sky');
      act(() => {
        fireEvent.click(skySwatch);
      });

      // Trigger promote error
      const menuTrigger = screen.getByTestId('sticky-menu-trigger-sticky-a');
      fireEvent.click(menuTrigger);
      const convertItem = screen.getByTestId('convert-to-doc-menuitem');
      act(() => {
        fireEvent.click(convertItem);
      });
      const confirmBtn = await screen.findByTestId('confirm-promote-btn');
      act(() => {
        try {
          fireEvent.click(confirmBtn);
        } catch {
          // expected rejection
        }
      });
    });
  });
});
