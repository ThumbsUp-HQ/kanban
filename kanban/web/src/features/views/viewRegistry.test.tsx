import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it } from 'vitest';
import { IssuesWorkspaceRoute, viewRegistry } from './viewRegistry.tsx';

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

  it('contains entries for board, list, grid, and calendar', () => {
    expect(viewRegistry.board).toBeDefined();
    expect(viewRegistry.list).toBeDefined();
    expect(viewRegistry.grid).toBeDefined();
    expect(viewRegistry.calendar).toBeDefined();
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
});
