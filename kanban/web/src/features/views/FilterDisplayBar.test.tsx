import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import React from 'react';
import { FilterDisplayBar, type ActiveFilters } from './FilterDisplayBar';
import * as railApi from '../drawer-rail/railApi';

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
});
