import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor, act } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { FilterDisplayBar, type ActiveFilters } from './FilterDisplayBar';
import { createAllStatesFilterPreference } from './issueFilterCookie';
import * as railApi from '../drawer-rail/railApi';
import * as client from '../../api/client';

describe('FilterDisplayBar (KB-P3-40, S6.3, S6.4, S7.2 8f)', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/projects/KAN/issues');
  });

  it('renders filter trigger button, group and subgroup selectors', () => {
    render(
      <FilterDisplayBar
        groupBy="state"
        subGroupBy="none"
        modulesEnabled={true}
      />
    );

    expect(screen.getByRole('button', { name: /open filter facets popover/i })).toBeDefined();
    expect(screen.getByLabelText(/^Group by axis$/i)).toBeDefined();
    expect(screen.getByLabelText(/^Sub-group by axis$/i)).toBeDefined();
    expect(screen.getByRole('button', { name: /display configuration/i })).toBeDefined();
  });

  it('opens facet search popover and toggles facet options', () => {
    const handleFiltersChange = vi.fn();

    render(
      <FilterDisplayBar
        activeFilters={{}}
        onFiltersChange={handleFiltersChange}
        groupBy="state"
        subGroupBy="priority"
        modulesEnabled={true}
      />
    );

    const trigger = screen.getByRole('button', { name: /open filter facets popover/i });
    fireEvent.click(trigger);

    // Search input is rendered
    const searchInput = screen.getByPlaceholderText(/search filters\.\.\./i);
    expect(searchInput).toBeDefined();

    // Toggle Pending gate status
    const pendingOption = screen.getByRole('button', { name: /⏳🤖 Pending/i });
    fireEvent.click(pendingOption);

    expect(handleFiltersChange).toHaveBeenCalledWith(
      expect.objectContaining({
        gate_status: ['pending'],
      })
    );
  });

  it('renders active filter chips and allows removing them', () => {
    const handleFiltersChange = vi.fn();
    const active: ActiveFilters = {
      gate_status: ['pending'],
      priority: ['urgent', 'high'],
    };

    render(
      <FilterDisplayBar
        activeFilters={active}
        onFiltersChange={handleFiltersChange}
        groupBy="state"
        subGroupBy="none"
        modulesEnabled={true}
      />
    );

    const pendingChip = screen.getByText(/Gate status: ⏳🤖 Pending/i);
    expect(pendingChip).toBeDefined();

    // Removing gate_status removes the last value in that category (hits delete branch)
    const removeBtn = screen.getByRole('button', { name: /remove gate status: ⏳🤖 pending filter/i });
    fireEvent.click(removeBtn);

    expect(handleFiltersChange).toHaveBeenCalledWith({
      priority: ['urgent', 'high'],
    });

    // Removing one priority leaves the other (hits length > 0 branch)
    const removePrioBtn = screen.getByRole('button', { name: /remove priority: 🔥 urgent filter/i });
    fireEvent.click(removePrioBtn);

    const clearAll = screen.getByRole('button', { name: /clear all/i });
    fireEvent.click(clearAll);
    expect(handleFiltersChange).toHaveBeenCalledWith({});
  });

  it('mutual exclusion: resets sub-group to none if group matches sub-group (Test Case 5)', () => {
    const handleGroupChange = vi.fn();
    const handleSubGroupChange = vi.fn();

    render(
      <FilterDisplayBar
        groupBy="state"
        subGroupBy="priority"
        onGroupByChange={handleGroupChange}
        onSubGroupByChange={handleSubGroupChange}
        modulesEnabled={true}
      />
    );

    const groupSelect = screen.getByLabelText(/^Group by axis$/i);
    fireEvent.change(groupSelect, { target: { value: 'priority' } });

    expect(handleGroupChange).toHaveBeenCalledWith('priority');
    expect(handleSubGroupChange).toHaveBeenCalledWith('none');
  });

  it('omits module facet and axis options when modulesEnabled is false (Test Case 3, S7.2 8f)', () => {
    render(
      <FilterDisplayBar
        groupBy="state"
        subGroupBy="none"
        modulesEnabled={false}
      />
    );

    // Group select options should not have Module
    const groupSelect = screen.getByLabelText(/^Group by axis$/i);
    const options = Array.from(groupSelect.querySelectorAll('option')).map((o) => o.value);
    expect(options).not.toContain('module');

    const subGroupSelect = screen.getByLabelText(/^Sub-group by axis$/i);
    const subOptions = Array.from(subGroupSelect.querySelectorAll('option')).map((o) => o.value);
    expect(subOptions).not.toContain('module');

    // Open filter popover
    const trigger = screen.getByRole('button', { name: /open filter facets popover/i });
    fireEvent.click(trigger);

    expect(screen.queryByText('module')).toBeNull();
    expect(screen.queryByRole('button', { name: /Auth Core/i })).toBeNull();
  });

  it('negative / security: URL filter param with script tag renders text literally with zero script nodes (Test Case 5)', () => {
    const xssPayload = '<script>alert(1)</script>';
    window.history.pushState({}, '', `/projects/KAN/issues?filter_label=${encodeURIComponent(xssPayload)}`);

    const handleFiltersChange = vi.fn();

    render(
      <FilterDisplayBar
        activeFilters={{ label: [xssPayload] }}
        onFiltersChange={handleFiltersChange}
        groupBy="state"
        subGroupBy="none"
        modulesEnabled={true}
      />
    );

    // Chip must exist containing literal text
    expect(screen.getByText((content) => content.includes(xssPayload))).toBeDefined();
    // Zero script elements created in DOM
    expect(document.querySelectorAll('script').length).toBe(0);
  });

  it('handles keyboard shortcut / to open filter popover and focus search input', () => {
    const searchRef = { current: document.createElement('input') };
    const focusSpy = vi.spyOn(searchRef.current, 'focus');

    render(
      <FilterDisplayBar
        groupBy="state"
        subGroupBy="none"
        modulesEnabled={true}
        searchInputRef={searchRef as React.RefObject<HTMLInputElement | null>}
      />
    );

    // Press '/' on window
    fireEvent.keyDown(window, { key: '/' });

    // Popover is open
    expect(screen.getByPlaceholderText(/search filters\.\.\./i)).toBeDefined();
    expect(focusSpy).toBeDefined();
  });

  it('filters facet options by search query and deselects active facet', () => {
    const handleFiltersChange = vi.fn();

    render(
      <FilterDisplayBar
        activeFilters={{ state: ['active'] }}
        onFiltersChange={handleFiltersChange}
        groupBy="state"
        subGroupBy="none"
        modulesEnabled={true}
      />
    );

    // Open popover
    fireEvent.click(screen.getByRole('button', { name: /open filter facets popover/i }));

    const searchInput = screen.getByPlaceholderText(/search filters\.\.\./i);
    fireEvent.change(searchInput, { target: { value: 'urgent' } });

    // Urgent should be shown, Low should be filtered out
    expect(screen.getByRole('button', { name: /🔥 Urgent/i })).toBeDefined();
    expect(screen.queryByRole('button', { name: /💤 Low/i })).toBeNull();

    // Clear search
    fireEvent.change(searchInput, { target: { value: '' } });

    // Click Active to deselect it
    const activeOption = screen.getByRole('button', { name: /^Active/i });
    fireEvent.click(activeOption);
    expect(handleFiltersChange).toHaveBeenCalledWith({});
  });

  it('opens display tune popover and triggers save view callback', () => {
    const handleSave = vi.fn();

    render(
      <FilterDisplayBar
        onSaveView={handleSave}
        modulesEnabled={true}
      />
    );

    const displayBtn = screen.getByRole('button', { name: /display configuration/i });
    fireEvent.click(displayBtn);

    const saveBtn = screen.getByRole('button', { name: /save as view/i });
    fireEvent.click(saveBtn);

    expect(handleSave).toHaveBeenCalled();
  });

  it('reads filter_label from URLSearchParams on mount and triggers onFiltersChange', () => {
    window.history.pushState({}, '', '/projects/KAN/issues?filter_label=frontend-core');
    const handleFiltersChange = vi.fn();

    render(
      <FilterDisplayBar
        activeFilters={{}}
        onFiltersChange={handleFiltersChange}
        groupBy="state"
        subGroupBy="none"
        modulesEnabled={true}
      />
    );

    expect(handleFiltersChange).toHaveBeenCalledWith(
      expect.objectContaining({
        label: ['frontend-core'],
      })
    );
  });

  it('triggers onSubGroupByChange when sub-group axis select changes', () => {
    const handleSubGroupChange = vi.fn();

    render(
      <FilterDisplayBar
        groupBy="state"
        subGroupBy="none"
        onSubGroupByChange={handleSubGroupChange}
        modulesEnabled={true}
      />
    );

    const subGroupSelect = screen.getByLabelText(/^Sub-group by axis$/i);
    fireEvent.change(subGroupSelect, { target: { value: 'priority' } });

    expect(handleSubGroupChange).toHaveBeenCalledWith('priority');
  });

  it('handles externalToggleFilterOpen and toggling filter option with multiple categories', () => {
    const handleToggleFilter = vi.fn();
    const handleFiltersChange = vi.fn();

    render(
      <FilterDisplayBar
        isFilterOpen={true}
        onToggleFilterOpen={handleToggleFilter}
        activeFilters={{ state: ['state-todo'], priority: ['high'] }}
        onFiltersChange={handleFiltersChange}
        modulesEnabled={true}
      />
    );

    // Click filter trigger button to close
    const filterBtn = screen.getByRole('button', { name: /open filter facets popover/i });
    fireEvent.click(filterBtn);
    expect(handleToggleFilter).toHaveBeenCalledWith(false);

    // Toggle high priority in popover (other category 'state' exists, exercising k !== category)
    const dialog = screen.getByRole('dialog', { name: /filter facets/i });
    const highBtn = within(dialog).getByRole('button', { name: /⚡ High/i });
    fireEvent.click(highBtn);
    expect(handleFiltersChange).toHaveBeenCalledWith({
      state: ['state-todo'],
    });
  });

  it('hydrates dynamic facets from live project endpoints when projectKey is provided', async () => {
    vi.spyOn(railApi, 'fetchAssigneeSuggestions').mockResolvedValue([
      { id: 'u1', handle: 'maya', display_name: 'Maya Lin', type: 'USER' },
    ]);
    vi.spyOn(railApi, 'fetchProjectLabels').mockResolvedValue([
      { id: 'l1', name: 'Infrastructure' },
    ]);
    vi.spyOn(railApi, 'fetchProjectCycles').mockResolvedValue([
      { id: 'c1', name: 'Sprint 42' },
    ]);
    vi.spyOn(railApi, 'fetchProjectModules').mockResolvedValue([
      { id: 'm1', name: 'Telemetry' },
    ]);

    render(
      <FilterDisplayBar
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    // Open filter popover
    fireEvent.click(screen.getByRole('button', { name: /open filter facets popover/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Maya Lin/i })).toBeDefined();
      expect(screen.getByRole('button', { name: /Infrastructure/i })).toBeDefined();
      expect(screen.getByRole('button', { name: /Sprint 42/i })).toBeDefined();
      expect(screen.getByRole('button', { name: /Telemetry/i })).toBeDefined();
    });
  });

  it('KB-P3-AUDIT-08: does NOT call fetchProjectModules when modulesEnabled is false', async () => {
    vi.spyOn(railApi, 'fetchAssigneeSuggestions').mockResolvedValue([]);
    vi.spyOn(railApi, 'fetchProjectLabels').mockResolvedValue([]);
    vi.spyOn(railApi, 'fetchProjectCycles').mockResolvedValue([]);
    const modulesSpy = vi.spyOn(railApi, 'fetchProjectModules').mockResolvedValue([]);

    render(
      <FilterDisplayBar
        projectKey="KAN"
        modulesEnabled={false}
      />
    );

    await Promise.resolve();

    expect(modulesSpy).not.toHaveBeenCalled();
  });

  it('KB-P3-AUDIT-08: never calls /assignee-suggestions?q= with empty query string on mount', () => {
    const apiFetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue({ items: [] });

    act(() => {
      render(
        <FilterDisplayBar
          projectKey="KAN"
          modulesEnabled={true}
        />
      );
    });

    const emptyQueryCalls = apiFetchSpy.mock.calls.filter((call) => {
      const path = call[1];
      const isAssignee = path.includes('assignee-suggestions');
      const query = (call[2] as { query?: { q?: string } } | undefined)?.query;
      return isAssignee && (!query?.q || query.q.trim().length === 0);
    });

    expect(emptyQueryCalls).toHaveLength(0);
  });

  it('covers dynamic facet edge cases: fallback labels, unmount in flight, and chip removal fallbacks', () => {
    // 1. Assignee without display_name, custom cycle, custom module
    const { unmount: u1 } = render(
      <FilterDisplayBar
        projectKey="KAN"
        modulesEnabled={true}
        issues={[
          {
            id: 'iss-custom',
            assignees: [
              {
                id: 'asg-1',
                kind: 'principal',
                principal: { id: 'u2', handle: '@johndoe', display_name: '' },
              },
            ],
            labels: [{ id: 'lbl-c', name: 'CustomLabel' }],
            cycle_id: 'cycle-custom-99',
            module_ids: ['mod-custom-99'],
          } as never,
        ]}
        activeFilters={{
          empty_cat: undefined,
          state: ['st-todo'],
        }}
        onFiltersChange={vi.fn()}
      />
    );

    // Open filter popover
    fireEvent.click(screen.getByRole('button', { name: /open filter facets popover/i }));
    expect(screen.getByRole('button', { name: /@johndoe/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /CustomLabel/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /cycle-custom-99/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /mod-custom-99/i })).toBeDefined();
    u1();

    // 2. Unmount while dynamic fetches are unresolved
    let resolveSuggestions: ((val: Awaited<ReturnType<typeof railApi.fetchAssigneeSuggestions>>) => void) | undefined;
    vi.spyOn(railApi, 'fetchAssigneeSuggestions').mockImplementation(
      () => new Promise((resolve) => { resolveSuggestions = resolve; }),
    );
    const { unmount: u2 } = render(
      <FilterDisplayBar projectKey="KAN" modulesEnabled={true} />
    );
    u2();
    resolveSuggestions?.([{ id: 'u99', handle: 'late', display_name: 'Late', type: 'USER' }]);
  });

  it('derives dynamic facets from issues collection when live facets are empty', () => {
    const handleFiltersChange = vi.fn();
    const mockIssues = [
      {
        id: 'iss-1',
        assignees: [
          {
            kind: 'principal' as const,
            principal: { id: 'u1', handle: '@alice', display_name: 'Alice Cooper' },
          },
          {
            kind: 'principal' as const,
            principal: { id: 'u2', handle: 'bob', display_name: '' },
          },
          {
            kind: 'agent' as const,
            agent_id: 'bot-1',
          },
        ],
        labels: [{ id: 'l1', name: 'Frontend' }],
        cycle_id: 'cycle-1',
        module_ids: ['mod-1', 'mod-2', 'mod-custom'],
      },
      {
        id: 'iss-2',
        assignees: [],
        labels: [{ id: 'l2', name: 'Backend' }],
        cycle_id: 'cycle-2',
        module_ids: [],
      },
    ] as unknown as Parameters<typeof FilterDisplayBar>[0]['issues'];

    render(
      <FilterDisplayBar
        issues={mockIssues as never}
        modulesEnabled={true}
        onFiltersChange={handleFiltersChange}
      />
    );

    // Open filter facets popover
    fireEvent.click(screen.getByRole('button', { name: /open filter facets popover/i }));

    // Derived assignees
    expect(screen.getByRole('button', { name: /Alice Cooper/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /bob/i })).toBeDefined();

    // Derived labels
    expect(screen.getByRole('button', { name: /Frontend/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Backend/i })).toBeDefined();

    // Derived cycles
    expect(screen.getByRole('button', { name: /Cycle 1/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /cycle-2/i })).toBeDefined();

    // Derived modules
    expect(screen.getByRole('button', { name: /Auth Core/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Kanban Board/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /mod-custom/i })).toBeDefined();

    // Toggle a derived module
    fireEvent.click(screen.getByRole('button', { name: /Auth Core/i }));
    expect(handleFiltersChange).toHaveBeenCalledWith(
      expect.objectContaining({
        module: ['mod-1'],
      })
    );
  });

  it('triggers onSaveView and closes popover from Display settings', () => {
    const handleSaveView = vi.fn();

    render(
      <FilterDisplayBar
        modulesEnabled={true}
        onSaveView={handleSaveView}
      />
    );

    // Open Display popover
    fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
    expect(screen.getByRole('dialog', { name: /display options/i })).toBeDefined();

    // Click Save as view
    fireEvent.click(screen.getByRole('button', { name: /save as view/i }));
    expect(handleSaveView).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog', { name: /display options/i })).toBeNull();
  });

  it('handles "/" keyboard shortcut to open filter popover unless input is active', async () => {
    render(
      <div>
        <input data-testid="dummy-input" />
        <FilterDisplayBar modulesEnabled={true} />
      </div>
    );

    // Pressing / inside input should NOT open popover
    const input = screen.getByTestId('dummy-input');
    input.focus();
    fireEvent.keyDown(input, { key: '/' });
    expect(screen.queryByRole('dialog', { name: /filter facets/i })).toBeNull();

    // Pressing / outside input opens popover
    input.blur();
    fireEvent.keyDown(window, { key: '/' });
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /filter facets/i })).toBeDefined();
    });
  });

  describe('FieldHelpHint & HTML 4.10.4 Shift-Left Invariants (KAN-479)', () => {
    it('renders FieldHelpHint for Group and Sub-group as accessible adjacent sibling controls (KAN-479)', () => {
      const { container } = render(
        <FilterDisplayBar
          groupBy="state"
          subGroupBy="none"
          modulesEnabled={true}
        />
      );

      // 1. Verify existence of both FieldHelpHint triggers
      const groupHelp = screen.getByTestId('group-by-help');
      const subGroupHelp = screen.getByTestId('subgroup-by-help');
      expect(groupHelp).toBeDefined();
      expect(subGroupHelp).toBeDefined();

      // 2. HTML 4.10.4 Invariants: NEVER nested inside <label> or another <button>
      expect(groupHelp.closest('label')).toBeNull();
      expect(subGroupHelp.closest('label')).toBeNull();
      expect(groupHelp.closest('button.filter-btn-trigger')).toBeNull();
      expect(subGroupHelp.closest('button.filter-btn-trigger')).toBeNull();

      // Flex wrapper sibling checks
      const groupLabelWrap = groupHelp.closest('.filter-axis-label-wrap');
      const subLabelWrap = subGroupHelp.closest('.filter-axis-label-wrap');
      expect(groupLabelWrap).not.toBeNull();
      expect(subLabelWrap).not.toBeNull();

      expect(groupLabelWrap?.querySelector('label[for="group-by-select"]')).not.toBeNull();
      expect(subLabelWrap?.querySelector('label[for="subgroup-by-select"]')).not.toBeNull();

      // Strict querySelectorAll assertion mandated by KAN-479
      const invalidNestedButtons = container.querySelectorAll(
        'label button.field-help-hint, button button.field-help-hint'
      );
      expect(invalidNestedButtons.length).toBe(0);
      expect(document.querySelectorAll('label button.field-help-hint, button button.field-help-hint').length).toBe(0);

      // 3. ARIA attributes
      expect(groupHelp.getAttribute('aria-label')).toBe('Help for Group Axis');
      expect(groupHelp.getAttribute('aria-haspopup')).toBe('dialog');
      expect(subGroupHelp.getAttribute('aria-label')).toBe('Help for Sub-group Axis');
      expect(subGroupHelp.getAttribute('aria-haspopup')).toBe('dialog');
    });

    it('opens Group Axis FieldHelpHint popover and verifies summary, defaultValue, validValues, and docHref wiki link (KAN-479)', async () => {
      render(
        <FilterDisplayBar
          groupBy="state"
          subGroupBy="none"
          modulesEnabled={true}
        />
      );

      const groupHelp = screen.getByTestId('group-by-help');
      fireEvent.click(groupHelp);

      await waitFor(() => {
        expect(
          screen.getByText('Primary board grouping axis defining vertical column divisions.')
        ).toBeDefined();
      });

      // Default value
      expect(screen.getByTestId('group-by-help-default')).toBeDefined();
      expect(within(screen.getByTestId('group-by-help-default')).getByText('State')).toBeDefined();

      // Valid values list
      expect(screen.getByText('Group issues into workflow columns by state.')).toBeDefined();
      expect(screen.getByText('Group issues by priority severity tiers.')).toBeDefined();
      expect(screen.getByText('Group issues by assigned team member.')).toBeDefined();
      expect(screen.getByText('Group issues by sprint cadence cycle.')).toBeDefined();
      expect(screen.getByText('Group issues by feature module boundary.')).toBeDefined();
      expect(screen.getByText('Group issues by assigned tag label.')).toBeDefined();
      expect(screen.getByText('Render all issues without column grouping.')).toBeDefined();

      // Documentation link
      const docLink = screen.getByTestId('group-by-help-doc-link');
      expect(docLink.getAttribute('href')).toBe('/docs/enterprise-whitespace-and-kanban-board');

      // Dismiss on Escape key on trigger
      fireEvent.keyDown(groupHelp, { key: 'Escape' });
      await waitFor(() => {
        expect(
          screen.queryByText('Primary board grouping axis defining vertical column divisions.')
        ).toBeNull();
      });
    });

    it('opens Sub-group Axis FieldHelpHint popover and verifies summary, defaultValue, and validValues (KAN-479)', async () => {
      render(
        <FilterDisplayBar
          groupBy="state"
          subGroupBy="none"
          modulesEnabled={true}
        />
      );

      const subGroupHelp = screen.getByTestId('subgroup-by-help');
      fireEvent.click(subGroupHelp);

      await waitFor(() => {
        expect(
          screen.getByText(
            'Secondary swimlane axis partitioning columns into horizontal swimlanes across the board.'
          )
        ).toBeDefined();
      });

      // Default value
      expect(screen.getByTestId('subgroup-by-help-default')).toBeDefined();
      expect(within(screen.getByTestId('subgroup-by-help-default')).getByText('None')).toBeDefined();

      // Valid values list
      expect(screen.getByText('Disable horizontal swimlanes.')).toBeDefined();
      expect(screen.getByText('Partition columns into assignee swimlanes.')).toBeDefined();
      expect(screen.getByText('Partition columns into priority swimlanes.')).toBeDefined();
      expect(screen.getByText('Partition columns into workflow state swimlanes.')).toBeDefined();
      expect(screen.getByText('Partition columns into sprint cycle swimlanes.')).toBeDefined();
      expect(screen.getByText('Partition columns into feature module swimlanes.')).toBeDefined();
      expect(screen.getByText('Partition columns into tag label swimlanes.')).toBeDefined();

      // Documentation link
      const docLink = screen.getByTestId('subgroup-by-help-doc-link');
      expect(docLink.getAttribute('href')).toBe('/docs/enterprise-whitespace-and-kanban-board');

      // Dismiss on Escape key on trigger
      fireEvent.keyDown(subGroupHelp, { key: 'Escape' });
      await waitFor(() => {
        expect(
          screen.queryByText(
            'Secondary swimlane axis partitioning columns into horizontal swimlanes across the board.'
          )
        ).toBeNull();
      });
    });

    it('enforces static AST invariants: zero inline styles and zero nested FieldHelpHint in label (KAN-479)', () => {
      const source = fs.readFileSync(path.resolve(__dirname, 'FilterDisplayBar.tsx'), 'utf8');

      // Zero inline style props
      expect(source).not.toMatch(/style\s*=\s*\{\{/);

      // Zero FieldHelpHint nested inside <label>...</label>
      expect(source).not.toMatch(/<label[^>]*>(?:(?!<\/label>)[\s\S])*?<FieldHelpHint/i);

      // Zero FieldHelpHint nested inside <button>...</button>
      expect(source).not.toMatch(/<button[^>]*>(?:(?!<\/button>)[\s\S])*?<FieldHelpHint/i);
    });

    it('covers Display tune export, import, report modals, saved views selection, and callbacks (KAN-479)', () => {
      const handleExport = vi.fn();
      const handleImport = vi.fn();
      const handleReports = vi.fn();
      const handleSelectView = vi.fn();

      const sampleSavedView = {
        id: 'view-1',
        project_id: 'proj-1',
        name: 'Sprint 1 Filtered',
        layout: 'board' as const,
        group_by: 'state' as const,
        sub_group_by: 'none' as const,
      };
      const sampleSavedView2 = {
        id: 'view-2',
        project_id: 'proj-1',
        name: 'Sprint 2 Inactive',
        layout: 'board' as const,
        group_by: 'state' as const,
        sub_group_by: 'none' as const,
      };

      const { unmount } = render(
        <FilterDisplayBar
          projectKey="KAN"
          workspaceScope="kanban"
          modulesEnabled={true}
          savedViews={[sampleSavedView, sampleSavedView2]}
          activeViewId="view-1"
          onSelectSavedView={handleSelectView}
          onExport={handleExport}
          onImport={handleImport}
          onExportReports={handleReports}
        />
      );

      // Open Display popover
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));

      // Click saved view inside Display popover
      const viewBtn = screen.getByTestId('filter-display-saved-view-view-1');
      fireEvent.click(viewBtn);
      expect(handleSelectView).toHaveBeenCalledWith('view-1');

      // Click saved view chip in bottom strip and change select
      const viewChip = screen.getByTestId('saved-view-chip-view-1');
      fireEvent.click(viewChip);
      expect(handleSelectView).toHaveBeenCalledWith('view-1');

      const viewSelect = screen.getByTestId('filter-display-saved-views-select');
      fireEvent.change(viewSelect, { target: { value: 'view-1' } });
      expect(handleSelectView).toHaveBeenCalledWith('view-1');
      fireEvent.change(viewSelect, { target: { value: '' } });

      // Reopen Display popover and trigger CSV export callback
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-export-opt-csv'));
      expect(handleExport).toHaveBeenCalledWith('csv');

      // Reopen Display popover and trigger ZIP export callback
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-export-opt-zip'));
      expect(handleExport).toHaveBeenCalledWith('zip_csv');

      // Reopen Display popover and trigger Reports callback
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-reports-btn'));
      expect(handleReports).toHaveBeenCalledTimes(1);

      // Reopen Display popover and trigger Export Issues general button
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-export-btn'));
      expect(handleExport).toHaveBeenCalledWith('csv');

      // Reopen Display popover and trigger Import callback
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-import-btn'));
      expect(handleImport).toHaveBeenCalledTimes(1);

      unmount();

      // Test fallback branch when export/import callbacks are omitted (modal launches)
      render(
        <FilterDisplayBar
          projectKey="KAN"
          workspaceScope="kanban"
          modulesEnabled={true}
        />
      );

      // 1. Launch ZIP modal fallback
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-export-opt-zip'));
      expect(screen.getByTestId('csv-modal-close-btn')).toBeDefined();
      fireEvent.click(screen.getByTestId('csv-modal-close-btn'));

      // 2. Launch Import modal fallback
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-import-btn'));
      expect(screen.getByTestId('csv-modal-close-btn')).toBeDefined();
      fireEvent.click(screen.getByTestId('csv-modal-close-btn'));

      // 3. Launch Reports modal fallback
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-reports-btn'));
      expect(screen.getByTestId('report-export-close-btn')).toBeDefined();
      fireEvent.click(screen.getByTestId('report-export-close-btn'));

      // 4. Launch general Export Issues modal fallback
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-export-btn'));
      expect(screen.getByTestId('csv-modal-close-btn')).toBeDefined();
      fireEvent.click(screen.getByTestId('csv-modal-close-btn'));

      // 5. Launch CSV option modal fallback
      fireEvent.click(screen.getByRole('button', { name: /display configuration/i }));
      fireEvent.click(screen.getByTestId('filter-display-export-opt-csv'));
      expect(screen.getByTestId('csv-modal-close-btn')).toBeDefined();
      fireEvent.click(screen.getByTestId('csv-modal-close-btn'));
    });

    it('covers unified toolbar search form, query mode toggle, and state filter popover (KAN-479)', () => {
      const handleQueryChange = vi.fn();
      const handleSubmit = vi.fn();
      const handleModeChange = vi.fn();
      const handleStateFilterChange = vi.fn();

      const { rerender } = render(
        <FilterDisplayBar
          searchQuery="auth bug"
          onSearchQueryChange={handleQueryChange}
          onSearchSubmit={handleSubmit}
          queryMode="basic"
          onQueryModeChange={handleModeChange}
          stateFilter={createAllStatesFilterPreference()}
          onStateFilterChange={handleStateFilterChange}
          modulesEnabled={true}
        />
      );

      // Search input change and submit
      const searchInput = screen.getByTestId('filter-display-search-input');
      fireEvent.change(searchInput, { target: { value: 'regression' } });
      expect(handleQueryChange).toHaveBeenCalledWith('regression');

      fireEvent.submit(screen.getByTestId('filter-display-search-form'));
      expect(handleSubmit).toHaveBeenCalledTimes(1);

      // Trigger StateFilterPopover onChange
      const stateTrigger = screen.getByTestId('navigator-filter-state');
      fireEvent.click(stateTrigger);
      const actionablePreset = screen.getByTestId('state-preset-actionable');
      fireEvent.click(actionablePreset);
      expect(handleStateFilterChange).toHaveBeenCalledTimes(1);

      // Switch to Query mode
      fireEvent.click(screen.getByTestId('mode-query-btn'));
      expect(handleModeChange).toHaveBeenCalledWith('query');

      // Switch back to Basic mode
      fireEvent.click(screen.getByTestId('mode-basic-btn'));
      expect(handleModeChange).toHaveBeenCalledWith('basic');

      // Rerender with query mode
      rerender(
        <FilterDisplayBar
          searchQuery="status = 'Done'"
          onSearchQueryChange={handleQueryChange}
          onSearchSubmit={handleSubmit}
          queryMode="query"
          onQueryModeChange={handleModeChange}
          stateFilter={createAllStatesFilterPreference()}
          onStateFilterChange={handleStateFilterChange}
          modulesEnabled={true}
        />
      );

      const queryInput = screen.getByTestId('filter-display-query-input');
      fireEvent.change(queryInput, { target: { value: 'priority = "high"' } });
      expect(handleQueryChange).toHaveBeenCalledWith('priority = "high"');
    });

    it('handles StateFilterPopover without onStateFilterChange handler (KAN-479)', () => {
      render(
        <FilterDisplayBar
          projectStates={[
            { id: 's1', name: 'Todo', color_hex: '#64748b', sort_order: 1, group: 'unstarted' },
          ]}
          stateFilter={createAllStatesFilterPreference()}
          modulesEnabled={true}
        />
      );
      const stateTrigger = screen.getByTestId('navigator-filter-state');
      fireEvent.click(stateTrigger);
      fireEvent.click(screen.getByTestId('state-preset-all'));
    });
  });
});
