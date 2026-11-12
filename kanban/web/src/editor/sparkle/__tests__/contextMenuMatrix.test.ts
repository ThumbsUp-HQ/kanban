/**
 * Unit tests for pure Context Menu Resolution Matrix (KB-P5-09, S9.2).
 * Validates all 6 rows of S9.2, boundary conditions, precedence rules, and state coverage.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  resolveContextMenu,
  computeCaretDistance,
  isOverSpellingNode,
  isOnBadge,
  setBadgeContextMenuSuppression,
  consumeBadgeContextMenuSuppression,
  resetBadgeContextMenuSuppression,
  CARET_PROXIMITY_RADIUS_PX,
  type ContextMenuInput,
} from '../contextMenuMatrix';
import type { SparkleStateName } from '../sparkleMachine';

describe('contextMenuMatrix (S9.2 Right-Click Accept Matrix)', () => {
  beforeEach(() => {
    resetBadgeContextMenuSuppression();
  });

  describe('1. Table-driven S9.2 Rows 1-6', () => {
    interface MatrixTestCase {
      row: number;
      name: string;
      input: ContextMenuInput;
      expectedAction: 'ACCEPT' | 'NATIVE';
      expectedPreventDefault: boolean;
    }

    const testCases: MatrixTestCase[] = [
      {
        row: 1,
        name: 'Row 1: READY_BLINKING + Collapsed + onBadge -> ACCEPT (single-step undo)',
        input: {
          sparkleState: 'READY_BLINKING',
          selectionEmpty: true,
          onBadge: true,
          distancePx: 100, // Distance irrelevant when clicking on badge
          overSpellingNode: false,
          shiftKey: false,
        },
        expectedAction: 'ACCEPT',
        expectedPreventDefault: true,
      },
      {
        row: 2,
        name: 'Row 2: READY_BLINKING + Collapsed + within <= 28px & not over spelling -> ACCEPT',
        input: {
          sparkleState: 'READY_BLINKING',
          selectionEmpty: true,
          onBadge: false,
          distancePx: 18.5,
          overSpellingNode: false,
          shiftKey: false,
        },
        expectedAction: 'ACCEPT',
        expectedPreventDefault: true,
      },
      {
        row: 3,
        name: 'Row 3: READY_BLINKING + Collapsed + Holding Shift -> NATIVE (user escape hatch)',
        input: {
          sparkleState: 'READY_BLINKING',
          selectionEmpty: true,
          onBadge: true, // Even on badge, shift key forces native menu
          distancePx: 10,
          overSpellingNode: false,
          shiftKey: true,
        },
        expectedAction: 'NATIVE',
        expectedPreventDefault: false,
      },
      {
        row: 4,
        name: 'Row 4: READY_BLINKING + Non-empty selection -> NATIVE (Copy/Cut preserved)',
        input: {
          sparkleState: 'READY_BLINKING',
          selectionEmpty: false,
          onBadge: false,
          distancePx: 5,
          overSpellingNode: false,
          shiftKey: false,
        },
        expectedAction: 'NATIVE',
        expectedPreventDefault: false,
      },
      {
        row: 5,
        name: 'Row 5a: READY_BLINKING + Collapsed + Over misspelled word -> NATIVE (Spellcheck preserved)',
        input: {
          sparkleState: 'READY_BLINKING',
          selectionEmpty: true,
          onBadge: false,
          distancePx: 10, // within 28px, but over spelling node
          overSpellingNode: true,
          shiftKey: false,
        },
        expectedAction: 'NATIVE',
        expectedPreventDefault: false,
      },
      {
        row: 5,
        name: 'Row 5b: READY_BLINKING + Collapsed + > 28px away from caret -> NATIVE (Paste menu preserved)',
        input: {
          sparkleState: 'READY_BLINKING',
          selectionEmpty: true,
          onBadge: false,
          distancePx: 45,
          overSpellingNode: false,
          shiftKey: false,
        },
        expectedAction: 'NATIVE',
        expectedPreventDefault: false,
      },
      {
        row: 6,
        name: 'Row 6: IDLE / DISMISSED / other states -> NATIVE (100% standard behavior)',
        input: {
          sparkleState: 'IDLE',
          selectionEmpty: true,
          onBadge: false,
          distancePx: 5,
          overSpellingNode: false,
          shiftKey: false,
        },
        expectedAction: 'NATIVE',
        expectedPreventDefault: false,
      },
    ];

    it.each(testCases)(
      'evaluates $name -> $expectedAction (preventDefault: $expectedPreventDefault)',
      ({ input, expectedAction, expectedPreventDefault }) => {
        const action = resolveContextMenu(input);
        expect(action).toBe(expectedAction);
        const wouldPreventDefault = action === 'ACCEPT';
        expect(wouldPreventDefault).toBe(expectedPreventDefault);
      },
    );
  });

  describe('2. Boundary Conditions on Caret Radius (28px)', () => {
    const baseInput: ContextMenuInput = {
      sparkleState: 'READY_BLINKING',
      selectionEmpty: true,
      onBadge: false,
      distancePx: 28,
      overSpellingNode: false,
      shiftKey: false,
    };

    it('returns ACCEPT at distancePx = 0 (exact caret hit)', () => {
      expect(resolveContextMenu({ ...baseInput, distancePx: 0 })).toBe('ACCEPT');
    });

    it('returns ACCEPT at distancePx = 28 (exact boundary hit)', () => {
      expect(resolveContextMenu({ ...baseInput, distancePx: CARET_PROXIMITY_RADIUS_PX })).toBe('ACCEPT');
    });

    it('returns NATIVE at distancePx = 28.01 (just outside boundary)', () => {
      expect(resolveContextMenu({ ...baseInput, distancePx: 28.01 })).toBe('NATIVE');
    });

    it('returns NATIVE at distancePx = 28.0001', () => {
      expect(resolveContextMenu({ ...baseInput, distancePx: 28.0001 })).toBe('NATIVE');
    });

    it('returns NATIVE when distancePx is NaN or Infinity', () => {
      expect(resolveContextMenu({ ...baseInput, distancePx: Number.NaN })).toBe('NATIVE');
      expect(resolveContextMenu({ ...baseInput, distancePx: Number.POSITIVE_INFINITY })).toBe('NATIVE');
    });
  });

  describe('3. Precedence Rules Hierarchy', () => {
    it('shiftKey + onBadge -> NATIVE (Shift escape hatch trumps onBadge)', () => {
      const action = resolveContextMenu({
        sparkleState: 'READY_BLINKING',
        selectionEmpty: true,
        onBadge: true,
        distancePx: 0,
        overSpellingNode: false,
        shiftKey: true,
      });
      expect(action).toBe('NATIVE');
    });

    it('non-empty selection + onBadge -> NATIVE (Selection copy/cut trumps onBadge)', () => {
      const action = resolveContextMenu({
        sparkleState: 'READY_BLINKING',
        selectionEmpty: false,
        onBadge: true,
        distancePx: 0,
        overSpellingNode: false,
        shiftKey: false,
      });
      expect(action).toBe('NATIVE');
    });

    it('overSpellingNode at distancePx = 5 -> NATIVE (Spellcheck trumps proximity)', () => {
      const action = resolveContextMenu({
        sparkleState: 'READY_BLINKING',
        selectionEmpty: true,
        onBadge: false,
        distancePx: 5,
        overSpellingNode: true,
        shiftKey: false,
      });
      expect(action).toBe('NATIVE');
    });

    it('onBadge + overSpellingNode -> ACCEPT (onBadge trumps overSpellingNode)', () => {
      const action = resolveContextMenu({
        sparkleState: 'READY_BLINKING',
        selectionEmpty: true,
        onBadge: true,
        distancePx: 5,
        overSpellingNode: true,
        shiftKey: false,
      });
      expect(action).toBe('ACCEPT');
    });
  });

  describe('4. Inactive / Non-Ready States', () => {
    const inactiveStates: SparkleStateName[] = [
      'IDLE',
      'TYPING',
      'FETCHING',
      'DISMISSED',
      'ACCEPTED',
    ];

    it.each(inactiveStates)('returns NATIVE for state %s even at distance 0 on badge', (state) => {
      const action = resolveContextMenu({
        sparkleState: state,
        selectionEmpty: true,
        onBadge: true,
        distancePx: 0,
        overSpellingNode: false,
        shiftKey: false,
      });
      expect(action).toBe('NATIVE');
    });
  });

  describe('5. Distance and DOM Helpers', () => {
    it('computes Euclidean distance to caret midpoint', () => {
      // Caret at left: 100, top: 50, bottom: 70 -> center is (100, 60)
      const caretCoords = { left: 100, top: 50, bottom: 70 };

      // Point at (100, 60): distance = 0
      expect(computeCaretDistance(100, 60, caretCoords)).toBe(0);

      // Point at (103, 64): dx=3, dy=4 -> distance = 5
      expect(computeCaretDistance(103, 64, caretCoords)).toBe(5);

      // Null coords yields Infinity
      expect(computeCaretDistance(100, 60, null)).toBe(Number.POSITIVE_INFINITY);
    });

    it('detects spelling nodes via .cm-lint-spelling and [data-spell-error]', () => {
      const container = document.createElement('div');
      const spellingSpan = document.createElement('span');
      spellingSpan.className = 'cm-lint-spelling';
      const textNode = document.createElement('strong');
      spellingSpan.appendChild(textNode);
      container.appendChild(spellingSpan);

      const dataSpellDiv = document.createElement('div');
      dataSpellDiv.setAttribute('data-spell-error', 'true');
      container.appendChild(dataSpellDiv);

      const normalDiv = document.createElement('p');
      container.appendChild(normalDiv);

      expect(isOverSpellingNode(textNode)).toBe(true);
      expect(isOverSpellingNode(spellingSpan)).toBe(true);
      expect(isOverSpellingNode(dataSpellDiv)).toBe(true);
      expect(isOverSpellingNode(normalDiv)).toBe(false);
      expect(isOverSpellingNode(null)).toBe(false);
    });

    it('detects badge element via .sparkle-badge', () => {
      const badge = document.createElement('div');
      badge.className = 'sparkle-badge';
      const icon = document.createElement('span');
      badge.appendChild(icon);

      const normal = document.createElement('div');

      expect(isOnBadge(badge)).toBe(true);
      expect(isOnBadge(icon)).toBe(true);
      expect(isOnBadge(normal)).toBe(false);
      expect(isOnBadge(null)).toBe(false);
    });

    it('handles badge contextmenu suppression flag lifecycle', () => {
      vi.useFakeTimers();

      expect(consumeBadgeContextMenuSuppression()).toBe(false);

      setBadgeContextMenuSuppression();
      expect(consumeBadgeContextMenuSuppression()).toBe(true);
      // Single-use: subsequent consumption returns false
      expect(consumeBadgeContextMenuSuppression()).toBe(false);

      // Auto-clear after 500ms timeout
      setBadgeContextMenuSuppression();
      // Calling it again while timer active clears previous timer
      setBadgeContextMenuSuppression();
      vi.advanceTimersByTime(501);
      expect(consumeBadgeContextMenuSuppression()).toBe(false);

      // Reset with active timer
      setBadgeContextMenuSuppression();
      resetBadgeContextMenuSuppression();
      expect(consumeBadgeContextMenuSuppression()).toBe(false);

      vi.useRealTimers();
    });
  });
});
