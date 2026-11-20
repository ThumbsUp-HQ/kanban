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
  });
});
