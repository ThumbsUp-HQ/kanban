import { describe, it, expect } from 'vitest';
import {
  MAX_CLAUSES,
  MAX_QUERY_LENGTH,
  MAX_TOKENS,
  buildStateQueryTokens,
  hasExplicitStatePredicate,
  matchesIssueQuery,
  parseStateFilterFromQuery,
  sanitizeSearchQueryInput,
} from './predicateParser';
import {
  createActionableStateFilterPreference,
  createAllStatesFilterPreference,
  createNoStatesFilterPreference,
  isIssueStateVisible,
} from './issueFilterCookie';
import type { IssueItem, StateSummary } from './viewsApi';

describe('predicateParser (KAN-52 & KAN-308 Problem 3)', () => {
  const mockIssue: IssueItem = {
    id: '11111111-1111-1111-1111-111111111111',
    key: 'KAN-101',
    summary: 'Fix mars rover antenna connection',
    description_markdown: 'Detailed report on mars rover communication loss.',
    state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
    priority: { slug: 'high', label: 'High' },
    cycle_id: 'cycle-1',
    cycle: { id: 'cycle-1', name: 'Sprint 1' },
    module_ids: ['mod-1'],
    modules: [{ id: 'mod-1', name: 'Rover Telemetry' }],
    labels: [{ id: 'lbl-1', name: 'hardware', color_hex: '#ff0000' }],
    assignees: [
      {
        id: 'asg-1',
        kind: 'principal',
        principal: {
          id: 'u-1',
          handle: 'alice',
          display_name: 'Alice Smith',
          type: 'USER',
        },
      },
    ],
  };

  const doneIssue: IssueItem = {
    ...mockIssue,
    id: '22222222-2222-2222-2222-222222222222',
    key: 'KAN-102',
    state: { id: 'state-done', name: 'Done', group: 'completed' },
  };

  const cancelledIssue: IssueItem = {
    ...mockIssue,
    id: '33333333-3333-3333-3333-333333333333',
    key: 'KAN-103',
    state: { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled' },
  };

  const projectStates: StateSummary[] = [
    { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 10 },
    { id: 'state-todo', name: 'Todo', group: 'unstarted', sort_order: 20 },
    { id: 'state-prog', name: 'In Progress', group: 'started', sort_order: 30 },
    { id: 'state-done', name: 'Done', group: 'completed', sort_order: 40 },
    { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', sort_order: 50 },
  ];

  it('matches empty query to true', () => {
    expect(matchesIssueQuery('', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('   ', mockIssue, 'KAN')).toBe(true);
    expect(sanitizeSearchQueryInput('')).toBe('');
  });

  it('matches structured SQL/JQL queries with AND, =, !=, and NOT operators', () => {
    expect(
      matchesIssueQuery('project = "KAN" AND status = "Todo"', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('status != "Done" AND status != "Cancelled"', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('status != "Done" AND status != "Cancelled"', doneIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('status != "Done" AND status != "Cancelled"', cancelledIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('NOT status = "Done"', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('NOT status = "Done"', doneIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('project = "KAN" AND priority = "high"', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('assignee = "alice" AND label = "hardware"', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('cycle = "Sprint 1" AND module = "Rover Telemetry"', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('key = "KAN-101"', mockIssue, 'KAN'),
    ).toBe(true);

    // Negative matches
    expect(
      matchesIssueQuery('project = "OTHER" AND status = "Todo"', mockIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('status = "Done"', mockIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('priority = "low"', mockIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('assignee = "bob"', mockIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('label = "software"', mockIssue, 'KAN'),
    ).toBe(false);
  });

  it('matches negated colon tokens (-state:completed, !priority:low, NOT), state:actionable, state:all, and state_group', () => {
    expect(
      matchesIssueQuery('-state:completed -state:cancelled "mars"', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('-state:completed -state:cancelled "mars"', doneIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('!priority:low state:actionable', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('state:actionable', doneIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('status:active', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('state:all', doneIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('state:closed', doneIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('state_group:unstarted', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('group:actionable', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('group:all', doneIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('NOT state:completed', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('NOT state:completed', doneIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('NOT "jupiter"', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('state:"To Do" priority:\'high\'', mockIssue, 'KAN'),
    ).toBe(true);
  });

  it('evaluates adversarial ReDoS and oversized inputs in < 10ms under MAX_QUERY_LENGTH/MAX_TOKENS/MAX_CLAUSES caps', () => {
    expect(MAX_QUERY_LENGTH).toBe(512);
    expect(MAX_TOKENS).toBe(32);
    expect(MAX_CLAUSES).toBe(32);

    const redosQuotes = 'a:"'.repeat(2000);
    const redosClauses = Array.from({ length: 200 }, () => 'status != "Completed"').join(' AND ');
    const redosTokens = Array.from({ length: 200 }, () => '-state:completed').join(' ');

    // Warm up JIT before timing individual adversarial inputs
    matchesIssueQuery('status:todo', mockIssue, 'KAN');

    const t1 = performance.now();
    const r1 = matchesIssueQuery(redosQuotes, mockIssue, 'KAN');
    const elapsed1 = performance.now() - t1;

    const t2 = performance.now();
    const r2 = matchesIssueQuery(redosClauses, mockIssue, 'KAN');
    const elapsed2 = performance.now() - t2;

    const t3 = performance.now();
    const r3 = matchesIssueQuery(redosTokens, mockIssue, 'KAN');
    const elapsed3 = performance.now() - t3;

    expect(typeof r1).toBe('boolean');
    expect(r2).toBe(true);
    expect(r3).toBe(true);
    expect(elapsed1).toBeLessThan(10);
    expect(elapsed2).toBeLessThan(10);
    expect(elapsed3).toBeLessThan(10);
  });

  it('supports hasExplicitStatePredicate, buildStateQueryTokens, and parseStateFilterFromQuery round-trips', () => {
    expect(hasExplicitStatePredicate('')).toBe(false);
    expect(hasExplicitStatePredicate('priority:high "mars"')).toBe(false);
    expect(hasExplicitStatePredicate('project = "KAN" AND priority = "high"')).toBe(false);
    expect(hasExplicitStatePredicate('state:completed')).toBe(true);
    expect(hasExplicitStatePredicate('-state:completed -state:cancelled')).toBe(true);
    expect(hasExplicitStatePredicate('status != "Done"')).toBe(true);
    expect(hasExplicitStatePredicate('state_group:started')).toBe(true);

    // buildStateQueryTokens
    const actionablePref = createActionableStateFilterPreference();
    expect(buildStateQueryTokens(actionablePref, projectStates)).toBe(
      '-state:completed -state:cancelled',
    );
    expect(buildStateQueryTokens(createAllStatesFilterPreference(), projectStates)).toBe('');
    expect(buildStateQueryTokens(createNoStatesFilterPreference(projectStates), projectStates)).toBe(
      '-state:all',
    );
    expect(
      buildStateQueryTokens(
        { hc: 1, hx: 1, ex: ['state-prog'], inc: ['state-done'], ua: 10 },
        projectStates,
      ),
    ).toBe('-state:completed -state:cancelled -state:inprogress state:done');

    // parseStateFilterFromQuery round-trips
    const parsedActionable = parseStateFilterFromQuery(
      '-state:completed -state:cancelled priority:high "mars"',
      projectStates,
    );
    expect(parsedActionable.hasStatePredicate).toBe(true);
    expect(parsedActionable.hc).toBe(1);
    expect(parsedActionable.hx).toBe(1);
    expect(parsedActionable.remainingQuery).toBe('priority:high mars');

    const parsedSql = parseStateFilterFromQuery(
      'status != "Done" AND status != "Cancelled" AND priority = "High" AND -state:backlog priority:high mars',
      projectStates,
    );
    expect(parsedSql.hasStatePredicate).toBe(true);
    expect(parsedSql.hc).toBe(1);
    expect(parsedSql.hx).toBe(1);
    expect(parsedSql.ex).toContain('state-backlog');
    expect(parsedSql.remainingQuery).toContain('priority = "High"');
    expect(matchesIssueQuery('invalid-field = "Todo" AND antenna', mockIssue, 'KAN')).toBe(false);
    expect(
      buildStateQueryTokens(
        { hc: 0, hx: 0, ex: ['custom_unknown_ex'], inc: ['custom_unknown_inc'], ua: 1 },
        projectStates,
      ),
    ).toBe('-state:custom_unknown_ex state:custom_unknown_inc');

    const parsedAll = parseStateFilterFromQuery('state:all', projectStates);
    expect(parsedAll.hc).toBe(0);
    expect(parsedAll.hx).toBe(0);

    const parsedNone = parseStateFilterFromQuery('-state:all', projectStates);
    expect(parsedNone.ex).toContain('__all__');

    const parsedActive = parseStateFilterFromQuery('state:actionable', projectStates);
    expect(parsedActive.hc).toBe(1);
    expect(parsedActive.hx).toBe(1);

    const parsedNotActive = parseStateFilterFromQuery('-state:actionable', projectStates);
    expect(parsedNotActive.hasStatePredicate).toBe(true);

    const parsedPositiveCompleted = parseStateFilterFromQuery('state:completed', projectStates);
    expect(isIssueStateVisible(doneIssue.state, parsedPositiveCompleted)).toBe(true);
    expect(isIssueStateVisible(mockIssue.state, parsedPositiveCompleted)).toBe(false);

    const parsedPositiveNoStates = parseStateFilterFromQuery('state:done', []);
    expect(parsedPositiveNoStates.inc).toContain('done');

    const parsedMixed = parseStateFilterFromQuery(
      '-state:completed -state:backlog state:done',
      projectStates,
    );
    expect(parsedMixed.hc).toBe(1);
    expect(parsedMixed.ex).toContain('state-backlog');
    expect(parsedMixed.inc).toContain('state-done');

    const parsedEmpty = parseStateFilterFromQuery('');
    expect(parsedEmpty.hasStatePredicate).toBe(false);
    expect(parsedEmpty.hc).toBe(1);

    const parsedNoState = parseStateFilterFromQuery('priority:high mars', projectStates);
    expect(parsedNoState.hasStatePredicate).toBe(false);
    expect(parsedNoState.remainingQuery).toBe('priority:high mars');
  });

  it('handles edge cases for unassigned, no-cycle, and free text assignee', () => {
    const unassignedIssue: IssueItem = {
      ...mockIssue,
      assignees: [],
      cycle_id: null,
      cycle: null,
    };
    expect(matchesIssueQuery('assignee:unassigned', unassignedIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('assignee = "unassigned"', unassignedIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('cycle = "none"', unassignedIssue, 'KAN')).toBe(true);

    const freeTextIssue: IssueItem = {
      ...mockIssue,
      assignees: [
        {
          id: 'asg-2',
          kind: 'free_text',
          free_text: 'contractor@example.com',
          notify: false,
          hint: 'External',
        },
      ],
    };
    expect(matchesIssueQuery('assignee:contractor', freeTextIssue, 'KAN')).toBe(true);

    const modIdIssue: IssueItem = {
      ...mockIssue,
      modules: [],
      module_ids: ['mod-raw-only'],
    };
    expect(matchesIssueQuery('module = "mod-raw-only"', modIdIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('customfield = "antenna"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('status = "Todo" AND antenna', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery("'antenna'", mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('project = "KAN"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('project = "OTHER"', mockIssue, 'KAN')).toBe(false);
    expect(matchesIssueQuery('key = "KAN-101"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('key = "KAN-999"', mockIssue, 'KAN')).toBe(false);
    expect(matchesIssueQuery('priority = "High"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('priority = "high"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('priority = "low"', mockIssue, 'KAN')).toBe(false);
    expect(matchesIssueQuery('assignee = "Alice Smith"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('assignee = "u-1"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('assignee = "nonexistent-user"', mockIssue, 'KAN')).toBe(false);
    expect(matchesIssueQuery('label = "hardware"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('label = "hard"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('label = "lbl-1"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('label = "nonexistent"', mockIssue, 'KAN')).toBe(false);
    expect(matchesIssueQuery('cycle = "cycle-1"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('cycle = "Sprint 1"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('cycle = "cycle-unknown"', mockIssue, 'KAN')).toBe(false);

    const descOnlyIssue: IssueItem = {
      ...mockIssue,
      summary: 'Short title',
      description_markdown: 'Deep space calibration telemetry',
    };
    expect(matchesIssueQuery('telemetry', descOnlyIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('nonexistent_word', descOnlyIssue, 'KAN')).toBe(false);
    expect(matchesIssueQuery('priority = "High"', mockIssue)).toBe(true);
    expect(matchesIssueQuery("status = 'Todo'", mockIssue)).toBe(true);
    expect(matchesIssueQuery('status = Todo', mockIssue)).toBe(true);
    expect(matchesIssueQuery('state = "unstarted"', mockIssue)).toBe(true);
    expect(matchesIssueQuery('state = "state-todo"', mockIssue)).toBe(true);
    expect(matchesIssueQuery('state = "od"', mockIssue)).toBe(true);

    const noCycleIssue: IssueItem = { ...mockIssue, cycle_id: null, cycle: null };
    expect(matchesIssueQuery('cycle = "Sprint 1"', noCycleIssue)).toBe(false);

    const cycleIdOnlyIssue: IssueItem = { ...mockIssue, cycle_id: 'cycle-99', cycle: null };
    expect(matchesIssueQuery('cycle = "cycle-99"', cycleIdOnlyIssue)).toBe(true);
    expect(matchesIssueQuery('cycle = "Sprint 99"', cycleIdOnlyIssue)).toBe(false);

    expect(matchesIssueQuery('module = "mod-1"', mockIssue)).toBe(true);

    const noModulesIssue = { ...mockIssue };
    delete (noModulesIssue as unknown as Record<string, unknown>).modules;
    delete (noModulesIssue as unknown as Record<string, unknown>).module_ids;
    expect(matchesIssueQuery('module = "Rover"', noModulesIssue)).toBe(false);

    expect(matchesIssueQuery('custom = "101"', mockIssue)).toBe(true);
    expect(matchesIssueQuery('custom = "nomatch"', mockIssue)).toBe(false);

    const noDescIssue = { ...mockIssue };
    delete (noDescIssue as unknown as Record<string, unknown>).description_markdown;
    expect(matchesIssueQuery('antenna', noDescIssue)).toBe(true);
    expect(matchesIssueQuery('telemetry', noDescIssue)).toBe(false);

    expect(matchesIssueQuery('project = "KAN"', mockIssue, 'DIFFERENT')).toBe(true);

    const noAsgOrLabelsIssue = { ...mockIssue };
    delete (noAsgOrLabelsIssue as unknown as Record<string, unknown>).assignees;
    delete (noAsgOrLabelsIssue as unknown as Record<string, unknown>).labels;
    expect(matchesIssueQuery('assignee = "alice"', noAsgOrLabelsIssue)).toBe(false);
    expect(matchesIssueQuery('label = "hardware"', noAsgOrLabelsIssue)).toBe(false);
  });
});
