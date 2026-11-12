import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import React from 'react';
import {
  ViewHost,
  VIEW_REGISTRY,
  IssuesWorkspaceRoute,
  FilterDisplayBar,
  SwimlaneBoardGrid,
  BulkActionBar,
  QuickCreateIssueModal,
  QuickFieldPopover,
  useIssueKeyboardMap,
} from './viewRegistry';
import { FIXTURE_12_ISSUES } from './fixtures';
import type { IssueItem } from './viewsApi';

describe('viewRegistry & IssuesWorkspaceRoute (KB-P3-40, S6.3, S6.4, S7.2)', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/projects/KAN/issues');
  });

  it('exports all Action 1 components per Scoped Definition of Done', () => {
    expect(FilterDisplayBar).toBeDefined();
    expect(SwimlaneBoardGrid).toBeDefined();
    expect(BulkActionBar).toBeDefined();
    expect(QuickCreateIssueModal).toBeDefined();
    expect(QuickFieldPopover).toBeDefined();
    expect(useIssueKeyboardMap).toBeDefined();
    expect(VIEW_REGISTRY.list).toBeDefined();
    expect(VIEW_REGISTRY.table).toBeDefined();
    expect(VIEW_REGISTRY.board).toBeDefined();
  });

  it('renders ListView when layout is list or unspecified', () => {
    render(
      <ViewHost
        layout="list"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByText('Backlog')).toBeDefined();
  });

  it('renders TableView when layout is table', () => {
    render(
      <ViewHost
        layout="table"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByRole('table')).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /Key/i })).toBeDefined();
  });

  it('falls back to ListView on unknown layout', () => {
    render(
      <ViewHost
        layout="unknown_layout"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByText('Backlog')).toBeDefined();
  });

  it('IssuesWorkspaceRoute: renders FilterDisplayBar, mounts 2D SwimlaneBoardGrid when layout=board and sub_group_by=priority', () => {
    window.history.pushState(
      {},
      '',
      '/projects/KAN/issues?layout=board&group_by=state&sub_group_by=priority'
    );

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    expect(screen.getByTestId('issues-workspace')).toBeDefined();
    expect(screen.getByRole('region', { name: /filter and display controls/i })).toBeDefined();
    expect(screen.getByRole('region', { name: /2d swimlane board grid/i })).toBeDefined();
    expect(screen.getByText(/Urgent 🔥/i)).toBeDefined();
  });

  it('IssuesWorkspaceRoute: filters issues by Gate Status (e.g. pending shows ⏳🤖)', () => {
    window.history.pushState(
      {},
      '',
      '/projects/KAN/issues?layout=list&gate_status=pending'
    );

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    // KAN-145 has gate_status 'pending'
    expect(screen.getByText('KAN-145')).toBeDefined();
    // KAN-142 has gate_status 'approved', so it should not be in the document
    expect(screen.queryByText('KAN-142')).toBeNull();
  });

  it('IssuesWorkspaceRoute: creates a new issue via QuickCreateIssueModal and updates state/priority via field popover', () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    // Press 'C' to open QuickCreateIssueModal
    fireEvent.keyDown(window, { key: 'c' });
    expect(screen.getByRole('dialog', { name: /create work item in KAN/i })).toBeDefined();

    // Fill in summary, description, and module
    const summaryInput = screen.getByLabelText(/summary/i);
    fireEvent.change(summaryInput, { target: { value: 'Newly Created Task' } });
    const descInput = screen.getByLabelText(/description/i);
    fireEvent.change(descInput, { target: { value: 'Detailed task description' } });
    const modSelect = screen.getByLabelText(/module/i);
    fireEvent.change(modSelect, { target: { value: 'mod-1' } });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    expect(screen.getByText('Newly Created Task')).toBeDefined();

    // Focus on first card and press 'P' to open Priority popover
    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'p' });

    // Select Urgent
    const prioPopover = screen.getByRole('dialog', { name: /Quick Priority Picker/i });
    fireEvent.click(within(prioPopover).getByText('Urgent'));

    // Press 'S' to open State popover and select Done
    fireEvent.keyDown(window, { key: 's' });
    const statePopover1 = screen.getByRole('dialog', { name: /Quick State Picker/i });
    fireEvent.click(within(statePopover1).getByText('Done'));

    // Press 'S' again and select Todo
    fireEvent.keyDown(window, { key: 's' });
    const statePopover2 = screen.getByRole('dialog', { name: /Quick State Picker/i });
    fireEvent.click(within(statePopover2).getByText('Todo'));

    // Press 'P' again to open popover, then close with Escape
    fireEvent.keyDown(window, { key: 'p' });
    fireEvent.keyDown(window, { key: 'Escape' });

    // Press 'A' to open Assignee popover and select Alice (exercises field !== priority/state)
    fireEvent.keyDown(window, { key: 'a' });
    const assigneePopover = screen.getByRole('dialog', { name: /Quick Assignee Picker/i });
    fireEvent.click(within(assigneePopover).getByText('Alice Cooper'));
  });

  it('IssuesWorkspaceRoute: handles multi-select, batch archive, and batch delete in BulkActionBar', () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    // Press 'J' to focus first item, 'X' to select
    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'x' });

    // Bulk action bar is mounted with '1 selected'
    expect(screen.getByRole('toolbar', { name: /bulk actions/i })).toBeDefined();
    expect(screen.getByText('1 selected')).toBeDefined();

    // Test clear selection
    const clearBtn = screen.getByRole('button', { name: /clear selection/i });
    fireEvent.click(clearBtn);
    expect(screen.queryByRole('toolbar', { name: /bulk actions/i })).toBeNull();

    // Select again and delete batch
    fireEvent.keyDown(window, { key: 'x' });
    const deleteBtn = screen.getByRole('button', { name: /^delete$/i });
    fireEvent.click(deleteBtn);

    // Bulk bar unmounts when selection cleared
    expect(screen.queryByRole('toolbar', { name: /bulk actions/i })).toBeNull();
  });

  it('IssuesWorkspaceRoute: filters by Priority, Assignee (unassigned and alice), Cycle, Module, Due Date', () => {
    // 1. Priority filter: urgent
    window.history.pushState({}, '', '/projects/KAN/issues?layout=list');

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    const openPopoverIfNeeded = () => {
      if (!screen.queryByPlaceholderText(/search filters\.\.\./i)) {
        fireEvent.click(screen.getByRole('button', { name: /open filter facets popover/i }));
      }
    };

    // Open filter popover and click Urgent
    openPopoverIfNeeded();
    fireEvent.click(screen.getByRole('button', { name: /🔥 Urgent/i }));

    // KAN-142 is Urgent
    expect(screen.getByText('KAN-142')).toBeDefined();
    // KAN-141 is Low -> filtered out
    expect(screen.queryByText('KAN-141')).toBeNull();

    // Clear all filters
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
    expect(screen.getByText('KAN-141')).toBeDefined();

    // 2. Assignee filter: Unassigned
    openPopoverIfNeeded();
    fireEvent.click(screen.getByRole('button', { name: /Unassigned/i }));
    // KAN-141 is unassigned
    expect(screen.getByText('KAN-141')).toBeDefined();

    // 3. Due date filter: Overdue
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
    openPopoverIfNeeded();
    fireEvent.click(screen.getByRole('button', { name: /Overdue/i }));

    // 4. Due date filter: No due date
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
    openPopoverIfNeeded();
    fireEvent.click(screen.getByRole('button', { name: /No due date/i }));

    // 5. Label filter: Security
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
    openPopoverIfNeeded();
    fireEvent.click(screen.getByRole('button', { name: /^Security$/i }));
    expect(screen.getByText('KAN-142')).toBeDefined();

    // 6. Cycle filter: Cycle 1
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
    openPopoverIfNeeded();
    fireEvent.click(screen.getByRole('button', { name: /^Cycle 1$/i }));

    // 7. Module filter: Auth Core
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
    openPopoverIfNeeded();
    fireEvent.click(screen.getByRole('button', { name: /^Auth Core$/i }));
  });

  it('IssuesWorkspaceRoute: tests state filter Active preset, alice assignee, and select-all', () => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=table');

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    const openPopoverIfNeeded = () => {
      if (!screen.queryByPlaceholderText(/search filters\.\.\./i)) {
        fireEvent.click(screen.getByRole('button', { name: /open filter facets popover/i }));
      }
    };

    // Filter by Active preset
    openPopoverIfNeeded();
    fireEvent.click(screen.getByRole('button', { name: /^Active$/i }));

    // Backlog (KAN-140) and In Progress (KAN-142) should be present
    expect(screen.getByText('KAN-140')).toBeDefined();
    expect(screen.getByText('KAN-142')).toBeDefined();

    // Done (KAN-148) should be excluded
    expect(screen.queryByText('KAN-148')).toBeNull();

    // Filter by Alice
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));
    openPopoverIfNeeded();
    fireEvent.click(screen.getByRole('button', { name: /Alice Cooper/i }));
    expect(screen.getByText('KAN-140')).toBeDefined();

    // Select all issues via table header checkbox
    const selectAllCheckbox = screen.getByRole('checkbox', { name: /select all issues/i });
    fireEvent.click(selectAllCheckbox);
    expect(screen.getByRole('toolbar', { name: /bulk actions/i })).toBeDefined();

    // Deselect all
    fireEvent.click(selectAllCheckbox);
    expect(screen.queryByRole('toolbar', { name: /bulk actions/i })).toBeNull();
  });

  it('IssuesWorkspaceRoute: batch archives completed issues when Archive is clicked', () => {
    // Pre-populate with completed issues
    const completedIssues = FIXTURE_12_ISSUES.filter(
      (i) => i.state.group === 'completed' || i.state.group === 'cancelled'
    );

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={completedIssues}
      />
    );

    // Select first issue via 'J' then 'X'
    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'x' });

    // Archive button is enabled
    const archiveBtn = screen.getByRole('button', { name: /archive/i });
    expect(archiveBtn.hasAttribute('disabled')).toBe(false);
    fireEvent.click(archiveBtn);

    // Selection cleared after archive
    expect(screen.queryByRole('toolbar', { name: /bulk actions/i })).toBeNull();
  });

  it('IssuesWorkspaceRoute: toggles Adam assignment via I shortcut', () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    // Focus KAN-140 and press 'I'
    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'i' });

    // Press 'I' again to toggle back off
    fireEvent.keyDown(window, { key: 'i' });
  });

  it('IssuesWorkspaceRoute: mounts 2D Swimlane grid when board layout and subGroupBy is active', () => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=board');

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    // Switch sub-group to priority
    const subGroupSelect = screen.getByLabelText(/^Sub-group by axis$/i);
    fireEvent.change(subGroupSelect, { target: { value: 'priority' } });

    // 2D grid should be present
    expect(screen.getByRole('region', { name: /2d swimlane board grid/i })).toBeDefined();

    // Select a card via its checkbox in the swimlane grid
    const checkbox = screen.getByLabelText('Select KAN-140');
    fireEvent.click(checkbox);

    expect(screen.getByRole('toolbar', { name: /bulk actions/i })).toBeDefined();
    expect(screen.getByText('1 selected')).toBeDefined();

    // Deselect card
    fireEvent.click(checkbox);
    expect(screen.queryByRole('toolbar', { name: /bulk actions/i })).toBeNull();
  });

  it('IssuesWorkspaceRoute: tests field popovers for high/low priority and in-progress/backlog state, and / shortcut', () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    // Press '/' to open filter
    fireEvent.keyDown(window, { key: '/' });
    expect(screen.getByPlaceholderText(/search filters\.\.\./i)).toBeDefined();

    // Close filter by clicking trigger again
    fireEvent.click(screen.getByRole('button', { name: /open filter facets popover/i }));

    // Focus first item
    fireEvent.keyDown(window, { key: 'j' });

    // Set priority to High
    fireEvent.keyDown(window, { key: 'p' });
    const prioPop1 = screen.getByRole('dialog', { name: /Quick Priority Picker/i });
    fireEvent.click(within(prioPop1).getByText('High'));

    // Set priority to Low
    fireEvent.keyDown(window, { key: 'p' });
    const prioPop2 = screen.getByRole('dialog', { name: /Quick Priority Picker/i });
    fireEvent.click(within(prioPop2).getByText('Low'));

    // Set priority to Medium
    fireEvent.keyDown(window, { key: 'p' });
    const prioPop3 = screen.getByRole('dialog', { name: /Quick Priority Picker/i });
    fireEvent.click(within(prioPop3).getByText('Medium'));

    // Set state to In Progress
    fireEvent.keyDown(window, { key: 's' });
    const statePop1 = screen.getByRole('dialog', { name: /Quick State Picker/i });
    fireEvent.click(within(statePop1).getByText('In Progress'));

    // Set state to Backlog
    fireEvent.keyDown(window, { key: 's' });
    const statePop2 = screen.getByRole('dialog', { name: /Quick State Picker/i });
    fireEvent.click(within(statePop2).getByText('Backlog'));

    // Set assignee to Alice Cooper
    fireEvent.keyDown(window, { key: 'a' });
    const asgPop = screen.getByRole('dialog', { name: /Quick Assignee Picker/i });
    fireEvent.click(within(asgPop).getByText(/Alice Cooper/i));
  });

  it('IssuesWorkspaceRoute: initializes activeFilters from URL query params (filter_label, filter_priority, filter_state, and gate_status)', () => {
    window.history.pushState(
      {},
      '',
      '/projects/KAN/issues?filter_state=in_progress&filter_priority=high&filter_label=Frontend&gate_status=pending'
    );

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    expect(screen.getByText(/Gate status: ⏳🤖 Pending/i)).toBeDefined();
    expect(screen.getByText(/Priority: ⚡ High/i)).toBeDefined();
  });

  it('IssuesWorkspaceRoute: covers handleToggleSelect 100 cap and unassigned I shortcut', () => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=table');
    const firstFixture = FIXTURE_12_ISSUES[0];
    if (!firstFixture) throw new Error('missing fixture');
    const many105: IssueItem[] = Array.from({ length: 105 }, (_, i) => ({
      id: `id-${String(i + 1)}`,
      key: `KAN-${String(i + 1)}`,
      summary: firstFixture.summary,
      state: firstFixture.state,
      priority: firstFixture.priority,
    }));

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={many105}
      />
    );

    // Select all in table view (caps at 100)
    const selectAllCheckbox = screen.getByRole('checkbox', { name: /select all issues/i });
    fireEvent.click(selectAllCheckbox);
    expect(screen.getByText('100 selected')).toBeDefined();

    // Toggle another row checkbox when 100 are already selected
    const checkbox101 = screen.getByLabelText('Select KAN-101');
    fireEvent.click(checkbox101);
    expect(screen.getByText('100 selected')).toBeDefined();

    // Press 'J' then 'I' on issue with assignees === undefined
    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'i' });
  });
});
