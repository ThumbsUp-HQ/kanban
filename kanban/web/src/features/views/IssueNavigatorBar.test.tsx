import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { ShellPanelsProvider, registerShellPanel, useShellPanels } from '../../app/shellPanels';
import {
  IssueNavigatorBar,
  NAVIGATOR_HEADER_MODE_STORAGE_KEY,
} from './IssueNavigatorBar';
import {
  ISSUE_FILTER_COOKIE_NAME,
  createActionableStateFilterPreference,
} from './issueFilterCookie';
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

  it('calls onShowAllStates callback when clicking Show all in hidden-completed banner', () => {
    const onShowAllStates = vi.fn();
    const { unmount: unmount1 } = render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        queryMode="basic"
        searchQuery="KAN-2"
        onShowAllStates={onShowAllStates}
      />,
    );

    const banner = screen.getByTestId('hidden-completed-banner');
    expect(banner).toBeDefined();
    fireEvent.click(screen.getByTestId('hidden-completed-show-all-btn'));
    expect(onShowAllStates).toHaveBeenCalledTimes(1);
    unmount1();

    // Explicit hiddenCompletedCount and hiddenExactMatch props
    const { unmount: unmount2 } = render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        hiddenCompletedCount={5}
        hiddenExactMatch={{ key: 'KAN-99', stateName: 'Done' }}
      />,
    );
    expect(screen.getByTestId('hidden-completed-banner').textContent).toContain('KAN-99 is hidden (Done)');
    unmount2();

    // Exact match with empty state name falling back to state group
    const fallbackStateIssues: IssueItem[] = [
      {
        id: 'i-fallback',
        key: 'KAN-FALLBACK',
        summary: 'Fallback state issue',
        state: { id: 's-done', name: '', group: 'completed' },
        priority: { slug: 'low', label: 'Low' },
      },
    ];
    const { unmount: unmountFallback } = render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={fallbackStateIssues}
        searchQuery="KAN-FALLBACK"
      />,
    );
    expect(screen.getByTestId('hidden-completed-banner').textContent).toContain('KAN-FALLBACK is hidden (completed)');
    unmountFallback();
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

    // Render with activeViewId undefined
    rerender(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={mockIssues}
        savedViews={mockSavedViews}
        onSelectSavedView={onSelectSavedView}
      />,
    );
    expect(screen.getByTestId('navigator-saved-views-select')).toBeDefined();
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
    expect(screen.getByTestId('navigator-export-menu')).toBeDefined();
    // Non-Escape key does not close menu
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByTestId('navigator-export-menu')).toBeDefined();

    // Inside click does not close menu
    fireEvent.mouseDown(screen.getByTestId('navigator-export-menu'));
    expect(screen.getByTestId('navigator-export-menu')).toBeDefined();

    // Press Escape to close export menu
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('navigator-export-menu')).toBeNull();

    // Open export menu and click outside to close
    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    expect(screen.getByTestId('navigator-export-menu')).toBeDefined();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId('navigator-export-menu')).toBeNull();

    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    fireEvent.click(screen.getByTestId('navigator-export-opt-csv'));
    expect(onExport).toHaveBeenCalledWith('csv');

    // Click ZIP option from export dropdown
    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    fireEvent.click(screen.getByTestId('navigator-export-opt-zip'));
    expect(onExport).toHaveBeenCalledWith('zip_csv');

    // Click template option from export dropdown
    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    fireEvent.click(screen.getByTestId('navigator-export-opt-template'));
    expect(onExportReports).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('navigator-import-btn'));
    expect(onImport).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('navigator-reports-export-btn'));
    expect(onExportReports).toHaveBeenCalledTimes(2);
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
    fireEvent.change(prioSelect, { target: { value: 'all' } });

    // Controlled stateFilter and query mode with explicit state predicate
    const { unmount } = render(
      <IssueNavigatorBar
        projectKey="KAN"
        issues={defensiveIssues}
        stateFilter={createActionableStateFilterPreference()}
        queryMode="query"
        searchQuery="state:completed"
      />,
    );
    unmount();
    fireEvent.change(prioSelect, { target: { value: 'low' } });
  });

  it('toggles filters expansion via mobile filters toggle button and opens/closes CSV, ZIP, and Reports modals', () => {
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

    // Open export dropdown menu
    const exportBtn = screen.getByTestId('navigator-export-btn');
    expect(exportBtn.getAttribute('aria-haspopup')).toBe('menu');
    expect(exportBtn.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(exportBtn);
    expect(exportBtn.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByTestId('navigator-export-menu')).toBeDefined();

    // 1. Open and close CSV Export modal via CSV option
    fireEvent.click(screen.getByTestId('navigator-export-opt-csv'));
    expect(screen.getByTestId('csv-import-export-modal')).toBeDefined();
    const csvRadio = screen.getByTestId<HTMLInputElement>('export-format-csv');
    expect(csvRadio.checked).toBe(true);
    fireEvent.click(screen.getByTestId('csv-modal-close-btn'));
    expect(screen.queryByTestId('csv-import-export-modal')).toBeNull();

    // 2. Open and close ZIP Export modal via Password-Protected ZIP option
    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    fireEvent.click(screen.getByTestId('navigator-export-opt-zip'));
    expect(screen.getByTestId('csv-import-export-modal')).toBeDefined();
    const zipRadio = screen.getByTestId<HTMLInputElement>('export-format-zip');
    expect(zipRadio.checked).toBe(true);
    fireEvent.click(screen.getByTestId('csv-modal-close-btn'));
    expect(screen.queryByTestId('csv-import-export-modal')).toBeNull();

    // 3. Open and close Reports Export modal via Report Template option
    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    fireEvent.click(screen.getByTestId('navigator-export-opt-template'));
    expect(screen.getByTestId('report-export-backdrop')).toBeDefined();
    fireEvent.click(screen.getByTestId('report-export-close-btn'));
    expect(screen.queryByTestId('report-export-backdrop')).toBeNull();

    // 4. Open and close CSV Import modal
    fireEvent.click(screen.getByTestId('navigator-import-btn'));
    expect(screen.getByTestId('csv-import-export-modal')).toBeDefined();
    fireEvent.click(screen.getByTestId('csv-modal-close-btn'));

    // 5. Backwards-compatible alias for navigator-reports-export-btn
    fireEvent.click(screen.getByTestId('navigator-reports-export-btn'));
    expect(screen.getByTestId('report-export-backdrop')).toBeDefined();
    fireEvent.click(screen.getByTestId('report-export-close-btn'));
    expect(screen.queryByTestId('report-export-backdrop')).toBeNull();

    // 6. Test menu dismissal with Escape key and outside click
    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    expect(screen.getByTestId('navigator-export-menu')).toBeDefined();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('navigator-export-menu')).toBeNull();

    fireEvent.click(screen.getByTestId('navigator-export-btn'));
    expect(screen.getByTestId('navigator-export-menu')).toBeDefined();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId('navigator-export-menu')).toBeNull();
  });

  describe('Space-Preserving Header Modes (KAN-377 & KAN-386)', () => {
    it('renders compact expand/contract density toggle button as first child of top row and cycles through modes', () => {
      const onHeaderModeChange = vi.fn();
      render(
        <IssueNavigatorBar
          projectKey="KAN"
          issues={mockIssues}
          onHeaderModeChange={onHeaderModeChange}
        />,
      );

      const navBar = screen.getByTestId('issue-navigator-bar');
      const topRow = navBar.querySelector('.navigator-top-row');
      expect(topRow).not.toBeNull();

      // Density toggle button MUST be the first element in .navigator-top-row (before search form)
      const toggleBtn = screen.getByTestId('navigator-header-density-toggle');
      expect(topRow?.firstElementChild).toBe(toggleBtn);
      const searchForm = navBar.querySelector('.navigator-search-form');
      expect(toggleBtn.nextElementSibling).toBe(searchForm);

      // 1. Initial 1col mode checks
      expect(toggleBtn.getAttribute('data-header-mode')).toBe('1col');
      expect(toggleBtn.getAttribute('title')).toBe('Header layout: Compact 1-Column (click to expand to 2-Column)');
      expect(toggleBtn.getAttribute('aria-label')).toBe('Cycle header layout mode (current: 1-Col)');
      expect(toggleBtn.querySelector('.navigator-density-icon--expand')).not.toBeNull();
      expect(navBar.getAttribute('data-header-mode')).toBe('1col');

      // 2. Click 1: transition to basic-2col
      fireEvent.click(toggleBtn);
      expect(toggleBtn.getAttribute('data-header-mode')).toBe('basic-2col');
      expect(toggleBtn.getAttribute('title')).toBe('Header layout: Expanded 2-Column (click for 1-Line compact)');
      expect(toggleBtn.getAttribute('aria-label')).toBe('Cycle header layout mode (current: 2-Col)');
      expect(toggleBtn.querySelector('.navigator-density-icon--collapse-1line')).not.toBeNull();
      expect(navBar.getAttribute('data-header-mode')).toBe('basic-2col');
      expect(localStorage.getItem(NAVIGATOR_HEADER_MODE_STORAGE_KEY)).toBe('basic-2col');
      expect(onHeaderModeChange).toHaveBeenLastCalledWith('basic-2col');

      // 3. Click 2: transition to advanced-1line
      fireEvent.click(toggleBtn);
      expect(toggleBtn.getAttribute('data-header-mode')).toBe('advanced-1line');
      expect(toggleBtn.getAttribute('title')).toBe('Header layout: Single-Line (click to contract to 1-Column)');
      expect(toggleBtn.getAttribute('aria-label')).toBe('Cycle header layout mode (current: 1-Line)');
      expect(toggleBtn.querySelector('.navigator-density-icon--contract-1col')).not.toBeNull();
      expect(navBar.getAttribute('data-header-mode')).toBe('advanced-1line');
      expect(localStorage.getItem(NAVIGATOR_HEADER_MODE_STORAGE_KEY)).toBe('advanced-1line');
      expect(onHeaderModeChange).toHaveBeenLastCalledWith('advanced-1line');

      // 4. Click 3: cycle back to 1col
      fireEvent.click(toggleBtn);
      expect(toggleBtn.getAttribute('data-header-mode')).toBe('1col');
      expect(toggleBtn.getAttribute('title')).toBe('Header layout: Compact 1-Column (click to expand to 2-Column)');
      expect(toggleBtn.getAttribute('aria-label')).toBe('Cycle header layout mode (current: 1-Col)');
      expect(toggleBtn.querySelector('.navigator-density-icon--expand')).not.toBeNull();
      expect(navBar.getAttribute('data-header-mode')).toBe('1col');
      expect(localStorage.getItem(NAVIGATOR_HEADER_MODE_STORAGE_KEY)).toBe('1col');
      expect(onHeaderModeChange).toHaveBeenLastCalledWith('1col');
    });

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

  describe('FieldHelpHint, StudioDocLink & Shift-Left Invariants (KAN-477)', () => {
    it('renders FieldHelpHint and StudioDocLink as accessible adjacent sibling controls (KAN-477)', () => {
      const { container } = render(
        <IssueNavigatorBar
          projectKey="KAN"
          issues={mockIssues}
          queryMode="basic"
        />,
      );

      // 1. Verify existence of FieldHelpHint trigger and StudioDocLink
      const searchHelp = screen.getByTestId('search-mode-help');
      const docLink = screen.getByTestId('issue-navigator-doc-link');
      expect(searchHelp).toBeDefined();
      expect(docLink).toBeDefined();

      // 2. HTML 4.10.4 Invariants: NEVER nested inside <label> or another <button>
      expect(searchHelp.closest('label')).toBeNull();
      expect(searchHelp.closest('button.navigator-mode-btn')).toBeNull();
      expect(docLink.closest('label')).toBeNull();
      expect(docLink.closest('button')).toBeNull();

      // Sibling and container check
      const modeWrap = searchHelp.closest('.navigator-mode-wrap');
      expect(modeWrap).not.toBeNull();
      expect(modeWrap?.querySelector('.navigator-mode-group')).not.toBeNull();

      // Strict querySelectorAll assertion mandated by KAN-477 / HTML 4.10.4
      const invalidNestedElements = container.querySelectorAll(
        'label button.field-help-hint, button button.field-help-hint, label a.kb-studio-doc-link, button a.kb-studio-doc-link',
      );
      expect(invalidNestedElements.length).toBe(0);
      expect(
        document.querySelectorAll(
          'label button.field-help-hint, button button.field-help-hint, label a.kb-studio-doc-link, button a.kb-studio-doc-link',
        ).length,
      ).toBe(0);

      // 3. ARIA attributes and link properties
      expect(searchHelp.getAttribute('aria-label')).toBe('Help for Search Mode');
      expect(searchHelp.getAttribute('aria-haspopup')).toBe('dialog');
      expect(docLink.getAttribute('href')).toBe(
        '/docs/ticket-screen-and-work-item-features#search-and-filtering',
      );
      expect(docLink.textContent).toContain('Search Guide ->');
    });

    it('opens Search Mode FieldHelpHint popover and verifies summary, defaultValue, validValues, and docHref wiki link (KAN-477)', async () => {
      render(
        <IssueNavigatorBar
          projectKey="KAN"
          issues={mockIssues}
          queryMode="basic"
        />,
      );

      const searchHelp = screen.getByTestId('search-mode-help');
      fireEvent.click(searchHelp);

      await waitFor(() => {
        expect(
          screen.getByText('Toggle between simple text search and structured query syntax.'),
        ).toBeDefined();
      });

      // Default value assertion
      expect(screen.getByTestId('search-mode-help-default')).toBeDefined();
      expect(within(screen.getByTestId('search-mode-help-default')).getByText('Basic')).toBeDefined();

      // Valid values list
      expect(
        screen.getByText('Simple keyword search across summary, key, and details.'),
      ).toBeDefined();
      expect(
        screen.getByText('Structured syntax with attribute predicates and operators.'),
      ).toBeDefined();

      // Deep documentation link in popover
      const popoverLink = screen.getByTestId('search-mode-help-doc-link');
      expect(popoverLink.getAttribute('href')).toBe(
        '/docs/ticket-screen-and-work-item-features#search-and-filtering',
      );

      // Escape key dismisses popover
      fireEvent.keyDown(searchHelp, { key: 'Escape' });
      await waitFor(() => {
        expect(
          screen.queryByText('Toggle between simple text search and structured query syntax.'),
        ).toBeNull();
      });
    });

    it('opens HelpDrawer when StudioDocLink is clicked inside ShellPanelsProvider (KAN-477)', () => {
      const unregister = registerShellPanel('help', () => <div data-testid="mock-help-drawer" />);

      function PanelWatcher() {
        const { activePanel } = useShellPanels();
        return (
          <div>
            <div data-testid="active-panel-id">{activePanel?.id ?? 'none'}</div>
            <div data-testid="active-panel-arg">{JSON.stringify(activePanel?.arg ?? {})}</div>
          </div>
        );
      }

      try {
        render(
          <ShellPanelsProvider>
            <IssueNavigatorBar
              projectKey="KAN"
              issues={mockIssues}
            />
            <PanelWatcher />
          </ShellPanelsProvider>,
        );

        const docLink = screen.getByTestId('issue-navigator-doc-link');
        const idElem = screen.getByTestId('active-panel-id');
        expect(idElem.textContent).toBe('none');

        act(() => {
          fireEvent.click(docLink);
        });

        expect(idElem.textContent).toBe('help');
        const argElem = screen.getByTestId('active-panel-arg');
        expect(JSON.parse(argElem.textContent || '{}')).toEqual({
          href: '/docs/ticket-screen-and-work-item-features#search-and-filtering',
          title: 'Search Guide ->',
        });
      } finally {
        unregister();
      }
    });

    it('enforces static AST invariants: zero inline styles and zero nested FieldHelpHint in label (KAN-477)', () => {
      const tsxPath = path.resolve(__dirname, 'IssueNavigatorBar.tsx');
      const source = fs.readFileSync(tsxPath, 'utf8');

      // Zero inline style={{...}} props
      expect(source).not.toMatch(/style\s*=\s*\{\{/);

      // Zero FieldHelpHint or StudioDocLink nested inside <label>...</label>
      expect(source).not.toMatch(/<label[^>]*>(?:(?!<\/label>)[\s\S])*?<FieldHelpHint/i);
      expect(source).not.toMatch(/<label[^>]*>(?:(?!<\/label>)[\s\S])*?<StudioDocLink/i);

      // Zero FieldHelpHint or StudioDocLink nested inside <button>...</button>
      expect(source).not.toMatch(/<button\b(?![^>]*\/>)[^>]*>(?:(?!<\/button>)[\s\S])*?<FieldHelpHint/i);
      expect(source).not.toMatch(/<button\b(?![^>]*\/>)[^>]*>(?:(?!<\/button>)[\s\S])*?<StudioDocLink/i);
    });
  });
});
