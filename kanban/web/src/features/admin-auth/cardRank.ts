/**
 * Base-62 COLLATE "C" lexicographic rank calculation for Auth Cards reordering (KB-P3-36, S4.1).
 *
 * Alphabet: 0-9A-Za-z (ASCII 48-57, 65-90, 97-122).
 * Matches PostgreSQL binary byte comparison under COLLATE "C".
 */

export const BASE62_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';

/**
 * Computes a lexicographic midpoint rank string between prev and next in Base-62 COLLATE "C" order.
 * Guarantees prev < midpointRank(prev, next) < next in strict ASCII byte order.
 *
 * @param prev Preceding card sort_rank or null if inserting at top
 * @param next Succeeding card sort_rank or null if inserting at bottom
 */
export function midpointRank(prev: string | null, next: string | null): string {
  const p = prev ?? '';
  const n = next ?? '';

  if (!p && !n) {
    return 'V'; // midpoint of alphabet (index 31)
  }

  if (!p) {
    // Inserting at top: find a string smaller than n
    for (let i = 0; i < n.length; i++) {
      const v = BASE62_CHARS.indexOf(n.charAt(i));
      if (v > 1) {
        return n.slice(0, i) + BASE62_CHARS.charAt(Math.floor(v / 2));
      }
      if (v === 1) {
        return n.slice(0, i) + '0' + BASE62_CHARS.charAt(31);
      }
    }
    return n + '0' + BASE62_CHARS.charAt(31);
  }

  if (!n) {
    // Inserting at bottom: find a string larger than p
    for (let i = 0; i < p.length; i++) {
      const v = BASE62_CHARS.indexOf(p.charAt(i));
      if (v < 60) {
        return p.slice(0, i) + BASE62_CHARS.charAt(Math.floor((v + 61) / 2));
      }
    }
    return p + BASE62_CHARS.charAt(31);
  }

  // Find common prefix
  let common = 0;
  while (common < p.length && common < n.length && p.charAt(common) === n.charAt(common)) {
    common++;
  }

  if (common === p.length) {
    // p is an exact prefix of n (e.g. p = "A", n = "AV")
    const remainderNext = n.slice(common);
    const sub = midpointRank(null, remainderNext);
    return p + sub;
  }

  const pVal = BASE62_CHARS.indexOf(p.charAt(common));
  const nVal = BASE62_CHARS.indexOf(n.charAt(common));

  if (nVal - pVal > 1) {
    const midVal = Math.floor((pVal + nVal) / 2);
    return p.slice(0, common) + BASE62_CHARS.charAt(midVal);
  }

  // Adjacent characters: append midpoint of remainder
  const remainderPrev = p.slice(common + 1);
  const sub = midpointRank(remainderPrev, null);
  return p.slice(0, common + 1) + sub;
}
