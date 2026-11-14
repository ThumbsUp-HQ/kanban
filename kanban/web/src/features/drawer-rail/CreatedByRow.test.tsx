import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CreatedByRow } from './CreatedByRow';
import type { IssueDetail } from '../drawer/slots';

const baseIssue: IssueDetail = {
  key: 'KAN-142',
  summary: 'Created By test',
  project_key: 'KAN',
  provenance: { created_by: { handle: 'maya' } },
};

describe('CreatedByRow', () => {
  it('renders read-only creator handle and no override hint when not overridden', () => {
    render(
      <CreatedByRow
        issue={baseIssue}
        isAdmin={false}
        onOverrideCreator={vi.fn()}
      />,
    );

    const handle = screen.getByTestId('creator-handle');
    expect(handle.textContent).toContain('@maya');
    expect(screen.queryByLabelText('Creator overridden')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Change...' })).toBeNull();
  });

  it('renders creator override hint with exact provenance details when overridden', () => {
    const overriddenIssue: IssueDetail = {
      ...baseIssue,
      provenance: {
        created_by: { handle: 'alex' },
        original_created_by: { handle: 'maya' },
        creator_modified_by: { handle: 'admin-sarah' },
        creator_modified_at: '2026-11-12T10:00:00Z',
        reason: 'Correcting ticket author to lead architect',
        overridden: true,
      },
    };

    render(
      <CreatedByRow
        issue={overriddenIssue}
        isAdmin={true}
        onOverrideCreator={vi.fn()}
      />,
    );

    const handle = screen.getByTestId('creator-handle');
    expect(handle.textContent).toContain('@alex');
    expect(screen.getByLabelText('Creator overridden')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Change...' })).toBeDefined();
  });

  it('validates empty user, reason < 10, reason > 500, and allows cancelling', () => {
    render(
      <CreatedByRow
        issue={baseIssue}
        isAdmin={true}
        onOverrideCreator={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Change...' }));

    const userInput = screen.getByLabelText(/New Creator/i);
    const reasonInput = screen.getByLabelText(/Administrative Reason/i);
    const form = screen.getByRole('dialog').querySelector('form');
    if (!form) throw new Error('Form not found');

    // Empty user
    fireEvent.change(userInput, { target: { value: '   ' } });
    fireEvent.submit(form);
    expect(screen.getByRole('alert').textContent).toContain('Please provide a valid user handle or UUID.');

    // Short reason
    fireEvent.change(userInput, { target: { value: 'sarah' } });
    fireEvent.change(reasonInput, { target: { value: 'short' } });
    fireEvent.submit(form);
    expect(screen.getByRole('alert').textContent).toContain('Reason must be at least 10 characters.');

    // Long reason > 500 chars
    fireEvent.change(reasonInput, { target: { value: 'a'.repeat(501) } });
    fireEvent.submit(form);
    expect(screen.getByRole('alert').textContent).toContain('Reason cannot exceed 500 characters.');

    // Cancel modal
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('validates 10-char min reason and calls onOverrideCreator', async () => {
    const onOverrideCreator = vi.fn().mockResolvedValue(undefined);

    render(
      <CreatedByRow
        issue={baseIssue}
        isAdmin={true}
        onOverrideCreator={onOverrideCreator}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Change...' }));

    const userInput = screen.getByLabelText(/New Creator/i);
    const reasonInput = screen.getByLabelText(/Administrative Reason/i);
    const submitBtn = screen.getByRole('button', { name: 'Override' });

    fireEvent.change(userInput, { target: { value: '@sarah' } });
    fireEvent.change(reasonInput, { target: { value: 'Valid justification with at least ten characters.' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(onOverrideCreator).toHaveBeenCalledWith({
        created_by: 'sarah',
        reason: 'Valid justification with at least ten characters.',
      });
    });
  });

  it('displays AAL2 step-up requirement when API returns 403 AAL2_REQUIRED', async () => {
    const onOverrideCreator = vi.fn().mockRejectedValue({
      code: 'AAL2_REQUIRED',
      status: 403,
    });

    render(
      <CreatedByRow
        issue={baseIssue}
        isAdmin={true}
        onOverrideCreator={onOverrideCreator}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Change...' }));

    fireEvent.change(screen.getByLabelText(/New Creator/i), { target: { value: 'sarah' } });
    fireEvent.change(screen.getByLabelText(/Administrative Reason/i), {
      target: { value: 'Valid administrative reason for reassignment.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Override' }));

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert.textContent).toContain(
        'AAL2 second-factor authentication is required to override issue creator.',
      );
    });
  });

  it('displays generic error messages on override failure', async () => {
    const onOverrideCreator = vi
      .fn()
      .mockRejectedValueOnce(new Error('Internal server error'))
      .mockRejectedValueOnce('string error');

    render(
      <CreatedByRow
        issue={baseIssue}
        isAdmin={true}
        onOverrideCreator={onOverrideCreator}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Change...' }));

    fireEvent.change(screen.getByLabelText(/New Creator/i), { target: { value: 'sarah' } });
    fireEvent.change(screen.getByLabelText(/Administrative Reason/i), {
      target: { value: 'Valid administrative reason.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Override' }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Internal server error');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Override' }));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to override creator.');
    });
  });

  it('formats various creator shapes correctly (string with/without @, redacted without label, empty handle, null)', () => {
    const issueWithRedacted: IssueDetail = {
      ...baseIssue,
      provenance: {
        created_by: { redacted: true },
      },
    };

    const { rerender } = render(
      <CreatedByRow issue={issueWithRedacted} isAdmin={false} onOverrideCreator={vi.fn()} />,
    );
    expect(screen.getByTestId('creator-handle').textContent).toContain('1 External Collaborator');

    // String with @
    rerender(
      <CreatedByRow
        issue={{ ...baseIssue, provenance: { created_by: '@alice' as never } }}
        isAdmin={false}
        onOverrideCreator={vi.fn()}
      />,
    );
    expect(screen.getByTestId('creator-handle').textContent).toContain('@alice');

    // String without @
    rerender(
      <CreatedByRow
        issue={{ ...baseIssue, provenance: { created_by: 'bob' as never } }}
        isAdmin={false}
        onOverrideCreator={vi.fn()}
      />,
    );
    expect(screen.getByTestId('creator-handle').textContent).toContain('@bob');

    // Empty handle
    rerender(
      <CreatedByRow
        issue={{ ...baseIssue, provenance: { created_by: { handle: '' } } }}
        isAdmin={false}
        onOverrideCreator={vi.fn()}
      />,
    );
    expect(screen.getByTestId('creator-handle').textContent).toContain('Unknown');

    // Null provenance
    rerender(
      <CreatedByRow
        issue={{ ...baseIssue, provenance: undefined }}
        isAdmin={false}
        onOverrideCreator={vi.fn()}
      />,
    );
    expect(screen.getByTestId('creator-handle').textContent).toContain('Unknown');
  });
});
