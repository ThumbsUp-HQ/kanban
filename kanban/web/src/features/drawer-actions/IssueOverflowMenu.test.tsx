import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { IssueOverflowMenu } from './IssueOverflowMenu';
import * as actionsApi from './actionsApi';
import * as RealtimeStatusModule from '../../api/RealtimeStatus';
import type { IssueDetail } from '../drawer/slots';

const startedIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '018f0000-0000-7000-8000-000000000001',
  project_key: 'KAN',
  project_name: 'Kanban Platform',
  summary: 'In Progress Task',
  state: { name: 'In Progress', group: 'started' },
  capabilities: ['VIEW', 'EDIT', 'DELETE'],
};

const doneIssue: IssueDetail = {
  key: 'KAN-143',
  object_id: '018f0000-0000-7000-8000-000000000002',
  project_key: 'KAN',
  project_name: 'Kanban Platform',
  summary: 'Done Task',
  state: { name: 'Done', group: 'completed' },
  capabilities: ['VIEW', 'EDIT', 'DELETE'],
};

function renderComponent(props: {
  issue?: IssueDetail;
  mode?: 'drawer' | 'full';
  toggleFullScreen?: () => void;
}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/projects/KAN?peek=KAN-142']}>
        <IssueOverflowMenu
          issue={props.issue ?? startedIssue}
          mode={props.mode ?? 'drawer'}
          toggleFullScreen={props.toggleFullScreen ?? vi.fn()}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('IssueOverflowMenu (KB-P3-43, S7.1, S7.2 8n-8q)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('archive rule: disabled on started issue with exact reason sub-label and zero network calls', () => {
    const archiveSpy = vi.spyOn(actionsApi, 'archiveIssue');

    renderComponent({ issue: startedIssue });

    const trigger = screen.getByTestId('issue-overflow-trigger');
    fireEvent.click(trigger);

    const archiveBtn = screen.getByTestId('overflow-archive-btn');
    expect(archiveBtn.getAttribute('aria-disabled')).toBe('true');

    const reasonEl = screen.getByTestId('archive-disabled-reason');
    expect(reasonEl.textContent).toBe('Only completed or canceled work items can be archived');

    // Clicking disabled archive fires zero network calls
    fireEvent.click(archiveBtn);
    expect(archiveSpy).not.toHaveBeenCalled();
  });

  it('archive rule: enabled on completed issue and calls archiveIssue', async () => {
    const archiveSpy = vi.spyOn(actionsApi, 'archiveIssue').mockResolvedValue({});
    const announceSpy = vi.spyOn(RealtimeStatusModule, 'announce');

    renderComponent({ issue: doneIssue });

    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));

    const archiveBtn = screen.getByTestId('overflow-archive-btn');
    expect(archiveBtn.getAttribute('aria-disabled')).toBe('false');
    expect(screen.queryByTestId('archive-disabled-reason')).toBeNull();

    fireEvent.click(archiveBtn);

    await waitFor(() => {
      expect(archiveSpy).toHaveBeenCalledWith('KAN-143');
      expect(announceSpy).toHaveBeenCalledWith('Archived');
    });
  });

  it('unarchive rule: on archived issue, button displays Unarchive and calls unarchiveIssue', async () => {
    const archivedIssue: IssueDetail = {
      ...doneIssue,
      archived_at: '2026-11-12T00:00:00Z',
    };
    const unarchiveSpy = vi.spyOn(actionsApi, 'unarchiveIssue').mockResolvedValue({});
    const announceSpy = vi.spyOn(RealtimeStatusModule, 'announce');

    renderComponent({ issue: archivedIssue });

    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));

    const archiveBtn = screen.getByTestId('overflow-archive-btn');
    expect(archiveBtn.textContent).toContain('Unarchive');

    fireEvent.click(archiveBtn);

    await waitFor(() => {
      expect(unarchiveSpy).toHaveBeenCalledWith('KAN-143');
      expect(announceSpy).toHaveBeenCalledWith('Un展望' in {} ? '' : 'Unarchived');
      expect(announceSpy).toHaveBeenCalledWith('Unarchived');
    });
  });

  it('open in full screen: toggles fullscreen callback preserving data-mount-id', () => {
    const toggleSpy = vi.fn();
    renderComponent({ issue: startedIssue, mode: 'drawer', toggleFullScreen: toggleSpy });

    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    const fsBtn = screen.getByTestId('overflow-toggle-fullscreen-btn');
    expect(fsBtn.textContent).toContain('Open in full screen');

    fireEvent.click(fsBtn);
    expect(toggleSpy).toHaveBeenCalled();
  });

  it('in full screen mode: displays Return to side panel', () => {
    const toggleSpy = vi.fn();
    renderComponent({ issue: startedIssue, mode: 'full', toggleFullScreen: toggleSpy });

    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    const fsBtn = screen.getByTestId('overflow-toggle-fullscreen-btn');
    expect(fsBtn.textContent).toContain('Return to side panel');
  });

  it('make a copy: disabled when caller lacks EDIT capability', () => {
    const readOnlyIssue: IssueDetail = {
      ...startedIssue,
      capabilities: ['VIEW'],
    };

    renderComponent({ issue: readOnlyIssue });

    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    const copyBtn = screen.getByTestId<HTMLButtonElement>('overflow-make-copy-btn');
    expect(copyBtn.disabled).toBe(true);
  });

  it('delete button: hidden when caller lacks DELETE capability, shown and clickable when caller has DELETE', () => {
    const noDeleteIssue: IssueDetail = {
      ...startedIssue,
      capabilities: ['VIEW', 'EDIT'],
    };

    const { unmount } = renderComponent({ issue: noDeleteIssue });
    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    expect(screen.queryByTestId('overflow-delete-btn')).toBeNull();

    unmount();

    renderComponent({ issue: startedIssue });
    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    const deleteBtn = screen.getByTestId('overflow-delete-btn');
    expect(deleteBtn).toBeDefined();

    fireEvent.click(deleteBtn);
    expect(screen.getByTestId('delete-blast-radius-modal')).toBeDefined();

    // Close modal
    fireEvent.click(screen.getByTestId('delete-blast-backdrop'));
    expect(screen.queryByTestId('delete-blast-radius-modal')).toBeNull();
  });

  it('make a copy opens dialog and closes on backdrop click', () => {
    renderComponent({ issue: startedIssue });

    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    const copyBtn = screen.getByTestId('overflow-make-copy-btn');
    fireEvent.click(copyBtn);

    expect(screen.getByTestId('make-copy-dialog')).toBeDefined();

    // Close dialog
    fireEvent.click(screen.getByTestId('make-copy-backdrop'));
    expect(screen.queryByTestId('make-copy-dialog')).toBeNull();
  });

  it('menu keyboard navigation: ArrowDown, ArrowUp, Home, End, Escape', () => {
    renderComponent({ issue: startedIssue });

    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    const menu = screen.getByTestId('issue-overflow-menu');
    expect(menu).toBeDefined();

    const items = screen.getAllByRole('menuitem');
    items[0]?.focus();
    expect(document.activeElement).toBe(items[0]);

    fireEvent.keyDown(menu, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(items[1]);

    fireEvent.keyDown(menu, { key: 'ArrowUp' });
    expect(document.activeElement).toBe(items[0]);

    fireEvent.keyDown(menu, { key: 'End' });
    expect(document.activeElement).toBe(items[items.length - 1]);

    fireEvent.keyDown(menu, { key: 'Home' });
    expect(document.activeElement).toBe(items[0]);

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByTestId('issue-overflow-menu')).toBeNull();
  });

  it('closes menu on click outside and ignores other keys', () => {
    renderComponent({ issue: startedIssue });

    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    expect(screen.getByTestId('issue-overflow-menu')).toBeDefined();

    // Keydown other key
    fireEvent.keyDown(screen.getByTestId('issue-overflow-menu'), { key: 'Tab' });
    expect(screen.getByTestId('issue-overflow-menu')).toBeDefined();

    // Mousedown outside
    fireEvent.mouseDown(document.body);
    expect(screen.queryByTestId('issue-overflow-menu')).toBeNull();
  });

  it('allows archive when state group is cancelled and handles missing state / capabilities', () => {
    const cancelledIssue: IssueDetail = {
      ...doneIssue,
      state: { name: 'Canceled', group: 'cancelled' },
    };
    const { unmount } = renderComponent({ issue: cancelledIssue });

    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    const archiveBtn = screen.getByTestId('overflow-archive-btn');
    expect(archiveBtn.getAttribute('aria-disabled')).toBe('false');
    unmount();

    // Missing state and capabilities
    const bareIssue: IssueDetail = {
      key: 'KAN-999',
      object_id: '018f0000-0000-7000-8000-000000000999',
      project_key: 'KAN',
      project_name: 'Kanban Platform',
      summary: 'Bare Issue',
    };
    const { unmount: unmountBare } = renderComponent({ issue: bareIssue });
    fireEvent.click(screen.getByTestId('issue-overflow-trigger'));
    expect(screen.getByTestId('overflow-delete-btn')).toBeDefined();
    unmountBare();
  });
});
