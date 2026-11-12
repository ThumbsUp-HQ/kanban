import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
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

function createWrapper(initialData?: unknown) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  if (initialData) {
    queryClient.setQueryData(['access', mockIssue.object_id], initialData);
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
  });
});
