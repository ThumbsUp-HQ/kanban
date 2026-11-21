import { describe, it, expect } from 'vitest';
import { matchesIssueQuery } from './predicateParser';
import type { IssueItem } from './viewsApi';

describe('predicateParser (KAN-52)', () => {
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

  it('matches empty query to true', () => {
    expect(matchesIssueQuery('', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('   ', mockIssue, 'KAN')).toBe(true);
  });

  it('matches structured SQL/JQL queries with AND and equal operators', () => {
    expect(
      matchesIssueQuery('project = "KAN" AND status = "Todo"', mockIssue, 'KAN'),
    ).toBe(true);
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

  it('matches token-based queries like state:started priority:high "mars"', () => {
    expect(
      matchesIssueQuery('priority:high "mars"', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('status:todo priority:high', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('state:unstarted antenna', mockIssue, 'KAN'),
    ).toBe(true);
    expect(
      matchesIssueQuery('assignee:alice mars', mockIssue, 'KAN'),
    ).toBe(true);

    // Negative matches
    expect(
      matchesIssueQuery('priority:urgent "mars"', mockIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('state:completed mars', mockIssue, 'KAN'),
    ).toBe(false);
    expect(
      matchesIssueQuery('jupiter', mockIssue, 'KAN'),
    ).toBe(false);
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

    // Module matching by ID via module_ids when modules array has no match
    const modIdIssue: IssueItem = {
      ...mockIssue,
      modules: [],
      module_ids: ['mod-raw-only'],
    };
    expect(matchesIssueQuery('module = "mod-raw-only"', modIdIssue, 'KAN')).toBe(true);

    // Default general field check
    expect(matchesIssueQuery('customfield = "antenna"', mockIssue, 'KAN')).toBe(true);

    // Structured query fallback to tokens (no equal sign in one clause)
    expect(matchesIssueQuery('status = "Todo" AND antenna', mockIssue, 'KAN')).toBe(true);

    // Single quoted string tokens
    expect(matchesIssueQuery("'antenna'", mockIssue, 'KAN')).toBe(true);

    // Empty or whitespace query returns true
    expect(matchesIssueQuery('', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('   ', mockIssue, 'KAN')).toBe(true);

    // Project field match and mismatch
    expect(matchesIssueQuery('project = "KAN"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('project = "OTHER"', mockIssue, 'KAN')).toBe(false);

    // Key field match and mismatch
    expect(matchesIssueQuery('key = "KAN-101"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('key = "KAN-999"', mockIssue, 'KAN')).toBe(false);

    // Priority label match and slug match
    expect(matchesIssueQuery('priority = "High"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('priority = "high"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('priority = "low"', mockIssue, 'KAN')).toBe(false);

    // Assignee display name and principal ID
    expect(matchesIssueQuery('assignee = "Alice Smith"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('assignee = "u-1"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('assignee = "nonexistent-user"', mockIssue, 'KAN')).toBe(false);

    // Labels by name, ID, and substring
    expect(matchesIssueQuery('label = "hardware"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('label = "hard"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('label = "lbl-1"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('label = "nonexistent"', mockIssue, 'KAN')).toBe(false);

    // Cycle by ID, cycle name, and mismatch
    expect(matchesIssueQuery('cycle = "cycle-1"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('cycle = "Sprint 1"', mockIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('cycle = "cycle-unknown"', mockIssue, 'KAN')).toBe(false);

    // Description markdown search when word is only in description
    const descOnlyIssue: IssueItem = {
      ...mockIssue,
      summary: 'Short title',
      description_markdown: 'Deep space calibration telemetry',
    };
    expect(matchesIssueQuery('telemetry', descOnlyIssue, 'KAN')).toBe(true);
    expect(matchesIssueQuery('nonexistent_word', descOnlyIssue, 'KAN')).toBe(false);

    // Call matchesIssueQuery without projectKey (tests default parameter on line 23)
    expect(matchesIssueQuery('priority = "High"', mockIssue)).toBe(true);

    // Single-quoted and unquoted values in equal queries
    expect(matchesIssueQuery("status = 'Todo'", mockIssue)).toBe(true);
    expect(matchesIssueQuery('status = Todo', mockIssue)).toBe(true);

    // State group, ID, and substring matches
    expect(matchesIssueQuery('state = "unstarted"', mockIssue)).toBe(true);
    expect(matchesIssueQuery('state = "state-todo"', mockIssue)).toBe(true);
    expect(matchesIssueQuery('state = "od"', mockIssue)).toBe(true);

    // Cycle when cycle_id is null and target is not none
    const noCycleIssue: IssueItem = { ...mockIssue, cycle_id: null, cycle: null };
    expect(matchesIssueQuery('cycle = "Sprint 1"', noCycleIssue)).toBe(false);

    // Cycle when cycle_id is present but cycle object is null
    const cycleIdOnlyIssue: IssueItem = { ...mockIssue, cycle_id: 'cycle-99', cycle: null };
    expect(matchesIssueQuery('cycle = "cycle-99"', cycleIdOnlyIssue)).toBe(true);
    expect(matchesIssueQuery('cycle = "Sprint 99"', cycleIdOnlyIssue)).toBe(false);

    // Module matching by ID in modules array
    expect(matchesIssueQuery('module = "mod-1"', mockIssue)).toBe(true);

    // Module matching when modules and module_ids are undefined
    const noModulesIssue = { ...mockIssue };
    delete (noModulesIssue as unknown as Record<string, unknown>).modules;
    delete (noModulesIssue as unknown as Record<string, unknown>).module_ids;
    expect(matchesIssueQuery('module = "Rover"', noModulesIssue)).toBe(false);

    // Default field matching key or failing
    expect(matchesIssueQuery('custom = "101"', mockIssue)).toBe(true);
    expect(matchesIssueQuery('custom = "nomatch"', mockIssue)).toBe(false);

    // Description markdown nullish coalescing
    const noDescIssue = { ...mockIssue };
    delete (noDescIssue as unknown as Record<string, unknown>).description_markdown;
    expect(matchesIssueQuery('antenna', noDescIssue)).toBe(true);
    expect(matchesIssueQuery('telemetry', noDescIssue)).toBe(false);

    // Project match via issuePKey when projectKey argument differs
    expect(matchesIssueQuery('project = "KAN"', mockIssue, 'DIFFERENT')).toBe(true);

    // Assignee and label matching when assignees or labels are undefined
    const noAsgOrLabelsIssue = { ...mockIssue };
    delete (noAsgOrLabelsIssue as unknown as Record<string, unknown>).assignees;
    delete (noAsgOrLabelsIssue as unknown as Record<string, unknown>).labels;
    expect(matchesIssueQuery('assignee = "alice"', noAsgOrLabelsIssue)).toBe(false);
    expect(matchesIssueQuery('label = "hardware"', noAsgOrLabelsIssue)).toBe(false);
  });
});
