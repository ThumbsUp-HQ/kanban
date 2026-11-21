import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { IssueNavigatorBar } from './IssueNavigatorBar';
import type { IssueItem, SavedView } from './viewsApi';

describe('IssueNavigatorBar (KAN-52 Problem 1)', () => {
  const mockIssues: IssueItem[] = [
    {
      id: 'i-1',
      key: 'KAN-1',
      summary: 'Authentication bug',
      state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      priority: { slug: 'high', label: 'High' },
      assignees: [
        {
          id: 'asg-1',
          kind: 'principal',
          principal: { id: 'u-1', handle: 'alice', display_name: 'Alice A', type: 'USER' },
        },
      ],
      labels: [{ id: 'lbl-1', name: 'auth', color_hex: '#123456' }],
      cycle_id: 'c-1',
      cycle: { id: 'c-1', name: 'Sprint 1' },
      module_ids: ['m-1'],
      modules: [{ id: 'm-1', name: 'Security' }],
    },
    {
      id: 'i-2',
      key: 'KAN-2',
      summary: 'Database migration',
      state: { id: 'state-done', name: 'Done', group: 'completed' },
      priority: { slug: 'low', label: 'Low' },
      assignees: [
        { id: 'asg-free', kind: 'free_text', free_text: 'contractor', notify: false, hint: '' },
      ],
      module_ids: ['m-extra'],
    },
  ];

  const mockSavedViews: SavedView[] = [
    {
      id: 'view-1',
      name: 'My Open Issues',
      layout: 'list',
      group_by: 'state',
      sub_group_by: 'none',
    },
    {
      id: 'view-2',
      name: 'High Priority',
      layout: 'list',
      group_by: 'priority',
      sub_group_by: 'none',
    },
  ];

  it('renders issue navigator bar with basic mode filter dropdowns and search input', () => {
    const onSearchQueryChange = vi.fn();
    render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        projectStates={[{ id: 's-custom', name: 'Custom State', group: 'unstarted' }]}
        queryMode="basic"
        onSearchQueryChange={onSearchQueryChange}
      />,
    );

    expect(screen.getByTestId('issue-navigator-bar')).toBeDefined();
    const searchInput = screen.getByTestId('navigator-search-input');
    expect(searchInput).toBeDefined();
    fireEvent.change(searchInput, { target: { value: 'test search' } });
    expect(onSearchQueryChange).toHaveBeenCalledWith('test search');

    expect(screen.getByTestId('navigator-search-btn')).toBeDefined();
    expect(screen.getByTestId('navigator-mode-toggle')).toBeDefined();
    expect(screen.getByTestId('navigator-filter-state')).toBeDefined();
    expect(screen.getByTestId('navigator-filter-priority')).toBeDefined();
    expect(screen.getByTestId('navigator-filter-assignee')).toBeDefined();
    expect(screen.getByTestId('navigator-filter-label')).toBeDefined();
    expect(screen.getByTestId('navigator-filter-cycle')).toBeDefined();
    expect(screen.getByTestId('navigator-filter-module')).toBeDefined();
    expect(screen.getByTestId('filter-favorites-toggle')).toBeDefined();
  });

  it('toggles between basic and query mode', () => {
    const onQueryModeChange = vi.fn();
    render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        queryMode="query"
        onQueryModeChange={onQueryModeChange}
      />,
    );

    const basicBtn = screen.getByTestId('mode-basic-btn');
    fireEvent.click(basicBtn);
    expect(onQueryModeChange).toHaveBeenCalledWith('basic');

    const queryBtn = screen.getByTestId('mode-query-btn');
    fireEvent.click(queryBtn);
    expect(onQueryModeChange).toHaveBeenCalledWith('query');
  });

  it('renders query mode with monospace query input', () => {
    const onSearchQueryChange = vi.fn();
    const onSearchSubmit = vi.fn();

    render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        queryMode="query"
        searchQuery='project = "KAN" AND status = "Todo"'
        onSearchQueryChange={onSearchQueryChange}
        onSearchSubmit={onSearchSubmit}
      />,
    );

    expect(screen.getByTestId('navigator-query-input')).toBeDefined();
    expect(screen.queryByTestId('navigator-search-input')).toBeNull();

    const input = screen.getByTestId('navigator-query-input');
    fireEvent.change(input, { target: { value: 'priority:high "mars"' } });
    expect(onSearchQueryChange).toHaveBeenCalledWith('priority:high "mars"');

    const searchBtn = screen.getByTestId('navigator-search-btn');
    fireEvent.click(searchBtn);
    expect(onSearchSubmit).toHaveBeenCalled();
  });

  it('handles basic mode filter dropdown changes', () => {
    const onFiltersChange = vi.fn();
    render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        queryMode="basic"
        activeFilters={{ state: ['todo'], priority: ['urgent'] }}
        modulesEnabled={true}
        onFiltersChange={onFiltersChange}
      />,
    );

    // State filter
    const stateSelect = screen.getByTestId('navigator-filter-state');
    fireEvent.change(stateSelect, { target: { value: 'todo' } });
    expect(onFiltersChange).toHaveBeenCalledWith({ state: ['todo'], priority: ['urgent'] });

    // Priority filter
    const prioSelect = screen.getByTestId('navigator-filter-priority');
    fireEvent.change(prioSelect, { target: { value: 'urgent' } });
    expect(onFiltersChange).toHaveBeenCalledWith({ state: ['todo'], priority: ['urgent'] });

    // Assignee filter
    const asgSelect = screen.getByTestId('navigator-filter-assignee');
    fireEvent.change(asgSelect, { target: { value: 'alice' } });
    expect(onFiltersChange).toHaveBeenCalledWith({ state: ['todo'], priority: ['urgent'], assignee: ['alice'] });

    // Label filter
    const lblSelect = screen.getByTestId('navigator-filter-label');
    fireEvent.change(lblSelect, { target: { value: 'auth' } });
    expect(onFiltersChange).toHaveBeenCalledWith({ state: ['todo'], priority: ['urgent'], label: ['auth'] });

    // Cycle filter
    const cycleSelect = screen.getByTestId('navigator-filter-cycle');
    fireEvent.change(cycleSelect, { target: { value: 'c-1' } });
    expect(onFiltersChange).toHaveBeenCalledWith({ state: ['todo'], priority: ['urgent'], cycle: ['c-1'] });

    // Module filter (with modulesEnabled)
    const modSelect = screen.getByTestId('navigator-filter-module');
    fireEvent.change(modSelect, { target: { value: 'm-1' } });
    expect(onFiltersChange).toHaveBeenCalledWith({ state: ['todo'], priority: ['urgent'], module: ['m-1'] });

    // Reset filter to all
    fireEvent.change(stateSelect, { target: { value: 'all' } });
    expect(onFiltersChange).toHaveBeenCalledWith({ priority: ['urgent'] });
  });

  it('handles favorites toggle and saved view selection', () => {
    const onToggleFavoritesOnly = vi.fn();
    const onSelectSavedView = vi.fn();

    const { rerender } = render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        favoritesOnly={false}
        onToggleFavoritesOnly={onToggleFavoritesOnly}
        savedViews={mockSavedViews}
        activeViewId="view-1"
        onSelectSavedView={onSelectSavedView}
      />,
    );

    const favToggle = screen.getByTestId('filter-favorites-toggle');
    expect(favToggle.textContent).toContain('☆ Favorites only');
    fireEvent.click(favToggle);
    expect(onToggleFavoritesOnly).toHaveBeenCalled();

    rerender(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        favoritesOnly={true}
        onToggleFavoritesOnly={onToggleFavoritesOnly}
        savedViews={mockSavedViews}
        activeViewId="view-1"
        onSelectSavedView={onSelectSavedView}
      />,
    );
    expect(screen.getByTestId('filter-favorites-toggle').textContent).toContain('⭐ Favorites only');

    const savedViewsStrip = screen.getByTestId('navigator-saved-views-strip');
    expect(savedViewsStrip).toBeDefined();

    const view1Chip = screen.getByTestId('saved-view-chip-view-1');
    expect(view1Chip.classList.contains('navigator-view-chip--active')).toBe(true);

    const view2Chip = screen.getByTestId('saved-view-chip-view-2');
    fireEvent.click(view2Chip);
    expect(onSelectSavedView).toHaveBeenCalledWith('view-2');
  });

  it('covers defensive branches for missing assignees, display_name, cycle name, module_ids, and omitted onFiltersChange', () => {
    const defensiveIssues: IssueItem[] = [
      {
        id: 'i-def',
        key: 'KAN-DEF',
        summary: 'Defensive issue',
        state: { id: 's-1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
        assignees: [
          {
            id: 'asg-nodisp',
            kind: 'principal',
            principal: { id: 'u-2', handle: 'bob', display_name: '', type: 'USER' },
          },
        ],
        cycle_id: 'cycle-nocycleobj',
      },
      {
        id: 'i-noasg',
        key: 'KAN-NOASG',
        summary: 'No assignees',
        state: { id: 's-1', name: 'Todo', group: 'unstarted' },
        priority: { slug: 'low', label: 'Low' },
      },
    ];

    render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={defensiveIssues}
      />,
    );

    // Filter change without onFiltersChange does not crash
    const stateSelect = screen.getByTestId('navigator-filter-state');
    fireEvent.change(stateSelect, { target: { value: 'todo' } });
  });
});
