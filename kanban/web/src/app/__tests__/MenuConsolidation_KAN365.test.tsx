// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, act, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FilterDisplayBar, type ActiveFilters } from '../../features/views/FilterDisplayBar';
import { IssueNavigatorBar } from '../../features/views/IssueNavigatorBar';
import { IssuesWorkspaceRoute } from '../../features/views/viewRegistry';
import type { IssueItem, SavedView, StateSummary } from '../../features/views/viewsApi';
import * as railApi from '../../features/drawer-rail/railApi';
import {
  createActionableStateFilterPreference,
} from '../../features/views/issueFilterCookie';

vi.mock('../../api/client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({ items: [] }),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
  apiFetch: vi.fn().mockResolvedValue({ items: [] }),
}));

describe('Menu & View Toolbar Consolidation Suite (KAN-365)', () => {
  let queryClient: QueryClient;

  const mockProjectStates: StateSummary[] = [
    { id: 'state-backlog', name: 'Backlog', group: 'backlog', color_hex: '#64748b' },
    { id: 'state-todo', name: 'Todo', group: 'unstarted', color_hex: '#3b82f6' },
    { id: 'state-in-progress', name: 'In Progress', group: 'started', color_hex: '#f59e0b' },
    { id: 'state-done', name: 'Done', group: 'completed', color_hex: '#10b981' },
    { id: 'state-cancelled', name: 'Cancelled', group: 'cancelled', color_hex: '#ef4444' },
  ];

  const mockIssues: IssueItem[] = [
    {
      id: 'iss-1',
      key: 'KAN-101',
      summary: 'Frontend Toolbar Polish',
      state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
      priority: { slug: 'high', label: 'High' },
      assignees: [
        {
          id: 'asg-1',
          kind: 'principal',
          principal: { id: 'u-1', handle: 'alice', display_name: 'Alice Cooper', type: 'USER' },
        },
      ],
      labels: [{ id: 'lbl-1', name: 'ui', color_hex: '#3b82f6' }],
      cycle_id: 'c-1',
      cycle: { id: 'c-1', name: 'Sprint 1' },
      module_ids: ['m-1'],
      modules: [{ id: 'm-1', name: 'Navigation' }],
    },
    {
      id: 'iss-2',
      key: 'KAN-102',
      summary: 'Backend Export Endpoint',
      state: { id: 'state-done', name: 'Done', group: 'completed' },
      priority: { slug: 'low', label: 'Low' },
      assignees: [],
    },
  ];

  const mockSavedViews: SavedView[] = [
    {
      id: 'view-triage',
      name: 'Daily Triage',
      layout: 'list',
      group_by: 'state',
      sub_group_by: 'none',
      filters: { search_query: 'status = "Todo"' },
    },
    {
      id: 'view-sprint',
      name: 'Sprint Board',
      layout: 'board',
      group_by: 'priority',
      sub_group_by: 'state',
    },
  ];

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    vi.spyOn(railApi, 'fetchAssigneeSuggestions').mockResolvedValue([]);
    vi.spyOn(railApi, 'fetchProjectLabels').mockResolvedValue([]);
    vi.spyOn(railApi, 'fetchProjectCycles').mockResolvedValue([]);
    vi.spyOn(railApi, 'fetchProjectModules').mockResolvedValue([]);
    vi.clearAllMocks();
  });

  describe('Test Case 1: Unified View Toolbar Filter & State Popover Consistency Across Layouts', () => {
    it('renders StateFilterPopover in both IssueNavigatorBar (List) and FilterDisplayBar (Non-List) with state presets', () => {
      const onStateFilterChangeList = vi.fn();
      const onStateFilterChangeBoard = vi.fn();
      const onFiltersChangeList = vi.fn();
      const onFiltersChangeBoard = vi.fn();

      const actionablePref = createActionableStateFilterPreference();

      // 1. Render List Toolbar (IssueNavigatorBar)
      let rendered: ReturnType<typeof render>;
      act(() => {
        rendered = render(
          <IssueNavigatorBar
            projectKey="KAN"
            issues={mockIssues}
            projectStates={mockProjectStates}
            stateFilter={actionablePref}
            onStateFilterChange={onStateFilterChangeList}
            onFiltersChange={onFiltersChangeList}
          />,
        );
      });

      const listStateBtn = screen.getByTestId('navigator-filter-state');
      expect(listStateBtn).toBeDefined();
      expect(listStateBtn.getAttribute('aria-label')).toMatch(/filter by state/i);

      // Open State Filter Popover in List toolbar
      act(() => {
        fireEvent.click(listStateBtn);
      });
      const allStatesPreset = screen.getByTestId('state-preset-all');
      expect(allStatesPreset).toBeDefined();
      act(() => {
        fireEvent.click(allStatesPreset);
      });
      expect(onStateFilterChangeList).toHaveBeenCalled();

      // 2. Render Board Toolbar (FilterDisplayBar) with unified StateFilterPopover
      act(() => {
        rendered.rerender(
          <FilterDisplayBar
            projectKey=""
            issues={mockIssues}
            projectStates={mockProjectStates}
            stateFilter={actionablePref}
            onStateFilterChange={onStateFilterChangeBoard}
            onFiltersChange={onFiltersChangeBoard}
            groupBy="state"
            subGroupBy="none"
          />,
        );
      });

      const boardStateBtn = screen.getByTestId('navigator-filter-state');
      expect(boardStateBtn).toBeDefined();
      expect(boardStateBtn.getAttribute('aria-label')).toMatch(/filter by state/i);

      // Open State Filter Popover in Board toolbar
      act(() => {
        fireEvent.click(boardStateBtn);
      });
      const actionablePreset = screen.getByTestId('state-preset-actionable');
      expect(actionablePreset).toBeDefined();
      act(() => {
        fireEvent.click(actionablePreset);
      });
      expect(onStateFilterChangeBoard).toHaveBeenCalled();
    });

    it('propagates state and facet changes consistently across toolbars and renders active chips', () => {
      const handleFiltersChange = vi.fn();
      const active: ActiveFilters = {
        state: ['state-todo'],
        priority: ['urgent'],
      };

      act(() => {
        render(
          <FilterDisplayBar
            projectKey=""
            issues={mockIssues}
            activeFilters={active}
            onFiltersChange={handleFiltersChange}
            groupBy="state"
            subGroupBy="none"
          />,
        );
      });

      // Active chips exist
      expect(screen.getByText(/Priority: 🔥 Urgent/i)).toBeDefined();

      // Remove priority chip
      const removeBtn = screen.getByRole('button', { name: /remove priority: 🔥 urgent filter/i });
      act(() => {
        fireEvent.click(removeBtn);
      });
      expect(handleFiltersChange).toHaveBeenCalledWith({
        state: ['state-todo'],
      });
    });
  });

  describe('Test Case 2: Search DSL & Saved Views Consistency Across All 5 Layouts', () => {
    it('supports basic text search and Query DSL toggle in both IssueNavigatorBar and FilterDisplayBar', () => {
      const onSearchChange = vi.fn();
      const onModeChange = vi.fn();
      const onSearchSubmit = vi.fn();

      // 1. IssueNavigatorBar search DSL
      let rendered: ReturnType<typeof render>;
      act(() => {
        rendered = render(
          <IssueNavigatorBar
            projectKey="KAN"
            searchQuery="initial query"
            onSearchQueryChange={onSearchChange}
            queryMode="basic"
            onQueryModeChange={onModeChange}
            onSearchSubmit={onSearchSubmit}
          />,
        );
      });

      const listSearchInput = screen.getByTestId('navigator-search-input');
      expect(listSearchInput).toBeDefined();
      act(() => {
        fireEvent.change(listSearchInput, { target: { value: 'updated search' } });
      });
      expect(onSearchChange).toHaveBeenCalledWith('updated search');

      const queryModeBtn = screen.getByTestId('mode-query-btn');
      act(() => {
        fireEvent.click(queryModeBtn);
      });
      expect(onModeChange).toHaveBeenCalledWith('query');

      // 2. FilterDisplayBar search DSL
      act(() => {
        rendered.rerender(
          <FilterDisplayBar
            projectKey=""
            searchQuery="board search"
            onSearchQueryChange={onSearchChange}
            queryMode="query"
            onQueryModeChange={onModeChange}
            onSearchSubmit={onSearchSubmit}
          />,
        );
      });

      const boardQueryInput = screen.getByTestId('filter-display-query-input');
      expect(boardQueryInput).toBeDefined();
      act(() => {
        fireEvent.change(boardQueryInput, { target: { value: 'status = "Done"' } });
      });
      expect(onSearchChange).toHaveBeenCalledWith('status = "Done"');

      const basicModeBtn = screen.getByTestId('mode-basic-btn');
      act(() => {
        fireEvent.click(basicModeBtn);
      });
      expect(onModeChange).toHaveBeenCalledWith('basic');

      const submitBtn = screen.getByTestId('filter-display-search-btn');
      act(() => {
        fireEvent.click(submitBtn);
      });
      expect(onSearchSubmit).toHaveBeenCalled();
    });

    it('renders saved views chip strip and dropdown selector across all view toolbars', () => {
      const onSelectSavedView = vi.fn();

      // 1. IssueNavigatorBar saved views
      let rendered: ReturnType<typeof render>;
      act(() => {
        rendered = render(
          <IssueNavigatorBar
            projectKey="KAN"
            savedViews={mockSavedViews}
            activeViewId="view-triage"
            onSelectSavedView={onSelectSavedView}
          />,
        );
      });

      expect(screen.getByTestId('navigator-saved-views-strip')).toBeDefined();
      expect(screen.getByTestId('saved-view-chip-view-triage')).toBeDefined();
      expect(screen.getByTestId('saved-view-chip-view-sprint')).toBeDefined();

      const listSelect = screen.getByTestId<HTMLSelectElement>('navigator-saved-views-select');
      expect(listSelect.value).toBe('view-triage');
      act(() => {
        fireEvent.change(listSelect, { target: { value: 'view-sprint' } });
      });
      expect(onSelectSavedView).toHaveBeenCalledWith('view-sprint');

      // 2. FilterDisplayBar saved views
      act(() => {
        rendered.rerender(
          <FilterDisplayBar
            projectKey=""
            savedViews={mockSavedViews}
            activeViewId="view-sprint"
            onSelectSavedView={onSelectSavedView}
          />,
        );
      });

      expect(screen.getByTestId('filter-display-saved-views')).toBeDefined();
      expect(screen.getByTestId('saved-view-chip-view-sprint')).toBeDefined();

      const boardSelect = screen.getByTestId<HTMLSelectElement>('filter-display-saved-views-select');
      expect(boardSelect.value).toBe('view-sprint');
      act(() => {
        fireEvent.change(boardSelect, { target: { value: 'view-triage' } });
      });
      expect(onSelectSavedView).toHaveBeenCalledWith('view-triage');

      // Click chip directly
      const triageChip = screen.getByTestId('saved-view-chip-view-triage');
      act(() => {
        fireEvent.click(triageChip);
      });
      expect(onSelectSavedView).toHaveBeenCalledWith('view-triage');
    });
  });

  describe('Test Case 3: Export & Import Actions Parity and Display Popover Refinement', () => {
    it('provides export and import action buttons in both IssueNavigatorBar and FilterDisplayBar Display popover', () => {
      const handleExport = vi.fn();
      const handleImport = vi.fn();
      const handleExportReports = vi.fn();
      const handleSaveView = vi.fn();

      // 1. IssueNavigatorBar export actions
      let rendered: ReturnType<typeof render>;
      act(() => {
        rendered = render(
          <IssueNavigatorBar
            projectKey="KAN"
            onExport={handleExport}
            onImport={handleImport}
            onExportReports={handleExportReports}
          />,
        );
      });

      const listExportBtn = screen.getByTestId('navigator-export-btn');
      const listImportBtn = screen.getByTestId('navigator-import-btn');
      const listReportsBtn = screen.getByTestId('navigator-reports-export-btn');

      // Open export dropdown and test CSV option
      act(() => {
        fireEvent.click(listExportBtn);
      });
      const optCsv = screen.getByTestId('navigator-export-opt-csv');
      act(() => {
        fireEvent.click(optCsv);
      });
      expect(handleExport).toHaveBeenCalledTimes(1);
      expect(handleExport).toHaveBeenCalledWith('csv');

      // Open export dropdown and test ZIP option
      act(() => {
        fireEvent.click(listExportBtn);
      });
      const optZip = screen.getByTestId('navigator-export-opt-zip');
      act(() => {
        fireEvent.click(optZip);
      });
      expect(handleExport).toHaveBeenCalledTimes(2);
      expect(handleExport).toHaveBeenCalledWith('zip_csv');

      // Open export dropdown and test Report Template option
      act(() => {
        fireEvent.click(listExportBtn);
      });
      const optTemplate = screen.getByTestId('navigator-export-opt-template');
      act(() => {
        fireEvent.click(optTemplate);
      });
      expect(handleExportReports).toHaveBeenCalledTimes(1);

      act(() => {
        fireEvent.click(listImportBtn);
      });
      expect(handleImport).toHaveBeenCalledTimes(1);

      // Backwards-compatible reports trigger alias
      act(() => {
        fireEvent.click(listReportsBtn);
      });
      expect(handleExportReports).toHaveBeenCalledTimes(2);

      // 2. FilterDisplayBar refined Display popover actions
      act(() => {
        rendered.rerender(
          <FilterDisplayBar
            projectKey=""
            onExport={handleExport}
            onImport={handleImport}
            onExportReports={handleExportReports}
            onSaveView={handleSaveView}
            savedViews={mockSavedViews}
            activeViewId="view-triage"
            onSelectSavedView={vi.fn()}
          />,
        );
      });

      // Open Display Configuration Popover
      const displayBtn = screen.getByRole('button', { name: /display configuration/i });
      act(() => {
        fireEvent.click(displayBtn);
      });

      const popover = screen.getByRole('dialog', { name: /display options/i });
      expect(popover).toBeDefined();

      // Verify refined popover content: Saved Views list, Save as view, Reports, Export, Import
      expect(within(popover).getByTestId('filter-display-saved-views-list')).toBeDefined();
      expect(within(popover).getByTestId('filter-display-save-view-btn')).toBeDefined();
      expect(within(popover).getByTestId('filter-display-export-opt-csv')).toBeDefined();
      expect(within(popover).getByTestId('filter-display-export-opt-zip')).toBeDefined();
      expect(within(popover).getByTestId('filter-display-reports-btn')).toBeDefined();
      expect(within(popover).getByTestId('filter-display-export-btn')).toBeDefined();
      expect(within(popover).getByTestId('filter-display-import-btn')).toBeDefined();

      // Trigger Save as view
      act(() => {
        fireEvent.click(within(popover).getByTestId('filter-display-save-view-btn'));
      });
      expect(handleSaveView).toHaveBeenCalledTimes(1);

      // Reopen and trigger Export Reports
      act(() => {
        fireEvent.click(displayBtn);
      });
      const reportsOption = screen.getByTestId('filter-display-reports-btn');
      act(() => {
        fireEvent.click(reportsOption);
      });
      expect(handleExportReports).toHaveBeenCalledTimes(3);

      // Reopen and trigger Export CSV via option
      act(() => {
        fireEvent.click(displayBtn);
      });
      const optCsvOption = screen.getByTestId('filter-display-export-opt-csv');
      act(() => {
        fireEvent.click(optCsvOption);
      });
      expect(handleExport).toHaveBeenCalledTimes(3);
      expect(handleExport).toHaveBeenCalledWith('csv');

      // Reopen and trigger Export ZIP via option
      act(() => {
        fireEvent.click(displayBtn);
      });
      const optZipOption = screen.getByTestId('filter-display-export-opt-zip');
      act(() => {
        fireEvent.click(optZipOption);
      });
      expect(handleExport).toHaveBeenCalledTimes(4);
      expect(handleExport).toHaveBeenCalledWith('zip_csv');

      // Reopen and trigger Export CSV via backwards-compatible export btn
      act(() => {
        fireEvent.click(displayBtn);
      });
      const exportOption = screen.getByTestId('filter-display-export-btn');
      act(() => {
        fireEvent.click(exportOption);
      });
      expect(handleExport).toHaveBeenCalledTimes(5);

      // Reopen and trigger Import CSV
      act(() => {
        fireEvent.click(displayBtn);
      });
      const importOption = screen.getByTestId('filter-display-import-btn');
      act(() => {
        fireEvent.click(importOption);
      });
      expect(handleImport).toHaveBeenCalledTimes(2);
    });

    it('covers fallback modal states when callback props are omitted in FilterDisplayBar and IssueNavigatorBar', () => {
      // Render without callback props; internal modal triggers will execute cleanly without crashing
      let rendered: ReturnType<typeof render>;
      act(() => {
        rendered = render(
          <IssueNavigatorBar
            projectKey=""
          />,
        );
      });

      const listExport = screen.getByTestId('navigator-export-btn');
      act(() => {
        fireEvent.click(listExport);
      });
      const optCsv = screen.getByTestId('navigator-export-opt-csv');
      act(() => {
        fireEvent.click(optCsv);
      });

      const listImport = screen.getByTestId('navigator-import-btn');
      act(() => {
        fireEvent.click(listImport);
      });

      const listReports = screen.getByTestId('navigator-reports-export-btn');
      act(() => {
        fireEvent.click(listReports);
      });

      // FilterDisplayBar fallback branch
      act(() => {
        rendered.rerender(
          <FilterDisplayBar
            projectKey=""
          />,
        );
      });

      const displayBtn = screen.getByRole('button', { name: /display configuration/i });
      act(() => {
        fireEvent.click(displayBtn);
      });

      const reportsBtn = screen.getByTestId('filter-display-reports-btn');
      act(() => {
        fireEvent.click(reportsBtn);
      });

      act(() => {
        fireEvent.click(displayBtn);
      });
      const exportBtn = screen.getByTestId('filter-display-export-btn');
      act(() => {
        fireEvent.click(exportBtn);
      });

      act(() => {
        fireEvent.click(displayBtn);
      });
      const importBtn = screen.getByTestId('filter-display-import-btn');
      act(() => {
        fireEvent.click(importBtn);
      });
    });

    it('verifies IssuesWorkspaceRoute wires FilterDisplayBar with unified search, saved view, and export props in board layout', async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?layout=board']}>
            <IssuesWorkspaceRoute
              projectKey="KAN"
              initialLayout="board"
              initialIssues={mockIssues}
            />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Board layout renders FilterDisplayBar with unified search form and Display configuration
      await waitFor(() => {
        expect(screen.getByTestId('filter-display-bar')).toBeDefined();
        expect(screen.getByTestId('filter-display-search-form')).toBeDefined();
        expect(screen.getByTestId('filter-display-search-input')).toBeDefined();
        expect(screen.getByRole('button', { name: /display configuration/i })).toBeDefined();
      });
    });
  });
});
