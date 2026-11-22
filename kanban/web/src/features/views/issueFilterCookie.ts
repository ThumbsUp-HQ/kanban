/**
 * Bounded per-project workflow state filter cookie persistence & precedence engine (KAN-308 Problem 1).
 *
 * Security & Architecture Invariants:
 * - Single host-only cookie `kb_issue_state_filter` (`Path=/; Max-Age=2592000; SameSite=Lax`, plus `; Secure` on `https:`).
 * - Never touches or collides with `__Host-kb_session`, `__Host-kb_csrf`, or `kb_csrf`.
 * - Keys project entries by a deterministic opaque 8-hex-char FNV-1a digest of `${workspaceScope}:${projectKey}`
 *   so raw workspace slugs or project names never leak in HTTP `Cookie` headers.
 * - Exclusion-based `v: 1` schema (`hc: 1, hx: 1, ex, inc, ua`) ensures custom non-terminal states
 *   (such as `Crazy_Ideas`) stay visible by default.
 * - Enforces max 8 LRU projects on `ua`, hard write cap `<= 1024` encoded bytes, and hard read cap `<= 2048` raw bytes.
 * - Strips/rejects ASCII control chars, semicolons, CRLF, and lone UTF-16 surrogates; parses exclusively
 *   via `safeJsonParse` into a null-prototype map (`Object.create(null)`).
 * - Fails closed to actionable default (`hc: 1, hx: 1`) and clears corrupt cookies (`Max-Age=0`).
 */

import { safeJsonParse } from '../../utils/safeJson';
import { normalizeStateKey, type SavedView, type StateSummary } from './viewsApi';

export const ISSUE_FILTER_COOKIE_NAME = 'kb_issue_state_filter';
export const ISSUE_FILTER_COOKIE_MAX_AGE = 2592000; // 30 days
export const MAX_COOKIE_PROJECTS = 8;
export const MAX_COOKIE_WRITE_BYTES = 1024;
export const MAX_COOKIE_READ_BYTES = 2048;
export const MAX_STATE_TOKENS = 16;
export const MAX_URL_FILTER_STATE_LENGTH = 512;

export const STATE_TOKEN_REGEX = /^[a-zA-Z0-9_-]{1,64}$/;
export const PROJECT_HASH_KEY_REGEX = /^[0-9a-f]{8}$/;

export interface ProjectStateFilterPreference {
  /** 1 = hide completed state group (default 1), 0 = show completed */
  hc: 0 | 1;
  /** 1 = hide cancelled state group (default 1), 0 = show cancelled */
  hx: 0 | 1;
  /** Explicitly excluded state IDs/tokens (up to 16) */
  ex: string[];
  /** Explicitly included state IDs/tokens (up to 16) */
  inc: string[];
  /** Last updated epoch timestamp (seconds) for LRU eviction */
  ua: number;
}

export interface CompactProjectStateFilterEntry {
  hc: 0 | 1;
  hx: 0 | 1;
  ex?: string[];
  inc?: string[];
  ua: number;
}

export interface IssueFilterCookiePayload {
  v: 1;
  p: Record<string, ProjectStateFilterPreference>;
}

export type StateFilterPreset = 'actionable' | 'all' | 'none' | 'custom';

export type StateFilterResolutionSource = 'url' | 'saved_view' | 'cookie' | 'default';

export interface ResolvedStateFilterResult {
  preference: ProjectStateFilterPreference;
  source: StateFilterResolutionSource;
}

const KNOWN_STANDARD_STATE_TOKENS: ReadonlySet<string> = new Set([
  'all',
  'active',
  'actionable',
  'none',
  'backlog',
  'unstarted',
  'started',
  'completed',
  'cancelled',
  'todo',
  'in-progress',
  'in_progress',
  'inprogress',
  'in-review',
  'in_review',
  'inreview',
  'done',
  'state-backlog',
  'state-todo',
  'state-in-progress',
  'state-in-review',
  'state-done',
  'state-cancelled',
]);

/**
 * Returns true if the input string contains ASCII control characters (0x00-0x1F, 0x7F),
 * CR/LF, or lone UTF-16 surrogates (0xD800-0xDFFF).
 */
export function hasControlOrLoneSurrogate(input: string): boolean {
  for (let i = 0; i < input.length; i += 1) {
    const code = input.charCodeAt(i);
    if (code <= 0x1f || code === 0x7f) {
      return true;
    }
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = i + 1 < input.length ? input.charCodeAt(i + 1) : 0;
      if (next >= 0xdc00 && next <= 0xdfff) {
        i += 1;
        continue;
      }
      return true;
    }
    if (code >= 0xdc00 && code <= 0xdfff) {
      return true;
    }
  }
  return false;
}

/**
 * Strips ASCII control characters (0x00-0x1F, 0x7F), CR/LF, optional semicolons,
 * and lone UTF-16 surrogates while preserving valid astral emoji surrogate pairs.
 */
export function stripControlAndSurrogates(input: string, stripSemicolons = false): string {
  let out = '';
  for (let i = 0; i < input.length; i += 1) {
    const code = input.charCodeAt(i);
    if (code <= 0x1f || code === 0x7f) {
      continue;
    }
    if (stripSemicolons && code === 0x3b) {
      continue;
    }
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = i + 1 < input.length ? input.charCodeAt(i + 1) : 0;
      if (next >= 0xdc00 && next <= 0xdfff) {
        out += input.charAt(i) + input.charAt(i + 1);
        i += 1;
      }
      continue;
    }
    if (code >= 0xdc00 && code <= 0xdfff) {
      continue;
    }
    out += input.charAt(i);
  }
  return out;
}

/**
 * Computes a deterministic 8-hex-char 32-bit FNV-1a digest of `${workspaceScope}:${projectKey}`.
 * Ensures raw workspace slugs and project names never appear in browser cookies.
 */
export function computeProjectFilterKey(
  projectKey: string,
  workspaceScope = 'default',
): string {
  const cleanScope = stripControlAndSurrogates(workspaceScope, true).trim().toLowerCase() || 'default';
  const cleanProject = stripControlAndSurrogates(projectKey, true).trim().toLowerCase() || 'default';
  const raw = `${cleanScope}:${cleanProject}`;
  const bytes = new TextEncoder().encode(raw);
  let hash = 0x811c9dc5;
  for (const b of bytes) {
    hash ^= b;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

/**
 * Creates the default Actionable state filter preference (`hc: 1, hx: 1, ex: [], inc: []`).
 */
export function createActionableStateFilterPreference(
  nowSec: number = Math.floor(Date.now() / 1000),
): ProjectStateFilterPreference {
  return {
    hc: 1,
    hx: 1,
    ex: [],
    inc: [],
    ua: nowSec,
  };
}

/**
 * Creates the All-States filter preference (`hc: 0, hx: 0, ex: [], inc: []`).
 */
export function createAllStatesFilterPreference(
  nowSec: number = Math.floor(Date.now() / 1000),
): ProjectStateFilterPreference {
  return {
    hc: 0,
    hx: 0,
    ex: [],
    inc: [],
    ua: nowSec,
  };
}

/**
 * Creates the None (0 states visible) filter preference.
 */
export function createNoStatesFilterPreference(
  projectStates: readonly StateSummary[] = [],
  nowSec: number = Math.floor(Date.now() / 1000),
): ProjectStateFilterPreference {
  const actionableIds = projectStates
    .filter((s) => {
      const grp = s.group.toLowerCase();
      return grp !== 'completed' && grp !== 'cancelled';
    })
    .map((s) => stripControlAndSurrogates(s.id, true).trim())
    .filter((id) => STATE_TOKEN_REGEX.test(id));

  const ex = Array.from(new Set(['__all__', ...actionableIds])).slice(0, MAX_STATE_TOKENS);
  return {
    hc: 1,
    hx: 1,
    ex,
    inc: [],
    ua: nowSec,
  };
}

function canonicalTokenAlias(token: string): string {
  const norm = normalizeStateKey(token);
  if (norm.startsWith('state') && norm.length > 5) {
    return norm.slice(5);
  }
  return norm;
}

function tokenMatchesState(
  token: string,
  state: { id?: string | undefined; name?: string | undefined; group?: string | undefined },
): boolean {
  const stateId = state.id ?? '';
  const stateIdLower = stateId.toLowerCase();
  const tokenLower = token.toLowerCase();
  if (stateIdLower && tokenLower === stateIdLower) {
    return true;
  }
  const stateName = state.name ?? '';
  const normName = stateName ? normalizeStateKey(stateName) : '';
  const normId = stateId ? canonicalTokenAlias(stateId) : '';
  const normToken = canonicalTokenAlias(token);
  return Boolean(
    normToken && ((normName && normToken === normName) || (normId && normToken === normId)),
  );
}

/**
 * Evaluates whether a workflow state is visible under the given preference:
 * (1) if `inc` includes `s.id` (or normalized state key) -> visible;
 * (2) else if `ex` includes `s.id` (or normalized state key or `__all__`) -> hidden;
 * (3) else if `s.group === 'completed'` -> hidden iff `hc === 1`;
 * (4) else if `s.group === 'cancelled'` -> hidden iff `hx === 1`;
 * (5) else (`backlog`, `unstarted`, `started`, and custom non-terminal states like `Crazy_Ideas`) -> visible.
 */
export function isIssueStateVisible(
  state: { id?: string | undefined; name?: string | undefined; group?: string | undefined } | null | undefined,
  pref: ProjectStateFilterPreference,
): boolean {
  if (!state) {
    return !pref.ex.includes('__all__');
  }
  for (const incToken of pref.inc) {
    if (tokenMatchesState(incToken, state)) {
      return true;
    }
  }
  if (pref.ex.includes('__all__')) {
    return false;
  }
  for (const exToken of pref.ex) {
    if (tokenMatchesState(exToken, state)) {
      return false;
    }
  }
  const group = (state.group ?? 'unstarted').toLowerCase();
  if (group === 'completed') {
    return pref.hc !== 1;
  }
  if (group === 'cancelled') {
    return pref.hx !== 1;
  }
  return true;
}

/**
 * Toggles a single workflow state's visibility inside an exclusion-based preference.
 * Preserves the invariant that newly added non-terminal custom states stay visible unless explicitly excluded.
 */
export function toggleStateInPreference(
  pref: ProjectStateFilterPreference,
  targetState: StateSummary,
  checked: boolean,
  allStates: readonly StateSummary[] = [],
  nowSec: number = Math.floor(Date.now() / 1000),
): ProjectStateFilterPreference {
  const stateId = stripControlAndSurrogates(targetState.id, true).trim();
  const validId = STATE_TOKEN_REGEX.test(stateId) ? stateId : normalizeStateKey(targetState.name);
  const group = targetState.group.toLowerCase();
  const isTerminal = group === 'completed' || group === 'cancelled';

  // If currently in `__all__` excluded mode ("None" preset) and user checks one state:
  if (pref.ex.includes('__all__')) {
    const actionableStates = allStates.filter((s) => {
      const g = s.group.toLowerCase();
      return g !== 'completed' && g !== 'cancelled';
    });
    const nextEx = actionableStates
      .filter((s) => !(checked && !isTerminal && tokenMatchesState(validId, s)))
      .map((s) => s.id)
      .filter((id) => STATE_TOKEN_REGEX.test(id))
      .slice(0, MAX_STATE_TOKENS);
    const nextInc =
      checked && isTerminal && STATE_TOKEN_REGEX.test(validId) ? [validId] : [];
    return {
      hc: 1,
      hx: 1,
      ex: nextEx,
      inc: nextInc,
      ua: nowSec,
    };
  }

  let nextHc: 0 | 1 = pref.hc;
  let nextHx: 0 | 1 = pref.hx;
  let nextEx = pref.ex.filter((t) => !tokenMatchesState(t, targetState) && t !== '__all__');
  let nextInc = pref.inc.filter((t) => !tokenMatchesState(t, targetState));

  if (group === 'completed') {
    if (checked) {
      if (nextHc === 1 && STATE_TOKEN_REGEX.test(validId)) {
        nextInc = [...nextInc, validId].slice(0, MAX_STATE_TOKENS);
      }
    } else {
      if (nextHc === 0) {
        const otherCompleted = allStates.filter(
          (s) => s.group.toLowerCase() === 'completed' && !tokenMatchesState(validId, s),
        );
        nextHc = 1;
        for (const s of otherCompleted) {
          if (isIssueStateVisible(s, pref) && STATE_TOKEN_REGEX.test(s.id)) {
            nextInc.push(s.id);
          }
        }
        nextInc = Array.from(new Set(nextInc)).slice(0, MAX_STATE_TOKENS);
      }
    }
  } else if (group === 'cancelled') {
    if (checked) {
      if (nextHx === 1 && STATE_TOKEN_REGEX.test(validId)) {
        nextInc = [...nextInc, validId].slice(0, MAX_STATE_TOKENS);
      }
    } else {
      if (nextHx === 0) {
        const otherCancelled = allStates.filter(
          (s) => s.group.toLowerCase() === 'cancelled' && !tokenMatchesState(validId, s),
        );
        nextHx = 1;
        for (const s of otherCancelled) {
          if (isIssueStateVisible(s, pref) && STATE_TOKEN_REGEX.test(s.id)) {
            nextInc.push(s.id);
          }
        }
        nextInc = Array.from(new Set(nextInc)).slice(0, MAX_STATE_TOKENS);
      }
    }
  } else {
    // Non-terminal / actionable state
    if (!checked && STATE_TOKEN_REGEX.test(validId)) {
      nextEx = [...nextEx, validId].slice(0, MAX_STATE_TOKENS);
    }
  }

  return {
    hc: nextHc,
    hx: nextHx,
    ex: nextEx,
    inc: nextInc,
    ua: nowSec,
  };
}

/**
 * Classifies the active state filter preference against the current project states
 * for the `StateFilterPopover` trigger pill summary and preset buttons.
 */
export function classifyStateFilterPreset(
  pref: ProjectStateFilterPreference,
  projectStates: readonly StateSummary[],
): {
  preset: StateFilterPreset;
  selectedStates: StateSummary[];
  actionableCount: number;
  label: string;
} {
  const selectedStates = projectStates.filter((s) => isIssueStateVisible(s, pref));
  const actionableStates = projectStates.filter((s) => {
    const g = s.group.toLowerCase();
    return g !== 'completed' && g !== 'cancelled';
  });
  const closedStates = projectStates.filter((s) => {
    const g = s.group.toLowerCase();
    return g === 'completed' || g === 'cancelled';
  });

  const allActionableSelected = actionableStates.every((s) => isIssueStateVisible(s, pref));
  const noClosedSelected = closedStates.every((s) => !isIssueStateVisible(s, pref));
  const allClosedSelected =
    closedStates.length > 0
      ? closedStates.every((s) => isIssueStateVisible(s, pref))
      : pref.hc === 0 && pref.hx === 0;

  if (selectedStates.length === 0 || pref.ex.includes('__all__')) {
    return {
      preset: 'none',
      selectedStates: [],
      actionableCount: actionableStates.length,
      label: 'States: None (0)',
    };
  }

  if (allActionableSelected && allClosedSelected && pref.ex.length === 0) {
    return {
      preset: 'all',
      selectedStates,
      actionableCount: actionableStates.length,
      label: 'States: All',
    };
  }

  if (allActionableSelected && noClosedSelected && pref.hc === 1 && pref.hx === 1 && pref.ex.length === 0 && pref.inc.length === 0) {
    return {
      preset: 'actionable',
      selectedStates,
      actionableCount: actionableStates.length,
      label: `States: Actionable (${String(actionableStates.length)})`,
    };
  }

  if (selectedStates.length === 1 && selectedStates[0]) {
    return {
      preset: 'custom',
      selectedStates,
      actionableCount: actionableStates.length,
      label: `State: ${selectedStates[0].name}`,
    };
  }

  return {
    preset: 'custom',
    selectedStates,
    actionableCount: actionableStates.length,
    label: `States: ${String(selectedStates.length)} selected`,
  };
}

/**
 * Formats and writes a Max-Age=0 directive to clear a corrupt `kb_issue_state_filter` cookie.
 */
export function clearIssueFilterCookie(options?: { protocol?: string | undefined }): string {
  const protocol =
    options?.protocol ??
    (typeof window !== 'undefined' ? window.location.protocol : 'http:');
  const secureAttr = protocol === 'https:' ? '; Secure' : '';
  const directive = `${ISSUE_FILTER_COOKIE_NAME}=; Path=/; Max-Age=0; SameSite=Lax${secureAttr}`;
  if (typeof document !== 'undefined') {
    document.cookie = directive;
  }
  return directive;
}

function extractRawFilterCookieValue(cookieHeader: string): string | null {
  if (!cookieHeader) return null;
  const parts = cookieHeader.split(';');
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(`${ISSUE_FILTER_COOKIE_NAME}=`)) {
      return trimmed.slice(ISSUE_FILTER_COOKIE_NAME.length + 1);
    }
  }
  return null;
}

function validateTokenArray(arr: unknown): string[] | null {
  if (arr === undefined) return [];
  if (!Array.isArray(arr) || arr.length > MAX_STATE_TOKENS) {
    return null;
  }
  const result: string[] = [];
  for (const item of arr) {
    if (typeof item !== 'string' || !STATE_TOKEN_REGEX.test(item)) {
      return null;
    }
    if (!result.includes(item)) {
      result.push(item);
    }
  }
  return result;
}

/**
 * Reads and validates the full `kb_issue_state_filter` cookie payload into a null-prototype map.
 * On any parse failure, schema violation, prototype-pollution key, control character, or oversize
 * payload (> 2048 raw bytes), clears the cookie (`Max-Age=0`) and fails closed.
 */
export function readIssueFilterCookiePayload(options?: {
  cookieHeader?: string | undefined;
  protocol?: string | undefined;
}): {
  valid: boolean;
  present: boolean;
  payload: IssueFilterCookiePayload;
} {
  const emptyMap = Object.create(null) as Record<string, ProjectStateFilterPreference>;
  const emptyPayload: IssueFilterCookiePayload = { v: 1, p: emptyMap };

  const source =
    options?.cookieHeader ?? (typeof document !== 'undefined' ? document.cookie : '');
  const rawVal = extractRawFilterCookieValue(source);
  if (rawVal === null || rawVal === '') {
    return { valid: true, present: false, payload: emptyPayload };
  }

  const rawBytes = new TextEncoder().encode(rawVal).length;
  if (rawBytes > MAX_COOKIE_READ_BYTES || hasControlOrLoneSurrogate(rawVal)) {
    clearIssueFilterCookie({ protocol: options?.protocol });
    return { valid: false, present: true, payload: emptyPayload };
  }

  let decoded: string;
  try {
    decoded = decodeURIComponent(rawVal);
  } catch {
    clearIssueFilterCookie({ protocol: options?.protocol });
    return { valid: false, present: true, payload: emptyPayload };
  }

  if (
    hasControlOrLoneSurrogate(decoded) ||
    decoded.includes(';') ||
    decoded.includes('"__proto__"') ||
    decoded.includes('"constructor"') ||
    decoded.includes('"prototype"')
  ) {
    clearIssueFilterCookie({ protocol: options?.protocol });
    return { valid: false, present: true, payload: emptyPayload };
  }

  let parsed: unknown;
  try {
    parsed = safeJsonParse(decoded);
  } catch {
    clearIssueFilterCookie({ protocol: options?.protocol });
    return { valid: false, present: true, payload: emptyPayload };
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    clearIssueFilterCookie({ protocol: options?.protocol });
    return { valid: false, present: true, payload: emptyPayload };
  }

  const root = parsed as Record<string, unknown>;
  if (root.v !== 1 || !root.p || typeof root.p !== 'object' || Array.isArray(root.p)) {
    clearIssueFilterCookie({ protocol: options?.protocol });
    return { valid: false, present: true, payload: emptyPayload };
  }

  const rawProjects = root.p as Record<string, unknown>;
  const entries: [string, ProjectStateFilterPreference][] = [];

  for (const [hashKey, rawEntry] of Object.entries(rawProjects)) {
    if (!PROJECT_HASH_KEY_REGEX.test(hashKey)) {
      clearIssueFilterCookie({ protocol: options?.protocol });
      return { valid: false, present: true, payload: emptyPayload };
    }
    if (!rawEntry || typeof rawEntry !== 'object' || Array.isArray(rawEntry)) {
      clearIssueFilterCookie({ protocol: options?.protocol });
      return { valid: false, present: true, payload: emptyPayload };
    }
    const entryObj = rawEntry as Record<string, unknown>;
    const hc = entryObj.hc ?? 1;
    const hx = entryObj.hx ?? 1;
    if ((hc !== 0 && hc !== 1) || (hx !== 0 && hx !== 1)) {
      clearIssueFilterCookie({ protocol: options?.protocol });
      return { valid: false, present: true, payload: emptyPayload };
    }
    const ex = validateTokenArray(entryObj.ex);
    const inc = validateTokenArray(entryObj.inc);
    if (ex === null || inc === null) {
      clearIssueFilterCookie({ protocol: options?.protocol });
      return { valid: false, present: true, payload: emptyPayload };
    }
    const rawUa = entryObj.ua ?? 0;
    if (typeof rawUa !== 'number' || !Number.isFinite(rawUa) || rawUa < 0) {
      clearIssueFilterCookie({ protocol: options?.protocol });
      return { valid: false, present: true, payload: emptyPayload };
    }

    entries.push([
      hashKey,
      {
        hc,
        hx,
        ex,
        inc,
        ua: Math.floor(rawUa),
      },
    ]);
  }

  // Enforce max 8 projects via LRU on ua
  entries.sort((a, b) => b[1].ua - a[1].ua);
  const cleanMap = Object.create(null) as Record<string, ProjectStateFilterPreference>;
  for (const [k, v] of entries.slice(0, MAX_COOKIE_PROJECTS)) {
    cleanMap[k] = v;
  }

  return {
    valid: true,
    present: true,
    payload: { v: 1, p: cleanMap },
  };
}

/**
 * Reads the persisted state filter preference for a single project from `kb_issue_state_filter`.
 * Returns `null` if no entry exists for this project or if the cookie was corrupt/cleared.
 */
export function readProjectStateFilterCookie(
  projectKey: string,
  options?: {
    workspaceScope?: string | undefined;
    cookieHeader?: string | undefined;
    protocol?: string | undefined;
  },
): ProjectStateFilterPreference | null {
  const { valid, payload } = readIssueFilterCookiePayload({
    cookieHeader: options?.cookieHeader,
    protocol: options?.protocol,
  });
  if (!valid) {
    return null;
  }
  const hashKey = computeProjectFilterKey(projectKey, options?.workspaceScope);
  return payload.p[hashKey] ?? null;
}

function sanitizeTokenListForWrite(tokens: readonly string[]): string[] {
  const clean: string[] = [];
  for (const raw of tokens) {
    const stripped = stripControlAndSurrogates(raw, true).trim();
    if (STATE_TOKEN_REGEX.test(stripped) && !clean.includes(stripped)) {
      clean.push(stripped);
      if (clean.length >= MAX_STATE_TOKENS) {
        break;
      }
    }
  }
  return clean;
}

function serializeCompactCookiePayload(
  entries: readonly [string, ProjectStateFilterPreference][],
): string {
  const p: Record<string, CompactProjectStateFilterEntry> = Object.create(null) as Record<
    string,
    CompactProjectStateFilterEntry
  >;
  for (const [hashKey, pref] of entries) {
    const item: CompactProjectStateFilterEntry = {
      hc: pref.hc ? 1 : 0,
      hx: pref.hx ? 1 : 0,
      ua: Math.floor(pref.ua),
    };
    if (pref.ex.length > 0) {
      item.ex = pref.ex;
    }
    if (pref.inc.length > 0) {
      item.inc = pref.inc;
    }
    p[hashKey] = item;
  }
  return encodeURIComponent(JSON.stringify({ v: 1, p }));
}

/**
 * Persists a project's state filter preference into `kb_issue_state_filter`,
 * enforcing max 8 LRU projects, `<= 1024` encoded byte budget, and strict cookie attributes.
 */
export function writeProjectStateFilterCookie(
  projectKey: string,
  pref: ProjectStateFilterPreference,
  options?: {
    workspaceScope?: string | undefined;
    cookieHeader?: string | undefined;
    protocol?: string | undefined;
    nowSec?: number | undefined;
  },
): { cookieDirective: string; encodedValue: string; encodedBytes: number } {
  const nowSec = options?.nowSec ?? (Number.isFinite(pref.ua) && pref.ua > 0 ? Math.floor(pref.ua) : Math.floor(Date.now() / 1000));
  const hashKey = computeProjectFilterKey(projectKey, options?.workspaceScope);

  const existing = readIssueFilterCookiePayload({
    cookieHeader: options?.cookieHeader,
    protocol: options?.protocol,
  });

  const cleanPref: ProjectStateFilterPreference = {
    hc: pref.hc ? 1 : 0,
    hx: pref.hx ? 1 : 0,
    ex: sanitizeTokenListForWrite(pref.ex),
    inc: sanitizeTokenListForWrite(pref.inc),
    ua: nowSec,
  };

  const otherEntries = Object.entries(existing.payload.p).filter(([k]) => k !== hashKey);
  otherEntries.sort((a, b) => b[1].ua - a[1].ua);

  const firstTuple: [string, ProjectStateFilterPreference] = [hashKey, cleanPref];
  const activeEntries: [string, ProjectStateFilterPreference][] = [
    firstTuple,
    ...otherEntries,
  ].slice(0, MAX_COOKIE_PROJECTS);

  let encodedValue = serializeCompactCookiePayload(activeEntries);
  let encodedBytes = new TextEncoder().encode(encodedValue).length;

  // Evict oldest LRU entries until encoded byte length <= 1024
  while (encodedBytes > MAX_COOKIE_WRITE_BYTES && activeEntries.length > 1) {
    activeEntries.pop();
    encodedValue = serializeCompactCookiePayload(activeEntries);
    encodedBytes = new TextEncoder().encode(encodedValue).length;
  }

  // Trim tokens if a single project's ex/inc arrays exceed 1024 encoded bytes
  while (
    encodedBytes > MAX_COOKIE_WRITE_BYTES &&
    (cleanPref.ex.length > 0 || cleanPref.inc.length > 0)
  ) {
    if (cleanPref.ex.length > 0) {
      cleanPref.ex.pop();
    } else {
      cleanPref.inc.pop();
    }
    encodedValue = serializeCompactCookiePayload(activeEntries);
    encodedBytes = new TextEncoder().encode(encodedValue).length;
  }

  const protocol =
    options?.protocol ??
    (typeof window !== 'undefined' ? window.location.protocol : 'http:');
  const secureAttr = protocol === 'https:' ? '; Secure' : '';
  const cookieDirective = `${ISSUE_FILTER_COOKIE_NAME}=${encodedValue}; Path=/; Max-Age=${String(ISSUE_FILTER_COOKIE_MAX_AGE)}; SameSite=Lax${secureAttr}`;

  if (typeof document !== 'undefined') {
    document.cookie = cookieDirective;
  }

  return { cookieDirective, encodedValue, encodedBytes };
}

/**
 * Validates and converts a raw `?filter_state=...` URL query parameter into a `ProjectStateFilterPreference`.
 * Returns `null` if absent, oversized (`> 512` chars), or containing invalid/hostile tokens.
 */
export function parseUrlFilterStateParam(
  rawParam: string | null | undefined,
  projectStates: readonly StateSummary[] = [],
  nowSec: number = Math.floor(Date.now() / 1000),
): ProjectStateFilterPreference | null {
  if (!rawParam || typeof rawParam !== 'string') {
    return null;
  }
  if (
    rawParam.length > MAX_URL_FILTER_STATE_LENGTH ||
    hasControlOrLoneSurrogate(rawParam) ||
    rawParam.includes(';')
  ) {
    return null;
  }

  const rawTokens = rawParam
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);

  if (rawTokens.length === 0 || rawTokens.length > MAX_STATE_TOKENS) {
    return null;
  }

  const validTokens: string[] = [];
  for (const token of rawTokens) {
    if (!STATE_TOKEN_REGEX.test(token)) {
      return null;
    }
    const lower = token.toLowerCase();
    const isKnownStandard = KNOWN_STANDARD_STATE_TOKENS.has(lower);
    const isKnownProjectState = projectStates.some(
      (s) =>
        s.id.toLowerCase() === lower ||
        normalizeStateKey(s.name) === normalizeStateKey(token) ||
        s.group.toLowerCase() === lower,
    );
    if (!isKnownStandard && !isKnownProjectState) {
      return null;
    }
    validTokens.push(token);
  }

  return buildPreferenceFromExplicitStateTokens(validTokens, projectStates, nowSec);
}

/**
 * Converts a list of selected state IDs or group tokens (from URL `?filter_state=` or `SavedView.filters`)
 * into a `ProjectStateFilterPreference`.
 */
export function buildPreferenceFromExplicitStateTokens(
  tokens: readonly string[],
  projectStates: readonly StateSummary[] = [],
  nowSec: number = Math.floor(Date.now() / 1000),
): ProjectStateFilterPreference {
  const cleanTokens = tokens
    .map((t) => stripControlAndSurrogates(t, true).trim())
    .filter((t) => STATE_TOKEN_REGEX.test(t))
    .slice(0, MAX_STATE_TOKENS);

  if (cleanTokens.length === 0) {
    return createActionableStateFilterPreference(nowSec);
  }

  const lowerSet = new Set(cleanTokens.map((t) => t.toLowerCase()));
  if (lowerSet.has('all')) {
    return createAllStatesFilterPreference(nowSec);
  }
  if (lowerSet.has('none')) {
    return createNoStatesFilterPreference(projectStates, nowSec);
  }
  if (lowerSet.size === 1 && (lowerSet.has('active') || lowerSet.has('actionable'))) {
    return createActionableStateFilterPreference(nowSec);
  }

  const effectiveStates: readonly StateSummary[] =
    projectStates.length > 0
      ? projectStates
      : [
          { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 10 },
          { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 20 },
          { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 30 },
          { id: 'state-in-review', name: 'In Review', group: 'started', sort_order: 40 },
          { id: 'state-done', name: 'Done', group: 'completed', sort_order: 50 },
          { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 60 },
        ];

  const isStateMatched = (s: StateSummary): boolean => {
    const sGroup = s.group.toLowerCase();
    if ((lowerSet.has('active') || lowerSet.has('actionable')) && sGroup !== 'completed' && sGroup !== 'cancelled') {
      return true;
    }
    if (lowerSet.has(sGroup)) {
      return true;
    }
    return cleanTokens.some((tok) => tokenMatchesState(tok, s));
  };

  const actionableStates = effectiveStates.filter((s) => {
    const g = s.group.toLowerCase();
    return g !== 'completed' && g !== 'cancelled';
  });
  const completedStates = effectiveStates.filter((s) => s.group.toLowerCase() === 'completed');
  const cancelledStates = effectiveStates.filter((s) => s.group.toLowerCase() === 'cancelled');

  const ex = actionableStates
    .filter((s) => !isStateMatched(s))
    .map((s) => s.id)
    .filter((id) => STATE_TOKEN_REGEX.test(id))
    .slice(0, MAX_STATE_TOKENS);

  const matchedCompleted = completedStates.filter(isStateMatched);
  const matchedCancelled = cancelledStates.filter(isStateMatched);

  const hc: 0 | 1 =
    lowerSet.has('completed') ||
    (completedStates.length > 0 && matchedCompleted.length === completedStates.length)
      ? 0
      : 1;
  const hx: 0 | 1 =
    lowerSet.has('cancelled') ||
    (cancelledStates.length > 0 && matchedCancelled.length === cancelledStates.length)
      ? 0
      : 1;

  const inc: string[] = [];
  if (hc === 1) {
    for (const s of matchedCompleted) {
      if (STATE_TOKEN_REGEX.test(s.id)) inc.push(s.id);
    }
  }
  if (hx === 1) {
    for (const s of matchedCancelled) {
      if (STATE_TOKEN_REGEX.test(s.id)) inc.push(s.id);
    }
  }

  return {
    hc,
    hx,
    ex,
    inc: inc.slice(0, MAX_STATE_TOKENS),
    ua: nowSec,
  };
}

/**
 * Extracts a `ProjectStateFilterPreference` from a `SavedView` if it defines `filters.state_ids` or `filters.state_groups`.
 */
export function resolveSavedViewStateFilter(
  savedView: SavedView | null | undefined,
  projectStates: readonly StateSummary[] = [],
  nowSec: number = Math.floor(Date.now() / 1000),
): ProjectStateFilterPreference | null {
  if (!savedView?.filters) {
    return null;
  }
  const stateIds = savedView.filters.state_ids ?? [];
  const stateGroups = savedView.filters.state_groups ?? [];
  const combined = [...stateIds, ...stateGroups];
  if (combined.length === 0) {
    return null;
  }
  return buildPreferenceFromExplicitStateTokens(combined, projectStates, nowSec);
}

/**
 * Resolves the initial state filter preference according to the strict precedence order:
 * 1. URL query param (`?filter_state=...`)
 * 2. Saved View (`?view=...` with `SavedView.filters`)
 * 3. Cookie (`kb_issue_state_filter`)
 * 4. Actionable Default (`hc: 1, hx: 1`)
 *
 * URL and Saved View resolutions never overwrite the user's persisted cookie.
 */
export function resolveInitialStateFilter(options: {
  projectKey: string;
  urlSearch?: string | undefined;
  savedView?: SavedView | null | undefined;
  projectStates?: readonly StateSummary[] | undefined;
  workspaceScope?: string | undefined;
  cookieHeader?: string | undefined;
  protocol?: string | undefined;
  nowSec?: number | undefined;
}): ResolvedStateFilterResult {
  const nowSec = options.nowSec ?? Math.floor(Date.now() / 1000);
  const projectStates = options.projectStates ?? [];
  const rawSearch =
    options.urlSearch ?? (typeof window !== 'undefined' ? window.location.search : '');

  try {
    const params = new URLSearchParams(rawSearch);
    const rawFilterState = params.get('filter_state');
    if (rawFilterState !== null) {
      const fromUrl = parseUrlFilterStateParam(rawFilterState, projectStates, nowSec);
      if (fromUrl) {
        return { preference: fromUrl, source: 'url' };
      }
    }
  } catch {
    // Ignore URLSearchParams errors and continue down precedence chain
  }

  const fromSavedView = resolveSavedViewStateFilter(options.savedView, projectStates, nowSec);
  if (fromSavedView) {
    return { preference: fromSavedView, source: 'saved_view' };
  }

  const fromCookie = readProjectStateFilterCookie(options.projectKey, {
    workspaceScope: options.workspaceScope,
    cookieHeader: options.cookieHeader,
    protocol: options.protocol,
  });
  if (fromCookie) {
    return { preference: fromCookie, source: 'cookie' };
  }

  return {
    preference: createActionableStateFilterPreference(nowSec),
    source: 'default',
  };
}
