/**
 * Mandatory Unit Tests for Sparkle State Machine (KB-P5-08, S9.1, S9.3).
 * Validates pure reducer table with every edge and non-edge in the S9.1 diagram.
 */

import { describe, it, expect } from 'vitest';
import {
  sparkleReducer,
  isPrintableChar,
  INITIAL_SPARKLE_STATE,
  type SparkleState,
  type SparkleEvent,
  type SparkleStateName,
} from '../sparkleMachine';

describe('sparkleMachine Reducer & Transitions (Case 1)', () => {
  interface TransitionTestCase {
    description: string;
    initialState: SparkleState;
    event: SparkleEvent;
    expectedState: SparkleStateName;
    assertContext?: (state: SparkleState) => void;
  }

  const tableTestCases: TransitionTestCase[] = [
    // 1. IDLE -> IDLE with 1 printable char (typedCount = 1)
    {
      description: 'Edge: IDLE + 1 printable char increments typedCount to 1 and stays IDLE',
      initialState: INITIAL_SPARKLE_STATE,
      event: { type: 'TYPE_CHAR', isCollapsed: true, isPrintable: true, char: 'a' },
      expectedState: 'IDLE',
      assertContext: (s) => { expect(s.context.typedCount).toBe(1); },
    },
    // 2. IDLE (typedCount=3) -> TYPING with 4th printable char
    {
      description: 'Edge: IDLE (count 3) + 4th printable char transitions to TYPING (count 4)',
      initialState: {
        name: 'IDLE',
        context: { typedCount: 3, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'TYPE_CHAR', isCollapsed: true, isPrintable: true, char: 'd' },
      expectedState: 'TYPING',
      assertContext: (s) => { expect(s.context.typedCount).toBe(4); },
    },
    // 3. TYPING -> TYPING with additional printable char
    {
      description: 'Edge: TYPING + printable char increments typedCount and stays TYPING',
      initialState: {
        name: 'TYPING',
        context: { typedCount: 4, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'TYPE_CHAR', isCollapsed: true, isPrintable: true, char: 'e' },
      expectedState: 'TYPING',
      assertContext: (s) => { expect(s.context.typedCount).toBe(5); },
    },
    // 4. TYPING -> FETCHING on DEBOUNCE_PAUSE
    {
      description: 'Edge: TYPING + DEBOUNCE_PAUSE transitions to FETCHING',
      initialState: {
        name: 'TYPING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'DEBOUNCE_PAUSE' },
      expectedState: 'FETCHING',
    },
    // 5. FETCHING -> READY_BLINKING on valid suggestion
    {
      description: 'Edge: FETCHING + FETCH_COMPLETION with non-empty text transitions to READY_BLINKING',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'FETCH_COMPLETION', text: ' world', requestId: 'req-123' },
      expectedState: 'READY_BLINKING',
      assertContext: (s) => {
        expect(s.context.suggestion).toBe(' world');
        expect(s.context.requestId).toBe('req-123');
      },
    },
    // 6. FETCHING -> IDLE on empty text completion
    {
      description: 'Edge: FETCHING + FETCH_COMPLETION with empty text transitions to IDLE',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'FETCH_COMPLETION', text: '' },
      expectedState: 'IDLE',
    },
    // 7. FETCHING -> IDLE on FETCH_FAIL (status: empty)
    {
      description: 'Edge: FETCHING + FETCH_FAIL (status: empty) transitions to IDLE',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'FETCH_FAIL', status: 'empty' },
      expectedState: 'IDLE',
    },
    // 8. FETCHING -> IDLE on FETCH_FAIL (status: timeout)
    {
      description: 'Edge: FETCHING + FETCH_FAIL (status: timeout) transitions to IDLE',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'FETCH_FAIL', status: 'timeout' },
      expectedState: 'IDLE',
    },
    // 9. FETCHING -> IDLE on FETCH_FAIL (status: secret_scrubbed)
    {
      description: 'Edge: FETCHING + FETCH_FAIL (status: secret_scrubbed) transitions to IDLE',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'FETCH_FAIL', status: 'secret_scrubbed' },
      expectedState: 'IDLE',
    },
    // 10. FETCHING -> IDLE on FETCH_FAIL (status: unavailable)
    {
      description: 'Edge: FETCHING + FETCH_FAIL (status: unavailable) transitions to IDLE',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'FETCH_FAIL', status: 'unavailable' },
      expectedState: 'IDLE',
    },
    // 11. FETCHING -> IDLE on FETCH_FAIL (status: budget)
    {
      description: 'Edge: FETCHING + FETCH_FAIL (status: budget) transitions to IDLE',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'FETCH_FAIL', status: 'budget' },
      expectedState: 'IDLE',
      assertContext: (s) => { expect(s.context.error).toBe('budget'); },
    },
    // 11b. FETCHING -> IDLE on FETCH_FAIL (error: explicit error string)
    {
      description: 'Edge: FETCHING + FETCH_FAIL (explicit error) transitions to IDLE with error',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'FETCH_FAIL', error: 'Network timeout' },
      expectedState: 'IDLE',
      assertContext: (s) => { expect(s.context.error).toBe('Network timeout'); },
    },
    // 11c. FETCHING -> IDLE on FETCH_FAIL (no error and no status)
    {
      description: 'Edge: FETCHING + FETCH_FAIL (no error, no status) transitions to IDLE with null error',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'FETCH_FAIL' },
      expectedState: 'IDLE',
      assertContext: (s) => { expect(s.context.error).toBeNull(); },
    },
    // 12. FETCHING -> TYPING on typing during FETCHING (aborts prior stream)
    {
      description: 'Edge: FETCHING + TYPE_CHAR transitions back to TYPING',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 5, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'TYPE_CHAR', isCollapsed: true, isPrintable: true, char: 'x' },
      expectedState: 'TYPING',
      assertContext: (s) => { expect(s.context.typedCount).toBe(6); },
    },
    // 13. READY_BLINKING -> ACCEPTED on ACCEPT (Tab or Click)
    {
      description: 'Edge: READY_BLINKING + ACCEPT transitions to ACCEPTED',
      initialState: {
        name: 'READY_BLINKING',
        context: { typedCount: 5, suggestion: 'hello', requestId: 'req-1', error: null },
      },
      event: { type: 'ACCEPT' },
      expectedState: 'ACCEPTED',
    },
    // 14. READY_BLINKING -> DISMISSED on DISMISS (Escape)
    {
      description: 'Edge: READY_BLINKING + DISMISS (escape) transitions to DISMISSED',
      initialState: {
        name: 'READY_BLINKING',
        context: { typedCount: 5, suggestion: 'hello', requestId: 'req-1', error: null },
      },
      event: { type: 'DISMISS', reason: 'escape' },
      expectedState: 'DISMISSED',
    },
    // 15. READY_BLINKING -> DISMISSED on DISMISS (cursor_move)
    {
      description: 'Edge: READY_BLINKING + DISMISS (cursor_move) transitions to DISMISSED',
      initialState: {
        name: 'READY_BLINKING',
        context: { typedCount: 5, suggestion: 'hello', requestId: 'req-1', error: null },
      },
      event: { type: 'DISMISS', reason: 'cursor_move' },
      expectedState: 'DISMISSED',
    },
    // 16. READY_BLINKING -> DISMISSED on mismatched typing
    {
      description: 'Edge: READY_BLINKING + mismatched TYPE_CHAR transitions to DISMISSED',
      initialState: {
        name: 'READY_BLINKING',
        context: { typedCount: 5, suggestion: 'hello', requestId: 'req-1', error: null },
      },
      event: { type: 'TYPE_CHAR', isCollapsed: true, isPrintable: true, char: 'z' },
      expectedState: 'DISMISSED',
    },
    // 17. READY_BLINKING -> READY_BLINKING on matching typing (advances ghost text)
    {
      description: 'Edge: READY_BLINKING + matched TYPE_CHAR advances ghost text by 1',
      initialState: {
        name: 'READY_BLINKING',
        context: { typedCount: 5, suggestion: 'hello', requestId: 'req-1', error: null },
      },
      event: { type: 'TYPE_CHAR', isCollapsed: true, isPrintable: true, char: 'h' },
      expectedState: 'READY_BLINKING',
      assertContext: (s) => { expect(s.context.suggestion).toBe('ello'); },
    },
    // 18. READY_BLINKING -> ACCEPTED on matching typing of the final char
    {
      description: 'Edge: READY_BLINKING + matched final char completes suggestion -> ACCEPTED',
      initialState: {
        name: 'READY_BLINKING',
        context: { typedCount: 5, suggestion: 'o', requestId: 'req-1', error: null },
      },
      event: { type: 'TYPE_CHAR', isCollapsed: true, isPrintable: true, char: 'o' },
      expectedState: 'ACCEPTED',
      assertContext: (s) => { expect(s.context.suggestion).toBe(''); },
    },
    // 19. ACCEPTED -> IDLE on RESET
    {
      description: 'Edge: ACCEPTED + RESET transitions to IDLE',
      initialState: {
        name: 'ACCEPTED',
        context: { typedCount: 5, suggestion: 'done', requestId: 'req-1', error: null },
      },
      event: { type: 'RESET' },
      expectedState: 'IDLE',
    },
    // 20. DISMISSED -> IDLE on RESET
    {
      description: 'Edge: DISMISSED + RESET transitions to IDLE',
      initialState: {
        name: 'DISMISSED',
        context: { typedCount: 5, suggestion: 'abandoned', requestId: 'req-1', error: null },
      },
      event: { type: 'RESET' },
      expectedState: 'IDLE',
    },
    // 21. Non-edge: IDLE + ACCEPT stays IDLE
    {
      description: 'Non-edge: IDLE + ACCEPT stays IDLE',
      initialState: INITIAL_SPARKLE_STATE,
      event: { type: 'ACCEPT' },
      expectedState: 'IDLE',
    },
    // 22. Non-edge: IDLE + DEBOUNCE_PAUSE stays IDLE
    {
      description: 'Non-edge: IDLE + DEBOUNCE_PAUSE stays IDLE',
      initialState: INITIAL_SPARKLE_STATE,
      event: { type: 'DEBOUNCE_PAUSE' },
      expectedState: 'IDLE',
    },
    // 23. Non-edge: IDLE + FETCH_COMPLETION stays IDLE
    {
      description: 'Non-edge: IDLE + FETCH_COMPLETION stays IDLE',
      initialState: INITIAL_SPARKLE_STATE,
      event: { type: 'FETCH_COMPLETION', text: 'ignored' },
      expectedState: 'IDLE',
    },
    // 24. Non-edge: TYPING + ACCEPT stays TYPING
    {
      description: 'Non-edge: TYPING + ACCEPT stays TYPING',
      initialState: {
        name: 'TYPING',
        context: { typedCount: 4, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'ACCEPT' },
      expectedState: 'TYPING',
    },
    // 25. Non-edge: FETCHING + ACCEPT stays FETCHING
    {
      description: 'Non-edge: FETCHING + ACCEPT stays FETCHING',
      initialState: {
        name: 'FETCHING',
        context: { typedCount: 4, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'ACCEPT' },
      expectedState: 'FETCHING',
    },
    // 26. Non-edge: READY_BLINKING + DEBOUNCE_PAUSE stays READY_BLINKING
    {
      description: 'Non-edge: READY_BLINKING + DEBOUNCE_PAUSE stays READY_BLINKING',
      initialState: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: 'stay', requestId: null, error: null },
      },
      event: { type: 'DEBOUNCE_PAUSE' },
      expectedState: 'READY_BLINKING',
    },
    // 27. Edge: IDLE with non-collapsed selection resets typedCount
    {
      description: 'Edge: IDLE + non-collapsed typing resets typedCount to 0',
      initialState: {
        name: 'IDLE',
        context: { typedCount: 2, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'TYPE_CHAR', isCollapsed: false, isPrintable: true, char: 'a' },
      expectedState: 'IDLE',
      assertContext: (s) => { expect(s.context.typedCount).toBe(0); },
    },
    // 28. Edge: TYPING with non-collapsed selection drops to IDLE
    {
      description: 'Edge: TYPING + non-collapsed typing drops to IDLE',
      initialState: {
        name: 'TYPING',
        context: { typedCount: 4, suggestion: '', requestId: null, error: null },
      },
      event: { type: 'TYPE_CHAR', isCollapsed: false, isPrintable: true, char: 'a' },
      expectedState: 'IDLE',
      assertContext: (s) => { expect(s.context.typedCount).toBe(0); },
    },
    // 29. Edge: READY_BLINKING with non-collapsed selection dismisses
    {
      description: 'Edge: READY_BLINKING + non-collapsed typing dismisses',
      initialState: {
        name: 'READY_BLINKING',
        context: { typedCount: 4, suggestion: 'hello', requestId: null, error: null },
      },
      event: { type: 'TYPE_CHAR', isCollapsed: false, isPrintable: true, char: 'h' },
      expectedState: 'DISMISSED',
    },
  ];

  for (const [index, tc] of tableTestCases.entries()) {
    it(`Row ${String(index + 1)}: ${tc.description}`, () => {
      const nextState = sparkleReducer(tc.initialState, tc.event);
      expect(nextState.name).toBe(tc.expectedState);
      if (tc.assertContext) {
        tc.assertContext(nextState);
      }
    });
  }

  it('verifies printable character detection helper', () => {
    expect(isPrintableChar('a')).toBe(true);
    expect(isPrintableChar('Z')).toBe(true);
    expect(isPrintableChar(' ')).toBe(true);
    expect(isPrintableChar('!')).toBe(true);
    expect(isPrintableChar('9')).toBe(true);
    expect(isPrintableChar('\n')).toBe(false);
    expect(isPrintableChar('\t')).toBe(false);
    expect(isPrintableChar('\r')).toBe(false);
    expect(isPrintableChar('')).toBe(false);
    expect(isPrintableChar('ab')).toBe(false);
    expect(isPrintableChar(String.fromCharCode(127))).toBe(false);
  });
});
