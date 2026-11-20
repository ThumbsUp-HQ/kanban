import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { IssueHeader } from './IssueHeader';
import { IssueSurfaceSlotsContext, type IssueDetail } from './slots';
import * as clipboardUtils from '../../utils/clipboard';

const baseIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '11111111-1111-1111-1111-111111111111',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Auth Studio',
  priority: {
    slug: 'urgent',
    label: 'Urgent',
    emoji: '🔥',
    sort_order: 1,
    sla_target: '4h',
  },
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  queryClient.setQueryData(['access', baseIssue.object_id], {
    scope_label: 'Project',
    explicit_grant_count: 2,
    users: 14,
    groups: 2,
    agents: 1,
    deny_rules: 0,
    redacted_count: 0,
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { queryClient, Wrapper };
}

describe('IssueHeader', () => {
  it('renders collapse, full-screen toggle, priority, key, access pill and slots', () => {
    const onClose = vi.fn();
    const toggleFullScreen = vi.fn();
    const { Wrapper } = createWrapper();

    const mockSlots = {
      subscribe: () => <button type="button">Subscribe</button>,
      link: () => <button type="button">Link</button>,
      overflow: () => <button type="button">Overflow</button>,
    };

    render(
      <Wrapper>
        <IssueSurfaceSlotsContext.Provider value={mockSlots}>
          <IssueHeader
            issue={baseIssue}
            mode="drawer"
            onClose={onClose}
            toggleFullScreen={toggleFullScreen}
          />
        </IssueSurfaceSlotsContext.Provider>
      </Wrapper>,
    );

    const closeBtn = screen.getByRole('button', { name: 'Close issue panel' });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);

    const fsBtn = screen.getByRole('button', { name: 'Open in full screen' });
    fireEvent.mouseDown(fsBtn);
    fireEvent.click(fsBtn);
    expect(toggleFullScreen).toHaveBeenCalledTimes(1);

    expect(screen.getByText('KAN-142')).toBeDefined();
    expect(screen.getByText('Subscribe')).toBeDefined();
    expect(screen.getByText('Link')).toBeDefined();
    expect(screen.getByText('Overflow')).toBeDefined();
  });

  it('renders "Return to side panel" label when mode is full', () => {
    const { Wrapper } = createWrapper();
    render(
      <Wrapper>
        <IssueHeader
          issue={baseIssue}
          mode="full"
          onClose={vi.fn()}
          toggleFullScreen={vi.fn()}
        />
      </Wrapper>,
    );

    expect(screen.getByRole('button', { name: 'Return to side panel' })).toBeDefined();
  });

  it('renders correctly for high, medium, low, and unknown priorities', () => {
    const { Wrapper } = createWrapper();
    const priorities = [
      { slug: 'high', label: 'High', sort_order: 2 },
      { slug: 'medium', label: 'Medium', sort_order: 3 },
      { slug: 'low', label: 'Low', sort_order: 4 },
      { slug: 'unknown', label: 'Unknown', sort_order: 9 },
    ];

    for (const prio of priorities) {
      const issue = {
        ...baseIssue,
        priority: {
          slug: prio.slug,
          label: prio.label,
          emoji: '•',
          sort_order: prio.sort_order,
          sla_target: null,
        },
      };

      const { unmount } = render(
        <Wrapper>
          <IssueHeader
            issue={issue}
            mode="drawer"
            onClose={vi.fn()}
            toggleFullScreen={vi.fn()}
          />
        </Wrapper>,
      );
      unmount();
    }
  });

  it('handles issue key copy and issue link copy with visible feedback', async () => {
    vi.useFakeTimers();
    /* eslint-disable @typescript-eslint/no-deprecated */
    document.execCommand = vi.fn().mockReturnValue(true);
    /* eslint-enable @typescript-eslint/no-deprecated */
    const { Wrapper } = createWrapper();

    const { unmount } = render(
      <Wrapper>
        <IssueHeader
          issue={baseIssue}
          mode="drawer"
          onClose={vi.fn()}
          toggleFullScreen={vi.fn()}
        />
      </Wrapper>,
    );

    const copyKeyBtn = screen.getByTestId('copy-issue-key-btn');
    expect(copyKeyBtn.getAttribute('title')).toBe('Copy issue key');
    await act(async () => {
      fireEvent.click(copyKeyBtn);
      await Promise.resolve();
    });

    expect(screen.getByTestId('copy-issue-key-btn').textContent).toBe('Copied!');
    expect(screen.getByTestId('copy-issue-key-btn').getAttribute('title')).toBe('Copied!');

    // Advance timer past 2000ms
    act(() => {
      vi.advanceTimersByTime(2100);
    });
    expect(screen.getByTestId('copy-issue-key-btn').textContent).toBe('📋');

    const copyLinkBtn = screen.getByTestId('copy-issue-link-btn');
    expect(copyLinkBtn.getAttribute('title')).toBe('Copy issue link');
    await act(async () => {
      fireEvent.click(copyLinkBtn);
      await Promise.resolve();
    });

    expect(screen.getByTestId('copy-issue-link-btn').textContent).toBe('Copied!');
    expect(screen.getByTestId('copy-issue-link-btn').getAttribute('title')).toBe('Copied!');

    act(() => {
      vi.advanceTimersByTime(2100);
    });
    expect(screen.getByTestId('copy-issue-link-btn').textContent).toBe('🔗');
    expect(screen.getByTestId('copy-issue-link-btn').getAttribute('title')).toBe('Copy issue link');

    unmount();
    vi.useRealTimers();

    // False branch when copyToClipboard returns false
    vi.spyOn(clipboardUtils, 'copyToClipboard').mockResolvedValue(false);
    render(
      <Wrapper>
        <IssueHeader
          issue={baseIssue}
          mode="drawer"
          onClose={vi.fn()}
          toggleFullScreen={vi.fn()}
        />
      </Wrapper>,
    );
    fireEvent.click(screen.getByTestId('copy-issue-key-btn'));
    fireEvent.click(screen.getByTestId('copy-issue-link-btn'));
  });

  it('resolves issue.object_id ?? issue.id for AccessPill when object_id is omitted', () => {
    const fallbackId = '33333333-3333-3333-3333-333333333333';
    const issueWithIdOnly: IssueDetail = {
      id: fallbackId,
      key: 'KAN-999',
      project_key: 'KAN',
      project_name: 'Platform Core',
      summary: 'Task with id only',
    };
    const { Wrapper } = createWrapper();
    const eventSpy = vi.fn();
    window.addEventListener('kb:open-access-inspector', eventSpy);

    render(
      <Wrapper>
        <IssueHeader
          issue={issueWithIdOnly}
          mode="drawer"
          onClose={vi.fn()}
          toggleFullScreen={vi.fn()}
        />
      </Wrapper>,
    );

    const hintTrigger = screen.getByTestId('access-hint');
    fireEvent.focus(hintTrigger);

    const actionBtn = screen.getByRole('button', { name: 'Open Access Inspector' });
    fireEvent.click(actionBtn);

    expect(eventSpy).toHaveBeenCalledTimes(1);
    const customEvent = eventSpy.mock.calls[0]?.[0] as CustomEvent<{ objectId: string }>;
    expect(customEvent.detail.objectId).toBe(fallbackId);

    window.removeEventListener('kb:open-access-inspector', eventSpy);
  });
});
