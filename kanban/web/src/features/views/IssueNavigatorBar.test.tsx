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
      assignees: [],
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
    render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        queryMode="basic"
      />,
    );

    expect(screen.getByTestId('issue-navigator-bar')).toBeDefined();
    expect(screen.getByTestId('navigator-search-input')).toBeDefined();
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
        queryMode="basic"
        onQueryModeChange={onQueryModeChange}
      />,
    );

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
        onFiltersChange={onFiltersChange}
      />,
    );

    // State filter
    const stateSelect = screen.getByTestId('navigator-filter-state');
    fireEvent.change(stateSelect, { target: { value: 'todo' } });
    expect(onFiltersChange).toHaveBeenCalledWith({ state: ['todo'] });

    // Priority filter
    const prioSelect = screen.getByTestId('navigator-filter-priority');
    fireEvent.change(prioSelect, { target: { value: 'urgent' } });
    expect(onFiltersChange).toHaveBeenCalledWith({ priority: ['urgent'] });

    // Reset filter to all
    fireEvent.change(stateSelect, { target: { value: 'all' } });
    expect(onFiltersChange).toHaveBeenCalledWith({});
  });

  it('handles favorites toggle and saved view selection', () => {
    const onToggleFavoritesOnly = vi.fn();
    const onSelectSavedView = vi.fn();

    render(
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
    fireEvent.click(favToggle);
    expect(onToggleFavoritesOnly).toHaveBeenCalled();

    const savedViewsStrip = screen.getByTestId('navigator-saved-views-strip');
    expect(savedViewsStrip).toBeDefined();

    const view1Chip = screen.getByTestId('saved-view-chip-view-1');
    expect(view1Chip.classList.contains('navigator-view-chip--active')).toBe(true);

    const view2Chip = screen.getByTestId('saved-view-chip-view-2');
    fireEvent.click(view2Chip);
    expect(onSelectSavedView).toHaveBeenCalledWith('view-2');
  });
});
