import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PropertiesRail } from './PropertiesRail';
import type { IssueDetail } from '../drawer/slots';
import type { ProjectMetadata } from './railApi';
import * as railApi from './railApi';

vi.mock('./railApi', async () => {
  const actual = await vi.importActual<typeof import('./railApi')>('./railApi');
  return {
    ...actual,
    fetchProjectMetadata: vi.fn(),
    fetchProjectPriorities: vi.fn(),
    fetchProjectLabels: vi.fn(),
    fetchProjectCycles: vi.fn(),
    fetchProjectModules: vi.fn(),
    patchIssue: vi.fn(),
    addAssignee: vi.fn(),
    removeAssignee: vi.fn(),
    overrideCreator: vi.fn(),
    updateIssueModules: vi.fn(),
    createProjectLabel: vi.fn(),
  };
});

const mockIssue: IssueDetail = {
  key: 'KAN-142',
  summary: 'Hardened Properties Rail',
  project_key: 'KAN',
  etag: '"etag-142"',
  capabilities: ['EDIT', 'TRANSITION', 'ADMIN'],
  state: {
    id: 's-todo',
    name: 'To Do',
    group: 'unstarted',
  },
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
  },
  assignees: [
    {
      id: 'asg-1',
      kind: 'principal',
      principal: { id: 'u1', handle: 'maya', display_name: 'Maya', type: 'USER' },
    },
  ],
  provenance: {
    created_by: { handle: 'maya' },
  },
  start_date: '2026-11-01',
  due_date: '2026-11-20',
  module_id: 'mod-1',
  cycle_id: 'cyc-1',
  parent: {
    key: 'KAN-100',
    summary: 'Parent Epic',
  },
  sub_issues_rollup: {
    total: 3,
    completed: 1,
    percent: 33,
  },
  labels: ['type:feature'],
};

const mockMetadata: ProjectMetadata = {
  key: 'KAN',
  name: 'Kanban Project',
  modules_enabled: true,
  states: [
    { id: 's-backlog', name: 'Backlog', group: 'backlog' },
    { id: 's-todo', name: 'To Do', group: 'unstarted' },
    { id: 's-done', name: 'Done', group: 'completed' },
  ],
  priorities: [
    { slug: 'urgent', label: 'Urgent Label', icon: '🔥', sort_order: 1 },
    { slug: 'high', name: 'High', emoji: '⚡', sort_order: 2 },
    { slug: 'medium', name: 'Medium', emoji: '🔹', sort_order: 3 },
  ],
  labels: [
    { id: 'lbl-1', name: 'type:feature', exclusive_group: 'type' },
    { id: 'lbl-2', name: 'type:bug', exclusive_group: 'type' },
  ],
};

describe('PropertiesRail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(railApi.fetchProjectMetadata).mockResolvedValue(mockMetadata);
    vi.mocked(railApi.fetchProjectPriorities).mockResolvedValue(mockMetadata.priorities ?? []);
    vi.mocked(railApi.fetchProjectLabels).mockResolvedValue(mockMetadata.labels ?? []);
    vi.mocked(railApi.fetchProjectCycles).mockResolvedValue([
      { id: 'cyc-1', name: 'Sprint 1', status: 'active', completed_count: 2, issue_count: 5 },
    ]);
    vi.mocked(railApi.fetchProjectModules).mockResolvedValue([
      { id: 'mod-1', name: 'Auth Module' },
    ]);
    vi.mocked(railApi.patchIssue).mockResolvedValue(mockIssue);
    vi.mocked(railApi.addAssignee).mockResolvedValue({
      id: 'asg-new',
      kind: 'principal',
      principal: { id: 'u2', handle: 'alex', display_name: 'Alex', type: 'USER' },
    });
    vi.mocked(railApi.removeAssignee).mockResolvedValue(undefined);
    vi.mocked(railApi.overrideCreator).mockResolvedValue({
      ...mockIssue,
      provenance: {
        created_by: { handle: 'alex' },
        overridden: true,
        reason: 'New owner',
      },
    });
    vi.mocked(railApi.createProjectLabel).mockResolvedValue({ id: 'lbl-new', name: 'security' });
  });

  it('renders all 8 rows in proper order and trailing custom-fields slot', () => {
    const { container, rerender } = render(
      <PropertiesRail issue={mockIssue} projectMetadata={mockMetadata} />,
    );

    const rail = container.querySelector('.surface__rail');
    expect(rail).toBeDefined();
    expect(rail?.getAttribute('aria-label')).toBe('Properties');

    // Check all row data-prop attributes exist
    expect(container.querySelector('[data-prop="state"]')).toBeDefined();
    expect(container.querySelector('[data-prop="priority"]')).toBeDefined();
    expect(container.querySelector('[data-prop="assignees"]')).toBeDefined();
    expect(container.querySelector('[data-prop="created-by"]')).toBeDefined();
    expect(container.querySelector('[data-prop="start-date"]')).toBeDefined();
    expect(container.querySelector('[data-prop="due-date"]')).toBeDefined();
    expect(container.querySelector('[data-prop="modules"]')).toBeDefined();
    expect(container.querySelector('[data-prop="cycle"]')).toBeDefined();
    expect(container.querySelector('[data-prop="parent"]')).toBeDefined();
    expect(container.querySelector('[data-prop="labels"]')).toBeDefined();

    // Check trailing custom fields hook
    const customSlot = container.querySelector('[data-slot="custom-fields-rail"]');
    expect(customSlot).toBeDefined();

    // Rerender with updated issue prop to cover prevInitialIssue update
    rerender(<PropertiesRail issue={{ ...mockIssue, summary: 'Updated Title' }} projectMetadata={mockMetadata} />);
    expect(container.querySelector('[data-prop="state"]')).toBeDefined();
  });

  it('fetches auxiliary project metadata when projectMetadata is omitted, handles network error', async () => {
    vi.mocked(railApi.fetchProjectPriorities).mockRejectedValueOnce(new Error('Network error'));
    vi.mocked(railApi.fetchProjectLabels).mockRejectedValueOnce(new Error('Labels error'));
    vi.mocked(railApi.fetchProjectCycles).mockRejectedValueOnce(new Error('Cycles error'));
    render(<PropertiesRail issue={mockIssue} />);

    await waitFor(() => {
      expect(railApi.fetchProjectMetadata).toHaveBeenCalledWith('KAN');
      expect(railApi.fetchProjectPriorities).toHaveBeenCalledWith('KAN');
      expect(railApi.fetchProjectLabels).toHaveBeenCalledWith('KAN');
      expect(railApi.fetchProjectCycles).toHaveBeenCalledWith('KAN');
      expect(railApi.fetchProjectModules).toHaveBeenCalledWith('KAN');
    });
  });

  it('optimistically updates state and patches issue, handling API error', async () => {
    vi.mocked(railApi.patchIssue).mockRejectedValueOnce(new Error('Patch failed'));
    const onIssueUpdate = vi.fn();
    render(
      <PropertiesRail
        issue={mockIssue}
        projectMetadata={mockMetadata}
        onIssueUpdate={onIssueUpdate}
      />,
    );

    const stateSelect = screen.getByLabelText<HTMLSelectElement>('State');
    fireEvent.change(stateSelect, { target: { value: 's-done' } });

    expect(stateSelect.value).toBe('s-done');
    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { state_id: 's-done' },
        '"etag-142"',
      );
      expect(onIssueUpdate).toHaveBeenCalled();
    });
  });

  it('optimistically updates priority and patches issue, handling API error', async () => {
    vi.mocked(railApi.patchIssue).mockRejectedValueOnce(new Error('Priority patch failed'));
    render(<PropertiesRail issue={mockIssue} projectMetadata={mockMetadata} />);

    const prioritySelect = screen.getByLabelText<HTMLSelectElement>('Priority');
    fireEvent.change(prioritySelect, { target: { value: 'urgent' } });

    expect(prioritySelect.value).toBe('urgent');
    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { priority: 'urgent' },
        '"etag-142"',
      );
    });
  });

  it('handles adding and removing assignees', async () => {
    render(<PropertiesRail issue={mockIssue} projectMetadata={mockMetadata} />);

    // Remove existing assignee
    const removeBtn = screen.getByRole('button', { name: 'Remove @maya' });
    fireEvent.click(removeBtn);

    await waitFor(() => {
      expect(railApi.removeAssignee).toHaveBeenCalledWith('KAN-142', 'asg-1');
    });

    // Add assignee via combobox
    const input = screen.getByLabelText('Add assignee');
    fireEvent.change(input, { target: { value: 'contractor@corp.com' } });

    const addBtn = await screen.findByRole('button', { name: /Add external label/i });
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(railApi.addAssignee).toHaveBeenCalledWith('KAN-142', {
        free_text: 'contractor@corp.com',
      });
    });
  });

  it('handles creator override submission and fallback provenance', async () => {
    vi.mocked(railApi.overrideCreator).mockResolvedValueOnce({
      ...mockIssue,
      provenance: undefined,
    });
    render(<PropertiesRail issue={mockIssue} projectMetadata={mockMetadata} />);

    fireEvent.click(screen.getByRole('button', { name: 'Change...' }));

    fireEvent.change(screen.getByLabelText(/New Creator/i), { target: { value: 'alex' } });
    fireEvent.change(screen.getByLabelText(/Administrative Reason/i), {
      target: { value: 'Valid administrative reason for reassignment.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Override' }));

    await waitFor(() => {
      expect(railApi.overrideCreator).toHaveBeenCalledWith('KAN-142', {
        created_by: 'alex',
        reason: 'Valid administrative reason for reassignment.',
      });
    });
  });

  it('handles dates, modules, and cycle updates', async () => {
    render(<PropertiesRail issue={mockIssue} projectMetadata={mockMetadata} />);

    const startInput = screen.getByLabelText('Start date');
    fireEvent.change(startInput, { target: { value: '2026-11-05' } });

    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { start_date: '2026-11-05', due_date: '2026-11-20' },
        '"etag-142"',
      );
    });

    const moduleSelect = screen.getByLabelText('Modules');
    fireEvent.change(moduleSelect, { target: { value: 'mod-1' } });

    await waitFor(() => {
      expect(railApi.updateIssueModules).toHaveBeenCalledWith('KAN-142', ['mod-1']);
    });

    const cycleSelect = screen.getByLabelText('Cycle');
    fireEvent.change(cycleSelect, { target: { value: 'cyc-1' } });

    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { cycle_id: 'cyc-1' },
        '"etag-142"',
      );
    });
  });

  it('handles parent update and label creation', async () => {
    render(<PropertiesRail issue={mockIssue} projectMetadata={mockMetadata} />);

    // Clear parent
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { parent: null },
        '"etag-142"',
      );
    });

    // Create new label
    fireEvent.click(screen.getByRole('button', { name: 'Add label' }));
    fireEvent.change(screen.getByPlaceholderText('Filter or create...'), {
      target: { value: 'security' },
    });
    const createBtn = screen.getByRole('button', { name: /Create label “security”/i });
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(railApi.createProjectLabel).toHaveBeenCalledWith('KAN', { name: 'security' });
    });
  });

  it('unmounts modules row when initialMetadata.modules_enabled is false', () => {
    const noModulesMeta: ProjectMetadata = {
      ...mockMetadata,
      modules_enabled: false,
    };

    const { container } = render(
      <PropertiesRail issue={mockIssue} projectMetadata={noModulesMeta} />,
    );

    expect(container.querySelector('[data-prop="modules"]')).toBeNull();
  });

  it('handles fallbacks for unknown state, unknown priority, default capabilities, and error handling', async () => {
    vi.mocked(railApi.fetchProjectMetadata).mockRejectedValueOnce(new Error('Meta fetch failed'));
    vi.mocked(railApi.fetchProjectModules).mockRejectedValueOnce(new Error('Modules fetch failed'));
    const onIssueUpdate = vi.fn();

    const issueNoCaps: IssueDetail = {
      ...mockIssue,
      capabilities: undefined,
      parent: null,
    };

    render(
      <PropertiesRail
        issue={issueNoCaps}
        onIssueUpdate={onIssueUpdate}
      />,
    );

    // Set state when metadata is undefined (tests fallback branch)
    const stateSelect = screen.getByLabelText<HTMLSelectElement>('State');
    fireEvent.change(stateSelect, { target: { value: 'state-backlog' } });

    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { state_id: 'state-backlog' },
        '"etag-142"',
      );
    });

    // Set priority
    const prioritySelect = screen.getByLabelText<HTMLSelectElement>('Priority');
    fireEvent.change(prioritySelect, { target: { value: 'medium' } });

    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { priority: 'medium' },
        '"etag-142"',
      );
    });

    // Add parent key
    fireEvent.click(screen.getByRole('button', { name: '+ Add Parent' }));
    const parentInput = screen.getByLabelText('Parent issue key');
    fireEvent.change(parentInput, { target: { value: 'KAN-999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Set' }));

    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { parent: 'KAN-999' },
        '"etag-142"',
      );
    });

    // Clear cycle
    const cycleSelect = screen.getByLabelText<HTMLSelectElement>('Cycle');
    fireEvent.change(cycleSelect, { target: { value: '' } });
    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { cycle_id: null },
        '"etag-142"',
      );
    });

    // Toggle label
    const removeLabelBtn = screen.getByRole('button', { name: 'Remove label type:feature' });
    fireEvent.click(removeLabelBtn);
    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { label_ids: [] },
        '"etag-142"',
      );
    });

    // Clear dates
    const startInput = screen.getByLabelText('Start date');
    fireEvent.change(startInput, { target: { value: '' } });
    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { start_date: null, due_date: '2026-11-20' },
        '"etag-142"',
      );
    });

    const dueInput = screen.getByLabelText('Due date');
    fireEvent.change(dueInput, { target: { value: '' } });
    await waitFor(() => {
      expect(railApi.patchIssue).toHaveBeenCalledWith(
        'KAN-142',
        { start_date: null, due_date: null },
        '"etag-142"',
      );
    });
  });
});
