/**
 * Fractional Base-62 (COLLATE "C") board rank indexing engine (KB-P3-12, KB-P3-37, S6.4).
 *
 * Strict ASCII byte order: '0'-'9' (48-57) < 'A'-'Z' (65-90) < 'a'-'z' (97-122).
 * This matches PostgreSQL COLLATE "C" exactly.
 */

export const ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
export const BASE62_LEN = 62;
export const DEFAULT_MIDPOINT_CHAR = 'V'; // ALPHABET[31]
const MIN_DIVISIBLE_VAL = 2;

const VAL_MAP: Record<string, number> = {};
for (let i = 0; i < ALPHABET.length; i++) {
  VAL_MAP[ALPHABET.charAt(i)] = i;
}

export function getVal(char: string | undefined): number {
  if (char === undefined) return 0;
  return VAL_MAP[char] ?? 0;
}

export function getChar(index: number): string {
  return ALPHABET[index] ?? DEFAULT_MIDPOINT_CHAR;
}

export class RankOrderError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RankOrderError';
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

function midpointHead(nextRank: string): string {
  let k = 0;
  while (k < nextRank.length && nextRank[k] === '0') {
    k++;
  }
  const c = nextRank[k];
  const val = getVal(c);
  if (val >= MIN_DIVISIBLE_VAL) {
    return '0'.repeat(k) + getChar(Math.floor(val / 2));
  }
  return '0'.repeat(k + 1) + DEFAULT_MIDPOINT_CHAR;
}

function midpointTail(prevRank: string): string {
  const lastChar = prevRank[prevRank.length - 1];
  if (lastChar !== undefined && lastChar < 'z') {
    return prevRank.slice(0, -1) + getChar(getVal(lastChar) + 1);
  }
  return prevRank + DEFAULT_MIDPOINT_CHAR;
}

function midpointBetween(prevRank: string, nextRank: string): string {
  let prefixLen = 0;
  while (
    prefixLen < prevRank.length &&
    prefixLen < nextRank.length &&
    prevRank[prefixLen] === nextRank[prefixLen]
  ) {
    prefixLen++;
  }

  const prefix = prevRank.slice(0, prefixLen);

  if (prefixLen < prevRank.length && prefixLen < nextRank.length) {
    const pVal = getVal(prevRank[prefixLen]);
    const nVal = getVal(nextRank[prefixLen]);
    const diff = nVal - pVal;
    if (diff > 1) {
      const mid = Math.floor((pVal + nVal) / 2);
      return prefix + getChar(mid);
    }
    const pRest = prevRank.slice(prefixLen + 1);
    if (!pRest) {
      return prevRank + DEFAULT_MIDPOINT_CHAR;
    }
    const curPChar = prevRank.charAt(prefixLen);
    return prefix + curPChar + midpointTail(pRest);
  }

  // prevRank is a proper prefix of nextRank
  const nRest = nextRank.slice(prefixLen);
  return prefix + midpointHead(nRest);
}

/**
 * Compute the shortest Base-62 rank satisfying prevRank < midpoint < nextRank in COLLATE "C".
 */
export function midpointRank(prevRank: string | null, nextRank: string | null): string {
  if (prevRank !== null && nextRank !== null && prevRank >= nextRank) {
    throw new RankOrderError(
      `prev_rank '${prevRank}' must be strictly less than next_rank '${nextRank}'`,
    );
  }

  if (prevRank === null) {
    if (nextRank === null) {
      return DEFAULT_MIDPOINT_CHAR;
    }
    return midpointHead(nextRank);
  }
  if (nextRank === null) {
    return midpointTail(prevRank);
  }
  return midpointBetween(prevRank, nextRank);
}
