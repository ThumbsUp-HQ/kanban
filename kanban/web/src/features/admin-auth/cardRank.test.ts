import { describe, it, expect } from 'vitest';
import { midpointRank } from './cardRank';

describe('cardRank (KB-P3-36)', () => {
  it('returns default rank when both bounds are null', () => {
    expect(midpointRank(null, null)).toBe('V');
  });

  it('computes rank smaller than next when prev is null', () => {
    const next = 'V';
    const rank = midpointRank(null, next);
    expect(rank < next).toBe(true);
  });

  it('computes rank greater than prev when next is null', () => {
    const prev = 'V';
    const rank = midpointRank(prev, null);
    expect(rank > prev).toBe(true);
  });

  it('computes rank strictly between two adjacent ranks', () => {
    const prev = '1';
    const next = '2';
    const mid = midpointRank(prev, next);
    expect(prev < mid && mid < next).toBe(true);
  });

  it('computes rank when prev is a prefix of next', () => {
    const prev = 'A';
    const next = 'AV';
    const mid = midpointRank(prev, next);
    expect(prev < mid && mid < next).toBe(true);
  });

  it('computes rank when distance between characters is greater than 1', () => {
    const prev = '1';
    const next = '5';
    const mid = midpointRank(prev, next);
    expect(prev < mid && mid < next).toBe(true);
    expect(mid).toBe('3');
  });

  it('handles edge case when inserting before rank 0', () => {
    const next = '0';
    const rank = midpointRank(null, next);
    expect(rank).toBe('00V');
  });

  it('handles edge case when inserting after max character rank z', () => {
    const prev = 'z';
    const rank = midpointRank(prev, null);
    expect(rank > prev).toBe(true);
  });

  it('maintains strict a < b ASCII COLLATE "C" ordering across 100 sequential insertions at top (Mandatory Test Case 6)', () => {
    const ranks = ['V'];
    for (let i = 0; i < 100; i++) {
      const top = ranks[0];
      if (!top) break;
      const newRank = midpointRank(null, top);
      expect(newRank < top).toBe(true);
      ranks.unshift(newRank);
    }

    // Verify all 101 elements are strictly increasing
    for (let i = 0; i < ranks.length - 1; i++) {
      const current = ranks[i];
      const next = ranks[i + 1];
      if (current && next) {
        expect(current < next).toBe(true);
      }
    }
  });

  it('maintains strict ordering across 100 sequential insertions at bottom', () => {
    const ranks = ['V'];
    for (let i = 0; i < 100; i++) {
      const bottom = ranks[ranks.length - 1];
      if (!bottom) break;
      const newRank = midpointRank(bottom, null);
      expect(newRank > bottom).toBe(true);
      ranks.push(newRank);
    }

    for (let i = 0; i < ranks.length - 1; i++) {
      const current = ranks[i];
      const next = ranks[i + 1];
      if (current && next) {
        expect(current < next).toBe(true);
      }
    }
  });

  it('maintains strict ordering across 100 middle insertions between adjacent items', () => {
    const ranks = ['1', '2'];
    for (let i = 0; i < 100; i++) {
      const r0 = ranks[0];
      const r1 = ranks[1];
      if (!r0 || !r1) break;
      const newRank = midpointRank(r0, r1);
      expect(r0 < newRank && newRank < r1).toBe(true);
      ranks.splice(1, 0, newRank);
    }

    for (let i = 0; i < ranks.length - 1; i++) {
      const current = ranks[i];
      const next = ranks[i + 1];
      if (current && next) {
        expect(current < next).toBe(true);
      }
    }
  });
});
