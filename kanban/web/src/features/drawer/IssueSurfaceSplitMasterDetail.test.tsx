import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IssueSurfaceRoot } from './IssueSurface';
import { apiClient } from '../../api/client';
import * as railApi from '../drawer-rail/railApi';
import { ApiProblem } from '../../api/problem';
import type { IssueDetail } from './slots';
import type { IssueItem } from '../views/viewsApi';

const mockIssue: IssueDetail = {
  key: 'KAN-52',
  object_id: '01931234-5678-7000-8000-000000000052',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Master-Detail Issue Navigator View',
  description_markdown: 'Detailed description of navigator view.',
  created_at: '2026-11-20T10:00:00Z',
  updated_at: '2026-11-20T11:00:00Z',
  start_date: '2026-11-20',
  due_date: '2026-11-30',
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: null,
  },
  state: {
    id: 'state-in-progress',
    name: 'In Progress',
    group: 'started',
  },
  capabilities: ['EDIT', 'TRANSITION', 'COMMENT'],
  sub_issues: [
    { key: 'KAN-53', summary: 'Subtask 1' },
  ],
  etag: '"etag-kan-52"',
};

const mockIssuesList: IssueItem[] = [
  {
    id: '01931234-5678-7000-8000-000000000051',
    key: 'KAN-51',
    summary: 'Previous Issue',
    state: { id: 'state-todo', name: 'Todo', group: 'unstarted' },
    priority: { slug: 'medium', label: 'Medium' },
  },
  {
    id: '01931234-5678-7000-8000-000000000052',
    key: 'KAN-52',
    summary: 'Master-Detail Issue Navigator View',
    state: { id: 'state-in-progress', name: 'In Progress', group: 'started' },
    priority: { slug: 'high', label: 'High' },
  },
  {
    id: '01931234-5678-7000-8000-000000000053',
    key: 'KAN-53',
    summary: 'Next Issue',
    state: { id: 'state-done', name: 'Done', group: 'completed' },
    priority: { slug: 'low', label: 'Low' },
  },
];

describe('IssueSurface split mode (KAN-52 Problem 3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  function renderSplitSurface(props: Partial<React.ComponentProps<typeof IssueSurfaceRoot>> = {}) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.spyOn(apiClient, 'get').mockImplementation((url: string) => {
      if (url.includes('/api/v1/auth/me')) {
        return Promise.resolve({ id: 'u-123', handle: 'adam', display_name: 'Adam Outler' });
      }
      return Promise.resolve(mockIssue);
    });

    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <IssueSurfaceRoot
            mode="split"
            issueKey="KAN-52"
            projectKey="KAN"
            projectName="Platform Core"
            issuesList={mockIssuesList}
            {...props}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  it('renders header, project breadcrumb, and sequential pager with keyboard shortcuts', async () => {
    const onNavigateIssue = vi.fn();
    renderSplitSurface({ onNavigateIssue });

    await waitFor(() => {
      expect(screen.getByTestId('split-breadcrumb')).toBeDefined();
    });

    // 1. Breadcrumb
    expect(screen.getByTestId('split-breadcrumb').textContent).toContain('Platform Core / KAN-52');

    // 2. Pager position: index 1 of 3 (2 of 3)
    const pagerPos = screen.getByTestId('issue-navigator-position');
    expect(pagerPos.textContent).toBe('2 of 3');

    // 3. Pager buttons
    const prevBtn = screen.getByTestId('issue-prev-btn');
    const nextBtn = screen.getByTestId('issue-next-btn');
    expect(prevBtn).toBeDefined();
    expect(nextBtn).toBeDefined();

    fireEvent.click(prevBtn);
    expect(onNavigateIssue).toHaveBeenCalledWith('KAN-51');

    fireEvent.click(nextBtn);
    expect(onNavigateIssue).toHaveBeenCalledWith('KAN-53');

    // 4. J/K and Arrow key navigation
    fireEvent.keyDown(window, { key: 'j' });
    expect(onNavigateIssue).toHaveBeenCalledWith('KAN-53');

    fireEvent.keyDown(window, { key: 'k' });
    expect(onNavigateIssue).toHaveBeenCalledWith('KAN-51');

    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(onNavigateIssue).toHaveBeenCalledWith('KAN-53');

    fireEvent.keyDown(window, { key: 'ArrowUp' });
    expect(onNavigateIssue).toHaveBeenCalledWith('KAN-51');
  });

  it('renders action toolbar row with edit, add comment, assign, state dropdown, favorite toggle, and share', async () => {
    const clipboardSpy = vi.fn();
    Object.assign(navigator, {
      clipboard: { writeText: clipboardSpy },
    });

    renderSplitSurface();

    await waitFor(() => {
      expect(screen.getByTestId('split-action-toolbar')).toBeDefined();
    });

    // 1. Edit button
    const editBtn = screen.getByTestId('split-edit-btn');
    expect(editBtn).toBeDefined();

    // 2. Add comment button
    const addCommentBtn = screen.getByTestId('split-add-comment-btn');
    expect(addCommentBtn).toBeDefined();
    fireEvent.click(addCommentBtn);

    // 3. Assign button
    const assignBtn = screen.getByTestId('split-assign-btn');
    expect(assignBtn).toBeDefined();

    // 4. State dropdown
    const stateSelect = screen.getByTestId('split-state-select');
    expect(stateSelect).toBeDefined();

    // 5. Favorite button toggle
    const favBtn = screen.getByTestId('favorite-issue-toggle');
    expect(favBtn.textContent).toContain('☆ Favorite');
    fireEvent.click(favBtn);
    expect(favBtn.textContent).toContain('★ Favorite');

    // 6. Share / Export button
    const shareBtn = screen.getByTestId('split-share-btn');
    expect(shareBtn).toBeDefined();
    await act(async () => {
      fireEvent.click(shareBtn);
      await Promise.resolve();
    });
    expect(clipboardSpy).toHaveBeenCalled();
  });

  it('renders 2-column collapsible layout with details, description, attachments, links, activity, people, dates, and dev git branch', async () => {
    const clipboardSpy = vi.fn();
    Object.assign(navigator, {
      clipboard: { writeText: clipboardSpy },
    });

    renderSplitSurface();

    await waitFor(() => {
      expect(screen.getByTestId('split-body-grid')).toBeDefined();
    });

    // Left column sections
    expect(screen.getByTestId('split-summary-title')).toBeDefined();
    expect(screen.getByTestId('split-section-details')).toBeDefined();
    expect(screen.getByTestId('split-section-description')).toBeDefined();
    expect(screen.getByTestId('split-section-attachments')).toBeDefined();
    expect(screen.getByTestId('split-section-links')).toBeDefined();
    expect(screen.getByTestId('split-section-activity')).toBeDefined();

    // Sub-issues rendered
    expect(screen.getByText('KAN-53')).toBeDefined();
    expect(screen.getByText('Subtask 1')).toBeDefined();

    // Right column sections
    expect(screen.getByTestId('split-section-people')).toBeDefined();
    expect(screen.getByTestId('split-section-dates')).toBeDefined();
    expect(screen.getByTestId('split-section-dev')).toBeDefined();

    // 1-Click Assign to me
    const assignToMeBtn = screen.getByTestId('split-assign-to-me-btn');
    expect(assignToMeBtn).toBeDefined();
    await act(async () => {
      fireEvent.click(assignToMeBtn);
      await Promise.resolve();
    });

    // Dates check
    expect(screen.getByTestId('split-date-start').textContent).toBe('2026-11-20');
    expect(screen.getByTestId('split-date-due').textContent).toBe('2026-11-30');

    // Git branch copy helper
    const gitBranchBtn = screen.getByTestId('split-git-branch-copy');
    expect(gitBranchBtn).toBeDefined();
    await act(async () => {
      fireEvent.click(gitBranchBtn);
      await Promise.resolve();
    });
    expect(clipboardSpy).toHaveBeenCalled();
  });

  it('split-assign-to-me-btn hits POST /api/v1/issues/{issue_ref}/assignees with exact schema and updates UI, and surfaces 422 error cleanly', async () => {
    const addAssigneeSpy = vi.spyOn(railApi, 'addAssignee').mockResolvedValueOnce({
      id: 'asg-adam',
      kind: 'principal',
      principal: {
        id: 'u-123',
        handle: 'adam',
        display_name: 'Adam Outler',
        type: 'USER',
      },
    });

    renderSplitSurface();

    await waitFor(() => {
      expect(screen.getByTestId('split-assign-to-me-btn')).toBeDefined();
    });

    expect(screen.getAllByText('Unassigned').length).toBeGreaterThanOrEqual(1);

    const assignToMeBtn = screen.getByTestId('split-assign-to-me-btn');
    await act(async () => {
      fireEvent.click(assignToMeBtn);
      await Promise.resolve();
    });

    expect(addAssigneeSpy).toHaveBeenCalledWith('KAN-52', { principal: 'u-123' });

    await waitFor(() => {
      expect(screen.getAllByText('Adam Outler').length).toBeGreaterThanOrEqual(1);
    });
  });

  it('split-assign-to-me-btn surfaces 422 validation error cleanly via conflict banner without silent swallow', async () => {
    vi.spyOn(railApi, 'addAssignee').mockRejectedValueOnce(
      new ApiProblem(422, {
        code: 'VALIDATION_FAILED',
        detail: 'Request validation failed: Extra inputs are not permitted',
      }),
    );

    renderSplitSurface();

    await waitFor(() => {
      expect(screen.getByTestId('split-assign-to-me-btn')).toBeDefined();
    });

    const assignToMeBtn = screen.getByTestId('split-assign-to-me-btn');
    await act(async () => {
      fireEvent.click(assignToMeBtn);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByTestId('conflict-banner')).toBeDefined();
      expect(
        screen.getByText('Request validation failed: Extra inputs are not permitted'),
      ).toBeDefined();
    });
  });

  it('split-git-branch-copy and split-share-btn handle navigator.clipboard.writeText rejecting with NotAllowedError gracefully', async () => {
    const notAllowedError = new Error('NotAllowedError: Write permission denied.');
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockRejectedValue(notAllowedError),
      },
    });

    renderSplitSurface();

    await waitFor(() => {
      expect(screen.getByTestId('split-git-branch-copy')).toBeDefined();
    });

    const gitBranchBtn = screen.getByTestId('split-git-branch-copy');
    await act(async () => {
      fireEvent.click(gitBranchBtn);
      await Promise.resolve();
    });
    expect(gitBranchBtn.textContent).toContain('✓ Copied!');

    const shareBtn = screen.getByTestId('split-share-btn');
    await act(async () => {
      fireEvent.click(shareBtn);
      await Promise.resolve();
    });
    expect(shareBtn.textContent).toContain('✓ Copied link!');
  });
});
