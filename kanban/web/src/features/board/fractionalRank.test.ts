import { describe, expect, it } from 'vitest';
import {
  ALPHABET,
  DEFAULT_MIDPOINT_CHAR,
  getChar,
  getVal,
  midpointRank,
  RankOrderError,
} from './fractionalRank.ts';

describe('fractionalRank', () => {
  it('handles null boundaries', () => {
    expect(midpointRank(null, null)).toBe(DEFAULT_MIDPOINT_CHAR);
    expect(midpointRank(null, 'V')).toBe('F');
    expect(midpointRank('V', null)).toBe('W');
    expect(midpointRank('z', null)).toBe('zV');
  });

  it('computes midpoint between a000001 and a000002 matching requirement 1', () => {
    const prev = 'a000001';
    const next = 'a000002';
    const m = midpointRank(prev, next);
    expect(m).toBe('a000001V');
    expect(prev < m).toBe(true);
    expect(m < next).toBe(true);
  });

  it('computes midpoint with wide gaps', () => {
    const m = midpointRank('1', '9');
    expect(m).toBe('5');
    expect('1' < m && m < '9').toBe(true);
  });

  it('computes midpoint when prev is a proper prefix of next', () => {
    const prev = 'abc';
    const next = 'abcd';
    const m = midpointRank(prev, next);
    expect(prev < m).toBe(true);
    expect(m < next).toBe(true);
  });

  it('computes midpoint with zero-prefix in divergence rest', () => {
    const prev = 'a0';
    const next = 'a1';
    const m = midpointRank(prev, next);
    expect(prev < m && m < next).toBe(true);
  });

  it('throws RankOrderError when prev >= next', () => {
    expect(() => midpointRank('b', 'a')).toThrow(RankOrderError);
    expect(() => midpointRank('same', 'same')).toThrow(RankOrderError);
  });

  it('maintains strict ASCII order across alphabet', () => {
    for (let i = 0; i < ALPHABET.length - 1; i++) {
      const a = ALPHABET.charAt(i);
      const b = ALPHABET.charAt(i + 1);
      const m = midpointRank(a, b);
      expect(a < m).toBe(true);
      expect(m < b).toBe(true);
    }
  });

  it('covers head with 0-prefix and non-divisible character', () => {
    const m = midpointRank(null, '001');
    expect(m).toBe('000V');
    expect(m < '001').toBe(true);
  });

  it('covers between with adjacent characters and non-empty pRest', () => {
    const m = midpointRank('a0z', 'a1');
    expect('a0z' < m).toBe(true);
    expect(m < 'a1').toBe(true);
  });
});

  it('covers getVal and getChar edge cases', () => {
    expect(getVal(undefined)).toBe(0);
    expect(getVal('not-in-alphabet')).toBe(0);
    expect(getChar(999)).toBe(DEFAULT_MIDPOINT_CHAR);
  });
