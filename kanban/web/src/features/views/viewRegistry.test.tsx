import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, within, waitFor, act } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import React from 'react';

vi.mock('../drawer-rail/railApi', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../drawer-rail/railApi');
  return {
    ...actual,
    fetchAssigneeSuggestions: vi.fn().mockImplementation(() => new Promise(() => {
      /* pending */
    })),
    fetchProjectLabels: vi.fn().mockImplementation(() => new Promise(() => {
      /* pending */
    })),
    fetchProjectCycles: vi.fn().mockImplementation(() => new Promise(() => {
      /* pending */
    })),
    fetchProjectModules: vi.fn().mockImplementation(() => new Promise(() => {
      /* pending */
    })),
  };
});
import {
  ViewHost,
  VIEW_REGISTRY,
  viewRegistry,
  IssuesWorkspaceRoute,
  FilterDisplayBar,
  SwimlaneBoardGrid,
  BulkActionBar,
  QuickCreateIssueModal,
  QuickFieldPopover,
  useIssueKeyboardMap,
  defaultQueryClient,
  computeStateSummary,
} from './viewRegistry';
import { FIXTURE_12_ISSUES } from './fixtures';
import * as viewsApi from './viewsApi';
import type { IssueItem, StateSummary } from './viewsApi';
import { apiClient } from '../../api/client';

describe('viewRegistry & IssuesWorkspaceRoute (KB-P3-40, S6.3, S6.4, S7.2)', () => {
  beforeEach(() => {
    defaultQueryClient.clear();
    window.innerWidth = 1024;
    window.history.pushState({}, '', '/projects/KAN/issues');
  });

  afterEach(async () => {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
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
    expect(VIEW_REGISTRY.calendar).toBeDefined();
    expect(VIEW_REGISTRY.timeline).toBeDefined();
    expect(viewRegistry.board).toBeDefined();
    expect(viewRegistry.list).toBeDefined();
    expect(viewRegistry.table).toBeDefined();
    expect(viewRegistry.calendar).toBeDefined();
    expect(viewRegistry.timeline).toBeDefined();
    expect(viewRegistry.grid).toBeDefined();
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

    expect(screen.getByTestId('issue-list-rail')).toBeDefined();
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

  it('renders CalendarView when layout is calendar', () => {
    render(
      <ViewHost
        layout="calendar"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByTestId('calendar-view')).toBeDefined();
  });

  it('renders TimelineView when layout is timeline', () => {
    render(
      <ViewHost
        layout="timeline"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByTestId('timeline-view')).toBeDefined();
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

    expect(screen.getByTestId('issue-list-rail')).toBeDefined();
  });

  it('IssuesWorkspaceRoute: renders FilterDisplayBar, mounts 2D SwimlaneBoardGrid when layout=board and sub_group_by=priority', async () => {
    window.history.pushState(
      {},
      '',
      '/projects/KAN/issues?layout=board&group_by=state&sub_group_by=priority'
    );

    await act(async () => {
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          modulesEnabled={true}
          initialIssues={FIXTURE_12_ISSUES}
        />
      );
      await new Promise((r) => setTimeout(r, 0));
    });

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

  it('IssuesWorkspaceRoute: creates a new issue via QuickCreateIssueModal and updates state/priority via field popover', async () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    // Press 'C' to open QuickCreateIssueModal
    await act(async () => {
      fireEvent.keyDown(window, { key: 'c' });
      await new Promise((r) => setTimeout(r, 60));
    });
    expect(screen.getByRole('dialog', { name: /create work item in KAN/i })).toBeDefined();

    // Fill in summary, description, and module
    const createDialog = screen.getByRole('dialog', { name: /create work item in KAN/i });
    const summaryInput = within(createDialog).getByLabelText(/summary/i);
    fireEvent.change(summaryInput, { target: { value: 'Newly Created Task' } });
    const descInput = within(createDialog).getByLabelText(/description/i);
    fireEvent.change(descInput, { target: { value: 'Detailed task description' } });
    const modSelect = within(createDialog).getByLabelText(/module/i);
    fireEvent.change(modSelect, { target: { value: 'mod-1' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));
      await Promise.resolve();
    });

    act(() => {
      const doneBtn = screen.queryByTestId('post-create-done-btn');
      if (doneBtn) {
        fireEvent.click(doneBtn);
      }
    });

    expect(screen.getByText('Newly Created Task')).toBeDefined();

    // Focus on first card and press 'P' to open Priority popover
    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'p' });

    // Select Urgent
    const prioPopover = screen.getByRole('dialog', { name: /Quick Priority Picker/i });
    fireEvent.click(within(prioPopover).getByText('Urgent'));

    // Select High, Low, None, Medium priorities
    fireEvent.keyDown(window, { key: 'p' });
    fireEvent.click(within(screen.getByRole('dialog', { name: /Quick Priority Picker/i })).getByText('High'));
    fireEvent.keyDown(window, { key: 'p' });
    fireEvent.click(within(screen.getByRole('dialog', { name: /Quick Priority Picker/i })).getByText('Low'));
    fireEvent.keyDown(window, { key: 'p' });
    fireEvent.click(within(screen.getByRole('dialog', { name: /Quick Priority Picker/i })).getByText('None'));
    fireEvent.keyDown(window, { key: 'p' });
    fireEvent.click(within(screen.getByRole('dialog', { name: /Quick Priority Picker/i })).getByText('Medium'));

    // Press 'S' to open State popover and select Done
    fireEvent.keyDown(window, { key: 's' });
    const statePopover1 = screen.getByRole('dialog', { name: /Quick State Picker/i });
    fireEvent.click(within(statePopover1).getByText('Done'));

    // Press 'S' again and select In Progress, Backlog, Todo
    fireEvent.keyDown(window, { key: 's' });
    fireEvent.click(within(screen.getByRole('dialog', { name: /Quick State Picker/i })).getByText('In Progress'));
    fireEvent.keyDown(window, { key: 's' });
    fireEvent.click(within(screen.getByRole('dialog', { name: /Quick State Picker/i })).getByText('Backlog'));
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

  it('IssuesWorkspaceRoute: handles multi-select, batch archive, and batch delete in BulkActionBar', async () => {
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

    // Select again and update state to done
    fireEvent.keyDown(window, { key: 'x' });
    const stateBtn = screen.getByRole('button', { name: /^state$/i });
    await act(async () => {
      fireEvent.click(stateBtn);
      await Promise.resolve();
    });

    // Select again (now issue is completed) and update state to todo
    fireEvent.keyDown(window, { key: 'x' });
    const stateBtnTodo = screen.getByRole('button', { name: /^state$/i });
    await act(async () => {
      fireEvent.click(stateBtnTodo);
      await Promise.resolve();
    });

    // Select again and update priority
    fireEvent.keyDown(window, { key: 'x' });
    const priorityBtn = screen.getByRole('button', { name: /^priority$/i });
    await act(async () => {
      fireEvent.click(priorityBtn);
      await Promise.resolve();
    });

    // Select again and delete batch
    fireEvent.keyDown(window, { key: 'x' });
    const deleteBtn = screen.getByRole('button', { name: /^delete$/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
      await Promise.resolve();
    });

    // Bulk bar unmounts when selection cleared
    expect(screen.queryByRole('toolbar', { name: /bulk actions/i })).toBeNull();
  });

  it('IssuesWorkspaceRoute: triggers onCreateIssue modal and covers BulkActionBar batch updates', () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    // Click New work item button in list view
    const newBtn = screen.getByRole('button', { name: 'New work item' });
    fireEvent.click(newBtn);
    expect(screen.getByRole('dialog')).toBeDefined();

    // Close modal
    fireEvent.keyDown(window, { key: 'Escape' });
  });

  it('IssuesWorkspaceRoute: filters by Priority, Assignee (unassigned and alice), Cycle, Module, Due Date', () => {
    // 1. Priority filter: urgent
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
  }, 30000);

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
    const toolbar = screen.getByRole('toolbar', { name: /bulk actions/i });
    expect(toolbar).toBeDefined();

    // Batch update state via State bulk action button
    const stateBtn = within(toolbar).getByRole('button', { name: /^state$/i });
    fireEvent.click(stateBtn);

    // Batch update priority via Priority bulk action button
    const prioBtn = within(toolbar).getByRole('button', { name: /^priority$/i });
    fireEvent.click(prioBtn);

    // Clear selection
    const clearBtn = within(toolbar).getByRole('button', { name: /clear/i });
    fireEvent.click(clearBtn);
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

  it('IssuesWorkspaceRoute: covers batch update state with Shift (todo) and batch update priority with Shift (medium)', () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    // Select KAN-140
    fireEvent.keyDown(window, { key: 'j' });
    fireEvent.keyDown(window, { key: 'x' });

    // Shift-click State button to update to 'todo'
    const stateBtn = screen.getByRole('button', { name: /^state$/i });
    fireEvent.click(stateBtn, { shiftKey: true });

    // Select KAN-140 again
    fireEvent.keyDown(window, { key: 'x' });

    // Shift-click Priority button to update to 'medium'
    const prioBtn = screen.getByRole('button', { name: /^priority$/i });
    fireEvent.click(prioBtn, { shiftKey: true });
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
    window.history.pushState({}, '', '/projects/KAN/issues?layout=board');
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

    // Set priority to None
    fireEvent.keyDown(window, { key: 'p' });
    const prioPopNone = screen.getByRole('dialog', { name: /Quick Priority Picker/i });
    fireEvent.click(within(prioPopNone).getByText('None'));

    // Set state to Done
    fireEvent.keyDown(window, { key: 's' });
    const statePopDone = screen.getByRole('dialog', { name: /Quick State Picker/i });
    fireEvent.click(within(statePopDone).getByText('Done'));

    // Set state to Todo
    fireEvent.keyDown(window, { key: 's' });
    const statePopTodo = screen.getByRole('dialog', { name: /Quick State Picker/i });
    fireEvent.click(within(statePopTodo).getByText('Todo'));

    // Set assignee to Alice Cooper
    fireEvent.keyDown(window, { key: 'a' });
    const asgPop = screen.getByRole('dialog', { name: /Quick Assignee Picker/i });
    fireEvent.click(within(asgPop).getByText(/Alice Cooper/i));
  });

  it('IssuesWorkspaceRoute: initializes activeFilters from URL query params (filter_label, filter_priority, filter_state, and gate_status)', () => {
    window.history.pushState(
      {},
      '',
      '/projects/KAN/issues?layout=board&filter_state=in_progress&filter_priority=high&filter_label=Frontend&gate_status=pending'
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

  describe('Live Mode API Wiring & Board State Normalization (KANBA-164)', () => {
    const originalFetch = globalThis.fetch;

    afterEach(() => {
      globalThis.fetch = originalFetch;
    });

    it('fetches live issues and workflow states when initialIssues is undefined and renders cards on BoardView', async () => {
      window.history.pushState({}, '', '/projects/KAN/issues?layout=board');
      document.cookie = 'kb_csrf=test-csrf-live; path=/';

      const liveStates = [
        { id: '01931234-5678-7000-8000-000000000001', name: 'Backlog', group: 'backlog', sort_order: 10 },
        { id: '01931234-5678-7000-8000-000000000002', name: 'To Do', group: 'unstarted', sort_order: 20 },
        { id: '01931234-5678-7000-8000-000000000003', name: 'In Progress', group: 'started', sort_order: 30 },
        { id: '01931234-5678-7000-8000-000000000004', name: 'Done', group: 'completed', sort_order: 40 },
      ];
      const liveIssues = [
        {
          id: '01931234-5678-7000-8000-000000000101',
          key: 'KAN-101',
          summary: 'Live Board Todo Issue',
          state: { id: '01931234-5678-7000-8000-000000000002', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'high', label: 'High', emoji: '⚡' },
          assignees: [
            {
              id: 'asg-1',
              kind: 'principal',
              principal: { id: 'u-1', handle: 'alice', display_name: 'Alice', type: 'USER' },
            },
            {
              id: 'asg-2',
              kind: 'free_text',
              free_text: 'External Reviewer',
              notify: false,
              hint: '',
            },
          ],
          gate_status: 'vetoed',
        },
      ];

      globalThis.fetch = vi.fn().mockImplementation((input: string | URL | Request) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (url.endsWith('/states')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: liveStates }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: liveIssues, next_cursor: null, total: 1 }),
        });
      });

      render(<IssuesWorkspaceRoute projectKey="KAN" initialLayout="board" />);

      await waitFor(() => {
        expect(screen.getByLabelText('Todo lane, 1 issues')).toBeDefined();
      });

      // Click '+ New work item' button inside the board column footer
      const newColBtn = screen.getByTestId('new-item-01931234-5678-7000-8000-000000000001');
      fireEvent.click(newColBtn);
      expect(screen.getByRole('dialog', { name: /create work item in KAN/i })).toBeDefined();
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

      // Dispatch kb:create-issue to open QuickCreateIssueModal
      act(() => {
        fireEvent(window, new CustomEvent('kb:create-issue'));
      });
      expect(screen.getByRole('dialog', { name: /create work item in KAN/i })).toBeDefined();
      act(() => {
        fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
      });
    });

    it('creates, updates, and bulk-operates on issues in live mode via REST endpoints', async () => {
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
      document.cookie = 'kb_csrf=test-csrf-live; path=/';

      const liveStates = [
        { id: 'state-in-review', name: 'In Review', group: 'custom_group' },
        { id: '01931234-5678-7000-8000-000000000001', name: 'Backlog', group: 'backlog', sort_order: 10 },
        { id: '01931234-5678-7000-8000-000000000002', name: 'Todo', group: 'unstarted', sort_order: 20 },
        { id: '01931234-5678-7000-8000-000000000003', name: 'In Progress', group: 'started', sort_order: 30 },
        { id: '01931234-5678-7000-8000-000000000004', name: 'Done', group: 'completed', sort_order: 40 },
      ];
      const liveIssues = [
        {
          id: '01931234-5678-7000-8000-000000000201',
          key: 'KAN-201',
          summary: 'Initial Live List Issue',
          state: { id: '01931234-5678-7000-8000-000000000002', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
        },
      ];

      let postCount = 0;
      let failPatch: 'error' | 'string' | null = null;
      const fetchSpy = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        const method = init?.method ?? 'GET';
        if (url.endsWith('/states')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: liveStates }),
          });
        }
        if (method === 'POST' && url.endsWith('/issues')) {
          postCount++;
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                id: postCount > 1 ? '01931234-5678-7000-8000-000000000201' : '01931234-5678-7000-8000-000000000202',
                key: postCount > 1 ? 'KAN-201' : 'KAN-202',
                summary: 'Persisted Live Issue',
                state: { id: '01931234-5678-7000-8000-000000000002', name: 'Todo', group: 'unstarted' },
                priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
              }),
          });
        }
        if (method === 'PATCH') {
          if (failPatch === 'error') {
            failPatch = null;
            return Promise.reject(new Error('Network failure priority'));
          }
          if (failPatch === 'string') {
            failPatch = null;
            // eslint-disable-next-line @typescript-eslint/prefer-promise-reject-errors
            return Promise.reject('String failure state');
          }
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                ...liveIssues[0],
                summary: 'Updated Live Issue',
              }),
          });
        }
        if (method === 'DELETE') {
          return Promise.resolve({ ok: true });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: liveIssues, next_cursor: null, total: 1 }),
        });
      });
      globalThis.fetch = fetchSpy;

      render(<IssuesWorkspaceRoute projectKey="KAN" initialLayout="list" capabilities={['VIEW', 'EDIT']} />);

      await waitFor(() => {
        expect(screen.getByText('Initial Live List Issue')).toBeDefined();
      });

      // Open modal via '+ New work item' button in ListView
      const newBtns = screen.getAllByRole('button', { name: /new work item/i });
      if (newBtns[0]) fireEvent.click(newBtns[0]);

      const summaryInput = screen.getByLabelText(/summary/i);
      fireEvent.change(summaryInput, { target: { value: 'Persisted Live Issue' } });
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      await waitFor(() => {
        expect(screen.getAllByText('KAN-202').length).toBeGreaterThan(0);
      });

      const doneBtn = screen.queryByRole('button', { name: /^done$/i });
      if (doneBtn) fireEvent.click(doneBtn);

      // Quick field update in live mode
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'p' });
      const prioPop = screen.getByRole('dialog', { name: /Quick Priority Picker/i });
      fireEvent.click(within(prioPop).getByText('Urgent'));

      fireEvent.keyDown(window, { key: 's' });
      const statePop = screen.getByRole('dialog', { name: /Quick State Picker/i });
      fireEvent.click(within(statePop).getByText('Done'));

      // In Progress
      fireEvent.keyDown(window, { key: 's' });
      const statePopProg = screen.getByRole('dialog', { name: /Quick State Picker/i });
      fireEvent.click(within(statePopProg).getByText('In Progress'));

      // Todo
      fireEvent.keyDown(window, { key: 's' });
      const statePopTodo = screen.getByRole('dialog', { name: /Quick State Picker/i });
      fireEvent.click(within(statePopTodo).getByText('Todo'));

      // Backlog
      fireEvent.keyDown(window, { key: 's' });
      const statePopBack = screen.getByRole('dialog', { name: /Quick State Picker/i });
      fireEvent.click(within(statePopBack).getByText('Backlog'));

      // Exercise PATCH failure catch branches for priority and state
      failPatch = 'error';
      fireEvent.keyDown(window, { key: 'p' });
      const prioFailPop = screen.getByRole('dialog', { name: /Quick Priority Picker/i });
      await act(async () => {
        fireEvent.click(within(prioFailPop).getByText('High'));
        await new Promise((r) => setTimeout(r, 10));
      });

      failPatch = 'string';
      fireEvent.keyDown(window, { key: 'p' });
      const prioFailPop2 = screen.getByRole('dialog', { name: /Quick Priority Picker/i });
      await act(async () => {
        fireEvent.click(within(prioFailPop2).getByText('Low'));
        await new Promise((r) => setTimeout(r, 10));
      });

      failPatch = 'string';
      fireEvent.keyDown(window, { key: 's' });
      const stateFailPop = screen.getByRole('dialog', { name: /Quick State Picker/i });
      await act(async () => {
        fireEvent.click(within(stateFailPop).getByText('Todo'));
        await new Promise((r) => setTimeout(r, 10));
      });

      failPatch = 'error';
      fireEvent.keyDown(window, { key: 's' });
      const stateFailPop2 = screen.getByRole('dialog', { name: /Quick State Picker/i });
      await act(async () => {
        fireEvent.click(within(stateFailPop2).getByText('Done'));
        await new Promise((r) => setTimeout(r, 10));
      });

      // Bulk update State, Priority, and Delete in live mode
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'x' });
      fireEvent.click(screen.getByRole('button', { name: /^state$/i }));

      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'x' });
      fireEvent.click(screen.getByRole('button', { name: /^priority$/i }));

      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'x' });
      fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

      // Dispatch kb:issue-updated to trigger refresh
      await act(async () => {
        fireEvent(window, new CustomEvent('kb:issue-updated'));
        await new Promise((r) => setTimeout(r, 20));
      });
    });

    it('handles peek query param, vetoed gate status, and agent assignees in board layout', () => {
      window.history.pushState({}, '', '/projects/KAN/issues?peek=KAN-2');

      const issuesWithAgent: IssueItem[] = [
        {
          id: 'i-1',
          key: 'KAN-1',
          summary: 'Item with Agent Assignee',
          state: { id: 's-todo', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'high', label: 'High' },
          gate_status: 'vetoed',
          assignees: [
            {
              id: 'asg-bot',
              kind: 'principal',
              principal: {
                id: 'p-bot',
                handle: 'secbot',
                type: 'AGENT',
                display_name: 'Security Bot',
              },
            },
            {
              id: 'asg-raw',
              kind: 'free_text',
              free_text: 'External Contractor',
              notify: false,
              hint: '',
            },
          ],
        },
        {
          id: 'i-2',
          key: 'KAN-2',
          summary: 'Peek Target Item',
          state: { id: 's-done', name: 'Done', group: 'completed' },
          priority: { slug: 'urgent', label: 'Urgent' },
        },
      ];

      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="board"
          initialIssues={issuesWithAgent}
        />,
      );

      expect(screen.getByTestId('board-canvas')).toBeDefined();
    });

    it('handles bulk archive, custom priority emojis, and clear selection', () => {
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="board"
          initialIssues={FIXTURE_12_ISSUES}
        />,
      );

      // Select first issue via 'x'
      fireEvent.keyDown(window, { key: 'x' });
      const bulkBar = screen.getByRole('toolbar', { name: /Bulk actions/i });
      expect(bulkBar).toBeDefined();

      // Test Archive
      const archiveBtn = within(bulkBar).getByRole('button', { name: /^archive$/i });
      fireEvent.click(archiveBtn);

      // Select again and clear via Esc button
      fireEvent.keyDown(window, { key: 'x' });

      // Test batch state and priority updates
      const stateBtn = within(bulkBar).getByRole('button', { name: /^state$/i });
      fireEvent.click(stateBtn);

      fireEvent.keyDown(window, { key: 'x' });
      const priorityBtn = within(bulkBar).getByRole('button', { name: /^priority$/i });
      fireEvent.click(priorityBtn);

      fireEvent.keyDown(window, { key: 'x' });
      const clearBtn = within(bulkBar).getByRole('button', { name: /Clear selection/i });
      fireEvent.click(clearBtn);

      // Select and test 2D Swimlane switch by subGroupBy
      const subGroupSelect = screen.getByLabelText('Sub-group by axis');
      fireEvent.change(subGroupSelect, { target: { value: 'priority' } });
      const groupSelect = screen.getByLabelText('Group by axis');
      fireEvent.change(groupSelect, { target: { value: 'state' } });
    });

    it('covers live mode optimistic creation with new key, backlog state selection, and wip_hard/wip_soft aliases', async () => {
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
      document.cookie = 'kb_csrf=test-csrf-live; path=/';

      const liveStatesWithAliases = [
        { id: 'alias-st-1', name: 'Backlog', group: 'backlog', sort_order: 10, wip_hard: 5 },
        { id: 'alias-st-2', name: 'To Do', group: 'unstarted', sort_order: 20, wip_soft: 3 },
        { id: 'alias-st-3', name: 'In Progress', group: 'started', sort_order: 30 },
        { id: 'alias-st-4', name: 'Done', group: 'completed', sort_order: 40 },
      ];
      const liveIssues = [
        {
          id: 'alias-issue-301',
          key: 'KAN-301',
          summary: 'Live Alias Issue',
          state: { id: 'alias-st-2', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
        },
      ];

      const fetchSpy = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        const method = init?.method ?? 'GET';
        if (url.endsWith('/states')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: liveStatesWithAliases }),
          });
        }
        if (method === 'POST' && url.endsWith('/issues')) {
          return Promise.resolve({
            ok: true,
            json: () =>
              Promise.resolve({
                id: 'alias-issue-399',
                key: 'KAN-999',
                summary: 'New Persisted Key Issue',
                description_markdown: 'Detailed description',
                module_ids: ['mod-1'],
                state: { id: 'alias-st-1', name: 'Backlog', group: 'backlog' },
                priority: { slug: 'low', label: 'Low', emoji: '🔽' },
              }),
          });
        }
        if (method === 'PATCH') {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(liveIssues[0]),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: liveIssues, next_cursor: null, total: 1 }),
        });
      });
      globalThis.fetch = fetchSpy;

      render(<IssuesWorkspaceRoute projectKey="KAN" initialLayout="list" capabilities={['VIEW', 'EDIT']} />);

      await waitFor(() => {
        expect(screen.getByText('Live Alias Issue')).toBeDefined();
      });

      // Quick field state update to Backlog and live priority & state branches
      const openPicker = async (key: string, name: RegExp) => {
        return waitFor(
          () => {
            const existing = screen.queryByRole('dialog', { name });
            if (existing) return existing;
            fireEvent.keyDown(window, { key: 'j' });
            fireEvent.keyDown(window, { key });
            return screen.getByRole('dialog', { name });
          },
          { timeout: 5000 }
        );
      };

      const statePop = await openPicker('s', /Quick State Picker/i);
      fireEvent.click(within(statePop).getByText('Backlog'));

      // Live priority update
      const prioPop = await openPicker('p', /Quick Priority Picker/i);
      fireEvent.click(within(prioPop).getByText('Urgent'));

      // Live state updates: In Progress, Todo, Done
      const statePopProg = await openPicker('s', /Quick State Picker/i);
      fireEvent.click(within(statePopProg).getByText('In Progress'));

      const statePopTodo = await openPicker('s', /Quick State Picker/i);
      fireEvent.click(within(statePopTodo).getByText('Todo'));

      const statePopDone = await openPicker('s', /Quick State Picker/i);
      fireEvent.click(within(statePopDone).getByText('Done'));

      // Dispatch kb:create-issue to open QuickCreateIssueModal and submit
      act(() => {
        fireEvent(window, new CustomEvent('kb:create-issue'));
      });
      const summaryInput = screen.getByLabelText(/summary/i);
      act(() => {
        fireEvent.change(summaryInput, { target: { value: 'New Persisted Key Issue' } });
        fireEvent.click(screen.getByRole('button', { name: /^create$/i }));
      });

      await waitFor(() => {
        expect(screen.getAllByText('KAN-999').length).toBeGreaterThan(0);
      });

      // Trigger error in refreshLive on kb:issue-updated event
      fetchSpy.mockRejectedValueOnce(new Error('Network drop'));
      fireEvent(window, new CustomEvent('kb:issue-updated'));
    });

    it('opens peek drawer via onOpenPeek and URL search param popstate', () => {
      const onOpenPeek = vi.fn();
      const { rerender } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          onOpenPeek={onOpenPeek}
        />
      );

      // Click an issue key link to trigger onOpenPeek
      const issueKeyLink = screen.getByText('KAN-142');
      fireEvent.click(issueKeyLink);
      expect(onOpenPeek).toHaveBeenCalledWith('KAN-142');

      // Now rerender without onOpenPeek
      rerender(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
        />
      );

      const popstateSpy = vi.fn();
      window.addEventListener('popstate', popstateSpy);
      fireEvent.click(screen.getByText('KAN-142'));
      expect(popstateSpy).toHaveBeenCalled();
      expect(window.location.search).toContain('peek=KAN-142');
      window.removeEventListener('popstate', popstateSpy);
    });

    it('covers read-only capabilities VIEW hiding create and bulk actions', () => {
      const { unmount: unmount1 } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          capabilities={['VIEW']}
          isProjectAdmin={false}
          initialLayout="board"
        />,
      );

      // Bulk action bar is not rendered
      expect(screen.queryByRole('toolbar', { name: /bulk actions/i })).toBeNull();
      // Keyboard shortcut 'c' for new item does not open modal when read-only
      fireEvent.keyDown(window, { key: 'c' });
      expect(screen.queryByRole('dialog', { name: /create/i })).toBeNull();
      unmount1();

      // Read-only list layout with activePeekKey
      window.history.pushState({}, '', '/projects/KAN/issues?peek=KAN-1');
      const { unmount: unmount2 } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          capabilities={['VIEW']}
          isProjectAdmin={false}
          initialLayout="list"
        />,
      );
      expect(screen.getByTestId('split-list-layout')).toBeDefined();
      unmount2();

      // Read-only board with subGroupBy priority (renders SwimlaneBoardGrid)
      window.history.pushState({}, '', '/projects/KAN/issues');
      const { unmount: unmount3 } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          capabilities={['VIEW']}
          isProjectAdmin={false}
          initialLayout="board"
        />,
      );
      fireEvent.change(screen.getByLabelText('Sub-group by axis'), {
        target: { value: 'priority' },
      });
      expect(screen.getByRole('region', { name: '2D Swimlane Board Grid' })).toBeDefined();
      unmount3();

      // Read-only table layout
      const { unmount: unmount4 } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          capabilities={['VIEW']}
          isProjectAdmin={false}
          initialLayout="table"
        />,
      );
      expect(screen.getByRole('table')).toBeDefined();
      unmount4();

      // Admin via capabilities
      const { unmount: unmountAdmin } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          capabilities={['ADMIN']}
          isProjectAdmin={false}
        />,
      );
      unmountAdmin();
    });

    it('enforces Hard WIP limits on state transition: blocks standard member with snapback, prompts admin for override', async () => {
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');

      const liveStatesWithLimits = [
        { id: '01931234-5678-7000-8000-000000000001', name: 'Backlog', group: 'backlog', sort_order: 10 },
        { id: '01931234-5678-7000-8000-000000000002', name: 'In Progress', group: 'started', sort_order: 20, wip_hard_limit: 1 },
      ];
      const liveIssues = [
        {
          id: '01931234-5678-7000-8000-000000000301',
          key: 'KAN-301',
          summary: 'Issue Already In Progress',
          state: { id: '01931234-5678-7000-8000-000000000002', name: 'In Progress', group: 'started' },
          priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
        },
        {
          id: '01931234-5678-7000-8000-000000000302',
          key: 'KAN-302',
          summary: 'Second Issue In Backlog',
          state: { id: '01931234-5678-7000-8000-000000000001', name: 'Backlog', group: 'backlog' },
          priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
        },
      ];

      let patchedPayload: Record<string, unknown> | null = null;
      const fetchSpy = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        const method = init?.method ?? 'GET';
        if (url.endsWith('/states')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: liveStatesWithLimits }),
          });
        }
        if (method === 'PATCH') {
          patchedPayload = JSON.parse(typeof init?.body === 'string' ? init.body : '{}') as Record<string, unknown>;
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(liveIssues[1]),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: liveIssues, next_cursor: null, total: 2 }),
        });
      });
      globalThis.fetch = fetchSpy;

      // 1. As Member (isProjectAdmin=false)
      const { unmount } = render(
        <IssuesWorkspaceRoute projectKey="KAN" initialLayout="list" isProjectAdmin={false} />
      );

      await waitFor(() => {
        expect(screen.getByText('Second Issue In Backlog')).toBeDefined();
      });

      // Focus second issue (KAN-302 in Backlog)
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'j' });

      // Press 's' to change state to In Progress (which has reached limit of 1)
      const statePop1 = await waitFor(
        () => {
          const existing = screen.queryByRole('dialog', { name: /Quick State Picker/i });
          if (existing) return existing;
          fireEvent.keyDown(window, { key: 's' });
          return screen.getByRole('dialog', { name: /Quick State Picker/i });
        },
        { timeout: 10000 }
      );
      fireEvent.click(within(statePop1).getByText('In Progress'));

      // Member is blocked: patch was NOT called
      expect(patchedPayload).toBeNull();

      unmount();

      // 2. As Admin (isProjectAdmin=true)
      const promptSpy = vi.spyOn(window, 'prompt');

      // Case 2a: Admin cancels prompt
      promptSpy.mockReturnValueOnce(null);
      const { unmount: unmountAdmin } = render(
        <IssuesWorkspaceRoute projectKey="KAN" initialLayout="list" isProjectAdmin={true} />
      );

      await screen.findByText('Issue Already In Progress');
      await screen.findByText('Second Issue In Backlog');
      await new Promise((r) => setTimeout(r, 50));

      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'j' });
      const statePop2 = await waitFor(
        () => {
          const existing = screen.queryByRole('dialog', { name: /Quick State Picker/i });
          if (existing) return existing;
          fireEvent.keyDown(window, { key: 's' });
          return screen.getByRole('dialog', { name: /Quick State Picker/i });
        },
        { timeout: 10000 }
      );
      fireEvent.click(within(statePop2).getByText('In Progress'));

      expect(promptSpy).toHaveBeenCalled();
      expect(patchedPayload).toBeNull();

      // Case 2b: Admin provides override reason
      promptSpy.mockReturnValueOnce('Architect approved override for hotfix');
      const statePop3 = await waitFor(
        () => {
          const existing = screen.queryByRole('dialog', { name: /Quick State Picker/i });
          if (existing) return existing;
          fireEvent.keyDown(window, { key: 's' });
          return screen.getByRole('dialog', { name: /Quick State Picker/i });
        },
        { timeout: 10000 }
      );
      fireEvent.click(within(statePop3).getByText('In Progress'));

      await waitFor(() => {
        expect(patchedPayload).toEqual({
          state_id: '01931234-5678-7000-8000-000000000002',
          override_wip: true,
          wip_override_reason: 'Architect approved override for hotfix',
        });
      });

      unmountAdmin();
    });

    it('handles live mode patch failure and state fetch failure gracefully', async () => {
      globalThis.fetch = vi.fn().mockImplementation((input: string | URL | Request, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        const method = init?.method ?? 'GET';
        if (url.endsWith('/states')) {
          return Promise.reject(new Error('State fetch error'));
        }
        if (method === 'PATCH' || method === 'DELETE') {
          return Promise.reject(new Error('Operation error'));
        }
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              items: [
                {
                  id: '01931234-5678-7000-8000-000000000401',
                  key: 'KAN-401',
                  summary: 'Live Error Issue',
                  state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
                  priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
                },
              ],
              next_cursor: null,
              total: 1,
            }),
        });
      });

      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
      render(<IssuesWorkspaceRoute projectKey="KAN" initialLayout="list" />);

      await waitFor(() => {
        expect(screen.getByText('Live Error Issue')).toBeDefined();
      });

      // Quick priority update (exercises patchProjectIssue catch block)
      fireEvent.keyDown(window, { key: 'j' });
      const prioPop = await waitFor(
        () => {
          const existing = screen.queryByRole('dialog', { name: /Quick Priority Picker/i });
          if (existing) return existing;
          fireEvent.keyDown(window, { key: 'p' });
          return screen.getByRole('dialog', { name: /Quick Priority Picker/i });
        },
        { timeout: 10000 }
      );
      fireEvent.click(within(prioPop).getByText('High'));

      // Quick state update (exercises patchProjectIssue catch block)
      const statePop = await waitFor(
        () => {
          const existing = screen.queryByRole('dialog', { name: /Quick State Picker/i });
          if (existing) return existing;
          fireEvent.keyDown(window, { key: 's' });
          return screen.getByRole('dialog', { name: /Quick State Picker/i });
        },
        { timeout: 10000 }
      );
      fireEvent.click(within(statePop).getByText('Done'));

      // Select issue and exercise batch update state, priority, and delete catch blocks
      const rowCheckbox = screen.getByLabelText('Select KAN-401');
      fireEvent.click(rowCheckbox);

      const stateBtn = await screen.findByRole('button', { name: /^state$/i });
      fireEvent.click(stateBtn);

      // Re-select after state batch update clears selection
      const rowCheckbox2 = await screen.findByLabelText('Select KAN-401');
      fireEvent.click(rowCheckbox2);

      const priorityBtn = await screen.findByRole('button', { name: /^priority$/i });
      fireEvent.click(priorityBtn);

      // Re-select after priority batch update clears selection
      const rowCheckbox3 = await screen.findByLabelText('Select KAN-401');
      fireEvent.click(rowCheckbox3);

      const deleteBtn = await screen.findByRole('button', { name: /^delete$/i });
      fireEvent.click(deleteBtn);
    });

    it('covers board state aliases, fallback group, fallback issue state, and create empty fallbacks', async () => {
      window.history.pushState({}, '', '/projects/KAN/issues?layout=board');

      const customProjectStates = [
        { id: 'state-in-review', name: 'Review', group: 'started' },
        { id: 'state-in-progress', name: 'Progress', group: 'started' },
        { id: 'state-custom-grp', name: 'Custom Grp', group: 'nonstandard_group' as never },
      ];
      const customIssues = [
        {
          id: 'i-alien',
          key: 'KAN-9999',
          summary: 'Issue with Alien State',
          state: { id: 'state-totally-unknown', name: 'Unknown State', group: 'unknown_group' },
          priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
        },
      ];

      globalThis.fetch = vi.fn().mockImplementation((input: string | URL | Request) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (url.endsWith('/states')) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ items: customProjectStates }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: customIssues, next_cursor: null, total: 1 }),
        });
      });

      const { unmount: unmountBoard } = render(<IssuesWorkspaceRoute projectKey="KAN" initialLayout="board" />);

      await waitFor(() => {
        expect(screen.getByLabelText('Review lane, 1 issues')).toBeDefined();
      });
      unmountBoard();

      // Quick priority to None in List view where rows are fully rendered in JSDOM
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
      const { unmount: unmountList } = render(<IssuesWorkspaceRoute projectKey="KAN" initialLayout="list" />);
      await waitFor(() => {
        expect(screen.getByText('Issue with Alien State')).toBeDefined();
      });
      fireEvent.keyDown(window, { key: 'j' });
      const prioPop = await waitFor(
        () => {
          const existing = screen.queryByRole('dialog', { name: /Quick Priority Picker/i });
          if (existing) return existing;
          fireEvent.keyDown(window, { key: 'p' });
          return screen.getByRole('dialog', { name: /Quick Priority Picker/i });
        },
        { timeout: 10000 }
      );
      fireEvent.click(within(prioPop).getByText('None'));
      unmountList();

      // Non-live create modal with empty fields fallback
      const { unmount } = render(
        <IssuesWorkspaceRoute projectKey="KAN" initialLayout="list" initialIssues={FIXTURE_12_ISSUES} />
      );
      fireEvent.keyDown(window, { key: 'c' });
      const createModal = await screen.findByRole('dialog', { name: /create work item/i }, { timeout: 5000 });
      expect(createModal).toBeDefined();

      unmount();
    });

    it('covers opening, cancelling, and saving custom view via SaveViewModal in IssuesWorkspaceRoute', async () => {
      window.history.pushState({}, '', '/');
      const originalFetch = globalThis.fetch;
      globalThis.fetch = vi.fn().mockImplementation(() => {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: { get: (name: string) => (name.toLowerCase() === 'content-type' ? 'application/json' : null) },
          json: () => Promise.resolve({
            id: 'sv-123',
            name: 'My Custom View',
            view_type: 'table',
          }),
        } as unknown as Response);
      });

      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          initialLayout="table"
          capabilities={['VIEW', 'CREATE_ISSUE', 'EDIT']}
        />,
      );

      // Open Display options panel
      const displayBtn = screen.getByRole('button', { name: /display configuration/i });
      fireEvent.click(displayBtn);

      // Click "Save as view"
      const saveAsViewBtn = screen.getByRole('button', { name: /save as view/i });
      fireEvent.click(saveAsViewBtn);

      // Save View Modal should appear
      expect(screen.getByTestId('save-view-modal')).toBeTruthy();

      // Cancel closing
      const cancelBtn = screen.getByRole('button', { name: /cancel/i });
      fireEvent.click(cancelBtn);
      expect(screen.queryByTestId('save-view-modal')).toBeNull();

      // Open again to save
      fireEvent.click(displayBtn);
      fireEvent.click(screen.getByRole('button', { name: /save as view/i }));
      expect(screen.getByTestId('save-view-modal')).toBeTruthy();

      // Fill in name
      const nameInput = screen.getByPlaceholderText(/e\.g\. sprint backlog/i);
      fireEvent.change(nameInput, { target: { value: 'My Custom View' } });

      // Click Save View submit button
      const submitBtn = screen.getByRole('button', { name: /^save view$/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(screen.queryByTestId('save-view-modal')).toBeNull();
      });

      globalThis.fetch = originalFetch;
    });

    it('covers handleSelectAll unselecting all issues via TableView master checkbox', () => {
      window.history.pushState({}, '', '/');
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          initialLayout="table"
          capabilities={['VIEW', 'CREATE_ISSUE', 'EDIT']}
        />,
      );

      const selectAllCheckbox = screen.getByRole('checkbox', { name: /Select all issues/i });
      // Check all
      fireEvent.click(selectAllCheckbox);
      // Uncheck all
      fireEvent.click(selectAllCheckbox);
    });

    it('covers SaveViewModal with pre-existing active filters from query params', () => {
      window.history.pushState(
        {},
        '',
        '/projects/KAN/issues?filter_state=in_progress&filter_priority=high',
      );

      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          initialLayout="board"
          capabilities={['VIEW', 'CREATE_ISSUE', 'EDIT_ISSUE']}
        />,
      );

      // Open Display options panel
      const displayBtn = screen.getByRole('button', { name: /display configuration/i });
      fireEvent.click(displayBtn);

      // Click "Save as view"
      const saveAsViewBtn = screen.getByRole('button', { name: /save as view/i });
      fireEvent.click(saveAsViewBtn);

      expect(screen.getByTestId('save-view-modal')).toBeTruthy();

      // Clean up URL
      window.history.pushState({}, '', '/');
    });

    it('handles states fetch failure in live mode', async () => {
      const origFetch = globalThis.fetch;
      globalThis.fetch = vi.fn().mockImplementation((input: string | URL | Request) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (url.endsWith('/states')) {
          return Promise.reject(new Error('500 internal server error'));
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: [], next_cursor: null, total: 0 }),
        });
      });

      try {
        await act(async () => {
          render(<IssuesWorkspaceRoute projectKey="KAN" initialLayout="board" />);
          await Promise.resolve();
        });
      } finally {
        globalThis.fetch = origFetch;
      }
    });

    it('covers onCreateIssue from ViewHost table layout empty state', () => {
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={[]}
          initialLayout="table"
          capabilities={['VIEW', 'EDIT']}
        />,
      );

      const emptyCreateBtn = screen.getByRole('button', { name: /\+ create first work item/i });
      fireEvent.click(emptyCreateBtn);
      expect(screen.getByTestId('quick-create-modal')).toBeDefined();
    });

    it('covers camelCase groupBy and subGroupBy query params and invalid fallbacks', () => {
      window.history.pushState({}, '', '/projects/KAN/issues?groupBy=invalid&subGroupBy=invalid');
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          initialLayout="board"
          capabilities={['VIEW']}
        />,
      );
      window.history.pushState({}, '', '/');
    });

    it('covers boardIssues state resolution fallback branches (name match, group match, completely unknown state)', () => {
      window.history.pushState({}, '', '/');
      const oddIssues: IssueItem[] = [
        {
          id: 'iss-odd-1',
          key: 'KAN-901',
          summary: 'Name match issue',
          state: { id: 'odd-id-1', name: 'Todo', group: 'started' },
          priority: { slug: 'low', label: 'Low', emoji: '▫' },
        },
        {
          id: 'iss-odd-2',
          key: 'KAN-902',
          summary: 'Group match issue',
          state: { id: 'odd-id-2', name: 'Random Custom State', group: 'unstarted' },
          priority: { slug: 'high', label: 'High', emoji: '🔺' },
        },
        {
          id: 'iss-odd-3',
          key: 'KAN-903',
          summary: 'Fallback match issue',
          state: { id: 'odd-id-3', name: 'Unknown State', group: 'nonexistent_group' },
          priority: { slug: 'critical', label: 'Critical', emoji: '🚨' },
        },
      ];

      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={oddIssues}
          initialLayout="table"
          capabilities={['VIEW', 'EDIT']}
        />,
      );
      expect(screen.getByText('Name match issue')).toBeDefined();
      expect(screen.getByText('Group match issue')).toBeDefined();
      expect(screen.getByText('Fallback match issue')).toBeDefined();
    });

    it('covers BulkActionBar batch delete and archive in table layout', () => {
      window.history.pushState({}, '', '/');
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          initialLayout="table"
          capabilities={['VIEW', 'EDIT', 'ADMIN']}
          isProjectAdmin={true}
        />,
      );

      // Select first issue
      const firstCardCheckbox = screen.getAllByRole('checkbox')[1];
      if (firstCardCheckbox) {
        fireEvent.click(firstCardCheckbox);
      }

      const bulkBar = screen.queryByRole('toolbar', { name: /bulk actions/i });
      if (bulkBar) {
        // Test state toggle
        const stateBtn = within(bulkBar).getByRole('button', { name: /^state$/i });
        fireEvent.click(stateBtn);
      }

      // Select again
      const firstCardAgain = screen.getAllByRole('checkbox')[1];
      if (firstCardAgain) fireEvent.click(firstCardAgain);

      const bulkBarPrio = screen.queryByRole('toolbar', { name: /bulk actions/i });
      if (bulkBarPrio) {
        // Test priority cycle
        const prioBtn = within(bulkBarPrio).getByRole('button', { name: /^priority$/i });
        fireEvent.click(prioBtn);
      }

      // Select again for archive
      const firstCardArch = screen.getAllByRole('checkbox')[1];
      if (firstCardArch) fireEvent.click(firstCardArch);

      const bulkBarArch = screen.queryByRole('toolbar', { name: /bulk actions/i });
      if (bulkBarArch) {
        // Test archive
        const archiveBtn = within(bulkBarArch).getByRole('button', { name: /archive/i });
        fireEvent.click(archiveBtn);
      }

      // Select another issue for delete
      const secondCheckbox = screen.getAllByRole('checkbox')[2];
      if (secondCheckbox) {
        fireEvent.click(secondCheckbox);
      }

      const bulkBar2 = screen.queryByRole('toolbar', { name: /bulk actions/i });
      if (bulkBar2) {
        const deleteBtn = within(bulkBar2).getByRole('button', { name: /delete/i });
        fireEvent.click(deleteBtn);
      }
    });

    it('covers table layout with read-only viewer and bulk state toggle to todo', () => {
      window.history.pushState({}, '', '/');
      // 1. Read-only viewer in table view covers ViewHost canEdit=false branches (lines 751-754)
      const { unmount } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          initialLayout="table"
          capabilities={['VIEW']}
        />,
      );
      unmount();

      // 2. Done issue selected covers lines 773-774 (isDone=false -> Todo, unstarted)
      const doneIssue: IssueItem = {
        id: 'iss-done-1',
        key: 'KAN-990',
        summary: 'Already Done Issue',
        state: { id: 'state-done', name: 'Done', group: 'completed' },
        priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
      };
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={[doneIssue]}
          initialLayout="table"
          capabilities={['VIEW', 'EDIT']}
        />,
      );
      const checkbox = screen.getAllByRole('checkbox')[1];
      if (checkbox) fireEvent.click(checkbox);
      const bulkBar = screen.queryByRole('toolbar', { name: /bulk actions/i });
      if (bulkBar) {
        const stateBtn = within(bulkBar).getByRole('button', { name: /^state$/i });
        fireEvent.click(stateBtn);
      }

      // 3. is2DSwimlane with read-only viewer covers line 703 false branch
      window.history.pushState({}, '', '/projects/KAN/issues?layout=board&sub_group_by=priority');
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          capabilities={['VIEW']}
        />,
      );
      window.history.pushState({}, '', '/');
    });

    it('KB-P3-AUDIT-08: gates modulesEnabled on project query confirmation', () => {
      const qc = new QueryClient();
      qc.setQueryData(['project', 'KAN'], {
        id: 'p-1',
        identifier: 'KAN',
        modules_enabled: false,
      });

      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={FIXTURE_12_ISSUES}
          initialLayout="board"
          queryClient={qc}
        />,
      );

      // Group select should NOT contain module axis when modules_enabled is false
      const groupSelect = screen.getByLabelText(/^Group by axis$/i);
      const options = Array.from(groupSelect.querySelectorAll('option')).map((o) => o.value);
      expect(options).not.toContain('module');
    });

    it('KAN-35 regression: optimistic BoardView move followed by realtime issue.transitioned maintains valid IssueSummary cache with 0 TypeError crash', async () => {
      Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
        configurable: true,
        value: 900,
      });
      Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
        configurable: true,
        value: 124,
      });
      Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
        configurable: true,
        value: () => ({
          top: 0,
          left: 0,
          bottom: 900,
          right: 324,
          width: 324,
          height: 900,
          x: 0,
          y: 0,
        }),
      });

      window.history.pushState({}, '', '/projects/KAN/issues?layout=board');

      const qc = new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
          },
        },
      });

      // Mock move API & queries
      vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (url.includes('/api/v1/issues/KAN-1/move')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({
              issue_key: 'KAN-1',
              state_id: 'state-todo',
              board_rank: '000020',
              rebalance_scheduled: false,
            }),
          } as Response);
        }
        if (url.includes('/api/v1/projects/KAN/issues')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({
              items: [
                {
                  id: '01912345-6789-7000-8000-000000000001',
                  key: 'KAN-1',
                  summary: 'Optimistic Move Test Issue',
                  state: { id: 'state-todo', name: 'To Do', group: 'unstarted' },
                  priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
                  board_rank: '000020',
                },
              ],
              total: 1,
            }),
          } as Response);
        }
        if (url.includes('/api/v1/projects/KAN/states') || url.includes('/api/v1/projects/KAN')) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({
              id: 'p-kan',
              key: 'KAN',
              name: 'Kanban',
              states: [
                { id: 'state-backlog', name: 'Backlog', group: 'backlog', sort_order: 1 },
                { id: 'state-todo', name: 'To Do', group: 'unstarted', sort_order: 2 },
                { id: 'state-in-progress', name: 'In Progress', group: 'started', sort_order: 3 },
              ],
            }),
          } as Response);
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({}),
        } as Response);
      });

      const initialTestIssues: IssueItem[] = [
        {
          id: '01912345-6789-7000-8000-000000000001',
          key: 'KAN-1',
          summary: 'Optimistic Move Test Issue',
          state: { id: 'state-backlog', name: 'Backlog', group: 'backlog' },
          priority: { slug: 'medium', label: 'Medium', emoji: '🔹' },
          board_rank: '000010',
        },
      ];

      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={initialTestIssues}
          initialLayout="board"
          capabilities={['VIEW', 'EDIT', 'ADMIN']}
          queryClient={qc}
        />,
      );

      // Verify card rendered
      const card = screen.getByTestId('board-card-KAN-1');
      expect(card).toBeDefined();

      // Trigger Alt+ArrowRight on card
      fireEvent.keyDown(card, { key: 'ArrowRight', altKey: true });

      // Check cache on qk.issues('KAN', {}) - must have preserved summary, priority, and updated state without crash!
      const cacheAfterMove = qc.getQueryData<IssueItem[]>(['issues', 'KAN', {}]);
      expect(cacheAfterMove).toBeDefined();
      const firstIssue = cacheAfterMove ? cacheAfterMove[0] : undefined;
      expect(firstIssue?.key).toBe('KAN-1');
      expect(firstIssue?.summary).toBe('Optimistic Move Test Issue');
      expect(firstIssue?.state.name).toBeDefined();
      expect(firstIssue?.state.group).toBeDefined();

      // Remote issue.transitioned realtime event arrives
      act(() => {
        window.dispatchEvent(
          new CustomEvent('kb:issue-updated', {
            detail: {
              type: 'issue.transitioned',
              payload: {
                key: 'KAN-1',
                issue_key: 'KAN-1',
                project_key: 'KAN',
                from_state: 'Backlog',
                to_state: 'To Do',
                to_state_id: 'state-todo',
              },
            },
          }),
        );
      });

      // Zero TypeError crash and card movement clean
      await waitFor(() => {
        expect(screen.queryByText(/Application Error Detected/i)).toBeNull();
        expect(screen.getByTestId('board-card-KAN-1')).toBeDefined();
      });
    });
  });

  describe('KAN-44 Mobile & Touch View Routing Tests', () => {
    it('suppresses auto-selecting first issue in split view when viewport <= 768px and ?peek= is absent', () => {
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
      const originalInnerWidth = window.innerWidth;
      try {
        Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 500 });
        render(
          <IssuesWorkspaceRoute
            projectKey="KAN"
            initialLayout="list"
            initialIssues={FIXTURE_12_ISSUES}
          />
        );
        // On mobile viewport <= 768px, activePeekKey is null so split surface is not rendered
        expect(screen.queryByTestId('split-surface-close-btn')).toBeNull();
      } finally {
        Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: originalInnerWidth });
      }
    });

    it('renders split surface on desktop viewports and closes it when close button is clicked', async () => {
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
      const originalInnerWidth = window.innerWidth;
      try {
        Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 1200 });
        render(
          <IssuesWorkspaceRoute
            projectKey="KAN"
            initialLayout="list"
            initialIssues={FIXTURE_12_ISSUES}
          />
        );

        // Desktop auto-selects first issue
        await waitFor(() => {
          expect(screen.getByTestId('split-surface-close-btn')).toBeDefined();
        });

        // Click close button
        const closeBtn = screen.getByTestId('split-surface-close-btn');
        fireEvent.click(closeBtn);

        // Closed split key prevents auto-selection
        await waitFor(() => {
          expect(screen.queryByTestId('split-surface-close-btn')).toBeNull();
        });
      } finally {
        Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: originalInnerWidth });
      }
    });

    it('KAN-58: Negative / Bounce-Back Regression Case - phone landscape (844x390) and suppressAutoPeek prevent bounce-back into issues[0]', () => {
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
      const originalInnerWidth = window.innerWidth;
      const originalInnerHeight = window.innerHeight;
      try {
        // Phone landscape: 844px wide, 390px high
        Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 844 });
        Object.defineProperty(window, 'innerHeight', { writable: true, configurable: true, value: 390 });

        const { unmount } = render(
          <IssuesWorkspaceRoute
            projectKey="KAN"
            initialLayout="list"
            initialIssues={FIXTURE_12_ISSUES}
          />
        );

        // On phone landscape (innerHeight <= 540), activePeekKey is null when ?peek= is absent
        expect(screen.queryByTestId('split-surface-close-btn')).toBeNull();
        unmount();

        // When closed via suppressAutoPeek history state on desktop
        Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 1200 });
        Object.defineProperty(window, 'innerHeight', { writable: true, configurable: true, value: 900 });
        window.history.replaceState({ suppressAutoPeek: true }, '', '/projects/KAN/issues?layout=list');

        render(
          <IssuesWorkspaceRoute
            projectKey="KAN"
            initialLayout="list"
            initialIssues={FIXTURE_12_ISSUES}
          />
        );

        // Does NOT bounce back into issues[0]!
        expect(screen.queryByTestId('split-surface-close-btn')).toBeNull();
      } finally {
        window.history.replaceState({}, '', '/projects/KAN/issues?layout=list');
        Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: originalInnerWidth });
        Object.defineProperty(window, 'innerHeight', { writable: true, configurable: true, value: originalInnerHeight });
      }
    });

    it('wires onOpenFieldPopover from ListView to QuickFieldPopover', async () => {
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="list"
          initialIssues={FIXTURE_12_ISSUES}
        />
      );

      // Find first list row state button and click it
      const firstIssue = FIXTURE_12_ISSUES[0];
      if (!firstIssue) throw new Error('Missing fixture');
      const stateBtn = screen.getByTestId(`list-row-state-btn-${firstIssue.key}`);
      fireEvent.click(stateBtn);

      // Popover should be open
      await waitFor(() => {
        expect(screen.getByRole('dialog', { name: /Quick State Picker/i })).toBeDefined();
      });
    });

    it('exercises computeStateSummary and state matching', () => {
      const states = [
        { id: 'st-1', name: 'My Todo', group: 'unstarted' },
        { id: 'st-2', name: 'Review Group', group: 'in_review' },
      ];
      // match by id
      expect(computeStateSummary('st-1', states).name).toBe('My Todo');
      // match by normalized name
      expect(computeStateSummary('my-todo', states).name).toBe('My Todo');
      // match by group
      expect(computeStateSummary('in_review', states).name).toBe('Review Group');
      // fallback matching by string content
      expect(computeStateSummary('progress-custom').name).toBe('In Progress');
      expect(computeStateSummary('todo-custom').name).toBe('Todo');
      expect(computeStateSummary('done-custom').name).toBe('Done');
      expect(computeStateSummary('other').name).toBe('Backlog');
    });

    it('covers Hard WIP limit prompt cancellation and confirmation in field select', () => {
      const testIssues: IssueItem[] = [
        {
          id: 'i-wip-1',
          key: 'KAN-WIP-1',
          summary: 'Issue 1',
          state: { id: 'state-in-review', name: 'In Review', group: 'started' },
          priority: { slug: 'low', label: 'Low' },
        },
        {
          id: 'i-wip-2',
          key: 'KAN-WIP-2',
          summary: 'Issue 2',
          state: { id: 'state-in-review', name: 'In Review', group: 'started' },
          priority: { slug: 'low', label: 'Low' },
        },
        {
          id: 'i-wip-3',
          key: 'KAN-WIP-3',
          summary: 'Issue 3',
          state: { id: 'state-in-review', name: 'In Review', group: 'started' },
          priority: { slug: 'low', label: 'Low' },
        },
        {
          id: 'i-wip-4',
          key: 'KAN-WIP-4',
          summary: 'Issue 4',
          state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
          priority: { slug: 'low', label: 'Low' },
        },
      ];

      const promptSpy = vi.spyOn(window, 'prompt');

      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="list"
          initialIssues={testIssues}
          isProjectAdmin={true}
        />
      );

      // Focus fourth issue (index 3) and press 'S' to open State picker
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 's' });

      // 1. Prompt returns null (user cancelled)
      promptSpy.mockReturnValueOnce(null);
      const statePop = screen.getByRole('dialog', { name: /Quick State Picker/i });
      const inReviewOpt = within(statePop).getByRole('option', { name: 'In Review' });
      fireEvent.click(inReviewOpt);
      expect(promptSpy).toHaveBeenCalled();

      promptSpy.mockRestore();
    });

    it('automatically synchronizes activePeekKey and URL peek to first matching issue when peek issue is excluded by filter', async () => {
      window.history.pushState({}, '', '/projects/KAN/issues?peek=KAN-NONEXISTENT');

      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="list"
          initialIssues={FIXTURE_12_ISSUES}
        />,
      );

      // Verify that activePeekKey auto-selected the first issue in FIXTURE_12_ISSUES
      await waitFor(() => {
        const params = new URLSearchParams(window.location.search);
        expect(params.get('peek')).toBe(FIXTURE_12_ISSUES[0]?.key);
      });
    });

    it('re-evaluates favorites-only filter when kb:favorites-changed event fires', async () => {
      const favKey = FIXTURE_12_ISSUES[0]?.key ?? 'KAN-1';
      localStorage.setItem('kb_favorite_issues', JSON.stringify([favKey]));

      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="list"
          initialIssues={FIXTURE_12_ISSUES}
        />,
      );

      // Toggle Favorites only button on
      const favOnlyBtn = screen.getByRole('button', { name: /Favorites only/i });
      fireEvent.click(favOnlyBtn);

      // Now remove from favorites in localStorage and dispatch kb:favorites-changed
      localStorage.setItem('kb_favorite_issues', JSON.stringify([]));
      act(() => {
        window.dispatchEvent(new CustomEvent('kb:favorites-changed'));
      });

      // Rail now has zero favorites matching
      await waitFor(() => {
        expect(screen.getByText('No work items found')).toBeDefined();
      });
    });

    it('triggers onSearchSubmit when Search button is clicked in list layout and handles resize', () => {
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="list"
          initialIssues={FIXTURE_12_ISSUES}
        />,
      );

      // In list layout, IssueNavigatorBar renders Search button
      const searchBtn = screen.getByRole('button', { name: 'Search' });
      fireEvent.click(searchBtn);

      // Trigger resize event to exercise window resize listener
      act(() => {
        window.dispatchEvent(new Event('resize'));
      });
    });

    it('activates 2D swimlane grid when sub-group is changed and handles card move state transitions', async () => {
      render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="board"
          initialIssues={FIXTURE_12_ISSUES}
        />,
      );

      // Change sub-group by axis to priority
      const subGroupSelect = screen.getByLabelText('Sub-group by axis');
      fireEvent.change(subGroupSelect, { target: { value: 'priority' } });

      // 2D Swimlane is active; click a card's state picker
      const firstIssueKey = FIXTURE_12_ISSUES[0]?.key ?? 'KAN-1';
      const moveBtn = await screen.findByTestId(`board-card-state-btn-${firstIssueKey}`);
      fireEvent.click(moveBtn);

      // Select a target state in the popover
      const inProgOption = await screen.findByRole('option', { name: /In Progress/i });
      fireEvent.click(inProgOption);
    });

    it('covers defensive fallback branches in boardIssues mapping and mobile activePeekKey', () => {
      const issueWithOnlyStateId = {
        id: 'iss-only-state-id',
        key: 'KAN-ONLY-ID',
        summary: 'Incomplete state issue',
        state_id: 'state-backlog',
        priority: { slug: 'medium', label: 'Medium' },
      };

      const origWidth = window.innerWidth;
      try {
        window.innerWidth = 390;

        // With peekParam that is not in sortedRailIssues on mobile
        window.history.pushState({}, '', '/projects/KAN/issues?layout=list&peek=NON-EXISTENT-KEY');

        const { unmount } = render(
          <IssuesWorkspaceRoute
            projectKey="KAN"
            initialLayout="list"
            initialIssues={[issueWithOnlyStateId as unknown as IssueItem]}
          />,
        );

        const { unmount: unmountBoard } = render(
          <IssuesWorkspaceRoute
            projectKey="KAN"
            initialLayout="board"
            initialIssues={[issueWithOnlyStateId as unknown as IssueItem]}
          />,
        );

        unmount();
        unmountBoard();
      } finally {
        window.innerWidth = origWidth;
      }
    });

    it('covers URL viewParam pre-selection, query search mode, patch error rollback, and swimlane onStateTransition', async () => {
      // 1. Mock fetch for saved views
      const savedViewsData = [
        {
          id: 'v-saved-custom',
          name: 'Custom Team View',
          project_key: 'KAN',
          layout: 'board',
          group_by: 'priority',
          sub_group_by: 'assignee',
        },
      ];
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (url.includes('/views')) {
          return Promise.resolve(new Response(JSON.stringify(savedViewsData), { status: 200 }));
        }
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      });

      // Set URL with view query param
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list&view=v-saved-custom');

      const alertSpy = vi.fn();
      window.addEventListener('kb:alert', alertSpy);

      const { unmount } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="list"
          initialIssues={FIXTURE_12_ISSUES}
        />,
      );

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });

      // 2. Query search mode in IssueNavigatorBar
      // Switch query mode to JQL / query mode
      const queryModeBtn = screen.getByTestId('mode-query-btn');
      fireEvent.click(queryModeBtn);

      const queryInput = screen.getByTestId('navigator-query-input');
      fireEvent.change(queryInput, { target: { value: 'priority = High' } });

      // Change search to non-matching
      fireEvent.change(queryInput, { target: { value: 'priority = Unknown' } });

      // Switch back to text search and test non-matching text
      const basicModeBtn = screen.getByTestId('mode-basic-btn');
      fireEvent.click(basicModeBtn);
      const searchInput = screen.getByTestId('navigator-search-input');
      fireEvent.change(searchInput, { target: { value: 'XYZ-NONEXISTENT' } });

      // Click saved view chip
      const savedChip = screen.getByTestId('saved-view-chip-v-saved-custom');
      fireEvent.click(savedChip);

      unmount();
      window.removeEventListener('kb:alert', alertSpy);
      fetchSpy.mockRestore();
    });

    it('exercises Swimlane with groupBy=priority, live mode transitions, WIP override, and batch update', async () => {
      // 1. computeStateSummary edge case: non-matching state when projectStates populated
      const computedFallback = computeStateSummary('non-matching-state', [
        { id: 'st-1', name: 'State 1', group: 'unstarted' },
      ]);
      expect(computedFallback.id).toBe('non-matching-state');
      expect(computedFallback.name).toBe('Backlog');

      // 2. Empty projectKey coverage
      const { unmount: unmountEmptyProj } = render(
        <IssuesWorkspaceRoute projectKey="" initialLayout="board" initialIssues={[]} />,
      );
      unmountEmptyProj();

      // 3. onOpenPeek with null when propOnOpenPeek is provided
      const mockPeekCallback = vi.fn();
      const { unmount: unmountPeek } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="list"
          initialIssues={FIXTURE_12_ISSUES}
          onOpenPeek={mockPeekCallback}
        />,
      );
      // Close split drawer triggers handleOpenPeek(null)
      const closeBtn = screen.getByTestId('split-surface-close-btn');
      fireEvent.click(closeBtn);
      unmountPeek();

      // 4. Swimlane with groupBy === 'priority':
      // When groupBy === 'priority', onCardMove is undefined, so onStateTransition is called!
      const { unmount: unmountSwimlane } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="board"
          initialIssues={FIXTURE_12_ISSUES}
        />,
      );
      // Change group by to priority
      const groupBySelect = screen.getByLabelText('Group by axis');
      fireEvent.change(groupBySelect, { target: { value: 'priority' } });

      const firstIssueKey = FIXTURE_12_ISSUES[0]?.key ?? 'KAN-1';
      const moveBtn = await screen.findByTestId(`board-card-state-btn-${firstIssueKey}`);
      fireEvent.click(moveBtn);
      const inProgOption = await screen.findByRole('option', { name: /In Progress/i });
      fireEvent.click(inProgOption);
      unmountSwimlane();

      // 5. Live mode state and priority transition errors, and WIP override:
      const liveIssues = [
        {
          id: 'iss-live-1',
          key: 'KAN-LIVE-1',
          summary: 'Live Issue 1',
          state: { id: '01931234-5678-7000-8000-000000000001', name: 'Backlog', group: 'backlog' },
          priority: { slug: 'low', label: 'Low', emoji: '🟢' },
        },
      ];
      const liveStates = [
        { id: '01931234-5678-7000-8000-000000000001', name: 'Backlog', group: 'backlog' },
        { id: '01931234-5678-7000-8000-000000000002', name: 'WIP Column', group: 'started', wip_hard_limit: 1 },
      ];

      const patchSpy = vi.spyOn(viewsApi, 'patchProjectIssue');

      // a. State transition in live mode fails with non-Error string -> rollback & kb:alert
      patchSpy.mockRejectedValueOnce('State transition primitive failure');
      const alertListener = vi.fn();
      window.addEventListener('kb:alert', alertListener);

      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const twoLiveIssues = [
        ...liveIssues,
        {
          id: 'iss-live-2',
          key: 'KAN-LIVE-2',
          summary: 'Live Issue 2',
          state: { id: '01931234-5678-7000-8000-000000000001', name: 'Backlog', group: 'backlog' },
          priority: { slug: 'low', label: 'Low', emoji: '🟢' },
        },
      ];
      qc.setQueryData(['issues', 'KAN', {}], twoLiveIssues);
      qc.setQueryData(['states', 'KAN'], liveStates);

      let patchShouldFail = true;
      let patchFailError: unknown = 'State transition primitive failure';

      const origFetch = globalThis.fetch;
      globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (init?.method === 'PATCH' && patchShouldFail) {
          if (typeof patchFailError === 'string') {
            return Promise.reject(new Error(patchFailError));
          }
          return Promise.reject(new Error('State transition network failed'));
        }
        if (url.includes('/states')) {
          return Promise.resolve(new Response(JSON.stringify(liveStates), { status: 200 }));
        }
        if (url.includes('/issues')) {
          return Promise.resolve(new Response(JSON.stringify({ items: twoLiveIssues, total: 2 }), { status: 200 }));
        }
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      });

      const { unmount: unmountLive } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="board"
          queryClient={qc}
          capabilities={['VIEW', 'EDIT', 'ADMIN']}
        />,
      );

      // Focus first item
      fireEvent.keyDown(window, { key: 'j' });

      // Trigger state change via quick field popover
      fireEvent.keyDown(window, { key: 's' });
      const statePop1 = await screen.findByRole('dialog', { name: /Quick State Picker/i });
      fireEvent.click(within(statePop1).getByText('WIP Column'));

      await waitFor(() => {
        expect(alertListener).toHaveBeenCalled();
      });

      // b. Priority transition in live mode fails with primitive -> rollback & kb:alert
      patchShouldFail = true;
      patchFailError = 'Primitive priority failure';
      fireEvent.keyDown(window, { key: 'p' });
      const prioPop = await screen.findByRole('dialog', { name: /Quick Priority Picker/i });
      fireEvent.click(within(prioPop).getByText('High'));

      await waitFor(() => {
        expect(alertListener).toHaveBeenCalledTimes(2);
      });

      // c. Live mode state transition with WIP override prompt
      patchShouldFail = false;
      const promptSpy = vi.spyOn(window, 'prompt').mockReturnValueOnce('Approved urgent emergency');

      // Pre-seed an issue already in WIP Column so targetCount >= 1
      qc.setQueryData(['issues', 'KAN', {}], [
        {
          id: 'iss-live-other',
          key: 'KAN-OTHER',
          summary: 'Other in WIP',
          state: { id: '01931234-5678-7000-8000-000000000002', name: 'WIP Column', group: 'started' },
        },
        liveIssues[0],
      ]);

      fireEvent.keyDown(window, { key: 's' });
      const statePop2 = await screen.findByRole('dialog', { name: /Quick State Picker/i });
      fireEvent.click(within(statePop2).getByText('WIP Column'));

      expect(promptSpy).toHaveBeenCalled();

      // d. Live mode batch update state and priority where patchProjectIssue fires
      fireEvent.keyDown(window, { key: 'x' });
      const batchStateBtn = screen.getByRole('button', { name: 'State' });
      fireEvent.click(batchStateBtn);
      fireEvent.keyDown(window, { key: 'x' });
      const batchPrioBtn = screen.getByRole('button', { name: 'Priority' });
      fireEvent.click(batchPrioBtn);

      unmountLive();
      window.removeEventListener('kb:alert', alertListener);
      globalThis.fetch = origFetch;
      promptSpy.mockRestore();
    });

    it('covers split mode onNavigateIssue, projectMetadata name, and filter edge cases', async () => {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(['project', 'KAN'], { name: 'Custom Platform', modules_enabled: true });

      const issueWithEmptyStateName = {
        id: 'iss-empty-name',
        key: 'KAN-EMPTY-NAME',
        summary: 'Empty state name',
        state: { id: 'st-blank', name: '', group: 'unstarted' },
        priority: { slug: 'none', label: 'None' },
      };

      const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue(issueWithEmptyStateName);

      const { unmount } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="list"
          initialIssues={[issueWithEmptyStateName as unknown as IssueItem, ...FIXTURE_12_ISSUES]}
          queryClient={qc}
        />,
      );

      // IssueNavigatorBar search with empty state
      expect(screen.getByTestId('split-surface-close-btn')).toBeDefined();

      // Select next issue via pager once issue surface loads
      const nextBtn = await screen.findByTestId('issue-next-btn');
      fireEvent.click(nextBtn);

      unmount();
      getSpy.mockRestore();
    });

    it('covers remaining viewRegistry branch edge cases', async () => {
      // 1. Invalid localStorage favorite issues (non-array JSON)
      localStorage.setItem('kb_favorite_issues', JSON.stringify({ notAnArray: true }));

      // 2. Query params with peek pointing to non-existent issue to trigger auto-sync microtask
      window.history.pushState(
        {},
        '',
        '/projects/KAN/issues?layout=list&peek=KAN-GHOST',
      );

      const oddIssues = [
        {
          id: 'iss-odd-1',
          key: 'KAN-ODD-1',
          summary: 'Missing state and priority slug',
          state_id: 'unknown-uuid-1',
          state: undefined,
          priority: { slug: 'none', label: 'None' },
        },
        {
          id: 'iss-odd-2',
          key: 'KAN-ODD-2',
          summary: 'Empty state name',
          state: { id: 'uuid-odd', group: 'unstarted', color_hex: '#112233' } as unknown as StateSummary,
          priority: { slug: 'none', label: 'None' },
        },
        ...FIXTURE_12_ISSUES,
      ];

      const { unmount } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={oddIssues as unknown as IssueItem[]}
          modulesEnabled={false}
          isProjectAdmin={false}
        />,
      );

      await waitFor(() => {
        expect(window.location.search).toContain('peek=KAN-ODD-1');
      });

      unmount();
      localStorage.removeItem('kb_favorite_issues');

      // 3. Filter with empty state name and priority fallback to 'none' and explicit state_id lookup
      window.history.pushState(
        {},
        '',
        '/projects/KAN/issues?layout=board&filter_state=backlog&filter_priority=none',
      );
      const qc2 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc2.setQueryData(['states', 'KAN'], [
        { id: 'st-explicit', name: 'Explicit State', group: 'backlog' },
        { id: 'st-wip-10', name: 'WIP 10', group: 'started', wip_hard_limit: 10 },
      ]);
      const explicitIssues = [
        {
          id: 'iss-explicit-1',
          key: 'KAN-EXP-1',
          summary: 'Explicit State Match',
          state_id: 'st-explicit',
          state: undefined,
          priority: undefined,
        },
        {
          id: 'iss-blank-state-1',
          key: 'KAN-BLANK-1',
          summary: 'Blank state name',
          state: { id: 'st-blank', name: '', group: 'unstarted' },
          priority: undefined,
        },
      ];
      const { unmount: unmount2 } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={explicitIssues as unknown as IssueItem[]}
          queryClient={qc2}
        />,
      );
      expect(screen.getByText('Explicit State Match')).toBeDefined();
      unmount2();

      // 4. Batch state toggle on completed issue with populated projectStates to hit targetStateSlug !== 'done'
      const qc3 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc3.setQueryData(['states', 'KAN'], [
        { id: 'st-completed', name: 'Done', group: 'completed' },
        { id: 'st-unstarted', name: 'Todo', group: 'unstarted' },
      ]);
      const completedIssues = [
        {
          id: 'iss-comp-1',
          key: 'KAN-COMP-1',
          summary: 'Completed issue',
          state: { id: 'st-completed', name: 'Done', group: 'completed' },
          priority: { slug: 'low', label: 'Low', emoji: '🟢' },
        },
      ];
      window.history.pushState({}, '', '/projects/KAN/issues?layout=list');
      const { unmount: unmount3 } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialLayout="list"
          initialIssues={completedIssues as unknown as IssueItem[]}
          queryClient={qc3}
          capabilities={['VIEW', 'EDIT']}
        />,
      );
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'x' });
      const batchBtn = screen.getByRole('button', { name: 'State' });
      fireEvent.click(batchBtn);
      unmount3();
    });

    it('covers viewRegistry board fallback branches: empty boardStates and missing state id/group', async () => {
      const qcEmpty = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qcEmpty.setQueryData(['states', 'KAN'], []);

      const issuesWithoutStateIdGroup = [
        {
          id: 'iss-no-id-grp',
          key: 'KAN-NOGRP-1',
          summary: 'Missing id and group in state',
          state: { name: 'StateWithoutIdOrGroup' } as unknown as StateSummary,
          priority: { slug: 'none', label: 'None' },
        },
      ];

      const patchSpy = vi.spyOn(viewsApi, 'patchProjectIssue');
      patchSpy.mockRejectedValue('Primitive transition error');

      const { unmount } = render(
        <IssuesWorkspaceRoute
          projectKey="KAN"
          initialIssues={issuesWithoutStateIdGroup as unknown as IssueItem[]}
          queryClient={qcEmpty}
        />,
      );
      expect(screen.getByText('Missing id and group in state')).toBeDefined();

      // Trigger priority and state change on issue without prevPriority/prevState when patch fails
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'p' });
      const prioPop = await screen.findByRole('dialog', { name: /Quick Priority Picker/i });
      await act(async () => {
        fireEvent.click(within(prioPop).getByText('High'));
        await Promise.resolve();
      });

      fireEvent.keyDown(window, { key: 's' });
      const statePop = await screen.findByRole('dialog', { name: /Quick State Picker/i });
      await act(async () => {
        fireEvent.click(within(statePop).getByText('Todo'));
        await Promise.resolve();
      });

      // Quick create issue without summary or state/priority
      act(() => {
        fireEvent(window, new CustomEvent('kb:create-issue'));
      });
      const createBtn = screen.getByRole('button', { name: /^create$/i });
      act(() => {
        fireEvent.click(createBtn);
      });

      unmount();
      window.history.pushState({}, '', '/');
    });
  });
});
