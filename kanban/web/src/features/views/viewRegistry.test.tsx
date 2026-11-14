import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReactNode } from 'react';
import React from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  IssuesWorkspaceRoute,
  viewRegistry,
  ViewHost,
  VIEW_REGISTRY,
} from './viewRegistry.tsx';
import { FIXTURE_12_ISSUES } from './fixtures';

function renderWithClient(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('viewRegistry and IssuesWorkspaceRoute', () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', {
      configurable: true,
      value: 900,
    });
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
      configurable: true,
      value: 124,
    });
  });

  it('contains entries for board, list, table, grid, calendar, and timeline', () => {
    expect(viewRegistry.board).toBeDefined();
    expect(viewRegistry.list).toBeDefined();
    expect(viewRegistry.table).toBeDefined();
    expect(viewRegistry.grid).toBeDefined();
    expect(viewRegistry.calendar).toBeDefined();
    expect(viewRegistry.timeline).toBeDefined();
    expect(viewRegistry.board.id).toBe('board');
  });

  it('renders IssuesWorkspaceRoute with board layout by default', () => {
    renderWithClient(<IssuesWorkspaceRoute projectKey="TEST" />);

    const workspace = screen.getByTestId('issues-workspace');
    expect(workspace).toBeDefined();
    expect(workspace.getAttribute('data-layout')).toBe('board');
    expect(screen.getByTestId('board-canvas')).toBeDefined();
  });

  it('renders IssuesWorkspaceRoute respecting search params layout and fallback', () => {
    const originalSearch = window.location.search;
    try {
      window.history.pushState({}, '', '?layout=board');
      const { unmount } = renderWithClient(<IssuesWorkspaceRoute projectKey="TEST" />);
      const workspace = screen.getByTestId('issues-workspace');
      expect(workspace.getAttribute('data-layout')).toBe('board');
      unmount();

      // Test fallback for unknown layout
      window.history.pushState({}, '', '?layout=unknown_view');
      renderWithClient(<IssuesWorkspaceRoute projectKey="TEST" />);
      const fallbackWorkspace = screen.getByTestId('issues-workspace');
      expect(fallbackWorkspace.getAttribute('data-layout')).toBe('board');
    } finally {
      window.history.pushState({}, '', originalSearch || '/');
    }
  });

  it('handles row selection and select-all inside IssuesWorkspaceRoute', () => {
    renderWithClient(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        initialLayout="table"
        initialIssues={FIXTURE_12_ISSUES}
      />,
    );

    // Select all checkbox
    const selectAllCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: /Select all issues/i });
    fireEvent.click(selectAllCheckbox);
    expect(selectAllCheckbox.checked).toBe(true);

    // Deselect all
    fireEvent.click(selectAllCheckbox);
    expect(selectAllCheckbox.checked).toBe(false);

    // Single item toggle
    const firstKey = FIXTURE_12_ISSUES[0]?.key ?? 'KAN-1';
    const rowCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: `Select ${firstKey}` });
    fireEvent.click(rowCheckbox);
    expect(rowCheckbox.checked).toBe(true);

    fireEvent.click(rowCheckbox);
    expect(rowCheckbox.checked).toBe(false);
  });
});

describe('VIEW_REGISTRY and ViewHost', () => {
  it('registers list, table, calendar, and timeline views', () => {
    expect(VIEW_REGISTRY.list).toBeDefined();
    expect(VIEW_REGISTRY.table).toBeDefined();
    expect(VIEW_REGISTRY.calendar).toBeDefined();
    expect(VIEW_REGISTRY.timeline).toBeDefined();
  });

  it('renders ListView when layout is list or unspecified', () => {
    renderWithClient(
      <ViewHost
        layout="list"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />,
    );

    // List section header
    expect(screen.getByText('Backlog')).toBeDefined();
    expect(screen.getByText('Todo')).toBeDefined();
  });

  it('renders TableView when layout is table', () => {
    renderWithClient(
      <ViewHost
        layout="table"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />,
    );

    expect(screen.getByRole('table')).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /Key/i })).toBeDefined();
  });

  it('renders CalendarView when layout is calendar', () => {
    renderWithClient(
      <ViewHost
        layout="calendar"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />,
    );

    expect(screen.getByTestId('calendar-view')).toBeDefined();
  });

  it('renders TimelineView when layout is timeline', () => {
    renderWithClient(
      <ViewHost
        layout="timeline"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />,
    );

    expect(screen.getByTestId('timeline-view')).toBeDefined();
  });

  it('falls back to ListView on unknown layout', () => {
    renderWithClient(
      <ViewHost
        layout="nonexistent_view"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />,
    );

    expect(screen.getByText('Backlog')).toBeDefined();
  });
});
