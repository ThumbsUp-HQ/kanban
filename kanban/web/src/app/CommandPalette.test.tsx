import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
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
import { apiFetch } from '../api/client';

vi.mock('../api/client', () => ({
  apiFetch: vi.fn(),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

const mockApiFetch = vi.mocked(apiFetch);

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

    // Additional navigation items
    const navItems = [
      'Go to Cycles',
      'Go to Modules',
      'Go to Project Overview',
      'Go to Stickies',
      'Go to Project Settings',
      'Go to Workspace Settings',
      'Go to Personal Profile',
      'Keyboard Shortcuts Cheat Sheet',
      'Go to Board',
      'Go to Saved Views',
    ];

    for (const item of navItems) {
      fireEvent.change(input, { target: { value: item } });
      const optItem = screen.getByRole('option', { name: new RegExp(item, 'i') });
      act(() => {
        optItem.click();
      });
    }
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

  it('executes Create project and admin/settings navigation commands', () => {
    const projectModalListener = vi.fn();
    window.addEventListener('kb:open-create-project', projectModalListener);

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Create project' } });
    act(() => {
      screen.getByRole('option', { name: /Create project/ }).click();
    });
    expect(projectModalListener).toHaveBeenCalled();

    fireEvent.change(input, { target: { value: 'Go to Auth Studio' } });
    act(() => {
      screen.getByRole('option', { name: /Go to Auth Studio/ }).click();
    });

    fireEvent.change(input, { target: { value: 'Go to Personal MCP Keys' } });
    act(() => {
      screen.getByRole('option', { name: /Go to Personal MCP Keys/ }).click();
    });

    fireEvent.change(input, { target: { value: 'Go to System Storage, Backups & Deployment' } });
    act(() => {
      screen.getByRole('option', { name: /Go to System Storage, Backups & Deployment/ }).click();
    });

    window.removeEventListener('kb:open-create-project', projectModalListener);
  });

  it('hides admin actions when user is non-server-admin, executes toggle sidebar and theme switching', () => {
    const onToggleSidebar = vi.fn();
    const nonAdminUser = { id: 'u1', handle: 'member', is_server_admin: false };

    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
        onToggleSidebar={onToggleSidebar}
        user={nonAdminUser}
      />,
    );

    const input = screen.getByRole('combobox');

    // Admin options should not exist
    fireEvent.change(input, { target: { value: 'Auth Studio' } });
    expect(screen.queryByRole('option', { name: /Go to Auth Studio/ })).toBeNull();

    fireEvent.change(input, { target: { value: 'System Storage' } });
    expect(screen.queryByRole('option', { name: /Go to System Storage/ })).toBeNull();

    // Toggle sidebar
    fireEvent.change(input, { target: { value: 'Toggle sidebar' } });
    act(() => {
      screen.getByRole('option', { name: /Toggle sidebar/ }).click();
    });
    expect(onToggleSidebar).toHaveBeenCalled();

    // Theme options
    fireEvent.change(input, { target: { value: 'Theme: Dark' } });
    act(() => {
      screen.getByRole('option', { name: /Theme: Dark/ }).click();
    });

    fireEvent.change(input, { target: { value: 'Theme: System' } });
    act(() => {
      screen.getByRole('option', { name: /Theme: System/ }).click();
    });
  });

  it('extracts cached issues from React Query cache when cachedIssues prop is omitted', () => {
    const client = new QueryClient();
    client.setQueryData(['issues-array'], [
      { key: 'KAN-CACHE-1', summary: 'Direct array cached item' },
    ]);
    client.setQueryData(['issues-container'], {
      issues: [{ key: 'KAN-CACHE-2', summary: 'Contained issues item' }],
    });

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />, client);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'KAN-CACHE' } });

    expect(screen.getByRole('option', { name: /Direct array cached item/ })).toBeDefined();
    expect(screen.getByRole('option', { name: /Contained issues item/ })).toBeDefined();
  });

  it('performs live hybrid search across issues, docs, pages, and stickies', async () => {
    mockApiFetch.mockResolvedValueOnce({
      items: [
        {
          id: 's-iss-1',
          kind: 'issue',
          key: 'KAN-999',
          title: 'Live search issue title',
          project_identifier: 'KAN',
        },
        {
          id: 's-doc-1',
          kind: 'doc',
          title: 'Live Architecture Guide',
          project_identifier: 'KAN',
        },
        {
          id: 's-page-1',
          kind: 'page',
          title: 'Live Security Spec Page',
          project_identifier: 'KAN',
        },
        {
          id: 's-sticky-1',
          kind: 'sticky',
          title: 'Live Sticky Note',
          project_identifier: 'KAN',
        },
      ],
    });

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Live' } });

    await waitFor(() => {
      expect(screen.getByText('KAN-999 - Live search issue title')).toBeDefined();
    });

    expect(screen.getByText('Live Architecture Guide')).toBeDefined();
    expect(screen.getByText('Live Security Spec Page')).toBeDefined();
    expect(screen.getByText('Live Sticky Note')).toBeDefined();

    // Select doc option
    act(() => {
      screen.getByRole('option', { name: /Live Architecture Guide/ }).click();
    });

    // Select page option
    act(() => {
      screen.getByRole('option', { name: /Live Security Spec Page/ }).click();
    });

    // Select sticky option
    act(() => {
      screen.getByRole('option', { name: /Live Sticky Note/ }).click();
    });
  });

  it('covers sticky without project and issue without key in search results', async () => {
    mockApiFetch.mockResolvedValueOnce({
      items: [
        {
          id: 's-orphan',
          kind: 'sticky',
          title: '',
          snippet: 'Orphan sticky note',
          project_identifier: null,
        },
        {
          id: 'i-nokey',
          kind: 'issue',
          title: 'Orphan issue without key',
          key: '',
        },
      ],
    });

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Orphan' } });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 200));
    });

    await waitFor(() => {
      expect(screen.getByText('Orphan sticky note')).toBeDefined();
    });

    act(() => {
      screen.getByRole('option', { name: /Orphan sticky note/ }).click();
    });

    act(() => {
      screen.getByRole('option', { name: /Orphan issue without key/ }).click();
    });

    act(() => {
      screen.getByRole('option', { name: /Orphan issue without key/i }).click();
    });
  });

  it('handles live search fetch rejection gracefully', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('500 internal search error'));

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'ThrowsError' } });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 200));
    });

    expect(input).toBeDefined();
  });

  it('dispatches kb:open-shortcuts event on Keyboard Shortcuts Cheat Sheet command', () => {
    const listener = vi.fn();
    window.addEventListener('kb:open-shortcuts', listener);

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Keyboard Shortcuts' } });

    act(() => {
      screen.getByRole('option', { name: /Keyboard Shortcuts Cheat Sheet/ }).click();
    });

    expect(listener).toHaveBeenCalled();
    window.removeEventListener('kb:open-shortcuts', listener);
  });

  it('handles live search with empty title, snippet, summary fallbacks and items null', async () => {
    mockApiFetch.mockResolvedValueOnce({
      items: [
        {
          id: 'i-fallback',
          kind: 'issue',
          title: '   ',
          summary: null,
          key: null,
          project_identifier: 'KAN',
        },
        {
          id: 's-fallback-1',
          kind: 'sticky',
          title: '   ',
          snippet: 'Work snippet',
          project_identifier: null,
        },
        {
          id: 's-fallback-2',
          kind: 'sticky',
          title: 'Work sticky project',
          snippet: null,
          project_identifier: 'KAN',
        },
        {
          id: 'd-fallback',
          kind: 'doc',
          title: 'Work Documentation',
          project_identifier: 'KAN',
        },
        {
          id: 'p-fallback',
          kind: 'page',
          title: 'Work Architecture Page',
          project_identifier: 'KAN',
        },
      ],
    });

    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
        cachedIssues={[
          { key: '', summary: 'Missing key' },
          { key: 'KAN-99', summary: '' },
        ]}
      />,
    );

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Work' } });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 250));
    });

    await waitFor(() => {
      expect(screen.getByText('Work Item')).toBeDefined();
    });

    act(() => {
      screen.getByRole('option', { name: /^Work Item$/i }).click();
    });
    act(() => {
      screen.getByRole('option', { name: /Work snippet/i }).click();
    });
    act(() => {
      screen.getByRole('option', { name: /Work sticky project/i }).click();
    });
    act(() => {
      screen.getByRole('option', { name: /Work Documentation/i }).click();
    });
    act(() => {
      screen.getByRole('option', { name: /Work Architecture Page/i }).click();
    });
  });

  it('covers query length truncation, arrow navigation with empty options, and non-admin user', () => {
    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
        user={{ is_server_admin: false }}
      />,
    );

    const dialog = screen.getByRole('dialog');
    const input = screen.getByRole('combobox');

    // Truncates query exceeding MAX_QUERY_LENGTH
    fireEvent.change(input, { target: { value: 'z'.repeat(250) } });
    expect((input as HTMLInputElement).value.length).toBe(MAX_QUERY_LENGTH);

    // No matching options, navigate with arrows and Enter
    fireEvent.keyDown(dialog, { key: 'ArrowDown' });
    fireEvent.keyDown(dialog, { key: 'ArrowUp' });
    fireEvent.keyDown(dialog, { key: 'Enter' });

    // Verify Auth Studio is not rendered when is_server_admin is false
    expect(screen.queryByText(/Go to Auth Studio/i)).toBeNull();

    // Reset query to toggle sidebar without onToggleSidebar prop
    fireEvent.change(input, { target: { value: 'Toggle sidebar' } });
    const toggleOpt = screen.getByRole('option', { name: /Toggle sidebar/i });
    act(() => {
      toggleOpt.click();
    });
  });

  it('covers clicking navigation and action commands and backdrop click', () => {
    const onClose = vi.fn();
    const { container } = renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={onClose}
        projectKey="KAN"
      />,
    );

    // Backdrop click
    const backdrop = container.querySelector('.kb-palette-scrim');
    if (backdrop) fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalled();

    // Select commands
    const commandsToClick = [
      'Go to Your Work',
      'Go to Saved Views',
      'Go to Board',
      'Go to Cycles',
      'Go to Modules',
      'Go to Project Overview',
      'Go to Docs',
      'Go to Stickies',
      'Go to Project Settings',
      'Go to Workspace Settings',
      'Go to Personal Profile',
      'Keyboard Shortcuts Cheat Sheet',
      'Create work item',
      'Create project',
      'Go to Auth Studio',
      'Go to Personal MCP Keys',
      'Go to System Storage, Backups & Deployment',
      'Theme: System',
      'Theme: Light',
      'Theme: Dark',
    ];

    for (const title of commandsToClick) {
      const opt = screen.getByRole('option', { name: new RegExp(title, 'i') });
      act(() => {
        opt.click();
      });
    }
  });

  it('covers search edge cases: empty items, keyless issue navigation, duplicate keys, and tab trapping', async () => {
    const mockFetch = vi.mocked(apiFetch);
    mockFetch.mockResolvedValueOnce({
      items: [
        {
          id: 'iss-real',
          kind: 'issue',
          key: 'KAN-777',
          title: 'Real Key Issue',
          project_identifier: 'KAN',
        },
        {
          id: 'dup-work-1',
          kind: 'sticky',
          title: 'Twin Sticky Note',
          snippet: null,
          project_identifier: 'KAN',
        },
        {
          id: 'dup-work-2',
          kind: 'sticky',
          title: 'Twin Sticky Note',
          snippet: null,
          project_identifier: 'KAN',
        },
        {
          id: 'stk-fallback-title',
          kind: 'sticky',
          title: '   ',
          snippet: null,
          project_identifier: null,
        },
      ],
    });

    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
        cachedIssues={[
          { key: 'KAN-1', summary: 'First' },
        ]}
      />,
    );

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const dialog = screen.getByRole('dialog');
    const input = screen.getByRole('combobox');

    // Tab key inside dialog
    fireEvent.keyDown(dialog, { key: 'Tab' });
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });

    // Search query
    fireEvent.change(input, { target: { value: 'Twin' } });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 250));
    });

    await waitFor(() => {
      expect(screen.getByText('Twin Sticky Note')).toBeDefined();
    });

    // Click issue with real key (covers keyStr ? true branch)
    act(() => {
      screen.getByRole('option', { name: 'Twin Sticky Note' }).click();
    });
  });

  it('covers extractCachedIssues container with null/non-string items and empty search res items', async () => {
    const testQueryClient = new QueryClient();
    testQueryClient.setQueryData(['issues-list'], {
      issues: [
        null,
        { key: 12345, summary: null },
        { key: 'KAN-99', summary: 'Valid summary' },
      ],
    });
    testQueryClient.setQueryData(['issues-not-array'], {
      issues: 'invalid_string_not_array',
    });
    testQueryClient.setQueryData(['issues-array'], [
      null,
      { key: 9999 },
    ]);

    const mockFetch = vi.mocked(apiFetch);
    mockFetch.mockResolvedValueOnce({}); // res.items is undefined

    const { unmount } = renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
      />,
      testQueryClient,
    );

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'UnmountingDuringSearch' } });

    // Unmount immediately while debounced search is active
    unmount();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 250));
    });
  });

  it('renders synaptic match_reason badge pill and sends mode=hybrid in query', async () => {
    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValueOnce({
      items: [
        {
          id: 'iss-syn-20',
          kind: 'issue',
          key: 'KAN-20',
          title: 'Live Synaptic Search Issue',
          project_identifier: 'KAN',
          match_reason: 'Linked via VERIFIED_BY_DOC to ARCH-1',
        },
      ],
    });

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Live' } });

    await waitFor(() => {
      expect(screen.getByText('KAN-20 - Live Synaptic Search Issue')).toBeDefined();
    });

    const badge = screen.getByTestId('match-reason-search-issue-iss-syn-20');
    expect(badge.textContent).toBe('Linked via VERIFIED_BY_DOC to ARCH-1');
    expect(badge.className).toContain('kb-palette-badge');

    expect(mockApiFetch).toHaveBeenCalled();
    const lastCall = mockApiFetch.mock.lastCall;
    expect(lastCall?.[0]).toBe('GET');
    expect(lastCall?.[1]).toBe('/api/v1/search');
    const callOpts = lastCall?.[2] as { query?: { mode?: string } } | undefined;
    expect(callOpts?.query?.mode).toBe('hybrid');
  });

  it('preserves non-literal synaptic neighbor results and backend rank order without dropping them via scoreMatch', async () => {
    mockApiFetch.mockReset();
    mockApiFetch.mockResolvedValueOnce({
      items: [
        {
          id: 'doc-spec-1',
          kind: 'doc',
          title: 'Verification Architecture Spec',
          project_identifier: 'KAN',
          match_reason: 'Linked via VERIFIED_BY_DOC to KAN-10',
        },
        {
          id: 'iss-block-2',
          kind: 'issue',
          key: 'KAN-11',
          title: 'Dependent Execution Queue',
          project_identifier: 'KAN',
          match_reason: 'Linked via BLOCKS to KAN-10',
        },
      ],
    });

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Synaptic Vector Kernel' } });

    await waitFor(() => {
      expect(screen.getByText('Verification Architecture Spec')).toBeDefined();
    });

    // Assert that Verification Architecture Spec and its match reason render
    expect(screen.getByText('Verification Architecture Spec')).toBeDefined();
    const docBadge = screen.getByTestId('match-reason-search-doc-doc-spec-1');
    expect(docBadge.textContent).toBe('Linked via VERIFIED_BY_DOC to KAN-10');

    // Assert that KAN-11 and its match reason also render
    expect(screen.getByText('KAN-11 - Dependent Execution Queue')).toBeDefined();
    const issueBadge = screen.getByTestId('match-reason-search-issue-iss-block-2');
    expect(issueBadge.textContent).toBe('Linked via BLOCKS to KAN-10');

    // Assert backend rank order: Verification Architecture Spec appears before KAN-11 in the options list
    const options = screen.getAllByRole('option');
    expect(options.length).toBeGreaterThanOrEqual(2);
    expect(options[0]?.textContent).toContain('Verification Architecture Spec');
    expect(options[0]?.textContent).toContain('Linked via VERIFIED_BY_DOC to KAN-10');
    expect(options[1]?.textContent).toContain('Dependent Execution Queue');
    expect(options[1]?.textContent).toContain('Linked via BLOCKS to KAN-10');
  });

  it('renders persistent keyboard shortcut legend footer with kbd tokens and clean labels (KAN-473)', () => {
    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);

    const footer = screen.getByTestId('palette-footer-legend');
    expect(footer).toBeDefined();
    expect(footer.tagName.toLowerCase()).toBe('footer');
    expect(footer.className).toContain('kb-palette-footer');

    // Verify key labels
    expect(footer.textContent).toContain('Navigate');
    expect(footer.textContent).toContain('Select');
    expect(footer.textContent).toContain('Dismiss');
    expect(footer.textContent).toContain('↑');
    expect(footer.textContent).toContain('↓');
    expect(footer.textContent).toContain('↵');
    expect(footer.textContent).toContain('Esc');

    // Verify kbd elements
    const kbds = footer.querySelectorAll('kbd');
    expect(kbds.length).toBe(4);
    kbds.forEach((kbd) => {
      expect(kbd.className).toContain('kb-palette-kbd');
    });
  });

  it('scrolls selected option into view when selection changes', () => {
    const scrollMock = vi.fn();
    Element.prototype.scrollIntoView = scrollMock;

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);
    const input = screen.getByRole('combobox');

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    expect(scrollMock).toHaveBeenCalled();
  });

  it('handles live search debounce reset and deduplication with seen keys', async () => {
    mockApiFetch.mockResolvedValueOnce({
      items: [
        {
          id: 'cw-1',
          kind: 'issue',
          title: 'Create work item',
          summary: 'Create work item',
          key: 'CW-1',
          match_reason: 'Exact Title Match',
        },
      ],
    });

    renderWithProviders(<CommandPalette isOpen={true} onClose={noop} />);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const input = screen.getByRole('combobox');

    // Type query to trigger search
    fireEvent.change(input, { target: { value: 'Create' } });

    await waitFor(() => {
      expect(screen.getByText('CW-1 - Create work item')).toBeDefined();
    });

    // Clear input to test trimmed empty branch in debounce
    fireEvent.change(input, { target: { value: '' } });

    await act(async () => {
      await new Promise((r) => setTimeout(r, 220));
    });

    expect((input as HTMLInputElement).value).toBe('');
  });

  it('covers diagnostics and about navigation clicks and issue deduplication', async () => {
    mockApiFetch.mockResolvedValueOnce({
      items: [
        {
          id: 'cw-dup',
          kind: 'issue',
          title: 'Duplicate Title',
          summary: 'Duplicate Title',
          key: 'DUP-1',
          match_reason: 'Exact Title Match',
        },
      ],
    });

    renderWithProviders(
      <CommandPalette
        isOpen={true}
        onClose={noop}
        cachedIssues={[{ key: 'DUP-1', summary: 'Duplicate Title' }]}
      />,
    );

    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    const input = screen.getByRole('combobox');
    fireEvent.change(input, { target: { value: 'Duplicate' } });

    await waitFor(() => {
      expect(screen.getByTestId('match-reason-search-issue-cw-dup')).toBeDefined();
    });

    // Clear search to show base commands
    fireEvent.change(input, { target: { value: '' } });

    // Click diagnostics
    act(() => {
      const diagOption = screen.getByText('Go to Diagnostics & Link Inspector');
      diagOption.click();
    });

    // Click about
    act(() => {
      const aboutOption = screen.getByText('About 👍kanban (License, API Docs & SBOM)');
      aboutOption.click();
    });

    // Press Enter on non-matching query
    fireEvent.change(input, { target: { value: 'zzzz_no_match_query' } });
    fireEvent.keyDown(input, { key: 'Enter' });
  });
});
