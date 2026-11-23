import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import {
  IssueNavigatorBar,
  NAVIGATOR_HEADER_MODE_STORAGE_KEY,
} from './IssueNavigatorBar';
import { ISSUE_FILTER_COOKIE_NAME } from './issueFilterCookie';
import type { IssueItem, SavedView } from './viewsApi';

describe('IssueNavigatorBar (KAN-52 & KAN-308 Problems 2 & 3)', () => {
  beforeEach(() => {
    document.cookie = `${ISSUE_FILTER_COOKIE_NAME}=; Path=/; Max-Age=0`;
    localStorage.clear();
  });

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

  it('renders issue navigator bar with StateFilterPopover trigger and basic mode filter dropdowns', () => {
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

  it('handles StateFilterPopover checkbox/preset changes and basic mode filter dropdown changes', () => {
    const onFiltersChange = vi.fn();
    const onStateFilterChange = vi.fn();
    render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        queryMode="basic"
        activeFilters={{ state: ['todo'], priority: ['urgent'] }}
        modulesEnabled={true}
        onFiltersChange={onFiltersChange}
        onStateFilterChange={onStateFilterChange}
      />,
    );

    // StateFilterPopover open, check Done, and click All / Actionable presets
    const stateTrigger = screen.getByTestId('navigator-filter-state');
    fireEvent.click(stateTrigger);
    expect(screen.getByTestId('navigator-state-popover')).toBeDefined();

    fireEvent.click(screen.getByTestId('state-checkbox-state-done'));
    expect(onStateFilterChange).toHaveBeenCalled();
    expect(onFiltersChange).toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('state-preset-actionable'));
    expect(onFiltersChange).toHaveBeenCalledWith({ state: ['active'], priority: ['urgent'] });

    fireEvent.click(screen.getByTestId('state-preset-all'));
    expect(onFiltersChange).toHaveBeenCalledWith({ priority: ['urgent'] });

    // Priority filter
    const prioSelect = screen.getByTestId('navigator-filter-priority');
    fireEvent.change(prioSelect, { target: { value: 'urgent' } });
    expect(onFiltersChange).toHaveBeenCalled();

    // Assignee filter
    const asgSelect = screen.getByTestId('navigator-filter-assignee');
    fireEvent.change(asgSelect, { target: { value: 'alice' } });
    expect(onFiltersChange).toHaveBeenCalled();

    // Label filter
    const lblSelect = screen.getByTestId('navigator-filter-label');
    fireEvent.change(lblSelect, { target: { value: 'auth' } });
    expect(onFiltersChange).toHaveBeenCalled();

    // Cycle filter
    const cycleSelect = screen.getByTestId('navigator-filter-cycle');
    fireEvent.change(cycleSelect, { target: { value: 'c-1' } });
    expect(onFiltersChange).toHaveBeenCalled();

    // Module filter (with modulesEnabled)
    const modSelect = screen.getByTestId('navigator-filter-module');
    fireEvent.change(modSelect, { target: { value: 'm-1' } });
    expect(onFiltersChange).toHaveBeenCalled();

    // Reset priority filter to all
    fireEvent.change(prioSelect, { target: { value: 'all' } });
    expect(onFiltersChange).toHaveBeenCalled();
  });

  it('renders hidden-completed-banner when search matches hidden completed/cancelled issues and reveals them on Show all', () => {
    const { rerender } = render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        queryMode="basic"
        searchQuery="Database"
      />,
    );

    const banner = screen.getByTestId('hidden-completed-banner');
    expect(banner.textContent).toContain('1 completed/cancelled issue(s) hidden');

    // Exact key match banner text
    rerender(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        queryMode="basic"
        searchQuery="KAN-2"
      />,
    );
    expect(screen.getByTestId('hidden-completed-banner').textContent).toContain('KAN-2 is hidden (Done)');

    // Clicking Show all reveals completed issues and hides banner
    fireEvent.click(screen.getByTestId('hidden-completed-show-all-btn'));
    expect(screen.queryByTestId('hidden-completed-banner')).toBeNull();
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

    // Select view via dropdown
    const viewSelect = screen.getByTestId('navigator-saved-views-select');
    fireEvent.change(viewSelect, { target: { value: 'view-2' } });
    expect(onSelectSavedView).toHaveBeenCalledWith('view-2');
    fireEvent.change(viewSelect, { target: { value: '' } });
  });

  it('invokes onExport, onImport, and onExportReports callbacks when provided as props', () => {
    const onExport = vi.fn();
    const onImport = vi.fn();
    const onExportReports = vi.fn();

    render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        onExport={onExport}
        onImport={onImport}
        onExportReports={onExportReports}
      />,
    );

    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    expect(onExport).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('navigator-import-btn'));
    expect(onImport).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('navigator-reports-export-btn'));
    expect(onExportReports).toHaveBeenCalledTimes(1);
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

    const prioSelect = screen.getByTestId('navigator-filter-priority');
    fireEvent.change(prioSelect, { target: { value: 'low' } });
  });

  it('toggles filters expansion via mobile filters toggle button and opens/closes CSV and Reports modals', () => {
    render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        queryMode="basic"
      />,
    );

    const toggleBtn = screen.getByTestId('navigator-filters-toggle');
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggleBtn);
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('true');
    fireEvent.click(toggleBtn);
    expect(toggleBtn.getAttribute('aria-expanded')).toBe('false');

    // Open and close CSV Export modal
    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    expect(screen.getByTestId('csv-import-export-modal')).toBeDefined();
    fireEvent.click(screen.getByTestId('csv-modal-close-btn'));
    expect(screen.queryByTestId('csv-import-export-modal')).toBeNull();

    // Open and close CSV Import modal
    fireEvent.click(screen.getByTestId('navigator-import-btn'));
    expect(screen.getByTestId('csv-import-export-modal')).toBeDefined();
    fireEvent.click(screen.getByTestId('csv-modal-close-btn'));

    // Open and close Reports Export modal
    fireEvent.click(screen.getByTestId('navigator-reports-export-btn'));
    expect(screen.getByTestId('report-export-backdrop')).toBeDefined();
    fireEvent.click(screen.getByTestId('report-export-close-btn'));
    expect(screen.queryByTestId('report-export-backdrop')).toBeNull();
  });

  describe('Space-Preserving Header Modes (KAN-377)', () => {
    it('defaults to 1col mode, renders data-header-mode="1col", and updates on 2-Col and 1-Line button clicks', () => {
      const onHeaderModeChange = vi.fn();
      render(
        <IssueNavigatorBar
          projectKey="KAN"
          issues={mockIssues}
          onHeaderModeChange={onHeaderModeChange}
        />,
      );

      const navBar = screen.getByTestId('issue-navigator-bar');
      expect(navBar.getAttribute('data-header-mode')).toBe('1col');
      expect(navBar.classList.contains('issue-navigator-bar--1col')).toBe(true);

      const col1Btn = screen.getByTestId('header-mode-1col-btn');
      const col2Btn = screen.getByTestId('header-mode-basic-2col-btn');
      const line1Btn = screen.getByTestId('header-mode-advanced-1line-btn');

      expect(col1Btn.getAttribute('aria-pressed')).toBe('true');
      expect(col2Btn.getAttribute('aria-pressed')).toBe('false');
      expect(line1Btn.getAttribute('aria-pressed')).toBe('false');

      // Switch to Basic 2-Col
      fireEvent.click(col2Btn);
      expect(navBar.getAttribute('data-header-mode')).toBe('basic-2col');
      expect(navBar.classList.contains('issue-navigator-bar--basic-2col')).toBe(true);
      expect(col2Btn.getAttribute('aria-pressed')).toBe('true');
      expect(col1Btn.getAttribute('aria-pressed')).toBe('false');
      expect(localStorage.getItem(NAVIGATOR_HEADER_MODE_STORAGE_KEY)).toBe('basic-2col');
      expect(onHeaderModeChange).toHaveBeenCalledWith('basic-2col');

      // Switch to Advanced 1-Line
      fireEvent.click(line1Btn);
      expect(navBar.getAttribute('data-header-mode')).toBe('advanced-1line');
      expect(navBar.classList.contains('issue-navigator-bar--advanced-1line')).toBe(true);
      expect(line1Btn.getAttribute('aria-pressed')).toBe('true');
      expect(col2Btn.getAttribute('aria-pressed')).toBe('false');
      expect(localStorage.getItem(NAVIGATOR_HEADER_MODE_STORAGE_KEY)).toBe('advanced-1line');
      expect(onHeaderModeChange).toHaveBeenCalledWith('advanced-1line');

      // Switch back to 1-Col
      fireEvent.click(col1Btn);
      expect(navBar.getAttribute('data-header-mode')).toBe('1col');
      expect(col1Btn.getAttribute('aria-pressed')).toBe('true');
      expect(localStorage.getItem(NAVIGATOR_HEADER_MODE_STORAGE_KEY)).toBe('1col');
      expect(onHeaderModeChange).toHaveBeenCalledWith('1col');
    });

    it('initializes from persisted localStorage mode when valid', () => {
      localStorage.setItem(NAVIGATOR_HEADER_MODE_STORAGE_KEY, 'advanced-1line');

      render(
        <IssueNavigatorBar
          projectKey="KAN"
          issues={mockIssues}
        />,
      );

      const navBar = screen.getByTestId('issue-navigator-bar');
      expect(navBar.getAttribute('data-header-mode')).toBe('advanced-1line');
      expect(screen.getByTestId('header-mode-advanced-1line-btn').getAttribute('aria-pressed')).toBe('true');
    });

    it('honors controlled headerMode prop and reacts to prop changes', () => {
      const { rerender } = render(
        <IssueNavigatorBar
          projectKey="KAN"
          issues={mockIssues}
          headerMode="basic-2col"
        />,
      );

      const navBar = screen.getByTestId('issue-navigator-bar');
      expect(navBar.getAttribute('data-header-mode')).toBe('basic-2col');

      rerender(
        <IssueNavigatorBar
          projectKey="KAN"
          issues={mockIssues}
          headerMode="advanced-1line"
        />,
      );
      expect(navBar.getAttribute('data-header-mode')).toBe('advanced-1line');
    });

    it('handles localStorage errors gracefully during initialization and mode changes', () => {
      const getItemSpy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
        throw new Error('Storage disabled');
      });
      const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new Error('Quota exceeded');
      });

      const onHeaderModeChange = vi.fn();
      render(
        <IssueNavigatorBar
          projectKey="KAN"
          issues={mockIssues}
          onHeaderModeChange={onHeaderModeChange}
        />,
      );

      const navBar = screen.getByTestId('issue-navigator-bar');
      expect(navBar.getAttribute('data-header-mode')).toBe('1col');

      // Click to switch mode should still work internally and call callback despite setItem failure
      fireEvent.click(screen.getByTestId('header-mode-basic-2col-btn'));
      expect(navBar.getAttribute('data-header-mode')).toBe('basic-2col');
      expect(onHeaderModeChange).toHaveBeenCalledWith('basic-2col');

      getItemSpy.mockRestore();
      setItemSpy.mockRestore();
    });
  });
});
