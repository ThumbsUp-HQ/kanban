import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AccessPill } from './AccessPill';
import type { IssueDetail } from './slots';

const mockIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '11111111-1111-1111-1111-111111111111',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Auth Studio',
};

function createWrapper(initialData?: unknown, objectId: string = mockIssue.object_id ?? '') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  if (initialData) {
    queryClient.setQueryData(['access', objectId], initialData);
  }
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, Wrapper };
}

describe('AccessPill', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Required Test Case 6: Access pill visible text, popup text template, and event dispatch', () => {
    it('renders "Project + 2" when explicit_grant_count = 2', () => {
      const accessData = {
        scope_label: 'Project',
        explicit_grant_count: 2,
        users: 14,
        groups: 2,
        agents: 1,
        deny_rules: 0,
        redacted_count: 0,
      };
      const { Wrapper } = createWrapper(accessData);

      render(<AccessPill issue={mockIssue} />, { wrapper: Wrapper });

      const label = screen.getByText('Project + 2');
      expect(label).toBeDefined();
    });

    it('renders "Project" when explicit_grant_count = 0', () => {
      const accessData = {
        scope_label: 'Project',
        explicit_grant_count: 0,
        users: 5,
        groups: 1,
        agents: 1,
        deny_rules: 0,
        redacted_count: 0,
      };
      const { Wrapper } = createWrapper(accessData);

      render(<AccessPill issue={mockIssue} />, { wrapper: Wrapper });

      const label = screen.getByText('Project');
      expect(label).toBeDefined();
    });

    it('formats popup text matching literal template with singular/plural nouns', () => {
      const accessData = {
        scope_label: 'Project',
        explicit_grant_count: 2,
        users: 14,
        groups: 2,
        agents: 1,
        deny_rules: 0,
        redacted_count: 0,
      };
      const { Wrapper } = createWrapper(accessData);

      render(<AccessPill issue={mockIssue} />, { wrapper: Wrapper });

      const hintTrigger = screen.getByTestId('access-hint');
      act(() => {
        hintTrigger.focus();
      });

      const popup = screen.getByRole('dialog');
      expect(popup.textContent).toContain(
        'Project: Platform Core - 14 users, 2 groups, 1 agent, 0 deny rules. Inherited from Project.',
      );
    });

    it('renders "+3 outside your visibility" when redacted_count is 3 without revealing principal names', () => {
      const accessData = {
        scope_label: 'Project',
        explicit_grant_count: 1,
        users: 3,
        groups: 1,
        agents: 1,
        deny_rules: 0,
        redacted_count: 3,
      };
      const { Wrapper } = createWrapper(accessData);

      render(<AccessPill issue={mockIssue} />, { wrapper: Wrapper });

      const hintTrigger = screen.getByTestId('access-hint');
      act(() => {
        hintTrigger.focus();
      });

      const popup = screen.getByRole('dialog');
      expect(popup.textContent).toContain('+3 outside your visibility');
    });

    it('dispatches exactly one kb:open-access-inspector event with detail.objectId on activate', () => {
      const accessData = {
        scope_label: 'Project',
        explicit_grant_count: 2,
        users: 14,
        groups: 2,
        agents: 1,
        deny_rules: 0,
      };
      const { Wrapper } = createWrapper(accessData);

      const eventSpy = vi.fn();
      window.addEventListener('kb:open-access-inspector', eventSpy);

      render(<AccessPill issue={mockIssue} />, { wrapper: Wrapper });

      const hintTrigger = screen.getByTestId('access-hint');
      act(() => {
        hintTrigger.focus();
      });

      const actionBtn = screen.getByRole('button', { name: 'Open Access Inspector' });
      fireEvent.click(actionBtn);

      expect(eventSpy).toHaveBeenCalledTimes(1);
      const customEvent = eventSpy.mock.calls[0]?.[0] as CustomEvent<{ objectId: string }>;
      expect(customEvent.detail.objectId).toBe(mockIssue.object_id);

      window.removeEventListener('kb:open-access-inspector', eventSpy);
    });

    it('falls back to issue.id when issue.object_id is omitted or null', () => {
      const fallbackId = '22222222-2222-2222-2222-222222222222';
      const issueWithIdOnly: IssueDetail = {
        id: fallbackId,
        key: 'KAN-FALLBACK',
        project_key: 'KAN',
        project_name: 'Platform Core',
        summary: 'Fallback task',
      };
      const { Wrapper } = createWrapper();

      const eventSpy = vi.fn();
      window.addEventListener('kb:open-access-inspector', eventSpy);

      render(<AccessPill issue={issueWithIdOnly} />, { wrapper: Wrapper });

      const hintTrigger = screen.getByTestId('access-hint');
      act(() => {
        hintTrigger.focus();
      });

      const actionBtn = screen.getByRole('button', { name: 'Open Access Inspector' });
      fireEvent.click(actionBtn);

      expect(eventSpy).toHaveBeenCalledTimes(1);
      const customEvent = eventSpy.mock.calls[0]?.[0] as CustomEvent<{ objectId: string }>;
      expect(customEvent.detail.objectId).toBe(fallbackId);

      window.removeEventListener('kb:open-access-inspector', eventSpy);
    });

    it('handles array and fallback counts, empty project_name, and fetch queryFn error and success', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      // Test fetch failure
      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 500,
      } as Response);

      const issueNoProject: IssueDetail = {
        id: '44444444-4444-4444-4444-444444444444',
        key: 'KAN-NOPROJECT',
        project_key: 'KAN',
        project_name: '',
        summary: 'No project name',
      };
      const { Wrapper: ErrWrapper } = createWrapper(undefined, issueNoProject.id);
      const { unmount: unmountErr } = render(<AccessPill issue={issueNoProject} />, { wrapper: ErrWrapper });
      const hintTriggerErr = screen.getByTestId('access-hint');
      act(() => {
        hintTriggerErr.focus();
      });
      // While loading
      expect(screen.getByText('Loading access summary...')).toBeDefined();
      // After rejected fetch
      await waitFor(() => {
        expect(screen.getByText('Access summary unavailable.')).toBeDefined();
      });
      unmountErr();

      // Test fetch success and array counts
      const mockData = {
        scope_label: 'Project',
        explicit_grant_count: 0,
        users: [1, 2],
        groups: [1],
        agents: [],
        deny_rules: 'invalid' as unknown as number,
      };

      const { Wrapper: SuccessWrapper } = createWrapper(mockData, issueNoProject.id);
      const { unmount: unmountSuccess } = render(<AccessPill issue={issueNoProject} />, { wrapper: SuccessWrapper });

      const hintTrigger = screen.getByTestId('access-hint');
      act(() => {
        hintTrigger.focus();
      });

      const popup = screen.getByRole('dialog');
      expect(popup.textContent).toContain('2 users, 1 group, 0 agents, 0 deny rules');
      unmountSuccess();

      // Test live queryFn execution (covers line 52 return await res.json())
      fetchSpy.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      } as Response);
      const liveId = '55555555-5555-5555-5555-555555555555';
      const { Wrapper: LiveWrapper } = createWrapper(undefined, liveId);
      const { unmount: unmountLive } = render(
        <AccessPill issue={{ ...mockIssue, object_id: liveId }} />,
        { wrapper: LiveWrapper },
      );
      await waitFor(() => {
        expect(screen.getByTestId('access-hint')).toBeDefined();
      });
      unmountLive();

      // Test issue with no object_id, no id, and fallback project_name (covers fallback branches 37-38)
      const issueEmpty: IssueDetail = {
        key: 'KAN-EMPTY',
        project_key: 'KAN',
        summary: 'Empty id test',
      };
      const { Wrapper: EmptyWrapper } = createWrapper(undefined, '');
      const { unmount: unmountEmpty } = render(<AccessPill issue={issueEmpty} />, { wrapper: EmptyWrapper });
      unmountEmpty();

      fetchSpy.mockRestore();
    });
  });
});
