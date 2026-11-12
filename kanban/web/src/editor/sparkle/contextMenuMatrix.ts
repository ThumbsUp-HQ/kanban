/**
 * Pure Context Menu Resolution Matrix for Sparkle Completion (KB-P5-09, S9.1, S9.2).
 *
 * Implements the 6-row precedence matrix from Section 9.2:
 * 1. READY_BLINKING + Collapsed + onBadge -> ACCEPT (Row 1)
 * 2. READY_BLINKING + Collapsed + within <= 28px of caret & NOT over spelling -> ACCEPT (Row 2)
 * 3. READY_BLINKING + Shift + Right-Click -> NATIVE (Row 3: explicit user escape hatch)
 * 4. READY_BLINKING + Non-empty selection -> NATIVE (Row 4: Copy/Cut preserved)
 * 5. READY_BLINKING + Collapsed + (over spelling node OR > 28px away) -> NATIVE (Row 5: Spellcheck/Paste preserved)
 * 6. IDLE / DISMISSED / other states -> NATIVE (Row 6: 100% standard behavior)
 *
 * Note on Native Spellcheck Detectability Limitation:
 * Browser-native spellcheck squiggles (red wavy lines drawn by OS/browser spelling engines)
 * are rendered directly on the browser paint layer and are NOT observable in the DOM tree.
 * The `overSpellingNode` check inspects DOM annotations such as `.cm-lint-spelling` and `[data-spell-error]`.
 * Native browser spellcheck menus are preserved via the > 28px distance boundary, Shift escape hatch,
 * and selection checks.
 */

import type { SparkleStateName } from './sparkleMachine';

export type ContextMenuAction = 'ACCEPT' | 'NATIVE';

export const CARET_PROXIMITY_RADIUS_PX = 28;

export interface ContextMenuInput {
  sparkleState: SparkleStateName;
  selectionEmpty: boolean;
  onBadge: boolean;
  distancePx: number;
  overSpellingNode: boolean;
  shiftKey: boolean;
}

export interface CaretPoint {
  left: number;
  top: number;
  bottom: number;
}

/**
 * Pure resolution function enforcing the exact 6-step precedence order of S9.2:
 *
 * Step 1: sparkleState !== "READY_BLINKING" -> NATIVE (Row 6)
 * Step 2: shiftKey -> NATIVE (Row 3)
 * Step 3: !selectionEmpty -> NATIVE (Row 4)
 * Step 4: onBadge -> ACCEPT (Row 1)
 * Step 5: overSpellingNode || distancePx > 28 -> NATIVE (Row 5)
 * Step 6: distancePx <= 28 -> ACCEPT (Row 2)
 */
export function resolveContextMenu(input: ContextMenuInput): ContextMenuAction {
  // Step 1 (Row 6): Inactive states always yield native context menu
  if (input.sparkleState !== 'READY_BLINKING') {
    return 'NATIVE';
  }

  // Step 2 (Row 3): Holding Shift is an explicit user escape hatch for native menu
  if (input.shiftKey) {
    return 'NATIVE';
  }

  // Step 3 (Row 4): Non-empty text selection preserves native Copy / Cut menus
  if (!input.selectionEmpty) {
    return 'NATIVE';
  }

  // Step 4 (Row 1): Right-clicking the Sparkle badge accepts immediately
  if (input.onBadge) {
    return 'ACCEPT';
  }

  // Step 5 (Row 5): Over misspelled word OR > 28px away from caret preserves native menu
  if (
    input.overSpellingNode ||
    Number.isNaN(input.distancePx) ||
    input.distancePx > CARET_PROXIMITY_RADIUS_PX
  ) {
    return 'NATIVE';
  }

  // Step 6 (Row 2): Within <= 28px of blinking caret & not over spelling node
  return 'ACCEPT';
}

/**
 * Calculates Euclidean distance from mouse client coordinates to the caret midpoint.
 * Caret point is defined at x = left, y = (top + bottom) / 2.
 */
export function computeCaretDistance(
  clientX: number,
  clientY: number,
  caretCoords: CaretPoint | null,
): number {
  if (!caretCoords) return Infinity;
  const caretX = caretCoords.left;
  const caretY = (caretCoords.top + caretCoords.bottom) / 2;
  const dx = clientX - caretX;
  const dy = clientY - caretY;
  return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Checks whether an event target is located over a spelling error node.
 * Inspects `.cm-lint-spelling` (CodeMirror lint) or `[data-spell-error]` (ProseMirror decoration).
 */
export function isOverSpellingNode(target: EventTarget | null): boolean {
  if (!target || !(target instanceof Element)) return false;
  return Boolean(target.closest('.cm-lint-spelling, [data-spell-error]'));
}

/**
 * Checks whether an event target is the Sparkle badge element or its descendant.
 */
export function isOnBadge(target: EventTarget | null): boolean {
  if (!target || !(target instanceof Element)) return false;
  return Boolean(target.closest('.sparkle-badge'));
}

// Single-use suppression flag management for badge gesture
let badgeContextMenuSuppressed = false;
let badgeSuppressionTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * Sets single-use suppression flag for the contextmenu event immediately following a pointerdown accept on the badge.
 * Flag is automatically cleared after 500ms if no contextmenu arrives.
 */
export function setBadgeContextMenuSuppression(): void {
  badgeContextMenuSuppressed = true;
  if (badgeSuppressionTimer !== null) {
    clearTimeout(badgeSuppressionTimer);
  }
  badgeSuppressionTimer = setTimeout(() => {
    badgeContextMenuSuppressed = false;
    badgeSuppressionTimer = null;
  }, 500);
}

/**
 * Consumes and resets the badge contextmenu suppression flag.
 * Returns true if suppression was active and consumed.
 */
export function consumeBadgeContextMenuSuppression(): boolean {
  if (badgeContextMenuSuppressed) {
    badgeContextMenuSuppressed = false;
    if (badgeSuppressionTimer !== null) {
      clearTimeout(badgeSuppressionTimer);
      badgeSuppressionTimer = null;
    }
    return true;
  }
  return false;
}

/**
 * Resets suppression state directly (for testing).
 */
export function resetBadgeContextMenuSuppression(): void {
  badgeContextMenuSuppressed = false;
  if (badgeSuppressionTimer !== null) {
    clearTimeout(badgeSuppressionTimer);
    badgeSuppressionTimer = null;
  }
}
