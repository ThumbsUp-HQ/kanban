/**
 * Search Bar Flex Basis Collision and Overlap Regression Test Suite (KAN-385).
 * Validates flex basis, min-width, and flex-shrink: 0 invariants across
 * IssueNavigatorBar.css and filterBulk.css, and validates component DOM structure
 * across 1col, basic-2col, and advanced-1line header modes.
 *
 * Strict Security and Style Invariants:
 * - Apache-2.0 License
 * - Zero em-dashes and en-dashes (plain ASCII hyphens only)
 * - Strict CSP conformance
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { IssueNavigatorBar } from '../IssueNavigatorBar';
import { FilterDisplayBar } from '../FilterDisplayBar';
import { createAllStatesFilterPreference } from '../issueFilterCookie';
import type { IssueItem, StateSummary } from '../viewsApi';

const MOCK_STATES: StateSummary[] = [
  { id: 'st-backlog', name: 'Backlog', group: 'backlog', color_hex: '#64748b', sort_order: 1 },
  { id: 'st-todo', name: 'Todo', group: 'unstarted', color_hex: '#f59e0b', sort_order: 2 },
  { id: 'st-prog', name: 'In Progress', group: 'started', color_hex: '#3b82f6', sort_order: 3 },
  { id: 'st-done', name: 'Done', group: 'completed', color_hex: '#10b981', sort_order: 4 },
];

const MOCK_ISSUES: IssueItem[] = [
  {
    id: 'issue-1',
    key: 'KAN-1',
    summary: 'Search bar collision regression verification issue',
    state: { id: 'st-todo', name: 'Todo', group: 'unstarted' },
    priority: { slug: 'high', label: 'High' },
  },
  {
    id: 'issue-2',
    key: 'KAN-2',
    summary: 'States filter popover non-overlap verification issue',
    state: { id: 'st-prog', name: 'In Progress', group: 'started' },
    priority: { slug: 'medium', label: 'Medium' },
  },
];

describe('SearchBarOverlapRegression - KAN-385 Flex Basis and Non-Overlap Invariants', () => {
  const issueNavigatorCssPath = path.resolve(__dirname, '../IssueNavigatorBar.css');
  const filterBulkCssPath = path.resolve(__dirname, '../filterBulk.css');

  beforeEach(() => {
    localStorage.clear();
  });

  describe('CSS Invariants: IssueNavigatorBar.css', () => {
    it('verifies IssueNavigatorBar.css exists and contains required flex basis and min-width rules', () => {
      expect(fs.existsSync(issueNavigatorCssPath)).toBe(true);
      const css = fs.readFileSync(issueNavigatorCssPath, 'utf8');

      // 1. .navigator-search-form flex basis 280px and min-width: 0 to prevent rigid blowouts
      expect(css).toMatch(/\.navigator-search-form\s*\{[^}]*flex:\s*1\s+1\s+280px;/);
      expect(css).toMatch(/\.navigator-search-form\s*\{[^}]*min-width:\s*0;/);
      expect(css).toMatch(/\.navigator-search-form\s*\{[^}]*max-width:\s*100%;/);
      expect(css).toMatch(/\.navigator-search-form\s*\{[^}]*box-sizing:\s*border-box;/);

      // 2. .navigator-search-input, .navigator-query-input flex: 1 1 120px and min-width: 0
      expect(css).toMatch(/\.navigator-search-input,\s*\n?\.navigator-query-input\s*\{[^}]*flex:\s*1\s+1\s+120px;/);
      expect(css).toMatch(/\.navigator-search-input,\s*\n?\.navigator-query-input\s*\{[^}]*min-width:\s*0;/);
      expect(css).toMatch(/\.navigator-search-input,\s*\n?\.navigator-query-input\s*\{[^}]*width:\s*100%;/);

      // 3. Buttons, mode group, header group, csv actions, and state filter trigger flex-shrink: 0
      expect(css).toMatch(/\.navigator-search-btn,\s*\n?(?:\.navigator-mode-wrap,\s*\n?)?\.navigator-mode-group,\s*\n?\.navigator-header-mode-group,\s*\n?\.navigator-csv-actions,\s*\n?\.state-filter-popover-wrap,\s*\n?\.navigator-state-trigger\s*\{[^}]*flex-shrink:\s*0;/);

      // 4. Advanced 1-line mode (data-header-mode="advanced-1line")
      expect(css).toMatch(/\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-top-row\s*\{[^}]*min-width:\s*max-content;/);
      expect(css).toMatch(/\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-top-row\s*\{[^}]*flex-shrink:\s*0;/);
      expect(css).toMatch(/\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-search-form\s*\{[^}]*flex:\s*1\s+0\s+220px;/);
      expect(css).toMatch(/\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-search-form\s*\{[^}]*min-width:\s*220px;/);
      expect(css).toMatch(/\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-search-input,\s*\n?\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-query-input\s*\{[^}]*min-width:\s*100px;/);
      expect(css).toMatch(/\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-search-input,\s*\n?\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-query-input\s*\{[^}]*flex:\s*1\s+1\s+auto;/);
      expect(css).toMatch(/\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-filters-row\s*\{[^}]*min-width:\s*max-content;/);
      expect(css).toMatch(/\.issue-navigator-bar\[data-header-mode="advanced-1line"\]\s+\.navigator-filters-row\s*\{[^}]*flex-shrink:\s*0;/);
    });
  });

  describe('CSS Invariants: filterBulk.css', () => {
    it('verifies filterBulk.css exists and contains required flex basis, shrink, and responsive rules', () => {
      expect(fs.existsSync(filterBulkCssPath)).toBe(true);
      const css = fs.readFileSync(filterBulkCssPath, 'utf8');

      // 1. .filter-search-form flex basis 380px and min-width: min(100%, 340px)
      expect(css).toMatch(/\.filter-search-form\s*\{[^}]*flex:\s*1\s+1\s+380px;/);
      expect(css).toMatch(/\.filter-search-form\s*\{[^}]*min-width:\s*min\(100%,\s*340px\);/);
      expect(css).toMatch(/\.filter-search-form\s*\{[^}]*max-width:\s*100%;/);
      expect(css).toMatch(/\.filter-search-form\s*\{[^}]*box-sizing:\s*border-box;/);
      expect(css).toMatch(/\.filter-search-form\s*\{[^}]*flex-wrap:\s*nowrap;/);

      // 2. Inputs inside .filter-search-form
      expect(css).toMatch(/\.filter-search-form\s+\.navigator-search-input,\s*\n?\.filter-search-form\s+\.navigator-query-input\s*\{[^}]*flex:\s*1\s+1\s+120px;/);
      expect(css).toMatch(/\.filter-search-form\s+\.navigator-search-input,\s*\n?\.filter-search-form\s+\.navigator-query-input\s*\{[^}]*min-width:\s*80px;/);

      // 3. Sibling controls and buttons shrink protection
      expect(css).toMatch(/\.filter-search-form\s+\.navigator-search-btn,\s*\n?\.filter-search-form\s+\.navigator-mode-group,\s*\n?\.filter-controls-group,\s*\n?\.filter-controls-group\s*>\s*\*\s*\{[^}]*flex-shrink:\s*0;/);

      // 4. Responsive media query at <= 640px
      expect(css).toMatch(/@media\s*\(max-width:\s*640px\)\s*\{[^}]*\.filter-search-form\s*\{[^}]*flex-wrap:\s*wrap;[^}]*min-width:\s*100%;/);
    });
  });

  describe('Component Rendering: IssueNavigatorBar across Header Modes', () => {
    it('renders IssueNavigatorBar in 1col mode with search input, mode toggles, and state trigger', () => {
      const handleSearchSubmit = vi.fn();
      const handleSearchQueryChange = vi.fn();
      const handleQueryModeChange = vi.fn();
      const handleHeaderModeChange = vi.fn();

      render(
        <IssueNavigatorBar
          projectKey="KAN"
          headerMode="1col"
          queryMode="basic"
          searchQuery="test query"
          onSearchSubmit={handleSearchSubmit}
          onSearchQueryChange={handleSearchQueryChange}
          onQueryModeChange={handleQueryModeChange}
          onHeaderModeChange={handleHeaderModeChange}
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
        />
      );

      const bar = screen.getByTestId('issue-navigator-bar');
      expect(bar.getAttribute('data-header-mode')).toBe('1col');
      expect(bar.classList.contains('issue-navigator-bar--1col')).toBe(true);

      const input = screen.getByTestId<HTMLInputElement>('navigator-search-input');
      expect(input.value).toBe('test query');

      const basicBtn = screen.getByTestId('mode-basic-btn');
      const queryBtn = screen.getByTestId('mode-query-btn');
      expect(basicBtn.getAttribute('aria-pressed')).toBe('true');
      expect(queryBtn.getAttribute('aria-pressed')).toBe('false');

      fireEvent.click(queryBtn);
      expect(handleQueryModeChange).toHaveBeenCalledWith('query');

      const col2Btn = screen.getByTestId('header-mode-basic-2col-btn');
      fireEvent.click(col2Btn);
      expect(handleHeaderModeChange).toHaveBeenCalledWith('basic-2col');

      const stateTrigger = screen.getByTestId('navigator-filter-state');
      expect(stateTrigger).toBeDefined();
    });

    it('renders IssueNavigatorBar in basic-2col mode with query input when in query mode', () => {
      render(
        <IssueNavigatorBar
          projectKey="KAN"
          headerMode="basic-2col"
          queryMode="query"
          searchQuery='project = "KAN"'
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
        />
      );

      const bar = screen.getByTestId('issue-navigator-bar');
      expect(bar.getAttribute('data-header-mode')).toBe('basic-2col');

      const queryInput = screen.getByTestId<HTMLInputElement>('navigator-query-input');
      expect(queryInput.value).toBe('project = "KAN"');

      const queryBtn = screen.getByTestId('mode-query-btn');
      expect(queryBtn.getAttribute('aria-pressed')).toBe('true');
    });

    it('renders IssueNavigatorBar in advanced-1line mode and confirms both rows sit in single bar container', () => {
      const handleHeaderModeChange = vi.fn();

      const { container } = render(
        <IssueNavigatorBar
          projectKey="KAN"
          headerMode="advanced-1line"
          queryMode="basic"
          searchQuery=""
          onHeaderModeChange={handleHeaderModeChange}
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
        />
      );

      const bar = screen.getByTestId('issue-navigator-bar');
      expect(bar.getAttribute('data-header-mode')).toBe('advanced-1line');

      const topRow = container.querySelector('.navigator-top-row');
      const filtersRow = container.querySelector('.navigator-filters-row');
      expect(topRow).not.toBeNull();
      expect(filtersRow).not.toBeNull();

      const searchForm = container.querySelector('.navigator-search-form');
      expect(searchForm).not.toBeNull();

      const modeGroup = screen.getByTestId('navigator-mode-toggle');
      expect(modeGroup).toBeDefined();

      const headerModeGroup = screen.getByTestId('navigator-header-mode-selector');
      expect(headerModeGroup).toBeDefined();

      const stateTrigger = screen.getByTestId('navigator-filter-state');
      expect(stateTrigger).toBeDefined();
    });

    it('covers hidden banner with onShowAllStates callback and export menu outside click and escape key', () => {
      const onShowAllStates = vi.fn();
      const onExport = vi.fn();
      const onExportReports = vi.fn();

      const { rerender } = render(
        <IssueNavigatorBar
          projectKey="KAN"
          hiddenCompletedCount={3}
          hiddenExactMatch={{ key: 'KAN-99', stateName: 'Done' }}
          onShowAllStates={onShowAllStates}
          onExport={onExport}
          onExportReports={onExportReports}
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
        />
      );

      const banner = screen.getByTestId('hidden-completed-banner');
      expect(banner).toBeDefined();
      const showAllBtn = screen.getByTestId('hidden-completed-show-all-btn');
      fireEvent.click(showAllBtn);
      expect(onShowAllStates).toHaveBeenCalled();

      // Open Export dropdown menu and click ZIP option
      const exportBtn = screen.getByTestId('navigator-export-btn');
      fireEvent.click(exportBtn);
      const zipOpt = screen.getByTestId('navigator-export-opt-zip');
      fireEvent.click(zipOpt);
      expect(onExport).toHaveBeenCalledWith('zip_csv');

      // Re-open and click Template option
      fireEvent.click(exportBtn);
      const templateOpt = screen.getByTestId('navigator-export-opt-template');
      fireEvent.click(templateOpt);
      expect(onExportReports).toHaveBeenCalled();

      // Open again, press non-Escape key, click inside menu, then test escape key
      fireEvent.click(exportBtn);
      const menu = screen.getByTestId('navigator-export-menu');
      expect(menu).not.toBeNull();
      fireEvent.keyDown(document, { key: 'Tab' });
      expect(screen.queryByTestId('navigator-export-opt-csv')).not.toBeNull();
      fireEvent.mouseDown(menu);
      expect(screen.queryByTestId('navigator-export-opt-csv')).not.toBeNull();
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(screen.queryByTestId('navigator-export-opt-csv')).toBeNull();

      // Open again and test outside click
      fireEvent.click(exportBtn);
      expect(screen.queryByTestId('navigator-export-opt-csv')).not.toBeNull();
      fireEvent.mouseDown(document.body);
      expect(screen.queryByTestId('navigator-export-opt-csv')).toBeNull();

      // Rerender with hiddenExactMatch=null and singular count
      rerender(
        <IssueNavigatorBar
          projectKey="KAN"
          hiddenCompletedCount={1}
          hiddenExactMatch={null}
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
        />
      );
      expect(screen.getByTestId('hidden-completed-banner').textContent).toContain('1 completed/cancelled issue(s) hidden');
    });

    it('covers initial mounting branches for controlled stateFilter and activeFilters.state', () => {
      const { unmount: unmount1 } = render(
        <IssueNavigatorBar
          projectKey="KAN"
          stateFilter={createAllStatesFilterPreference()}
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
        />
      );
      expect(screen.getByTestId('navigator-filter-state')).toBeDefined();
      unmount1();

      const { unmount: unmount2 } = render(
        <IssueNavigatorBar
          projectKey="KAN"
          activeFilters={{ state: ['st-todo'] }}
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
        />
      );
      expect(screen.getByTestId('navigator-filter-state')).toBeDefined();
      unmount2();
    });

    it('covers saved views select with empty string selection branch', () => {
      const onSelectSavedView = vi.fn();
      render(
        <IssueNavigatorBar
          projectKey="KAN"
          savedViews={[{ id: 'v1', name: 'View 1', layout: 'list', group_by: 'state', sub_group_by: 'none' }]}
          onSelectSavedView={onSelectSavedView}
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
        />
      );
      const select = screen.getByTestId('navigator-saved-views-select');
      fireEvent.change(select, { target: { value: '' } });
      expect(onSelectSavedView).not.toHaveBeenCalled();
      fireEvent.change(select, { target: { value: 'v1' } });
      expect(onSelectSavedView).toHaveBeenCalledWith('v1');
    });
  });

  describe('Component Rendering: FilterDisplayBar', () => {
    it('renders FilterDisplayBar with search form and state filter trigger as discrete siblings', () => {
      const handleSearchSubmit = vi.fn();
      const handleSearchQueryChange = vi.fn();
      const handleQueryModeChange = vi.fn();
      const handleStateFilterChange = vi.fn();

      const { container } = render(
        <FilterDisplayBar
          projectKey="KAN"
          searchQuery="search phrase"
          onSearchSubmit={handleSearchSubmit}
          onSearchQueryChange={handleSearchQueryChange}
          queryMode="basic"
          onQueryModeChange={handleQueryModeChange}
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
          onStateFilterChange={handleStateFilterChange}
          groupBy="state"
          subGroupBy="none"
          modulesEnabled={true}
        />
      );

      const searchForm = screen.getByTestId('filter-display-search-form');
      expect(searchForm.classList.contains('filter-search-form')).toBe(true);

      const input = screen.getByTestId<HTMLInputElement>('filter-display-search-input');
      expect(input.value).toBe('search phrase');

      const searchBtn = screen.getByTestId('filter-display-search-btn');
      expect(searchBtn).toBeDefined();

      const basicBtn = screen.getByTestId('mode-basic-btn');
      const queryBtn = screen.getByTestId('mode-query-btn');
      expect(basicBtn.getAttribute('aria-pressed')).toBe('true');
      expect(queryBtn.getAttribute('aria-pressed')).toBe('false');

      fireEvent.click(queryBtn);
      expect(handleQueryModeChange).toHaveBeenCalledWith('query');

      // Check that filter-controls-group sits as sibling to filter-search-form
      const controlsGroup = container.querySelector('.filter-controls-group');
      expect(controlsGroup).not.toBeNull();
      expect(searchForm.nextElementSibling).toBe(controlsGroup);

      const stateTrigger = screen.getByTestId('navigator-filter-state');
      expect(stateTrigger).toBeDefined();
      expect(controlsGroup?.contains(stateTrigger)).toBe(true);
    });

    it('renders FilterDisplayBar with query input when in query mode and submits search', () => {
      const handleSearchSubmit = vi.fn();
      const handleSearchQueryChange = vi.fn();

      render(
        <FilterDisplayBar
          searchQuery='status = "In Progress"'
          onSearchSubmit={handleSearchSubmit}
          onSearchQueryChange={handleSearchQueryChange}
          queryMode="query"
          onQueryModeChange={vi.fn()}
          projectStates={MOCK_STATES}
          issues={MOCK_ISSUES}
          onStateFilterChange={vi.fn()}
        />
      );

      const queryInput = screen.getByTestId<HTMLInputElement>('filter-display-query-input');
      expect(queryInput.value).toBe('status = "In Progress"');

      fireEvent.change(queryInput, { target: { value: 'status = "Done"' } });
      expect(handleSearchQueryChange).toHaveBeenCalledWith('status = "Done"');

      const searchBtn = screen.getByTestId('filter-display-search-btn');
      fireEvent.click(searchBtn);
      expect(handleSearchSubmit).toHaveBeenCalled();
    });
  });
});
