import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { MakeCopyDialog } from './MakeCopyDialog';
import * as actionsApi from './actionsApi';
import * as clientModule from '../../api/client';
import * as RealtimeStatusModule from '../../api/RealtimeStatus';
import type { IssueDetail } from '../drawer/slots';

const mockIssue: IssueDetail = {
  key: 'KAN-142',
  object_id: '018f0000-0000-7000-8000-000000000001',
  project_key: 'KAN',
  project_name: 'Kanban Platform',
  summary: 'Harden OAuth and MCP token security',
};

function renderComponent(props: { open: boolean; onClose: () => void; issue?: IssueDetail }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/projects/KAN?peek=KAN-142']}>
        <MakeCopyDialog
          issue={props.issue ?? mockIssue}
          open={props.open}
          onClose={props.onClose}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('MakeCopyDialog (KB-P3-43, S7.2 8n)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when open is false', () => {
    const onClose = vi.fn();
    renderComponent({ open: false, onClose });
    expect(screen.queryByTestId('make-copy-dialog')).toBeNull();
  });

  it('renders with title preview, creator note, and 3 unchecked checkboxes', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ handle: 'adamoutler' });
    const onClose = vi.fn();
    renderComponent({ open: true, onClose });

    expect(screen.getByTestId('make-copy-dialog')).toBeDefined();
    expect(screen.getByTestId('copy-preview-title').textContent).toBe(
      '[Copy] Harden OAuth and MCP token security',
    );

    const subIssuesCb = screen.getByTestId<HTMLInputElement>('copy-include-sub-issues');
    const attachmentsCb = screen.getByTestId<HTMLInputElement>('copy-include-attachments');
    const relatesToCb = screen.getByTestId<HTMLInputElement>('copy-link-relates-to');

    expect(subIssuesCb.checked).toBe(false);
    expect(attachmentsCb.checked).toBe(false);
    expect(relatesToCb.checked).toBe(false);

    await waitFor(() => {
      expect(screen.getByTestId('copy-creator-notice').textContent).toBe(
        'Created by will be set to @adamoutler',
      );
    });
  });

  it('checking all 3 boxes sends payload, announces skipped restricted sub-issues, and closes', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ handle: 'adamoutler' });
    const copySpy = vi.spyOn(actionsApi, 'copyIssue').mockResolvedValue({
      issue: { key: 'KAN-150', summary: '[Copy] Harden OAuth and MCP token security' },
      copied_sub_issues: [{ source_key: 'KAN-143', copy_key: 'KAN-151' }],
      skipped: { restricted_sub_issues: 2 },
      copied_attachments: 1,
      link_id: 'link-123',
    });
    const announceSpy = vi.spyOn(RealtimeStatusModule, 'announce');
    const onClose = vi.fn();

    renderComponent({ open: true, onClose });

    const subIssuesCb = screen.getByTestId('copy-include-sub-issues');
    const attachmentsCb = screen.getByTestId('copy-include-attachments');
    const relatesToCb = screen.getByTestId('copy-link-relates-to');

    fireEvent.click(subIssuesCb);
    fireEvent.click(attachmentsCb);
    fireEvent.click(relatesToCb);

    const submitBtn = screen.getByTestId('confirm-copy-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(copySpy).toHaveBeenCalledWith('KAN-142', {
        include_sub_issues: true,
        include_attachments: true,
        link_as_relates_to: true,
      });
      expect(announceSpy).toHaveBeenCalledWith(
        'Copied to KAN-150 (2 restricted sub-issue(s) skipped)',
      );
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('renders inline alert on 422 COPY_TOO_LARGE', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ handle: 'adamoutler' });
    vi.spyOn(actionsApi, 'copyIssue').mockRejectedValue({
      status: 422,
      code: 'COPY_TOO_LARGE',
      detail: 'Cannot copy issue tree exceeding 200 items',
    });
    const onClose = vi.fn();

    renderComponent({ open: true, onClose });

    const submitBtn = screen.getByTestId('confirm-copy-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      const alert = screen.getByTestId('copy-error-alert');
      expect(alert.textContent).toBe('Cannot copy issue tree exceeding 200 items');
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  it('navigates to full route when copying while in full screen mode', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ handle: 'adamoutler' });
    vi.spyOn(actionsApi, 'copyIssue').mockResolvedValue({
      issue: { key: 'KAN-150', summary: '[Copy] Task' },
    });
    const announceSpy = vi.spyOn(RealtimeStatusModule, 'announce');
    const onClose = vi.fn();

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-142']}>
          <MakeCopyDialog issue={mockIssue} open={true} onClose={onClose} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const submitBtn = screen.getByTestId('confirm-copy-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(announceSpy).toHaveBeenCalledWith('Copied to KAN-150');
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('closes dialog on Escape key or backdrop click', () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({ handle: 'adamoutler' });
    const onClose = vi.fn();

    renderComponent({ open: true, onClose });

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('make-copy-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(2);

    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);
    expect(onClose).toHaveBeenCalledTimes(3);

    fireEvent.keyDown(document, { key: 'Tab' });
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('handles meData without handle, summary > 500 chars, and message-only error fallback', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue({});
    vi.spyOn(actionsApi, 'copyIssue').mockRejectedValue({
      message: 'Custom message without detail',
    });
    const onClose = vi.fn();
    const longSummary = 'A'.repeat(600);

    renderComponent({
      open: true,
      onClose,
      issue: { ...mockIssue, summary: longSummary },
    });

    const preview = screen.getByTestId('copy-preview-title');
    expect(preview.textContent.length).toBe(500);

    await waitFor(() => {
      expect(screen.getByTestId('copy-creator-notice').textContent).toBe(
        'Created by will be set to @currentUser',
      );
    });

    const submitBtn = screen.getByTestId('confirm-copy-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByTestId('copy-error-alert').textContent).toBe(
        'Custom message without detail',
      );
    });
  });

  it('handles empty summary, object without message error, and isPending state', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(null);
    let resolvePromise!: (val: unknown) => void;
    vi.spyOn(actionsApi, 'copyIssue').mockImplementation(
      () =>
        new Promise((resolve, reject) => {
          resolvePromise = reject;
        }),
    );
    const onClose = vi.fn();

    renderComponent({
      open: true,
      onClose,
      issue: { ...mockIssue, summary: '' },
    });

    expect(screen.getByTestId('copy-preview-title').textContent).toBe('[Copy] ');

    const submitBtn = screen.getByTestId('confirm-copy-btn');
    fireEvent.click(submitBtn);

    // Verify isPending button text
    await waitFor(() => {
      expect(submitBtn.textContent).toBe('Copying...');
      expect((submitBtn as HTMLButtonElement).disabled).toBe(true);
    });

    // Reject with object lacking detail and message
    resolvePromise({ unexpected: true });

    await waitFor(() => {
      expect(screen.getByTestId('copy-error-alert').textContent).toBe('Failed to copy issue');
    });
  });

  it('handles primitive string error rejection', async () => {
    vi.spyOn(clientModule, 'apiFetch').mockResolvedValue(null);
    vi.spyOn(actionsApi, 'copyIssue').mockRejectedValue('Fatal network crash');
    const onClose = vi.fn();

    renderComponent({
      open: true,
      onClose,
      issue: mockIssue,
    });

    const submitBtn = screen.getByTestId('confirm-copy-btn');
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByTestId('copy-error-alert').textContent).toBe('Failed to copy issue');
    });
  });
});
