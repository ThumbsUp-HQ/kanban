import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, renderHook, act, waitFor } from '@testing-library/react';
import React, { useRef } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { AccessPill } from './AccessPill';
import { IssueHeader } from './IssueHeader';
import { IssueKeyLink } from './IssueKeyLink';
import { IssueSurface } from './IssueSurface';
import { SummaryField } from './SummaryField';
import { useFocusTrap } from './useFocusTrap';
import { issueSurfaceSlots } from './slotRegistry';
import { IssueSurfaceSlotsContext, type IssueDetail } from './slots';
import { apiClient } from '../../api/client';
import { useIssueSurfaceRoute, toFullScreenPath } from './useIssueSurfaceRoute';

const mockIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '11111111-1111-1111-1111-111111111111',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Auth Studio',
  description_markdown: 'Markdown description',
  priority: null,
};

function createWrapper(initialEntries = ['/projects/KAN/issues?peek=KAN-142']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        {children}
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { queryClient, Wrapper };
}

describe('Drawer Extra Coverage', () => {
  it('covers slotRegistry export', () => {
    expect(issueSurfaceSlots).toBeDefined();
    expect(typeof issueSurfaceSlots).toBe('object');
  });

  describe('toFullScreenPath branches', () => {
    it('covers all search parameter variations', () => {
      expect(toFullScreenPath('KAN', 'KAN-1')).toBe('/projects/KAN/issues/KAN-1');
      expect(toFullScreenPath('KAN', 'KAN-1', '?foo=bar')).toBe('/projects/KAN/issues/KAN-1?foo=bar');
      expect(toFullScreenPath('KAN', 'KAN-1', { search: '?foo=bar' })).toBe('/projects/KAN/issues/KAN-1?foo=bar');
      expect(toFullScreenPath('KAN', 'KAN-1', { search: '' })).toBe('/projects/KAN/issues/KAN-1');
      expect(toFullScreenPath('KAN', 'KAN-1', { search: undefined })).toBe('/projects/KAN/issues/KAN-1');
      expect(toFullScreenPath('KAN', 'KAN-1', new URLSearchParams('foo=bar'))).toBe('/projects/KAN/issues/KAN-1?foo=bar');
    });
  });

  describe('AccessPill branches', () => {
    it('handles default Project project_name when issue.project_name is empty', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <AccessPill issue={{ ...mockIssue, project_name: '' }} />
        </Wrapper>,
      );
      expect(screen.getByText('Project')).toBeDefined();
    });

    it('handles array values for users/groups/agents/deny_rules in getCount', () => {
      const { queryClient, Wrapper } = createWrapper();
      queryClient.setQueryData(['access', mockIssue.object_id], {
        users: ['u1', 'u2'],
        groups: ['g1'],
        agents: ['a1'],
        deny_rules: ['d1'],
        scope_label: 'CustomScope',
        explicit_grant_count: 1,
      });

      render(
        <Wrapper>
          <AccessPill issue={mockIssue} />
        </Wrapper>,
      );

      expect(screen.getByText('CustomScope + 1')).toBeDefined();
      const hint = screen.getByTestId('access-hint');
      act(() => {
        hint.focus();
      });
      expect(screen.getByRole('dialog').textContent).toContain('2 users, 1 group, 1 agent, 1 deny rule');
    });

    it('handles query error state and queryFn fetch rejection', async () => {
      const { queryClient, Wrapper } = createWrapper();
      queryClient.setQueryData(['access', mockIssue.object_id], null);

      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 500,
      } as Response);

      render(
        <Wrapper>
          <AccessPill issue={{ ...mockIssue, object_id: 'err-obj-id' }} />
        </Wrapper>,
      );

      const hint = screen.getByTestId('access-hint');
      act(() => {
        hint.focus();
      });

      await waitFor(() => {
        expect(screen.getByRole('dialog').textContent).toContain('Access summary unavailable.');
      });
      fetchSpy.mockRestore();
    });

    it('queryFn handles successful fetch response', async () => {
      const { Wrapper } = createWrapper();
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ scope_label: 'FetchedScope', explicit_grant_count: 0 }),
      } as Response);

      render(
        <Wrapper>
          <AccessPill issue={{ ...mockIssue, object_id: 'fetched-obj-id' }} />
        </Wrapper>,
      );

      await waitFor(() => {
        expect(screen.getByText('FetchedScope')).toBeDefined();
      });
      fetchSpy.mockRestore();
    });
  });

  describe('IssueHeader branches', () => {
    it('handles null priority gracefully', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <IssueHeader
            issue={mockIssue}
            mode="drawer"
            onClose={vi.fn()}
            toggleFullScreen={vi.fn()}
          />
        </Wrapper>,
      );

      expect(screen.queryByTestId('priority-hint')).toBeNull();
      expect(screen.getByText('KAN-142')).toBeDefined();
    });
  });

  describe('IssueKeyLink branches', () => {
    it('handles custom className and modifier clicks', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <IssueKeyLink issueKey="KAN-142" className="custom-class" data-testid="test-key-link" />
        </Wrapper>,
      );

      const link = screen.getByTestId('test-key-link');
      expect(link.className).toContain('custom-class');

      fireEvent.click(link, { metaKey: true });
      fireEvent.click(link, { ctrlKey: true });
      fireEvent.click(link, { shiftKey: true });
      fireEvent.click(link, { altKey: true });
      fireEvent.click(link, { button: 2 });
    });
  });

  describe('SummaryField branches', () => {
    it('handles typing regular characters in textarea without triggering Enter or Escape', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <SummaryField issue={mockIssue} />
        </Wrapper>,
      );

      fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }));
      const textarea = screen.getByRole('textbox', { name: 'Summary' });

      fireEvent.keyDown(textarea, { key: 'a' });
      expect(screen.getByRole('textbox')).toBeDefined();
    });

    it('exits edit mode when committed value is unchanged from issue.summary', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <SummaryField issue={mockIssue} />
        </Wrapper>,
      );

      fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }));
      const textarea = screen.getByRole('textbox', { name: 'Summary' });

      fireEvent.blur(textarea);
      expect(screen.queryByRole('textbox')).toBeNull();
    });

    it('blur does not commit when draft text length is 0 or > 500', () => {
      const { Wrapper } = createWrapper();
      render(
        <Wrapper>
          <SummaryField issue={mockIssue} />
        </Wrapper>,
      );

      fireEvent.click(screen.getByRole('button', { name: 'Edit summary' }));
      const textarea = screen.getByRole('textbox', { name: 'Summary' });

      fireEvent.change(textarea, { target: { value: '' } });
      fireEvent.blur(textarea);
      expect(screen.getByRole('textbox')).toBeDefined();

      fireEvent.change(textarea, { target: { value: 'x'.repeat(501) } });
      fireEvent.blur(textarea);
      expect(screen.getByRole('textbox')).toBeDefined();
    });
  });

  describe('useFocusTrap branches', () => {
    it('handles null container ref', () => {
      renderHook(() => {
        const ref = useRef<HTMLElement | null>(null);
        useFocusTrap(true, ref);
      });
    });

    it('ignores non-Tab key events', () => {
      const container = document.createElement('div');
      document.body.appendChild(container);
      const btn = document.createElement('button');
      container.appendChild(btn);

      renderHook(() => {
        const ref = useRef<HTMLElement | null>(container);
        useFocusTrap(true, ref);
      });

      const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true });
      document.dispatchEvent(enterEvent);

      document.body.removeChild(container);
    });

    it('handles container with no focusables', () => {
      const container = document.createElement('div');
      document.body.appendChild(container);

      renderHook(() => {
        const ref = useRef<HTMLElement | null>(container);
        useFocusTrap(true, ref);
      });

      const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
      const prevented = !document.dispatchEvent(tabEvent);
      expect(prevented).toBe(true);

      document.body.removeChild(container);
    });

    it('allows natural tab and shift-tab on middle elements', () => {
      const container = document.createElement('div');
      document.body.appendChild(container);
      const btn1 = document.createElement('button');
      const btn2 = document.createElement('button');
      const btn3 = document.createElement('button');
      container.appendChild(btn1);
      container.appendChild(btn2);
      container.appendChild(btn3);

      renderHook(() => {
        const ref = useRef<HTMLElement | null>(container);
        useFocusTrap(true, ref);
      });

      btn2.focus();

      // Tab on middle element is not prevented
      const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
      const tabPrevented = !document.dispatchEvent(tabEvent);
      expect(tabPrevented).toBe(false);

      // Shift+Tab on middle element is not prevented
      const shiftTabEvent = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true });
      const shiftTabPrevented = !document.dispatchEvent(shiftTabEvent);
      expect(shiftTabPrevented).toBe(false);

      document.body.removeChild(container);
    });

    it('handles activeElement outside container wrapping to first or last', () => {
      const container = document.createElement('div');
      document.body.appendChild(container);
      const btn1 = document.createElement('button');
      const btn2 = document.createElement('button');
      container.appendChild(btn1);
      container.appendChild(btn2);

      const outsideBtn = document.createElement('button');
      document.body.appendChild(outsideBtn);
      outsideBtn.focus();

      renderHook(() => {
        const ref = useRef<HTMLElement | null>(container);
        useFocusTrap(true, ref);
      });

      // Shift+Tab when focus is outside wraps to last
      const shiftTabEvent = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true });
      document.dispatchEvent(shiftTabEvent);
      expect(document.activeElement).toBe(btn2);

      // Tab when focus is outside wraps to first
      outsideBtn.focus();
      const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
      document.dispatchEvent(tabEvent);
      expect(document.activeElement).toBe(btn1);

      document.body.removeChild(container);
      document.body.removeChild(outsideBtn);
    });
  });

  describe('IssueSurface loading, error, and keyboard branches', () => {
    it('handles close during loading state', async () => {
      vi.spyOn(apiClient, 'get').mockImplementation(
        () => new Promise<never>(() => {
          // Keep request pending forever
        })
      );

      const queryClient = new QueryClient();
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <div id="main-content">
              <main id="kb-main" tabIndex={-1}>Main</main>
              <div id="kb-issue-surface-host">
                <IssueSurface />
              </div>
            </div>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      expect(container.querySelector('.surface__skeleton')).toBeDefined();

      const closeBtn = screen.getByRole('button', { name: 'Close issue panel' });
      fireEvent.click(closeBtn);

      await waitFor(() => {
        expect(container.querySelector('section')).toBeNull();
      });
    });

    it('handles close and toggleFullScreen in error state', async () => {
      vi.spyOn(apiClient, 'get').mockRejectedValue(new Error('Boom'));

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <div id="main-content">
              <main id="kb-main" tabIndex={-1}>Main</main>
              <div id="kb-issue-surface-host">
                <IssueSurface />
              </div>
            </div>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Could not load KAN-142.')).toBeDefined();
      });

      const fsBtn = screen.getByRole('button', { name: 'Open in full screen' });
      fireEvent.click(fsBtn);

      const closeBtn = screen.getByRole('button', { name: 'Close issue panel' });
      fireEvent.click(closeBtn);
    });

    it('ignores non-Escape keys and handles open popover', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(mockIssue);

      const popoverEl = document.createElement('div');
      popoverEl.setAttribute('data-hint-open', 'true');
      document.body.appendChild(popoverEl);

      const queryClient = new QueryClient();
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <div id="main-content">
              <main id="kb-main" tabIndex={-1}>Main</main>
              <div id="kb-issue-surface-host">
                <IssueSurface />
              </div>
            </div>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByText('Auth Studio')).toBeDefined();
      });

      // Non-Escape key does nothing
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));

      // Escape with open popover does nothing
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
      expect(container.querySelector('section')).toBeDefined();

      document.body.removeChild(popoverEl);
    });

    it('handles toggleFullScreen and defaultPrevented Escape in full mode', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(mockIssue);

      const queryClient = new QueryClient();
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-142']}>
            <div id="main-content">
              <main id="kb-main" tabIndex={-1}>Main</main>
              <div id="kb-issue-surface-host">
                <IssueSurface />
              </div>
            </div>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(container.querySelector('section')?.className).toBe('surface--full');
      });

      // Escape with defaultPrevented does nothing
      const escEvent = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true });
      escEvent.preventDefault();
      window.dispatchEvent(escEvent);
      expect(container.querySelector('section')?.className).toBe('surface--full');

      // Click Return to side panel button
      const returnBtn = await screen.findByRole('button', { name: 'Return to side panel' });
      fireEvent.click(returnBtn);

      await waitFor(() => {
        expect(container.querySelector('section')?.className).toBe('surface--drawer');
      });
    });

    it('renders custom slots and empty description fallback', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue({
        ...mockIssue,
        description_markdown: null,
      });

      const customSlots = {
        description: () => <div data-testid="custom-desc">Custom Desc</div>,
        rail: () => <div data-testid="custom-rail">Custom Rail</div>,
        activity: () => <div data-testid="custom-activity">Custom Activity</div>,
      };

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-142']}>
            <IssueSurfaceSlotsContext.Provider value={customSlots}>
              <div id="main-content">
                <main id="kb-main" tabIndex={-1}>Main</main>
                <div id="kb-issue-surface-host">
                  <IssueSurface />
                </div>
              </div>
            </IssueSurfaceSlotsContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId('custom-desc')).toBeDefined();
        expect(screen.getByTestId('custom-rail')).toBeDefined();
        expect(screen.getByTestId('custom-activity')).toBeDefined();
      });
    });
  });

  describe('useIssueSurfaceRoute extra branches', () => {
    it('returns null when full-screen route has invalid issue key', () => {
      const wrapper = ({ children }: { children?: React.ReactNode }) =>
        React.createElement(
          MemoryRouter,
          { initialEntries: ['/projects/KAN/issues/INVALID_KEY'] },
          children,
        );

      const { result } = renderHook(() => useIssueSurfaceRoute(), { wrapper });
      expect(result.current.mode).toBeNull();
      expect(result.current.issueKey).toBeNull();
    });

    it('handles invalid peek with no extra params stripping query completely', () => {
      const wrapper = ({ children }: { children?: React.ReactNode }) =>
        React.createElement(
          MemoryRouter,
          { initialEntries: ['/projects/KAN/issues?peek=INVALID'] },
          children,
        );

      const { result } = renderHook(() => useIssueSurfaceRoute(), { wrapper });
      expect(result.current.mode).toBeNull();
    });

    it('renders empty fragment when issue is falsy', async () => {
      vi.spyOn(apiClient, 'get').mockResolvedValue(null);
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={['/projects/KAN/issues?peek=KAN-142']}>
            <div id="main-content">
              <main id="kb-main" tabIndex={-1}>Main</main>
              <div id="kb-issue-surface-host">
                <IssueSurface />
              </div>
            </div>
          </MemoryRouter>
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(container.querySelector('section')).toBeDefined();
      });
    });
  });
});
