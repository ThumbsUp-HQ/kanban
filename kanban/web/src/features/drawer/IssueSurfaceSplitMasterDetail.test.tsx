import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IssueSurfaceRoot } from './IssueSurface';
import { apiClient } from '../../api/client';
import * as railApi from '../drawer-rail/railApi';
import { ApiProblem } from '../../api/problem';
import { IssueSurfaceSlotsContext, type IssueDetail } from './slots';
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

  it('renders drawn SVG chevron icons in issue pager buttons without ASCII ^/v and disables at boundaries (KAN-378)', async () => {
    // 1. Test boundary at index 0 (first issue: KAN-51, 1 of 3)
    const onNavigateIssue = vi.fn();
    const { unmount } = renderSplitSurface({
      issueKey: 'KAN-51',
      issuesList: mockIssuesList,
      onNavigateIssue,
    });

    await waitFor(() => {
      expect(screen.getByTestId('split-pager')).toBeDefined();
    });

    const prevBtn = screen.getByTestId('issue-prev-btn');
    const nextBtn = screen.getByTestId('issue-next-btn');
    const pagerPos = screen.getByTestId('issue-navigator-position');

    expect(pagerPos.textContent).toBe('1 of 3');

    // Boundary check at index 0: prev is disabled, next is enabled
    expect((prevBtn as HTMLButtonElement).disabled).toBe(true);
    expect((nextBtn as HTMLButtonElement).disabled).toBe(false);

    // Verify SVG vector chevron icons rendered with aria-hidden="true"
    const prevSvg = prevBtn.querySelector('svg');
    const nextSvg = nextBtn.querySelector('svg');
    expect(prevSvg).not.toBeNull();
    expect(nextSvg).not.toBeNull();
    if (!prevSvg || !nextSvg) throw new Error('SVGs missing');
    expect(prevSvg.getAttribute('aria-hidden')).toBe('true');
    expect(nextSvg.getAttribute('aria-hidden')).toBe('true');
    expect(prevSvg.getAttribute('width')).toBe('14');
    expect(prevSvg.getAttribute('height')).toBe('14');
    expect(nextSvg.getAttribute('width')).toBe('14');
    expect(nextSvg.getAttribute('height')).toBe('14');

    // Verify no raw ASCII caret or v character content
    const prevText = prevBtn.textContent;
    const nextText = nextBtn.textContent;
    expect(prevText.trim()).not.toContain('^');
    expect(nextText.trim()).not.toContain('v');
    expect(prevText.trim()).toBe('');
    expect(nextText.trim()).toBe('');

    // Verify accessible labels
    expect(prevBtn.getAttribute('aria-label')).toBe('Previous issue (k)');
    expect(nextBtn.getAttribute('aria-label')).toBe('Next issue (j)');

    // Verify CSS classes unified
    expect(prevBtn.classList.contains('issue-pager-btn')).toBe(true);
    expect(prevBtn.classList.contains('issue-prev-btn')).toBe(true);
    expect(nextBtn.classList.contains('issue-pager-btn')).toBe(true);
    expect(nextBtn.classList.contains('issue-next-btn')).toBe(true);

    unmount();

    // 2. Test boundary at index N - 1 (last issue: KAN-53, 3 of 3)
    renderSplitSurface({
      issueKey: 'KAN-53',
      issuesList: mockIssuesList,
      onNavigateIssue,
    });

    await waitFor(() => {
      expect(screen.getByTestId('split-pager')).toBeDefined();
    });

    const prevBtnLast = screen.getByTestId('issue-prev-btn');
    const nextBtnLast = screen.getByTestId('issue-next-btn');
    const pagerPosLast = screen.getByTestId('issue-navigator-position');

    expect(pagerPosLast.textContent).toBe('3 of 3');

    // Boundary check at index N - 1: prev is enabled, next is disabled
    expect((prevBtnLast as HTMLButtonElement).disabled).toBe(false);
    expect((nextBtnLast as HTMLButtonElement).disabled).toBe(true);

    const prevSvgLast = prevBtnLast.querySelector('svg');
    const nextSvgLast = nextBtnLast.querySelector('svg');
    expect(prevSvgLast).not.toBeNull();
    expect(nextSvgLast).not.toBeNull();
    if (!prevSvgLast || !nextSvgLast) throw new Error('SVGs missing');
    expect(prevSvgLast.getAttribute('aria-hidden')).toBe('true');
    expect(nextSvgLast.getAttribute('aria-hidden')).toBe('true');
    const prevLastText = prevBtnLast.textContent;
    const nextLastText = nextBtnLast.textContent;
    expect(prevLastText.trim()).not.toContain('^');
    expect(nextLastText.trim()).not.toContain('v');
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

    // Sub-issues rendered once full detail query resolves past summary placeholderData
    await waitFor(() => {
      expect(screen.getByText('KAN-53')).toBeDefined();
    });
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

  it('separate copy timeouts allow both git branch and share export feedback to clear independently without timer collision', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });

    renderSplitSurface();

    await waitFor(() => {
      expect(screen.getByTestId('split-git-branch-copy')).toBeDefined();
    });

    const gitBranchBtn = screen.getByTestId('split-git-branch-copy');
    const shareBtn = screen.getByTestId('split-share-btn');

    await act(async () => {
      fireEvent.click(gitBranchBtn);
      await Promise.resolve();
    });
    expect(gitBranchBtn.textContent).toContain('✓ Copied!');

    // Click share button 500ms later
    act(() => {
      vi.advanceTimersByTime(500);
    });

    await act(async () => {
      fireEvent.click(shareBtn);
      await Promise.resolve();
    });
    expect(shareBtn.textContent).toContain('✓ Copied link!');
    expect(gitBranchBtn.textContent).toContain('✓ Copied!');

    // Advance 1550ms (total 2050ms for branch, 1550ms for share)
    act(() => {
      vi.advanceTimersByTime(1550);
    });
    expect(gitBranchBtn.textContent).not.toContain('✓ Copied!');
    expect(shareBtn.textContent).toContain('✓ Copied link!');

    // Advance 500ms more (total 2050ms for share)
    act(() => {
      vi.advanceTimersByTime(500);
    });
    expect(shareBtn.textContent).not.toContain('✓ Copied link!');

    vi.useRealTimers();
  });

  it('split mode description editor formatting tools and quick-props state select work cleanly', async () => {
    const patchSpy = vi.spyOn(railApi, 'patchIssue').mockResolvedValue(mockIssue);
    renderSplitSurface();

    await waitFor(() => {
      expect(screen.getByTestId('split-edit-btn')).toBeDefined();
    });

    // 1. Quick-props state select in split details
    const quickPropsState = screen.getByTestId('quick-props-state-select');
    expect(quickPropsState).toBeDefined();
    await act(async () => {
      fireEvent.change(quickPropsState, { target: { value: 'state-done' } });
      await Promise.resolve();
    });
    expect(patchSpy).toHaveBeenCalled();

    // 2. Click split-edit-btn to open description editor
    const editBtn = screen.getByTestId('split-edit-btn');
    fireEvent.click(editBtn);

    expect(screen.getByTestId('description-editor-toolbar')).toBeDefined();

    // Test formatting tools: bold, italic, code, link, tasklist, mermaid
    const boldBtn = screen.getByTestId('description-editor-tool-bold');
    fireEvent.click(boldBtn);

    const italicBtn = screen.getByTestId('description-editor-tool-italic');
    fireEvent.click(italicBtn);

    const codeBtn = screen.getByTestId('description-editor-tool-code');
    fireEvent.click(codeBtn);

    const linkBtn = screen.getByTestId('description-editor-tool-link');
    fireEvent.click(linkBtn);

    const taskBtn = screen.getByTestId('description-editor-tool-tasklist');
    fireEvent.click(taskBtn);

    const mermaidBtn = screen.getByTestId('description-editor-tool-mermaid');
    fireEvent.click(mermaidBtn);

    // Toggle preview on
    const previewToggle = screen.getByTestId('description-editor-tool-raw');
    fireEvent.click(previewToggle);
    expect(screen.getByTestId('desc-preview')).toBeDefined();

    // Toggle preview off back to raw textarea
    fireEvent.click(previewToggle);
    const textarea = screen.getByTestId('description-editor-raw');

    // Cmd+Shift+M keyboard toggle preview
    fireEvent.keyDown(textarea, { key: 'm', metaKey: true, shiftKey: true });
    expect(screen.getByTestId('desc-preview')).toBeDefined();
    fireEvent.click(screen.getByTestId('description-editor-tool-raw'));

    // Test file input selection
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ id: 'att-1', markdownUri: 'attachment://att-1' }), { status: 200 })
    );
    const fileInput = screen.getByTestId('desc-file-input');
    const testFile = new File(['test image data'], 'diagram.png', { type: 'image/png' });
    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [testFile] } });
      await Promise.resolve();
    });
    fetchSpy.mockRestore();

    // Re-query raw textarea after preview toggle off
    const rawEditor = screen.getByTestId('description-editor-raw');

    // Test HTML paste with sanitized pill
    fireEvent.paste(rawEditor, {
      clipboardData: {
        files: [],
        getData: (format: string) => (format === 'text/html' ? '<p>Hello <span style="display:none">hidden</span></p>' : ''),
      },
    });

    const sanitizedPill = await screen.findByTestId('desc-sanitized-pill');
    expect(sanitizedPill).toBeDefined();

    // Dismiss sanitized pill via Escape key
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByTestId('desc-sanitized-pill')).toBeNull();
    });

    fireEvent.change(rawEditor, { target: { value: 'Updated description from test' } });

    // Save description
    const saveBtn = screen.getByRole('button', { name: 'Save description' });
    await act(async () => {
      fireEvent.click(saveBtn);
      await Promise.resolve();
    });
    expect(patchSpy).toHaveBeenCalled();
    patchSpy.mockRestore();
  });

  it('covers split mode slots, null priority label, empty description preview, fence newlines, and string error rollback', async () => {
    // 1. Issue with null priority, null description_markdown, and string assignee
    const sparseIssue: IssueDetail = {
      ...mockIssue,
      priority: null,
      description_markdown: null,
      assignees: ['@adam'],
    };
    vi.spyOn(apiClient, 'get').mockResolvedValue(sparseIssue);

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <IssueSurfaceSlotsContext.Provider
            value={{
              description: () => <div data-testid="split-custom-desc">Custom Split Desc</div>,
              activity: () => <div data-testid="split-custom-act">Custom Split Activity</div>,
            }}
          >
            <IssueSurfaceRoot
              mode="split"
              issueKey="KAN-52"
              projectKey="KAN"
              issuesList={mockIssuesList}
            />
          </IssueSurfaceSlotsContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('split-custom-desc')).toBeDefined();
      expect(screen.getByTestId('split-custom-act')).toBeDefined();
      expect(screen.getByText('None')).toBeDefined();
    });
    unmount();

    // 2. Fence with double newline preceding
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      ...mockIssue,
      description_markdown: 'Preceding line\n\n',
    });
    const queryClient2 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount: unmount2 } = render(
      <QueryClientProvider client={queryClient2}>
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <IssueSurfaceRoot
            mode="split"
            issueKey="KAN-52"
            projectKey="KAN"
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('split-edit-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('split-edit-btn'));
    const rawEditor = screen.getByTestId('description-editor-raw');
    (rawEditor as HTMLTextAreaElement).setSelectionRange(16, 16);
    fireEvent.click(screen.getByTestId('description-editor-tool-mermaid'));

    // Empty description draft preview
    fireEvent.change(rawEditor, { target: { value: '' } });
    fireEvent.click(screen.getByTestId('description-editor-tool-raw'));
    expect(screen.getByText('No description')).toBeDefined();

    // Revert state change with non-object error
    vi.spyOn(railApi, 'patchIssue').mockRejectedValueOnce('Simple string error');
    const quickPropsState = screen.getByTestId('quick-props-state-select');
    await act(async () => {
      fireEvent.change(quickPropsState, { target: { value: 'state-done' } });
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    unmount2();

    // 3. Error state with mode="full"
    vi.spyOn(apiClient, 'get').mockRejectedValueOnce(new Error('Load failure'));
    const queryClient3 = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { unmount: unmount3 } = render(
      <QueryClientProvider client={queryClient3}>
        <MemoryRouter initialEntries={['/projects/KAN/issues']}>
          <IssueSurfaceRoot
            mode="full"
            issueKey="KAN-52"
            projectKey="KAN"
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(screen.getByLabelText('Return to side panel')).toBeDefined();
    });
    unmount3();
  });

  it('KAN-379: replaces duplicate issue key with Edit button in header, moves Add Comment to activity section, and relocates action toolbar to right column', async () => {
    renderSplitSurface();

    await waitFor(() => {
      expect(screen.getByTestId('split-action-toolbar')).toBeDefined();
    });

    // 1. Verify .surface__header--split contains split-edit-btn and does NOT contain duplicate #KAN-52 text
    const header = document.querySelector('.surface__header--split');
    expect(header).not.toBeNull();
    const editBtn = screen.getByTestId('split-edit-btn');
    expect(header?.contains(editBtn)).toBe(true);

    // Duplicate key #KAN-52 is no longer in header
    const headerKey = header?.querySelector('.issue-header__key');
    expect(headerKey).toBeNull();

    // AccessPill is no longer in header
    const accessPillInHeader = header?.querySelector('[data-testid="access-pill"]');
    expect(accessPillInHeader).toBeNull();

    // 2. Verify split-add-comment-btn is inside split-section-activity
    const activitySection = screen.getByTestId('split-section-activity');
    const addCommentBtn = screen.getByTestId('split-add-comment-btn');
    expect(activitySection.contains(addCommentBtn)).toBe(true);

    // 3. Verify split-action-toolbar is inside split-right-column
    const rightCol = screen.getByTestId('split-right-column');
    const toolbar = screen.getByTestId('split-action-toolbar');
    expect(rightCol.contains(toolbar)).toBe(true);

    // Toolbar contains AccessPill, state select, assign, favorite, and share
    expect(toolbar.querySelector('[data-testid="access-pill"]')).not.toBeNull();
    expect(toolbar.querySelector('[data-testid="split-state-select"]')).not.toBeNull();
    expect(toolbar.querySelector('[data-testid="split-assign-btn"]')).not.toBeNull();
    expect(toolbar.querySelector('[data-testid="favorite-issue-toggle"]')).not.toBeNull();
    expect(toolbar.querySelector('[data-testid="split-share-btn"]')).not.toBeNull();
  });
});
