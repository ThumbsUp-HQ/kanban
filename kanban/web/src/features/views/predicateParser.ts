/**
 * Predicate parser for Issue Navigator Query Mode (KAN-52, KAN-308 Problem 3).
 *
 * Security & Performance Invariants:
 * - Hard bounds: `MAX_QUERY_LENGTH = 512`, `MAX_TOKENS = 32`, `MAX_CLAUSES = 32`.
 * - Strips ASCII control characters (`[\x00-\x1F\x7F]`) and lone UTF-16 surrogates (`0xD800-0xDFFF`).
 * - Zero backtracking quote regexes (`O(n)` single-pass character scanner) so adversarial ReDoS inputs
 *   evaluate in `< 10ms`.
 * - Supports `=`, `!=`, `NOT <expr>`, negated colon tokens (`-state:completed`, `!priority:low`),
 *   `state:actionable` / `status:active`, `state:all`, and `state_group:<group>` / `group:<group>`.
 */

import {
  createActionableStateFilterPreference,
  createAllStatesFilterPreference,
  createNoStatesFilterPreference,
  stripControlAndSurrogates,
  STATE_TOKEN_REGEX,
  MAX_STATE_TOKENS,
  type ProjectStateFilterPreference,
} from './issueFilterCookie';
import { normalizeStateKey, type IssueItem, type StateSummary } from './viewsApi';

export const MAX_QUERY_LENGTH = 512;
export const MAX_TOKENS = 32;
export const MAX_CLAUSES = 32;

const STATE_FIELD_NAMES: ReadonlySet<string> = new Set([
  'state',
  'status',
  'state_group',
  'group',
]);

export interface ParsedToken {
  field?: string;
  value: string;
  negated: boolean;
}

export interface ParsedQueryStateFilter extends ProjectStateFilterPreference {
  preference: ProjectStateFilterPreference;
  remainingQuery: string;
  hasStatePredicate: boolean;
}

export function sanitizeSearchQueryInput(rawQuery: string, maxLen = MAX_QUERY_LENGTH): string {
  if (!rawQuery || typeof rawQuery !== 'string') {
    return '';
  }
  const boundedRaw = rawQuery.length > maxLen * 2 ? rawQuery.slice(0, maxLen * 2) : rawQuery;
  const stripped = stripControlAndSurrogates(boundedRaw, false);
  if (stripped.length <= maxLen) {
    return stripped;
  }
  const sliced = stripped.slice(0, maxLen);
  const nextChar = stripped.charAt(maxLen);
  if (nextChar !== ' ' && nextChar !== '\t' && nextChar !== '\n' && nextChar !== '\r') {
    const lastSpace = sliced.lastIndexOf(' ');
    if (lastSpace > 0) {
      return sliced.slice(0, lastSpace);
    }
  }
  return sliced;
}

function stripQuotes(str: string): string {
  const trimmed = str.trim();
  if (trimmed.length >= 2) {
    const first = trimmed.charAt(0);
    const last = trimmed.charAt(trimmed.length - 1);
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return trimmed.slice(1, -1);
    }
  }
  return trimmed;
}

/**
 * Linear O(n) non-backtracking splitter on top-level `AND` keywords outside quotes,
 * capped at `MAX_CLAUSES` (32).
 */
export function splitQueryClauses(query: string): string[] {
  const clauses: string[] = [];
  let inQuote: '"' | "'" | null = null;
  let clauseStart = 0;
  const len = query.length;

  const isWhitespace = (ch: string): boolean =>
    ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r';

  let i = 0;
  while (i < len) {
    const ch = query.charAt(i);
    if (inQuote) {
      if (ch === inQuote) {
        inQuote = null;
      }
      i += 1;
      continue;
    }
    if (ch === '"' || ch === "'") {
      inQuote = ch;
      i += 1;
      continue;
    }

    // Match top-level whitespace + "AND" + whitespace (case-insensitive)
    if (
      isWhitespace(ch) &&
      i + 4 < len &&
      (query.charAt(i + 1) === 'A' || query.charAt(i + 1) === 'a') &&
      (query.charAt(i + 2) === 'N' || query.charAt(i + 2) === 'n') &&
      (query.charAt(i + 3) === 'D' || query.charAt(i + 3) === 'd') &&
      isWhitespace(query.charAt(i + 4))
    ) {
      const piece = query.slice(clauseStart, i).trim();
      if (piece) {
        clauses.push(piece);
        if (clauses.length >= MAX_CLAUSES) {
          return clauses;
        }
      }
      i += 5;
      while (i < len && isWhitespace(query.charAt(i))) {
        i += 1;
      }
      clauseStart = i;
      continue;
    }
    i += 1;
  }

  if (clauses.length < MAX_CLAUSES) {
    const tail = query.slice(clauseStart).trim();
    if (tail) {
      clauses.push(tail);
    }
  }
  return clauses;
}

/**
 * Linear O(n) non-backtracking tokenizer supporting `field:value`, `-field:"quoted value"`,
 * `!field:'quoted'`, `NOT <token>`, and quoted/unquoted free-text words, capped at `MAX_TOKENS` (32).
 */
export function tokenizePredicateString(tokenString: string): ParsedToken[] {
  const tokens: ParsedToken[] = [];
  const len = tokenString.length;
  let i = 0;
  let pendingNot = false;

  const isWhitespace = (ch: string): boolean =>
    ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r';

  const isFieldChar = (ch: string): boolean => {
    const c = ch.charCodeAt(0);
    return (
      (c >= 48 && c <= 57) || // 0-9
      (c >= 65 && c <= 90) || // A-Z
      (c >= 97 && c <= 122) || // a-z
      c === 95 // _
    );
  };

  while (i < len && tokens.length < MAX_TOKENS) {
    while (i < len && isWhitespace(tokenString.charAt(i))) {
      i += 1;
    }
    if (i >= len) break;

    let negated = pendingNot;
    pendingNot = false;

    const firstChar = tokenString.charAt(i);
    if ((firstChar === '-' || firstChar === '!') && i + 1 < len && !isWhitespace(tokenString.charAt(i + 1))) {
      negated = !negated;
      i += 1;
    }

    const curr = tokenString.charAt(i);
    // Standalone quoted string
    if (curr === '"' || curr === "'") {
      const quoteChar = curr;
      i += 1;
      const start = i;
      while (i < len && tokenString.charAt(i) !== quoteChar) {
        i += 1;
      }
      const val = tokenString.slice(start, i);
      if (i < len && tokenString.charAt(i) === quoteChar) {
        i += 1;
      }
      tokens.push({ value: val, negated });
      continue;
    }

    // Scan identifier or word up to whitespace or colon
    const wordStart = i;
    while (
      i < len &&
      !isWhitespace(tokenString.charAt(i)) &&
      tokenString.charAt(i) !== ':' &&
      tokenString.charAt(i) !== '"' &&
      tokenString.charAt(i) !== "'"
    ) {
      i += 1;
    }
    const word = tokenString.slice(wordStart, i);

    // Check if this is a `field:` prefix
    if (
      word.length > 0 &&
      i < len &&
      tokenString.charAt(i) === ':' &&
      Array.from(word).every(isFieldChar)
    ) {
      i += 1; // skip ':'
      let val = '';
      if (i < len && (tokenString.charAt(i) === '"' || tokenString.charAt(i) === "'")) {
        const quoteChar = tokenString.charAt(i);
        i += 1;
        const vStart = i;
        while (i < len && tokenString.charAt(i) !== quoteChar) {
          i += 1;
        }
        val = tokenString.slice(vStart, i);
        if (i < len && tokenString.charAt(i) === quoteChar) {
          i += 1;
        }
      } else {
        const vStart = i;
        while (i < len && !isWhitespace(tokenString.charAt(i))) {
          i += 1;
        }
        val = stripQuotes(tokenString.slice(vStart, i));
      }
      tokens.push({
        field: word.toLowerCase(),
        value: val,
        negated,
      });
      continue;
    }

    // Consume remainder of non-whitespace token if any
    while (i < len && !isWhitespace(tokenString.charAt(i))) {
      i += 1;
    }
    const fullWord = stripQuotes(tokenString.slice(wordStart, i));
    if (!negated && fullWord.toUpperCase() === 'NOT') {
      pendingNot = true;
      continue;
    }
    if (fullWord.length > 0) {
      tokens.push({ value: fullWord, negated });
    }
  }

  return tokens;
}

interface ParsedComparisonClause {
  field: string;
  operator: '=' | '!=';
  value: string;
  negated: boolean;
}

function parseComparisonClause(rawClause: string): ParsedComparisonClause | null {
  let clause = rawClause.trim();
  let negated = false;
  if (/^NOT\s+/i.test(clause)) {
    negated = true;
    clause = clause.replace(/^NOT\s+/i, '').trim();
  }

  const neqIdx = clause.indexOf('!=');
  const eqIdx = clause.indexOf('=');
  if (neqIdx === -1 && eqIdx === -1) {
    return null;
  }

  let op: '=' | '!=' = '=';
  let splitIdx = eqIdx;
  if (neqIdx !== -1 && (eqIdx === -1 || neqIdx < eqIdx)) {
    op = '!=';
    splitIdx = neqIdx;
  }

  const rawField = clause.slice(0, splitIdx).trim();
  if (!rawField || !/^[a-zA-Z0-9_]+$/.test(rawField)) {
    return null;
  }
  const rawVal = stripQuotes(clause.slice(splitIdx + op.length));
  return {
    field: rawField.toLowerCase(),
    operator: op,
    value: rawVal,
    negated,
  };
}

export function matchesIssueQuery(
  rawQuery: string,
  issue: IssueItem,
  projectKey: string = issue.key.split('-')[0] ?? '',
): boolean {
  const query = sanitizeSearchQueryInput(rawQuery).trim();
  if (!query) {
    return true;
  }

  const clauses = splitQueryClauses(query);
  const hasMultipleClauses = clauses.length > 1;
  const hasComparisonOp = query.includes('=');

  if (hasMultipleClauses || hasComparisonOp) {
    return clauses.every((clause) => {
      const cmp = parseComparisonClause(clause);
      if (cmp) {
        const matched = matchesFieldValue(cmp.field, cmp.value, issue, projectKey);
        const opMatched = cmp.operator === '!=' ? !matched : matched;
        return cmp.negated ? !opMatched : opMatched;
      }
      return matchesTokens(clause, issue, projectKey);
    });
  }

  return matchesTokens(query, issue, projectKey);
}

function matchesStatePredicateValue(targetVal: string, issue: IssueItem): boolean {
  const sName = issue.state.name.toLowerCase();
  const sGroup = issue.state.group.toLowerCase();
  const sId = issue.state.id.toLowerCase();
  const sNorm = normalizeStateKey(sName);
  const targetNorm = normalizeStateKey(targetVal);

  if (targetVal === 'actionable' || targetVal === 'active') {
    return sGroup !== 'completed' && sGroup !== 'cancelled';
  }
  if (targetVal === 'all' || targetVal === '*') {
    return true;
  }
  if (targetVal === 'closed' || targetVal === 'terminal') {
    return sGroup === 'completed' || sGroup === 'cancelled';
  }

  return (
    sName === targetVal ||
    sGroup === targetVal ||
    sId === targetVal ||
    (targetVal.length > 0 && sName.includes(targetVal)) ||
    (sNorm.length > 0 && sNorm === targetNorm)
  );
}

function matchesFieldValue(
  field: string,
  val: string,
  issue: IssueItem,
  projectKey: string,
): boolean {
  const targetVal = val.toLowerCase().trim();

  switch (field) {
    case 'project': {
      const pKey = projectKey.toLowerCase();
      const issuePKey = (issue.key.split('-')[0] ?? '').toLowerCase();
      return pKey === targetVal || issuePKey === targetVal;
    }
    case 'status':
    case 'state': {
      return matchesStatePredicateValue(targetVal, issue);
    }
    case 'state_group':
    case 'group': {
      const sGroup = issue.state.group.toLowerCase();
      if (targetVal === 'actionable' || targetVal === 'active') {
        return sGroup !== 'completed' && sGroup !== 'cancelled';
      }
      if (targetVal === 'all' || targetVal === '*') {
        return true;
      }
      return sGroup === targetVal;
    }
    case 'priority': {
      const pSlug = issue.priority.slug.toLowerCase();
      const pLabel = issue.priority.label.toLowerCase();
      return pSlug === targetVal || pLabel === targetVal;
    }
    case 'assignee': {
      if (targetVal === 'unassigned') {
        return !issue.assignees || issue.assignees.length === 0;
      }
      return (issue.assignees ?? []).some((a) => {
        if (a.kind === 'principal') {
          return (
            a.principal.handle.toLowerCase() === targetVal ||
            a.principal.display_name.toLowerCase().includes(targetVal) ||
            a.principal.id === targetVal
          );
        }
        return a.free_text.toLowerCase().includes(targetVal);
      });
    }
    case 'label': {
      return (issue.labels ?? []).some(
        (l) =>
          l.name.toLowerCase() === targetVal ||
          l.id === targetVal ||
          l.name.toLowerCase().includes(targetVal),
      );
    }
    case 'cycle': {
      if (!issue.cycle_id) return targetVal === 'none' || targetVal === 'no-cycle';
      return (
        issue.cycle_id.toLowerCase() === targetVal ||
        (issue.cycle?.name ?? '').toLowerCase().includes(targetVal)
      );
    }
    case 'module': {
      const mods = issue.modules ?? [];
      const modIds = issue.module_ids ?? [];
      return (
        mods.some((m) => m.name.toLowerCase().includes(targetVal) || m.id === targetVal) ||
        modIds.some((id) => id.toLowerCase() === targetVal)
      );
    }
    case 'key': {
      return issue.key.toLowerCase() === targetVal;
    }
    default: {
      return (
        issue.summary.toLowerCase().includes(targetVal) ||
        issue.key.toLowerCase().includes(targetVal)
      );
    }
  }
}

function matchesTokens(
  tokenString: string,
  issue: IssueItem,
  projectKey: string,
): boolean {
  const tokens = tokenizePredicateString(tokenString);

  return tokens.every((token) => {
    let matched: boolean;
    if (token.field) {
      matched = matchesFieldValue(token.field, token.value, issue, projectKey);
    } else {
      const word = token.value.toLowerCase();
      const matchesSummary = issue.summary.toLowerCase().includes(word);
      const matchesKey = issue.key.toLowerCase().includes(word);
      const matchesDesc = (issue.description_markdown ?? '').toLowerCase().includes(word);
      matched = matchesSummary || matchesKey || matchesDesc;
    }
    return token.negated ? !matched : matched;
  });
}

/**
 * Returns true if the query explicitly specifies any state/status/state_group predicate
 * (e.g. `state:completed`, `-state:completed`, `status != "Done"`, `state_group:started`).
 */
export function hasExplicitStatePredicate(rawQuery: string): boolean {
  const query = sanitizeSearchQueryInput(rawQuery).trim();
  if (!query) return false;

  const clauses = splitQueryClauses(query);
  for (const clause of clauses) {
    const cmp = parseComparisonClause(clause);
    if (cmp && STATE_FIELD_NAMES.has(cmp.field)) {
      return true;
    }
    const tokens = tokenizePredicateString(clause);
    if (tokens.some((t) => Boolean(t.field && STATE_FIELD_NAMES.has(t.field)))) {
      return true;
    }
  }
  return false;
}

function formatQueryTokenValue(val: string): string {
  return /\s/.test(val) ? `"${val}"` : val;
}

/**
 * Serializes a `ProjectStateFilterPreference` into structured Query Mode tokens
 * (e.g. `-state:completed -state:cancelled` for default actionable).
 */
export function buildStateQueryTokens(
  pref: ProjectStateFilterPreference,
  projectStates: readonly StateSummary[] = [],
): string {
  if (pref.ex.includes('__all__')) {
    return '-state:all';
  }
  if (pref.hc === 0 && pref.hx === 0 && pref.ex.length === 0 && pref.inc.length === 0) {
    return '';
  }

  const tokens: string[] = [];
  if (pref.hc === 1) {
    tokens.push('-state:completed');
  }
  if (pref.hx === 1) {
    tokens.push('-state:cancelled');
  }

  for (const exId of pref.ex) {
    const matched = projectStates.find((s) => s.id === exId || normalizeStateKey(s.name) === normalizeStateKey(exId));
    const tokenVal = matched ? normalizeStateKey(matched.name) || matched.id : exId;
    tokens.push(`-state:${formatQueryTokenValue(tokenVal)}`);
  }

  for (const incId of pref.inc) {
    const matched = projectStates.find((s) => s.id === incId || normalizeStateKey(s.name) === normalizeStateKey(incId));
    const tokenVal = matched ? normalizeStateKey(matched.name) || matched.id : incId;
    tokens.push(`state:${formatQueryTokenValue(tokenVal)}`);
  }

  return tokens.join(' ');
}

/**
 * Parses state filter predicates out of a Query Mode string back into a `ProjectStateFilterPreference`
 * and a `remainingQuery` string stripped of state tokens (for Query -> Basic synchronization).
 */
export function parseStateFilterFromQuery(
  rawQuery: string,
  projectStates: readonly StateSummary[] = [],
  nowSec: number = Math.floor(Date.now() / 1000),
): ParsedQueryStateFilter {
  const query = sanitizeSearchQueryInput(rawQuery).trim();
  if (!query) {
    const actionable = createActionableStateFilterPreference(nowSec);
    return {
      ...actionable,
      preference: actionable,
      remainingQuery: '',
      hasStatePredicate: false,
    };
  }

  const acc = {
    hasStatePred: false,
    sawStateAll: false,
    sawStateNone: false,
    sawStateActionable: false,
  };
  const positiveStates: string[] = [];
  const negativeStates: string[] = [];
  const remainingParts: string[] = [];

  const recordStateCriterion = (val: string, isNegated: boolean): void => {
    acc.hasStatePred = true;
    const lower = val.toLowerCase().trim();
    if (!lower) return;
    if (lower === 'all' || lower === '*') {
      if (isNegated) {
        acc.sawStateNone = true;
      } else {
        acc.sawStateAll = true;
      }
      return;
    }
    if (lower === 'actionable' || lower === 'active') {
      if (!isNegated) {
        acc.sawStateActionable = true;
      } else {
        negativeStates.push('backlog', 'unstarted', 'started');
      }
      return;
    }
    if (isNegated) {
      negativeStates.push(lower);
    } else {
      positiveStates.push(lower);
    }
  };

  const clauses = splitQueryClauses(query);
  const isMultiClause = clauses.length > 1 || query.includes('=');

  if (isMultiClause) {
    for (const clause of clauses) {
      const cmp = parseComparisonClause(clause);
      if (cmp && STATE_FIELD_NAMES.has(cmp.field)) {
        const effectiveNeg = cmp.operator === '!=' ? !cmp.negated : cmp.negated;
        recordStateCriterion(cmp.value, effectiveNeg);
      } else if (cmp) {
        remainingParts.push(clause);
      } else {
        const subTokens = tokenizePredicateString(clause);
        for (const t of subTokens) {
          if (t.field && STATE_FIELD_NAMES.has(t.field)) {
            recordStateCriterion(t.value, t.negated);
          } else if (t.field) {
            remainingParts.push(`${t.negated ? '-' : ''}${t.field}:${formatQueryTokenValue(t.value)}`);
          } else {
            remainingParts.push(`${t.negated ? '-' : ''}${formatQueryTokenValue(t.value)}`);
          }
        }
      }
    }
  } else {
    const tokens = tokenizePredicateString(query);
    for (const t of tokens) {
      if (t.field && STATE_FIELD_NAMES.has(t.field)) {
        recordStateCriterion(t.value, t.negated);
      } else if (t.field) {
        remainingParts.push(`${t.negated ? '-' : ''}${t.field}:${formatQueryTokenValue(t.value)}`);
      } else {
        remainingParts.push(`${t.negated ? '-' : ''}${formatQueryTokenValue(t.value)}`);
      }
    }
  }

  let preference: ProjectStateFilterPreference;

  if (!acc.hasStatePred) {
    preference = createActionableStateFilterPreference(nowSec);
  } else if (acc.sawStateNone) {
    preference = createNoStatesFilterPreference(projectStates, nowSec);
  } else if (acc.sawStateAll && positiveStates.length === 0 && negativeStates.length === 0) {
    preference = createAllStatesFilterPreference(nowSec);
  } else if (acc.sawStateActionable && positiveStates.length === 0 && negativeStates.length === 0) {
    preference = createActionableStateFilterPreference(nowSec);
  } else {
    let hc: 0 | 1 = 0;
    let hx: 0 | 1 = 0;
    const ex: string[] = [];
    const inc: string[] = [];

    for (const neg of negativeStates) {
      const norm = normalizeStateKey(neg);
      if (neg === 'completed' || norm === 'done' || norm === 'statedone') {
        hc = 1;
      } else if (neg === 'cancelled' || norm === 'cancelled' || norm === 'statecancelled') {
        hx = 1;
      } else {
        const matched = projectStates.find(
          (s) => s.id.toLowerCase() === neg || normalizeStateKey(s.name) === norm,
        );
        const token = matched ? matched.id : neg;
        if (STATE_TOKEN_REGEX.test(token) && !ex.includes(token)) {
          ex.push(token);
        }
      }
    }

    if (positiveStates.length > 0 && negativeStates.length === 0) {
      // Positive state query such as `state:completed` or `state:todo`
      const posNorms = positiveStates.map((p) => normalizeStateKey(p));
      const wantsCompleted =
        positiveStates.includes('completed') ||
        posNorms.includes('done') ||
        posNorms.includes('statedone');
      const wantsCancelled =
        positiveStates.includes('cancelled') ||
        posNorms.includes('cancelled') ||
        posNorms.includes('statecancelled');

      hc = wantsCompleted ? 0 : 1;
      hx = wantsCancelled ? 0 : 1;

      if (projectStates.length > 0) {
        for (const st of projectStates) {
          const stGroup = st.group.toLowerCase();
          const stNorm = normalizeStateKey(st.name);
          const isMatched =
            positiveStates.includes(st.id.toLowerCase()) ||
            positiveStates.includes(stGroup) ||
            posNorms.includes(stNorm);

          if (stGroup === 'completed' || stGroup === 'cancelled') {
            if (isMatched && STATE_TOKEN_REGEX.test(st.id) && !inc.includes(st.id)) {
              inc.push(st.id);
            }
          } else if (!isMatched && STATE_TOKEN_REGEX.test(st.id) && !ex.includes(st.id)) {
            ex.push(st.id);
          }
        }
      } else {
        for (const pos of positiveStates) {
          if (STATE_TOKEN_REGEX.test(pos) && !inc.includes(pos)) {
            inc.push(pos);
          }
        }
      }
    } else {
      for (const pos of positiveStates) {
        const norm = normalizeStateKey(pos);
        const matched = projectStates.find(
          (s) => s.id.toLowerCase() === pos || normalizeStateKey(s.name) === norm,
        );
        const token = matched ? matched.id : pos;
        if (STATE_TOKEN_REGEX.test(token) && !inc.includes(token)) {
          inc.push(token);
        }
      }
    }

    preference = {
      hc,
      hx,
      ex: ex.slice(0, MAX_STATE_TOKENS),
      inc: inc.slice(0, MAX_STATE_TOKENS),
      ua: nowSec,
    };
  }

  return {
    ...preference,
    preference,
    remainingQuery: remainingParts.join(' '),
    hasStatePredicate: acc.hasStatePred,
  };
}
