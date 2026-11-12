import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { SwimlaneBoardGrid } from './SwimlaneBoardGrid';
import { FIXTURE_12_ISSUES } from './fixtures';
import type { IssueItem } from './viewsApi';

describe('SwimlaneBoardGrid (KB-P3-40, S6.4 item 2)', () => {
  it('partitions board into 2D grid with Priority swimlanes across State columns (Test Case 1)', () => {
    const handleToggleSelect = vi.fn();

    render(
      <SwimlaneBoardGrid
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="priority"
        modulesEnabled={true}
        selectedIds={['KAN-142']}
        onToggleSelect={handleToggleSelect}
      />
    );

    // Verify 324px state column headers
    expect(screen.getByRole('columnheader', { name: /Backlog/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /Todo/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /In Progress/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /Done/i })).toBeDefined();

    // Verify horizontal Priority swimlane bands: Urgent, High, Medium, Low, None
    expect(screen.getByText(/Urgent 🔥/i)).toBeDefined();
    expect(screen.getByText(/High ⚡/i)).toBeDefined();
    expect(screen.getByText(/Medium 🔹/i)).toBeDefined();
    expect(screen.getByText(/Low 💤/i)).toBeDefined();
    expect(screen.getByText(/^None$/i)).toBeDefined();

    // Verify KAN-142 is placed in Urgent swimlane band
    const urgentBand = document.querySelector('[data-subgroup-id="urgent"]');
    expect(urgentBand).not.toBeNull();
    const kan142Card = urgentBand?.querySelector('[data-issue-key="KAN-142"]');
    expect(kan142Card).not.toBeNull();
    expect(kan142Card?.classList.contains('swimlane-card--selected')).toBe(true);

    // Toggle checkbox on card
    const checkbox = kan142Card?.querySelector('input[type="checkbox"]');
    if (checkbox) {
      fireEvent.click(checkbox);
      expect(handleToggleSelect).toHaveBeenCalledWith('KAN-142', false);
    }
  });

  it('collapses and expands a swimlane band when toggle is clicked', () => {
    render(
      <SwimlaneBoardGrid
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="priority"
        modulesEnabled={true}
      />
    );

    const urgentToggle = screen.getByRole('button', { name: /Urgent 🔥/i });
    expect(urgentToggle.getAttribute('aria-expanded')).toBe('true');

    // Click to collapse
    fireEvent.click(urgentToggle);
    expect(urgentToggle.getAttribute('aria-expanded')).toBe('false');
    expect(document.getElementById('swimlane-content-urgent')).toBeNull();

    // Click to expand again
    fireEvent.click(urgentToggle);
    expect(urgentToggle.getAttribute('aria-expanded')).toBe('true');
    expect(document.getElementById('swimlane-content-urgent')).not.toBeNull();
  });

  it('renders assignee swimlanes when subGroupBy is assignee', () => {
    render(
      <SwimlaneBoardGrid
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="assignee"
        modulesEnabled={true}
      />
    );

    expect(screen.getByText(/Alice Cooper/i)).toBeDefined();
    expect(screen.getByText(/Unassigned/i)).toBeDefined();
  });

  it('renders cycle and module swimlanes when subGroupBy is cycle or module', () => {
    // Cycle swimlanes
    const { rerender } = render(
      <SwimlaneBoardGrid
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="cycle"
        modulesEnabled={true}
      />
    );
    expect(screen.getByText(/Cycle 1/i)).toBeDefined();
    expect(screen.getByText(/No Cycle/i)).toBeDefined();

    // Module swimlanes
    rerender(
      <SwimlaneBoardGrid
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="module"
        modulesEnabled={true}
      />
    );
    expect(screen.getByText(/Auth Core/i)).toBeDefined();
    expect(screen.getByText(/No Module/i)).toBeDefined();
  });

  it('renders Priority column headers when groupBy is priority', () => {
    render(
      <SwimlaneBoardGrid
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        groupBy="priority"
        subGroupBy="assignee"
        modulesEnabled={true}
      />
    );

    expect(screen.getByRole('columnheader', { name: /^Urgent$/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /^High$/i })).toBeDefined();
  });

  it('handles card click and fallback mapping for unmapped issues', () => {
    const base = FIXTURE_12_ISSUES[0];
    if (!base) throw new Error('missing fixture');
    const unmappedIssue: IssueItem = {
      ...base,
      key: 'KAN-999',
      state: { id: 'custom-state', name: 'Custom State', group: 'unknown' },
      priority: { slug: 'custom', label: 'Custom' },
    };

    render(
      <SwimlaneBoardGrid
        issues={[unmappedIssue]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="priority"
        modulesEnabled={true}
      />
    );

    const card = screen.getByText(unmappedIssue.summary);
    expect(card).toBeDefined();

    // Click card body
    fireEvent.click(card);
  });

  it('renders fallback single swimlane when subGroupBy is none', () => {
    render(
      <SwimlaneBoardGrid
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="none"
        modulesEnabled={true}
      />
    );

    expect(screen.getByText('All Work Items')).toBeDefined();
  });

  it('handles adam assignee swimlane, card key link click, and card checkbox toggle', () => {
    const handleToggle = vi.fn();
    const baseAdam = FIXTURE_12_ISSUES[0];
    if (!baseAdam) throw new Error('missing fixture');
    const adamIssue: IssueItem = {
      ...baseAdam,
      key: 'KAN-199',
      assignees: [
        {
          id: 'asg-adam',
          kind: 'principal' as const,
          principal: { id: 'u-adam', handle: 'adam', display_name: 'Adam Outler', type: 'USER' },
        },
      ],
      gate_status: 'vetoed' as const,
    };

    render(
      <SwimlaneBoardGrid
        issues={[adamIssue]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="assignee"
        modulesEnabled={true}
        selectedIds={['KAN-199']}
        onToggleSelect={handleToggle}
      />
    );

    expect(screen.getByText(/Adam Outler/i)).toBeDefined();

    // Checkbox toggle
    const checkbox = screen.getByLabelText('Select KAN-199');
    fireEvent.click(checkbox);
    expect(handleToggle).toHaveBeenCalledWith('KAN-199', false);

    // Card key link
    const keyLink = screen.getByText('KAN-199');
    fireEvent.click(keyLink);
  });

  it('renders card with low priority, approved gate status, and focused state', () => {
    const baseLow = FIXTURE_12_ISSUES[0];
    if (!baseLow) throw new Error('missing fixture');
    const lowApprovedIssue: IssueItem = {
      ...baseLow,
      key: 'KAN-200',
      priority: { slug: 'low', label: 'Low', emoji: '💤' },
      gate_status: 'approved' as const,
    };

    render(
      <SwimlaneBoardGrid
        issues={[lowApprovedIssue]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="priority"
        modulesEnabled={true}
        focusedKey="KAN-200"
      />
    );

    const card = screen.getByText(lowApprovedIssue.summary).closest('.swimlane-card');
    expect(card?.getAttribute('data-focused')).toBe('true');
  });

  it('covers assignee, cycle, module, and unknown subGroupBy branches', () => {
    const base = FIXTURE_12_ISSUES[0];
    if (!base) throw new Error('missing fixture');

    // 1. Assignee with non-principal kind (e.g. free_text)
    const agentAssigneeIssue: IssueItem = {
      ...base,
      key: 'KAN-301',
      assignees: [
        {
          id: 'asg-freetext',
          kind: 'free_text',
          free_text: 'External Contractor',
          notify: false,
          hint: '',
        },
      ],
    };

    // 2. Assignee with principal handle other than alice/adam (e.g. charlie)
    const charlieAssigneeIssue: IssueItem = {
      ...base,
      key: 'KAN-302',
      assignees: [
        {
          id: 'asg-charlie',
          kind: 'principal' as const,
          principal: { id: 'u-charlie', handle: 'charlie', display_name: 'Charlie Root', type: 'USER' },
        },
      ],
    };

    // 3. Issue with no assignees
    const noAssigneeIssue: IssueItem = {
      ...base,
      key: 'KAN-303',
      assignees: [],
    };

    // 4. Issue with no cycle_id
    const noCycleIssue: IssueItem = {
      ...base,
      key: 'KAN-304',
      cycle_id: null,
    };

    // 5. Issue with no module_ids
    const noModuleIssue: IssueItem = {
      ...base,
      key: 'KAN-305',
      module_ids: [],
    };

    const { rerender } = render(
      <SwimlaneBoardGrid
        issues={[agentAssigneeIssue, charlieAssigneeIssue, noAssigneeIssue]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="assignee"
        modulesEnabled={true}
      />
    );

    expect(screen.getByText('Unassigned')).toBeDefined();

    // Rerender with cycle
    rerender(
      <SwimlaneBoardGrid
        issues={[noCycleIssue]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="cycle"
        modulesEnabled={true}
      />
    );
    expect(screen.getByText('No Cycle')).toBeDefined();

    // Rerender with module
    rerender(
      <SwimlaneBoardGrid
        issues={[noModuleIssue]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="module"
        modulesEnabled={true}
      />
    );
    expect(screen.getByText('No Module')).toBeDefined();

    // Rerender with fallback single swimlane (e.g. label)
    rerender(
      <SwimlaneBoardGrid
        issues={[base]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="label"
        modulesEnabled={false}
      />
    );
    expect(screen.getByText('All Work Items')).toBeDefined();
  });
});
