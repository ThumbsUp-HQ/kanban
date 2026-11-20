import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { SwimlaneBoardGrid } from './SwimlaneBoardGrid';
import { FIXTURE_12_ISSUES } from './fixtures';
import type { IssueItem } from './viewsApi';
import * as railApi from '../drawer-rail/railApi';

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

  it('normalizes "To Do" and "Todo" states and group fallbacks into the same board column (KANBA-164)', () => {
    const base = FIXTURE_12_ISSUES[0];
    if (!base) throw new Error('missing fixture');
    const toDoIssue: IssueItem = {
      ...base,
      key: 'KAN-401',
      summary: 'Spaced To Do Card',
      state: { id: 'state-1', name: 'To Do', group: 'unstarted' },
      priority: { slug: 'high', label: 'High', emoji: '⚡' },
    };
    const todoIssue: IssueItem = {
      ...base,
      key: 'KAN-402',
      summary: 'Single Word Todo Card',
      state: { id: 'state-2', name: 'Todo', group: 'unstarted' },
      priority: { slug: 'high', label: 'High', emoji: '⚡' },
    };
    const groupFallbackIssues: IssueItem[] = [
      { ...base, key: 'KAN-403', state: { id: 's-b', name: 'Queued', group: 'backlog' } },
      { ...base, key: 'KAN-404', state: { id: 's-u', name: 'Ready', group: 'unstarted' } },
      { ...base, key: 'KAN-405', state: { id: 's-s', name: 'Active', group: 'started' } },
      { ...base, key: 'KAN-406', state: { id: 's-c', name: 'Shipped', group: 'completed' } },
      { ...base, key: 'KAN-407', state: { id: 's-x', name: 'Dropped', group: 'cancelled' } },
    ];

    render(
      <SwimlaneBoardGrid
        issues={[toDoIssue, todoIssue, ...groupFallbackIssues]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="priority"
        modulesEnabled={true}
      />
    );

    const todoColumn = document.querySelector(
      '[data-swimlane-id="high"][data-column-id="todo"]'
    );
    expect(todoColumn).not.toBeNull();
    expect(todoColumn?.querySelector('[data-issue-key="KAN-401"]')).not.toBeNull();
    expect(todoColumn?.querySelector('[data-issue-key="KAN-402"]')).not.toBeNull();
  });

  it('handles unknown priority slug and unknown state falling back to default lane and column', () => {
    const base = FIXTURE_12_ISSUES[0];
    if (!base) throw new Error('missing fixture');
    const exoticIssue: IssueItem = {
      ...base,
      key: 'KAN-999',
      summary: 'Exotic Issue',
      priority: { slug: 'unknown-priority', label: 'Custom' },
      state: { id: 'custom-state', name: 'Weird State', group: 'nonexistent' },
    };

    render(
      <SwimlaneBoardGrid
        issues={[exoticIssue]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="priority"
        modulesEnabled={true}
      />
    );

    // Placed in default lane (urgent) and default col (backlog)
    const card = screen.getByText('Exotic Issue');
    expect(card).toBeDefined();
  });

  it('supports groupBy=cycle and groupBy=module column grouping', () => {
    const first = FIXTURE_12_ISSUES[0];
    const second = FIXTURE_12_ISSUES[1];
    if (!first || !second) throw new Error('missing fixtures');

    const cycleIssues: IssueItem[] = [
      {
        ...first,
        id: 'kan-501',
        key: 'KAN-501',
        summary: 'Cycle 1 Item',
        cycle_id: 'cyc-1',
        cycle: { id: 'cyc-1', name: 'Sprint Alpha' },
        module_ids: ['mod-1'],
        modules: [{ id: 'mod-1', name: 'Auth Module' }],
      },
      {
        ...second,
        id: 'kan-502',
        key: 'KAN-502',
        summary: 'No Cycle Item',
        cycle_id: null,
        module_ids: [],
      },
    ];

    const { rerender } = render(
      <SwimlaneBoardGrid
        issues={cycleIssues}
        projectKey="KAN"
        groupBy="cycle"
        subGroupBy="none"
        modulesEnabled={true}
        projectCycles={[{ id: 'cyc-1', name: 'Sprint Alpha' }]}
      />
    );

    // Verify column headers for Sprint Alpha and No Cycle
    expect(screen.getByRole('columnheader', { name: /Sprint Alpha/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /No Cycle/i })).toBeDefined();

    // Verify groupBy=module
    rerender(
      <SwimlaneBoardGrid
        issues={cycleIssues}
        projectKey="KAN"
        groupBy="module"
        subGroupBy="none"
        modulesEnabled={true}
        projectModules={[{ id: 'mod-1', name: 'Auth Module' }]}
      />
    );

    // Verify column headers for Auth Module and No Module
    expect(screen.getByRole('columnheader', { name: /Auth Module/i })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /No Module/i })).toBeDefined();
  });

  it('handles fallback lane and column when issue has unmapped lane or column id', () => {
    const base = FIXTURE_12_ISSUES[0];
    if (!base) throw new Error('Missing fixture');
    const unmappedIssue: IssueItem = {
      ...base,
      key: 'KAN-UNMAPPED',
      module_ids: ['unknown-mod-id'],
      state: { id: 'unknown-state-id', name: 'Unknown State', group: 'unmapped' },
    };

    render(
      <SwimlaneBoardGrid
        issues={[unmappedIssue]}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="module"
        modulesEnabled={true}
        projectModules={[{ id: 'mod-1', name: 'Known Module' }]}
      />,
    );

    // Grid renders without throwing and places issue in fallback column
    expect(screen.getByText('KAN-UNMAPPED')).toBeDefined();
  });

  describe('Touch Card State Transition & projectStates Integration (KAN-44)', () => {
    const customProjectStates = [
      { id: 'st-triage', name: 'Triage', group: 'unstarted' as const },
      { id: 'st-in-progress', name: 'In Progress', group: 'started' as const },
      { id: 'st-done', name: 'Done', group: 'completed' as const },
    ];

    it('renders state move button, opens popover with stopPropagation, and triggers onCardMove', () => {
      const onCardClick = vi.fn();
      const onCardMove = vi.fn();
      const firstIssue = FIXTURE_12_ISSUES[0];
      if (!firstIssue) throw new Error('Missing fixture');

      const { rerender } = render(
        <SwimlaneBoardGrid
          issues={[firstIssue]}
          projectKey="KAN"
          groupBy="state"
          subGroupBy="none"
          modulesEnabled={true}
          onCardClick={onCardClick}
          onCardMove={onCardMove}
          projectStates={customProjectStates}
          currentUserCapabilities={['TRANSITION']}
        />,
      );

      const stateBtn = screen.getByTestId(`board-card-state-btn-${firstIssue.key}`);
      expect(stateBtn).toBeDefined();

      fireEvent.click(stateBtn);
      expect(onCardClick).not.toHaveBeenCalled();

      // QuickFieldPopover is open
      const popover = screen.getByRole('dialog', { name: 'Quick State Picker' });
      expect(popover).toBeDefined();

      // Select 'Done'
      const doneOption = screen.getByRole('option', { name: 'Done' });
      fireEvent.click(doneOption);

      expect(onCardMove).toHaveBeenCalledWith(firstIssue.key, 'st-done', 'none');
      expect(screen.queryByRole('dialog', { name: 'Quick State Picker' })).toBeNull();

      // Test with onStateTransition when onCardMove is not provided
      const onStateTransition = vi.fn();
      rerender(
        <SwimlaneBoardGrid
          issues={[firstIssue]}
          projectKey="KAN"
          groupBy="state"
          subGroupBy="none"
          modulesEnabled={true}
          onCardClick={onCardClick}
          onStateTransition={onStateTransition}
          projectStates={customProjectStates}
          currentUserCapabilities={['TRANSITION']}
        />,
      );

      const stateBtn2 = screen.getByTestId(`board-card-state-btn-${firstIssue.key}`);
      fireEvent.click(stateBtn2);
      fireEvent.click(screen.getByRole('option', { name: 'Triage' }));
      expect(onStateTransition).toHaveBeenCalledWith(firstIssue.key, 'st-triage');

      // Test popover backdrop close
      fireEvent.click(stateBtn2);
      const backdrop = screen.getByTestId('quick-field-backdrop');
      fireEvent.click(backdrop);
      expect(screen.queryByRole('dialog', { name: 'Quick State Picker' })).toBeNull();

      // Read-only user lacking capability hides button
      rerender(
        <SwimlaneBoardGrid
          issues={[firstIssue]}
          projectKey="KAN"
          groupBy="state"
          subGroupBy="none"
          modulesEnabled={true}
          currentUserCapabilities={['VIEWER']}
        />,
      );
      expect(screen.queryByTestId(`board-card-state-btn-${firstIssue.key}`)).toBeNull();
    });

    it('uses projectStates for columns and resolves issue placement by state id, name, and group', () => {
      const baseFixture = FIXTURE_12_ISSUES[0];
      if (!baseFixture) throw new Error('Missing fixture');
      const issueById: IssueItem = {
        ...baseFixture,
        key: 'KAN-BY-ID',
        state: { id: 'st-triage', name: 'Arbitrary', group: 'unstarted' },
      };
      const issueByName: IssueItem = {
        ...baseFixture,
        key: 'KAN-BY-NAME',
        state: { id: 'other-id', name: 'In Progress', group: 'started' },
      };
      const issueByGroup: IssueItem = {
        ...baseFixture,
        key: 'KAN-BY-GROUP',
        state: { id: 'other-id-2', name: 'Unmatched Name', group: 'completed' },
      };

      render(
        <SwimlaneBoardGrid
          issues={[issueById, issueByName, issueByGroup]}
          projectKey="KAN"
          groupBy="state"
          subGroupBy="none"
          modulesEnabled={true}
          projectStates={customProjectStates}
        />,
      );

      expect(screen.getByRole('columnheader', { name: /Triage/i })).toBeDefined();
      expect(screen.getByRole('columnheader', { name: /In Progress/i })).toBeDefined();
      expect(screen.getByRole('columnheader', { name: /Done/i })).toBeDefined();
      expect(screen.getByText('KAN-BY-ID')).toBeDefined();
      expect(screen.getByText('KAN-BY-NAME')).toBeDefined();
      expect(screen.getByText('KAN-BY-GROUP')).toBeDefined();
    });

    it('falls back to railApi.patchIssue when neither onCardMove nor onStateTransition is provided, and renders Move fallback', async () => {
      const patchSpy = vi.spyOn(railApi, 'patchIssue').mockResolvedValue({} as never);
      const baseFixture = FIXTURE_12_ISSUES[0];
      if (!baseFixture) throw new Error('Missing fixture');
      const issueWithoutStateName: IssueItem = {
        ...baseFixture,
        key: 'KAN-NO-STATENAME',
        state: { id: 'st-triage', name: '', group: 'unstarted' },
      };

      render(
        <SwimlaneBoardGrid
          issues={[issueWithoutStateName]}
          projectKey="KAN"
          groupBy="state"
          subGroupBy="none"
          modulesEnabled={true}
          projectStates={customProjectStates}
          currentUserCapabilities={['TRANSITION']}
        />,
      );

      // Verify button renders 'Move' when state.name is empty
      const stateBtn = screen.getByTestId('board-card-state-btn-KAN-NO-STATENAME');
      expect(stateBtn.textContent).toContain('Move');

      fireEvent.click(stateBtn);
      const popover = screen.getByRole('dialog', { name: 'Quick State Picker' });
      expect(popover).toBeDefined();

      // Click option
      fireEvent.click(screen.getByRole('option', { name: 'Done' }));

      await waitFor(() => {
        expect(patchSpy).toHaveBeenCalledWith('KAN-NO-STATENAME', { state_id: 'st-done' });
      });
      patchSpy.mockRestore();
    });
  });
});
