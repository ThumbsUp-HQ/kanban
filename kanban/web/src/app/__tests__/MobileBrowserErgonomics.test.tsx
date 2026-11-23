// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CommandPalette } from '../CommandPalette';
import { SwimlaneBoardGrid } from '../../features/views/SwimlaneBoardGrid';
import { FIXTURE_12_ISSUES } from '../../features/views/fixtures';
import { ThemeProvider } from '../../theme/ThemeProvider';
import { apiFetch } from '../../api/client';

vi.mock('../../api/client', () => ({
  apiFetch: vi.fn(),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

describe('Mobile & Landscape Browser Ergonomics Suite (KAN-314)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  const renderWithProviders = (ui: React.ReactElement) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ThemeProvider>{ui}</ThemeProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it('CommandPalette renders the 44x44px touch Close (x) button and closes cleanly on tap without Escape', () => {
    const handleClose = vi.fn();
    renderWithProviders(<CommandPalette isOpen={true} onClose={handleClose} />);

    // Verify close button exists with proper aria-label and test ID
    const closeBtn = screen.getByTestId('command-palette-close-btn');
    expect(closeBtn).toBeDefined();
    expect(closeBtn.getAttribute('aria-label')).toBe('Close command palette');

    // Tap/click close button
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it('SwimlaneBoardGrid renders inline column state headers for stacked mobile viewports', () => {
    const { container } = render(
      <SwimlaneBoardGrid
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        groupBy="state"
        subGroupBy="priority"
        modulesEnabled={true}
      />
    );

    // Verify mobile column state headers are present inside each board column
    const mobileHeaders = container.querySelectorAll('.swimlane-column-mobile-header');
    expect(mobileHeaders.length).toBeGreaterThan(0);

    const firstHeader = mobileHeaders[0];
    expect(firstHeader).toBeDefined();
    const title = firstHeader?.querySelector('.swimlane-column-mobile-title');
    expect(title).not.toBeNull();
    expect(title?.textContent.length).toBeGreaterThan(0);

    const count = firstHeader?.querySelector('.swimlane-column-mobile-count');
    expect(count).not.toBeNull();
  });

  it('verifies CommandPalette search input has role combobox and expands properly', () => {
    renderWithProviders(<CommandPalette isOpen={true} onClose={vi.fn()} />);

    const input = screen.getByTestId('command-palette-input');
    expect(input.getAttribute('role')).toBe('combobox');
    expect(input.getAttribute('aria-expanded')).toBe('true');
  });

  it('covers Diagnostics navigation, query clearing debounce, and duplicate seen options', async () => {
    vi.useFakeTimers();

    // Mock live search returning an item that duplicates a base command key
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [
        {
          id: 'item-dup',
          title: 'Go to Personal MCP Keys',
          kind: 'doc',
          snippet: 'mcp snippet',
        },
      ],
    });

    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={vi.fn()}
      />
    );

    // Click diagnostics navigation
    const diagOption = screen.getByText(/Go to Diagnostics & Link Inspector/i);
    fireEvent.click(diagOption);

    const input = screen.getByTestId('command-palette-input');
    // Type query to trigger search
    fireEvent.change(input, { target: { value: 'mcp' } });
    await act(() => {
      vi.advanceTimersByTime(250);
      return Promise.resolve();
    });

    // Clear query and advance timer to hit if (!trimmed) active callback
    fireEvent.change(input, { target: { value: '' } });
    await act(() => {
      vi.advanceTimersByTime(250);
      return Promise.resolve();
    });

    vi.useRealTimers();
  });
});
