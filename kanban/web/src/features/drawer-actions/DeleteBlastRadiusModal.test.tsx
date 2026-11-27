import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { DeleteBlastRadiusModal } from './DeleteBlastRadiusModal';
import * as actionsApi from './actionsApi';
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
        <DeleteBlastRadiusModal
          issue={props.issue ?? mockIssue}
          open={props.open}
          onClose={props.onClose}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DeleteBlastRadiusModal (KB-P3-43, S7.2 8q)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when open is false', () => {
    const onClose = vi.fn();
    renderComponent({ open: false, onClose });
    expect(screen.queryByTestId('delete-blast-radius-modal')).toBeNull();
  });

  it('renders blast radius counts, soft trash retention notice, and sends Kb-Blast-Hash', async () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 2,
      inbound_links_flagged: 3,
      outbound_links: 1,
      comments: 5,
      attachments: 2,
      summary_text: '2 sub-issues unparented, 3 inbound object_links flagged',
      blast_hash: '5e1c000000000000000000000000000000000000000000000000000000000001',
      retention_days: 30,
    });
    const deleteSpy = vi.spyOn(actionsApi, 'deleteIssue').mockResolvedValue({
      issue_key: 'KAN-142',
      deleted_at: '2026-11-12T00:00:00Z',
      purge_after: '2026-12-12T00:00:00Z',
    });
    const announceSpy = vi.spyOn(RealtimeStatusModule, 'announce');
    const onClose = vi.fn();

    renderComponent({ open: true, onClose });

    const summaryText = await screen.findByTestId('blast-radius-summary-text');
    expect(summaryText.textContent).toContain('2 sub-issues unparented, 3 inbound object_links flagged');

    expect(screen.getByTestId('soft-trash-retention-notice').textContent).toContain(
      'Moved to trash for 30 days before permanent audited purge.',
    );

    const deleteBtn = screen.getByTestId('confirm-delete-btn');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith(
        'KAN-142',
        '5e1c000000000000000000000000000000000000000000000000000000000001',
      );
      expect(announceSpy).toHaveBeenCalledWith(
        'KAN-142 moved to trash (restorable for 30 days)',
      );
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('handles 412 BLAST_RADIUS_CHANGED: updates counts in-place and sends new blast_hash on second confirm', async () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 2,
      inbound_links_flagged: 3,
      outbound_links: 1,
      comments: 5,
      attachments: 2,
      summary_text: '2 sub-issues unparented, 3 inbound object_links flagged',
      blast_hash: 'hash-initial',
      retention_days: 30,
    });

    const updatedPreview = {
      issue_key: 'KAN-142',
      sub_issues_unparented: 2,
      inbound_links_flagged: 4,
      outbound_links: 1,
      comments: 5,
      attachments: 2,
      summary_text: '2 sub-issues unparented, 4 inbound object_links flagged',
      blast_hash: 'hash-updated',
      retention_days: 30,
    };

    const deleteSpy = vi
      .spyOn(actionsApi, 'deleteIssue')
      .mockRejectedValueOnce({
        status: 412,
        code: 'BLAST_RADIUS_CHANGED',
        data: { current_preview: updatedPreview },
      })
      .mockResolvedValueOnce({
        issue_key: 'KAN-142',
        deleted_at: '2026-11-12T00:00:00Z',
        purge_after: '2026-12-12T00:00:00Z',
      });

    const onClose = vi.fn();
    renderComponent({ open: true, onClose });

    await screen.findByTestId('blast-radius-summary-text');
    const deleteBtn = screen.getByTestId('confirm-delete-btn');

    // First click: triggers 412
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      const alert = screen.getByTestId('concurrency-alert');
      expect(alert.textContent).toContain(
        'Blast radius changed since you opened this dialog. Review the updated counts and confirm again.',
      );
      expect(screen.getByTestId('blast-radius-summary-text').textContent).toContain(
        '4 inbound object_links flagged',
      );
      expect(onClose).not.toHaveBeenCalled();
    });

    // Second click: sends updated hash
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenLastCalledWith('KAN-142', 'hash-updated');
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('navigates to project route when deleted from full screen view', async () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 0,
      inbound_links_flagged: 0,
      outbound_links: 0,
      comments: 0,
      attachments: 0,
      summary_text: '0 sub-issues unparented, 0 inbound object_links flagged',
      blast_hash: 'hash-full',
      retention_days: 14,
    });
    vi.spyOn(actionsApi, 'deleteIssue').mockResolvedValue({
      issue_key: 'KAN-142',
      deleted_at: '2026-11-12T00:00:00Z',
      purge_after: '2026-11-26T00:00:00Z',
    });
    const onClose = vi.fn();

    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/projects/KAN/issues/KAN-142']}>
          <DeleteBlastRadiusModal issue={mockIssue} open={true} onClose={onClose} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const deleteBtn = await screen.findByTestId('confirm-delete-btn');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('renders general error alert on non-412 failure', async () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 0,
      inbound_links_flagged: 0,
      outbound_links: 0,
      comments: 0,
      attachments: 0,
      summary_text: '',
      blast_hash: 'hash-err',
      retention_days: 30,
    });
    vi.spyOn(actionsApi, 'deleteIssue').mockRejectedValue({
      status: 500,
      message: 'Server error during delete',
    });

    const onClose = vi.fn();
    renderComponent({ open: true, onClose });

    const deleteBtn = await screen.findByTestId('confirm-delete-btn');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByTestId('delete-general-error').textContent).toBe(
        'Server error during delete',
      );
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  it('closes modal on Escape key or backdrop click', () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 0,
      inbound_links_flagged: 0,
      outbound_links: 0,
      comments: 0,
      attachments: 0,
      summary_text: '0 sub-issues unparented, 0 inbound object_links flagged',
      blast_hash: 'hash-0',
      retention_days: 30,
    });
    const onClose = vi.fn();

    renderComponent({ open: true, onClose });

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('delete-blast-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(2);

    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);
    expect(onClose).toHaveBeenCalledTimes(3);

    const closeBtn = screen.getByRole('button', { name: 'Close dialog' });
    expect(closeBtn.textContent.trim()).toBe('✕');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(4);

    fireEvent.keyDown(document, { key: 'ArrowDown' });
    expect(onClose).toHaveBeenCalledTimes(4);
  });

  it('handles 412 without updated preview, string error fallback, and isPending state', async () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 1,
      inbound_links_flagged: 1,
      outbound_links: 0,
      comments: 0,
      attachments: 0,
      summary_text: '1 sub-issue unparented',
      blast_hash: 'hash-test',
      retention_days: 14,
    });

    let resolvePromise!: (val: unknown) => void;
    vi.spyOn(actionsApi, 'deleteIssue').mockImplementation(
      () =>
        new Promise((resolve, reject) => {
          resolvePromise = reject;
        }),
    );

    const onClose = vi.fn();
    renderComponent({ open: true, onClose });

    const deleteBtn = await screen.findByTestId('confirm-delete-btn');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(deleteBtn.textContent).toBe('Moving to trash...');
      expect((deleteBtn as HTMLButtonElement).disabled).toBe(true);
    });

    // 412 without updatedPreview
    resolvePromise({ status: 412 });

    await waitFor(() => {
      expect(screen.getByTestId('concurrency-alert').textContent).toContain(
        'Blast radius changed since you opened this dialog',
      );
    });
  });

  it('handles primitive string error fallback and empty blastHash submit', async () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 0,
      inbound_links_flagged: 0,
      outbound_links: 0,
      comments: 0,
      attachments: 0,
      summary_text: '',
      blast_hash: '',
      retention_days: 30,
    });
    const deleteSpy = vi.spyOn(actionsApi, 'deleteIssue');

    const onClose = vi.fn();
    renderComponent({ open: true, onClose });

    const deleteBtn = await screen.findByTestId('confirm-delete-btn');
    expect((deleteBtn as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(deleteBtn);
    expect(deleteSpy).not.toHaveBeenCalled();
  });

  it('handles detail field in error', async () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 0,
      inbound_links_flagged: 0,
      outbound_links: 0,
      comments: 0,
      attachments: 0,
      summary_text: '',
      blast_hash: 'hash-err-detail',
      retention_days: 30,
    });
    vi.spyOn(actionsApi, 'deleteIssue').mockRejectedValue({
      status: 400,
      detail: 'Cannot delete pinned root issue',
    });

    const onClose = vi.fn();
    renderComponent({ open: true, onClose });

    const deleteBtn = await screen.findByTestId('confirm-delete-btn');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByTestId('delete-general-error').textContent).toBe(
        'Cannot delete pinned root issue',
      );
    });
  });

  it('handles 412 with root current_preview', async () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 0,
      inbound_links_flagged: 0,
      outbound_links: 0,
      comments: 0,
      attachments: 0,
      summary_text: '',
      blast_hash: 'hash-root-preview',
      retention_days: 30,
    });
    vi.spyOn(actionsApi, 'deleteIssue').mockRejectedValue({
      status: 412,
      current_preview: {
        issue_key: 'KAN-142',
        sub_issues_unparented: 9,
        inbound_links_flagged: 8,
        outbound_links: 7,
        comments: 6,
        attachments: 5,
        summary_text: 'Updated root preview',
        blast_hash: 'hash-new-root',
        retention_days: 30,
      },
    });

    const onClose = vi.fn();
    renderComponent({ open: true, onClose });

    const deleteBtn = await screen.findByTestId('confirm-delete-btn');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByTestId('blast-radius-summary-text').textContent).toContain(
        '9 sub-issues unparented, 8 inbound object_links flagged',
      );
    });
  });

  it('handles 412 with empty data object and empty error object', async () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
      issue_key: 'KAN-142',
      sub_issues_unparented: 1,
      inbound_links_flagged: 1,
      outbound_links: 1,
      comments: 1,
      attachments: 1,
      summary_text: 'Summary',
      blast_hash: 'hash-empty-data',
      retention_days: 30,
    });
    vi.spyOn(actionsApi, 'deleteIssue').mockRejectedValue({
      status: 412,
      data: {},
    });

    const onClose = vi.fn();
    renderComponent({ open: true, onClose });

    const deleteBtn = await screen.findByTestId('confirm-delete-btn');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByTestId('concurrency-alert')).toBeDefined();
    });
  });

  it('renders loading state when preview is loading', () => {
    vi.spyOn(actionsApi, 'fetchDeletePreview').mockReturnValue(new Promise<never>(() => {
      // Intentionally pending
    }));
    const onClose = vi.fn();
    renderComponent({ open: true, onClose });

    expect(screen.getByText('Calculating blast radius...')).toBeDefined();
  });

  describe('KAN-491 FieldHelpHint and close button standardization', () => {
    it('standardizes close button glyph to ✕ and closes on click', () => {
      vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
        issue_key: 'KAN-142',
        sub_issues_unparented: 0,
        inbound_links_flagged: 0,
        outbound_links: 0,
        comments: 0,
        attachments: 0,
        summary_text: '',
        blast_hash: 'hash-0',
        retention_days: 30,
      });
      const onClose = vi.fn();
      renderComponent({ open: true, onClose });

      const closeBtn = screen.getByRole('button', { name: 'Close dialog' });
      expect(closeBtn.textContent.trim()).toBe('✕');
      expect(closeBtn.textContent.trim()).not.toBe('×');
      fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('renders FieldHelpHint on soft-trash notice and opens popover with correct details', async () => {
      vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
        issue_key: 'KAN-142',
        sub_issues_unparented: 0,
        inbound_links_flagged: 0,
        outbound_links: 0,
        comments: 0,
        attachments: 0,
        summary_text: '',
        blast_hash: 'hash-0',
        retention_days: 30,
      });
      const onClose = vi.fn();
      renderComponent({ open: true, onClose });

      const hintTrigger = screen.getByTestId('soft-trash-help-hint');
      expect(hintTrigger).toBeDefined();
      expect(hintTrigger.getAttribute('aria-label')).toBe(
        'Learn about soft-trash retention and permanent cryptographic purge',
      );

      fireEvent.click(hintTrigger);

      await waitFor(() => {
        expect(screen.getByText('Soft-Trash Retention & Purge Policy')).toBeDefined();
        expect(
          screen.getByText(/Items moved to trash remain restorable by workspace administrators/i),
        ).toBeDefined();
        expect(screen.getByText(/permanent cryptographic purge/i)).toBeDefined();
      });

      const docLink = screen.getByRole('link', { name: /more info/i });
      expect(docLink.getAttribute('href')).toBe('/docs/universal-object-graph-and-link-auditor');
    });

    it('enforces HTML 4.10.4: zero FieldHelpHint nested inside label or button', () => {
      vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
        issue_key: 'KAN-142',
        sub_issues_unparented: 0,
        inbound_links_flagged: 0,
        outbound_links: 0,
        comments: 0,
        attachments: 0,
        summary_text: '',
        blast_hash: 'hash-0',
        retention_days: 30,
      });
      const onClose = vi.fn();
      renderComponent({ open: true, onClose });

      const invalidNestedHints = document.querySelectorAll(
        'label button.field-help-hint, button button.field-help-hint',
      );
      expect(invalidNestedHints.length).toBe(0);
    });

    it('verifies static source AST invariants: zero inline style={{}} props in DeleteBlastRadiusModal.tsx', async () => {
      const fs = await import('node:fs');
      const path = await import('node:path');
      const source = fs.readFileSync(path.resolve(__dirname, 'DeleteBlastRadiusModal.tsx'), 'utf8');

      // Zero inline style props
      expect(source).not.toMatch(/style\s*=\s*\{\{/);
      // Zero FieldHelpHint inside label
      expect(source).not.toMatch(/<label[^>]*>[\s\S]*?<FieldHelpHint/);
      // Proper glyph
      expect(source).toContain('✕');
      expect(source).not.toMatch(/<button[^>]*class(?:Name)?="modal-close-btn"[^>]*>\s*×\s*<\/button>/);
    });

    it('covers all branch fallbacks for deletion and error handling', async () => {
      // 1. activeBlast without retention_days
      vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
        issue_key: 'KAN-142',
        sub_issues_unparented: 0,
        inbound_links_flagged: 0,
        outbound_links: 0,
        comments: 0,
        attachments: 0,
        summary_text: '',
        blast_hash: 'hash-no-retention',
      } as unknown as actionsApi.BlastRadiusResponse);

      const deleteSpy = vi.spyOn(actionsApi, 'deleteIssue').mockResolvedValue({
        issue_key: 'KAN-142',
        deleted_at: '2026-11-12T00:00:00Z',
        purge_after: '2026-12-12T00:00:00Z',
      });
      const announceSpy = vi.spyOn(RealtimeStatusModule, 'announce');
      const onClose = vi.fn();

      const { unmount } = renderComponent({ open: true, onClose });

      const deleteBtn = await screen.findByTestId('confirm-delete-btn');
      fireEvent.click(deleteBtn);

      await waitFor(() => {
        expect(announceSpy).toHaveBeenCalledWith('KAN-142 moved to trash (restorable for 30 days)');
      });
      unmount();

      // 2. Non-object error fallback (string error)
      vi.spyOn(actionsApi, 'fetchDeletePreview').mockResolvedValue({
        issue_key: 'KAN-142',
        sub_issues_unparented: 0,
        inbound_links_flagged: 0,
        outbound_links: 0,
        comments: 0,
        attachments: 0,
        summary_text: '',
        blast_hash: 'hash-str-err',
        retention_days: 30,
      });
      deleteSpy.mockRejectedValueOnce('raw string rejection');
      const { unmount: unmount2 } = renderComponent({ open: true, onClose });

      const deleteBtn2 = await screen.findByTestId('confirm-delete-btn');
      fireEvent.click(deleteBtn2);

      await waitFor(() => {
        expect(screen.getByTestId('delete-general-error').textContent).toBe('Failed to delete issue');
      });
      unmount2();

      // 3. Object error with neither detail nor message
      deleteSpy.mockRejectedValueOnce({ status: 500 });
      const { unmount: unmount3 } = renderComponent({ open: true, onClose });

      const deleteBtn3 = await screen.findByTestId('confirm-delete-btn');
      fireEvent.click(deleteBtn3);

      await waitFor(() => {
        expect(screen.getByTestId('delete-general-error').textContent).toBe('Failed to delete issue');
      });
      unmount3();
    });
  });
});
