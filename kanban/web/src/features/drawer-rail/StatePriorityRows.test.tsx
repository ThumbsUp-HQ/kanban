import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StatePriorityRows } from './StatePriorityRows';
import type { ProjectWorkflowState, ProjectPriority } from './railApi';
import type { IssueDetail } from '../drawer/slots';

const mockStates: ProjectWorkflowState[] = [
  { id: 's-backlog', name: 'Backlog', group: 'backlog' },
  { id: 's-todo', name: 'To Do', group: 'unstarted' },
  { id: 's-inprogress', name: 'In Progress', group: 'started' },
  { id: 's-done', name: 'Done', group: 'completed' },
  { id: 's-cancelled', name: 'Cancelled', group: 'cancelled' },
];

const mockPriorities: ProjectPriority[] = [
  { slug: 'urgent', name: 'Urgent', emoji: '🔥', sort_order: 1 },
  { slug: 'high', name: 'High', emoji: '⚡', sort_order: 2 },
  { slug: 'medium', name: 'Medium', emoji: '🔹', sort_order: 3 },
  { slug: 'low', name: 'Low', emoji: '💤', sort_order: 4 },
];

const baseIssue: IssueDetail = {
  key: 'KAN-142',
  summary: 'Properties Rail',
  project_key: 'KAN',
  state: { id: 's-todo', name: 'To Do', group: 'unstarted' },
  priority: { slug: 'high', label: 'High', emoji: '⚡' },
};

describe('StatePriorityRows', () => {
  it('renders grouped states and triggers onStateChange', () => {
    const onStateChange = vi.fn();
    const onPriorityChange = vi.fn();

    render(
      <StatePriorityRows
        issue={baseIssue}
        projectStates={mockStates}
        projectPriorities={mockPriorities}
        canTransition={true}
        canEdit={true}
        onStateChange={onStateChange}
        onPriorityChange={onPriorityChange}
      />,
    );

    const stateSelect = screen.getByLabelText<HTMLSelectElement>('State');
    expect(stateSelect.value).toBe('s-todo');

    const optgroups = screen.getAllByRole('group');
    expect(optgroups.length).toBeGreaterThanOrEqual(4);

    fireEvent.change(stateSelect, { target: { value: 's-inprogress' } });
    expect(onStateChange).toHaveBeenCalledWith('s-inprogress');
  });

  it('renders priorities with emoji hints and triggers onPriorityChange', () => {
    const onStateChange = vi.fn();
    const onPriorityChange = vi.fn();

    render(
      <StatePriorityRows
        issue={baseIssue}
        projectStates={mockStates}
        projectPriorities={mockPriorities}
        canTransition={true}
        canEdit={true}
        onStateChange={onStateChange}
        onPriorityChange={onPriorityChange}
      />,
    );

    const prioritySelect = screen.getByLabelText<HTMLSelectElement>('Priority');
    expect(prioritySelect.value).toBe('high');

    fireEvent.change(prioritySelect, { target: { value: 'urgent' } });
    expect(onPriorityChange).toHaveBeenCalledWith('urgent');
  });

  it('disables selects when capabilities are missing', () => {
    render(
      <StatePriorityRows
        issue={baseIssue}
        projectStates={mockStates}
        projectPriorities={mockPriorities}
        canTransition={false}
        canEdit={false}
        onStateChange={vi.fn()}
        onPriorityChange={vi.fn()}
      />,
    );

    expect(screen.getByLabelText<HTMLSelectElement>('State').disabled).toBe(true);
    expect(screen.getByLabelText<HTMLSelectElement>('Priority').disabled).toBe(true);
  });

  it('handles fallbacks when projectStates, projectPriorities, state, and priority are missing or have alternative fields', () => {
    const fallbackIssue: IssueDetail = {
      key: 'KAN-142',
      summary: 'Properties Rail',
      project_key: 'KAN',
      state: undefined,
      priority: undefined,
    };

    const prioritiesWithIcon: ProjectPriority[] = [
      { slug: 'custom-prio', label: 'Custom Label', icon: '⭐', sort_order: 1 },
      { slug: 'bare-prio', sort_order: 2 },
    ];

    render(
      <StatePriorityRows
        issue={fallbackIssue}
        projectStates={[]}
        projectPriorities={prioritiesWithIcon}
        canTransition={true}
        canEdit={true}
        onStateChange={vi.fn()}
        onPriorityChange={vi.fn()}
      />,
    );

    const stateSelect = screen.getByLabelText<HTMLSelectElement>('State');
    expect(stateSelect.value).toBe('state-backlog');

    const prioritySelect = screen.getByLabelText<HTMLSelectElement>('Priority');
    expect(prioritySelect.value).toBe('custom-prio');
    expect(screen.queryByLabelText(/Priority:/)).toBeNull();
    expect(screen.getByText('bare-prio')).toBeDefined();
  });
});
