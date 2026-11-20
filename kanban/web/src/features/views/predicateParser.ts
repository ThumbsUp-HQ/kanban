/**
 * Predicate parser for Issue Navigator Query Mode (KAN-52).
 * Supports structured SQL/JQL predicates (e.g. project = "KAN" AND status = "Todo")
 * and token predicates (e.g. state:started priority:high "mars").
 */

import type { IssueItem } from './viewsApi';

function stripQuotes(str: string): string {
  const trimmed = str.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

export function matchesIssueQuery(
  rawQuery: string,
  issue: IssueItem,
  projectKey: string = issue.key.split('-')[0] ?? '',
): boolean {
  const query = rawQuery.trim();
  if (!query) {
    return true;
  }

  // Check if query uses JQL / SQL style "AND" clauses or "=" operators
  if (/\s+AND\s+/i.test(query) || query.includes('=')) {
    const clauses = query.split(/\s+AND\s+/i);
    return clauses.every((clause) => {
      const trimmedClause = clause.trim();
      if (!trimmedClause) return true;

      const equalMatch = /^([a-zA-Z0-9_]+)\s*=\s*(.+)$/.exec(trimmedClause);
      if (equalMatch) {
        const field = equalMatch[1]?.toLowerCase();
        const rawVal = stripQuotes(equalMatch[2] ?? '');
        return matchesFieldValue(field, rawVal, issue, projectKey);
      }

      // Fallback: tokenize clause
      return matchesTokens(trimmedClause, issue, projectKey);
    });
  }

  // Token-based predicate mode: e.g. state:started priority:high "mars"
  return matchesTokens(query, issue, projectKey);
}

function matchesFieldValue(
  field: string | undefined,
  val: string,
  issue: IssueItem,
  projectKey: string,
): boolean {
  if (!field) return true;
  const targetVal = val.toLowerCase().trim();

  switch (field) {
    case 'project': {
      const pKey = projectKey.toLowerCase();
      const issuePKey = issue.key.split('-')[0]?.toLowerCase() ?? '';
      return pKey === targetVal || issuePKey === targetVal;
    }
    case 'status':
    case 'state': {
      const sName = issue.state.name.toLowerCase();
      const sGroup = issue.state.group.toLowerCase();
      const sId = issue.state.id.toLowerCase();
      return (
        sName === targetVal ||
        sGroup === targetVal ||
        sId === targetVal ||
        sName.includes(targetVal)
      );
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
      // General field check
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
  // Regex to match key:value, quoted strings "...", or regular words
  const regex = /([a-zA-Z0-9_]+):(".*?"|'.*?'|[^\s]+)|"([^"]+)"|'([^']+)'|([^\s]+)/g;
  let match: RegExpExecArray | null;
  const tokens: { field?: string; value: string }[] = [];

  while ((match = regex.exec(tokenString)) !== null) {
    if (match[1] && match[2]) {
      tokens.push({
        field: match[1].toLowerCase(),
        value: stripQuotes(match[2]),
      });
    } else if (match[3]) {
      tokens.push({ value: match[3] });
    } else if (match[4]) {
      tokens.push({ value: match[4] });
    } else if (match[5]) {
      tokens.push({ value: match[5] });
    }
  }

  if (tokens.length === 0) return true;

  return tokens.every((token) => {
    if (token.field) {
      return matchesFieldValue(token.field, token.value, issue, projectKey);
    }
    const word = token.value.toLowerCase();
    const matchesSummary = issue.summary.toLowerCase().includes(word);
    const matchesKey = issue.key.toLowerCase().includes(word);
    const matchesDesc = (issue.description_markdown ?? '').toLowerCase().includes(word);
    return matchesSummary || matchesKey || matchesDesc;
  });
}
