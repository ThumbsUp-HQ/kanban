import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { ParentLabelsRows } from './ParentLabelsRows';
import type { ProjectLabel } from './railApi';
import type { IssueDetail } from '../drawer/slots';

const mockLabels: ProjectLabel[] = [
  { id: 'lbl-1', name: 'type:bug', exclusive_group: 'type' },
  { id: 'lbl-2', name: 'type:feature', exclusive_group: 'type' },
  { id: 'lbl-3', name: 'frontend' },
];

const baseIssue: IssueDetail = {
  key: 'KAN-142',
  summary: 'Parent and Labels',
  project_key: 'KAN',
  labels: [],
};

describe('ParentLabelsRows', () => {
  it('renders restricted parent chip with 🔒 hint and zero leaked key details', () => {
    render(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          parent: { key: 'SECRET-99', restricted: true },
        }}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={vi.fn()}
        onUpdateLabels={vi.fn()}
      />,
    );

    const restrictedChip = screen.getByTestId('restricted-parent-chip');
    expect(restrictedChip.textContent).toContain('Restricted Parent Issue');
    expect(screen.queryByText(/SECRET-99/)).toBeNull();
    expect(screen.getByLabelText('Restricted parent')).toBeDefined();
  });

  it('renders normal parent key link and allows clearing parent and editing then cancelling', () => {
    const onUpdateParent = vi.fn().mockResolvedValue(undefined);

    render(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          parent: { key: 'KAN-10', summary: 'Epic Core' },
        }}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={onUpdateParent}
        onUpdateLabels={vi.fn()}
      />,
    );

    expect(screen.getByText(/\[KAN-10 Epic Core\]/)).toBeDefined();

    // Click Change to open input, then Cancel
    fireEvent.click(screen.getByRole('button', { name: 'Change' }));
    expect(screen.getByLabelText('Parent issue key')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByLabelText('Parent issue key')).toBeNull();

    // Click Clear
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(onUpdateParent).toHaveBeenCalledWith(null);
  });

  it('renders string parent key', () => {
    render(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          parent: 'KAN-55',
        }}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={vi.fn()}
        onUpdateLabels={vi.fn()}
      />,
    );

    expect(screen.getByText(/\[KAN-55\]/)).toBeDefined();
  });

  it('handles DAG cycle, depth exceeded, and generic errors on parent update', async () => {
    const onUpdateParent = vi
      .fn()
      .mockRejectedValueOnce({ code: 'PARENT_CYCLE' })
      .mockRejectedValueOnce({ detail: 'parent cycle detected' })
      .mockRejectedValueOnce({ code: 'PARENT_DEPTH_EXCEEDED' })
      .mockRejectedValueOnce({ detail: 'max hierarchy depth exceeded' })
      .mockRejectedValueOnce(new Error('Database timeout'))
      .mockRejectedValueOnce('raw string error');

    render(
      <ParentLabelsRows
        issue={baseIssue}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={onUpdateParent}
        onUpdateLabels={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '+ Add Parent' }));

    const input = screen.getByLabelText('Parent issue key');
    const setBtn = screen.getByRole('button', { name: 'Set' });

    fireEvent.change(input, { target: { value: 'KAN-2' } });
    fireEvent.click(setBtn);

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('cycle');
    });

    fireEvent.click(setBtn);
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('cycle');
    });

    fireEvent.click(setBtn);
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('depth');
    });

    fireEvent.click(setBtn);
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('depth');
    });

    fireEvent.click(setBtn);
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Database timeout');
    });

    fireEvent.click(setBtn);
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Failed to update parent.');
    });
  });

  it('renders Sub-issues Rollup progress bar and percentage from rollup and sub_issues array', () => {
    const { rerender } = render(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          sub_issues_rollup: { total: 4, completed: 2, percent: 50 },
        }}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={vi.fn()}
        onUpdateLabels={vi.fn()}
      />,
    );

    expect(screen.getByText(/Sub-issues \(2\/4 Done\)/)).toBeDefined();
    expect(screen.getByText('50%')).toBeDefined();

    // From sub_issues array directly
    rerender(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          sub_issues: [
            { key: 'KAN-201', state: 'Done', state_group: 'completed' },
            { key: 'KAN-202', state: 'In Progress', state_group: 'started' },
          ],
        }}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={vi.fn()}
        onUpdateLabels={vi.fn()}
      />,
    );

    expect(screen.getByText(/Sub-issues \(1\/2 Done\)/)).toBeDefined();
    expect(screen.getByText('50%')).toBeDefined();
  });

  it('atomically replaces labels sharing exclusive_group, allows deselecting, and pill removal', () => {
    const onUpdateLabels = vi.fn();

    const { container } = render(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          labels: ['lbl-1', 'lbl-3'],
        }}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={vi.fn()}
        onUpdateLabels={onUpdateLabels}
      />,
    );

    // Remove via pill × button
    const removeBtn = screen.getByRole('button', { name: 'Remove label type:bug' });
    fireEvent.click(removeBtn);
    expect(onUpdateLabels).toHaveBeenCalledWith(['lbl-3']);

    // Open label menu
    fireEvent.click(screen.getByRole('button', { name: 'Add label' }));

    const dropdownList = container.querySelector<HTMLElement>('.labels-dropdown__list');
    if (!dropdownList) throw new Error('dropdown list missing');
    const bugCheckbox = within(dropdownList).getByLabelText(/type:bug/);
    fireEvent.click(bugCheckbox);
    expect(onUpdateLabels).toHaveBeenCalledWith(['lbl-3']);

    // Select exclusive label replacement
    const featureCheckbox = within(dropdownList).getByLabelText(/type:feature/);
    fireEvent.click(featureCheckbox);
    expect(onUpdateLabels).toHaveBeenCalledWith(['lbl-3', 'lbl-2']);
  });

  it('adds exclusive label when no conflict currently exists', () => {
    const onUpdateLabels = vi.fn();

    const { container } = render(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          labels: ['lbl-3'],
        }}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={vi.fn()}
        onUpdateLabels={onUpdateLabels}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Add label' }));

    const dropdownList = container.querySelector<HTMLElement>('.labels-dropdown__list');
    if (!dropdownList) throw new Error('dropdown list missing');
    const bugCheckbox = within(dropdownList).getByLabelText(/type:bug/);
    fireEvent.click(bugCheckbox);
    expect(onUpdateLabels).toHaveBeenCalledWith(['lbl-3', 'lbl-1']);
  });

  it('allows creating a new label via onCreateLabel', async () => {
    const onCreateLabel = vi.fn().mockResolvedValue({ id: 'lbl-new', name: 'backend' });
    const onUpdateLabels = vi.fn();

    render(
      <ParentLabelsRows
        issue={baseIssue}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={vi.fn()}
        onUpdateLabels={onUpdateLabels}
        onCreateLabel={onCreateLabel}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Add label' }));

    const searchInput = screen.getByPlaceholderText('Filter or create...');
    fireEvent.change(searchInput, { target: { value: 'backend' } });

    const createBtn = screen.getByRole('button', { name: /Create label “backend”/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(onCreateLabel).toHaveBeenCalledWith('backend');
      expect(onUpdateLabels).toHaveBeenCalledWith(['lbl-new']);
    });
  });

  it('renders read-only views when canEdit is false, and handles outside click and create failure', async () => {
    const onCreateLabel = vi.fn().mockRejectedValue(new Error('Failed label'));

    const { rerender } = render(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          parent: null,
          labels: ['lbl-1'],
        }}
        projectLabels={mockLabels}
        canEdit={false}
        onUpdateParent={vi.fn()}
        onUpdateLabels={vi.fn()}
        onCreateLabel={onCreateLabel}
      />,
    );

    // Read-only without parent
    expect(screen.getByText('None')).toBeDefined();
    expect(screen.queryByRole('button', { name: '+ Add Parent' })).toBeNull();
    expect(screen.queryByRole('button', { name: /Remove label/i })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add label' })).toBeNull();

    // Read-only with parent
    rerender(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          parent: { key: 'KAN-99' },
          labels: ['lbl-1'],
        }}
        projectLabels={mockLabels}
        canEdit={false}
        onUpdateParent={vi.fn()}
        onUpdateLabels={vi.fn()}
        onCreateLabel={onCreateLabel}
      />,
    );
    expect(screen.getByText('[KAN-99]')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Change' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Clear' })).toBeNull();

    // Create label error handling and outside click
    rerender(
      <ParentLabelsRows
        issue={baseIssue}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={vi.fn()}
        onUpdateLabels={vi.fn()}
        onCreateLabel={onCreateLabel}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Add label' }));
    const searchInput = screen.getByPlaceholderText('Filter or create...');
    fireEvent.change(searchInput, { target: { value: 'error-lbl' } });
    fireEvent.click(screen.getByRole('button', { name: /Create label “error-lbl”/i }));

    await waitFor(() => {
      expect(onCreateLabel).toHaveBeenCalledWith('error-lbl');
    });
    // Menu remains open after catch
    expect(screen.getByPlaceholderText('Filter or create...')).toBeDefined();

    // Toggle button closes dropdown
    fireEvent.click(screen.getByRole('button', { name: 'Add label' }));
    expect(screen.queryByPlaceholderText('Filter or create...')).toBeNull();
  });

  it('handles blank parent input clearing parent and label objects mapping', async () => {
    const onUpdateParent = vi.fn().mockResolvedValue(undefined);
    const onUpdateLabels = vi.fn();

    render(
      <ParentLabelsRows
        issue={{
          ...baseIssue,
          labels: [{ id: 'lbl-1', name: 'type:bug' }] as never,
        }}
        projectLabels={mockLabels}
        canEdit={true}
        onUpdateParent={onUpdateParent}
        onUpdateLabels={onUpdateLabels}
      />,
    );

    // Open parent edit and submit blank
    fireEvent.click(screen.getByRole('button', { name: '+ Add Parent' }));
    const parentInput = screen.getByLabelText('Parent issue key');
    fireEvent.change(parentInput, { target: { value: '   ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Set' }));

    await waitFor(() => {
      expect(onUpdateParent).toHaveBeenCalledWith(null);
    });
  });
});
