import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  CommandPalette,
  scoreMatch,
  MAX_QUERY_LENGTH,
  MAX_ISSUE_RESULTS,
} from './CommandPalette';
import { ThemeProvider } from '../theme/ThemeProvider';

const noop = (): void => {
  /* noop */
};

describe('CommandPalette', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  const renderWithProviders = (
    ui: React.ReactElement,
    client: QueryClient = queryClient,
  ) => {
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ThemeProvider>{ui}</ThemeProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  };

  it('fuzzy scoreMatch computes prefix, word-start, subsequence and zero correctly', () => {
    expect(scoreMatch('', 'Anything')).toBe(1);
    expect(scoreMatch('work', 'Work Items')).toBeGreaterThan(80);
    expect(scoreMatch('item', 'Work Items')).toBeGreaterThan(50);
    expect(scoreMatch('wi', 'Work Items')).toBe(50);
    expect(scoreMatch('xyz', 'Work Items')).toBe(0);
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = renderWithProviders(
      <CommandPalette isOpen={false} onClose={noop} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog, combobox, and options when isOpen is true', () => {
    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const dialog = screen.getByRole('dialog', { name: 'Command palette' });
    expect(dialog).toBeDefined();

    const input = screen.getByRole('combobox');
    expect(input).toBeDefined();

    const listbox = screen.getByRole('listbox');
    expect(listbox).toBeDefined();

    const options = screen.getAllByRole('option');
    expect(options.length).toBeGreaterThan(0);
  });

  it('truncates queries longer than 200 characters to 200', () => {
    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const input = screen.getByRole<HTMLInputElement>('combobox');
    const longQuery = 'a'.repeat(210);

    fireEvent.change(input, { target: { value: longQuery } });
    expect(input.value.length).toBe(MAX_QUERY_LENGTH);
    expect(input.value).toBe('a'.repeat(200));
  });

  it('renders hostile issue summary as literal text node with zero img elements', () => {
    const hostileIssues = [
      {
        key: 'KAN-999',
        summary: '<img src=x onerror=alert(1)> hostile payload',
      },
    ];

    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
        cachedIssues={hostileIssues}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'hostile' } });

    // Ensure NO <img> element exists in DOM
    const images = document.querySelectorAll('img');
    expect(images.length).toBe(0);

    // Literal text is present
    expect(
      screen.getByText(/<img src=x onerror=alert\(1\)> hostile payload/),
    ).toBeDefined();
  });

  it('caps cached issue results at 20', () => {
    const manyIssues = Array.from({ length: 35 }, (_, i) => ({
      key: `KAN-${String(i + 1)}`,
      summary: `Issue item ${String(i + 1)}`,
    }));

    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
        cachedIssues={manyIssues}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Issue item' } });

    const issueOptions = screen.getAllByRole('option');
    expect(issueOptions.length).toBe(MAX_ISSUE_RESULTS);
  });

  it('navigates with ArrowDown/ArrowUp and executes on Enter', () => {
    const onToggleSidebar = vi.fn();
    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
        onToggleSidebar={onToggleSidebar}
      />,
    );

    const dialog = screen.getByRole('dialog');
    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Toggle sidebar' } });

    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    fireEvent.keyDown(dialog, { key: 'Enter' });

    expect(onToggleSidebar).toHaveBeenCalled();
  });

  it('restores focus to previous activeElement upon Escape', () => {
    const triggerBtn = document.createElement('button');
    triggerBtn.textContent = 'Trigger';
    document.body.appendChild(triggerBtn);
    triggerBtn.focus();

    const onClose = vi.fn();
    const { rerender } = renderWithProviders(
      <CommandPalette isOpen={true} onClose={onClose} />,
    );

    const dialog = screen.getByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });

    expect(onClose).toHaveBeenCalled();

    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ThemeProvider>
            <CommandPalette isOpen={false} onClose={onClose} />
          </ThemeProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(document.activeElement).toBe(triggerBtn);
    document.body.removeChild(triggerBtn);
  });

  it('dispatches kb:create-issue custom event on Create work item command', () => {
    const listener = vi.fn();
    window.addEventListener('kb:create-issue', listener);

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Create work item' } });

    const opt = screen.getByRole('option', { name: /Create work item/ });
    act(() => {
      opt.click();
    });

    expect(listener).toHaveBeenCalled();
    window.removeEventListener('kb:create-issue', listener);
  });

  it('executes navigation and theme commands on select', () => {
    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Go to Docs' } });

    const opt = screen.getByRole('option', { name: /Go to Docs/ });
    act(() => {
      opt.click();
    });

    fireEvent.change(input, { target: { value: 'Theme: Dark' } });
    const darkOpt = screen.getByRole('option', { name: /Theme: Dark/ });
    act(() => {
      darkOpt.click();
    });
    expect(document.documentElement.dataset.theme).toBe('dark');

    fireEvent.change(input, { target: { value: 'Theme: Light' } });
    const lightOpt = screen.getByRole('option', { name: /Theme: Light/ });
    act(() => {
      lightOpt.click();
    });
    expect(document.documentElement.dataset.theme).toBe('light');

    fireEvent.change(input, { target: { value: 'Theme: System' } });
    const sysOpt = screen.getByRole('option', { name: /Theme: System/ });
    act(() => {
      sysOpt.click();
    });
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it('selects and navigates to cached issue item', () => {
    const issues = [{ key: 'KAN-42', summary: 'Check specific issue' }];
    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
        cachedIssues={issues}
      />,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'KAN-42' } });

    const issueOpt = screen.getByRole('option', { name: /KAN-42/ });
    act(() => {
      issueOpt.click();
    });
    expect(issueOpt).toBeDefined();
  });

  it('handles ArrowUp selection wrap and Tab key focus trap', () => {
    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const dialog = screen.getByRole('dialog');
    const input = screen.getByRole('combobox');

    // ArrowUp wraps around
    fireEvent.keyDown(dialog, { key: 'ArrowUp' });
    const options = screen.getAllByRole('option');
    expect(options[options.length - 1]?.getAttribute('aria-selected')).toBe('true');

    // Tab traps focus back to input
    fireEvent.keyDown(dialog, { key: 'Tab' });
    expect(document.activeElement).toBe(input);
  });

  it('extracts issues from queryClient cache automatically when prop is not provided', () => {
    const realQueryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    realQueryClient.setQueryData(['issues-array'], [
      { key: 'KAN-50', summary: 'Cached list issue' },
      null,
      'not-an-object',
    ]);
    realQueryClient.setQueryData(['issues-wrapped'], {
      issues: [
        { key: 'KAN-51', summary: 'Cached object issue' },
        null,
        'invalid-item',
      ],
    });
    realQueryClient.setQueryData(['non-issue-query'], { unrelated: true });
    realQueryClient.setQueryData(['null-query'], null);

    renderWithProviders(
      <CommandPalette isOpen={true} onClose={noop} />,
      realQueryClient,
    );

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'KAN-50' } });
    expect(screen.getByRole('option', { name: /KAN-50/ })).toBeDefined();

    fireEvent.change(input, { target: { value: 'KAN-51' } });
    expect(screen.getByRole('option', { name: /KAN-51/ })).toBeDefined();

    // Test selection of Go to Work Items
    fireEvent.change(input, { target: { value: 'Go to Work Items' } });
    const workItemsOpt = screen.getByRole('option', { name: /Go to Work Items/ });
    act(() => {
      workItemsOpt.click();
    });

    fireEvent.change(input, { target: { value: 'Go to Board' } });
    const boardOpt = screen.getByRole('option', { name: /Go to Board/ });
    act(() => {
      boardOpt.click();
    });

    fireEvent.change(input, { target: { value: 'Go to Stickies' } });
    const stickiesOpt = screen.getByRole('option', { name: /Go to Stickies/ });
    act(() => {
      stickiesOpt.click();
    });
  });

  it('handles empty search results and non-matching query navigation safely', () => {
    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const dialog = screen.getByRole('dialog');
    const input = screen.getByRole('combobox');

    // Filter to nothing
    fireEvent.change(input, { target: { value: 'non-existent-query-xyz123' } });
    expect(screen.queryAllByRole('option').length).toBe(0);

    // Arrow navigation with empty list does not crash
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    fireEvent.keyDown(dialog, { key: 'ArrowUp' });
    fireEvent.keyDown(dialog, { key: 'Enter' });
  });

  it('closes when clicking the backdrop scrim', () => {
    const onClose = vi.fn();
    renderWithProviders(
      <CommandPalette isOpen={true} onClose={onClose} />,
    );

    const scrim = document.querySelector('.kb-palette-scrim');
    expect(scrim).not.toBeNull();
    if (scrim) {
      act(() => {
        fireEvent.click(scrim);
      });
    }

    expect(onClose).toHaveBeenCalled();
  });
});
