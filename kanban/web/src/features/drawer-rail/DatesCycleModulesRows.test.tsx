import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DatesCycleModulesRows } from './DatesCycleModulesRows';
import type { ProjectModule, ProjectCycle } from './railApi';
import type { IssueDetail } from '../drawer/slots';

const mockModules: ProjectModule[] = [
  { id: 'mod-1', name: 'Auth & Security', status: 'in_progress' },
  { id: 'mod-2', name: 'UI Components', status: 'planned' },
];

const mockCycles: ProjectCycle[] = [
  { id: 'cyc-1', name: 'Sprint 24', status: 'active', completed_count: 5, issue_count: 10 },
  { id: 'cyc-2', name: 'Sprint 25', status: 'upcoming', completed_count: 0, issue_count: 12 },
  { id: 'cyc-3', name: 'Sprint 26' }, // no status, no issue_count
  { id: 'cyc-4', name: 'Sprint 27', issue_count: 5 }, // issue_count present, completed_count undefined
];

const baseIssue: IssueDetail = {
  key: 'KAN-142',
  summary: 'Dates and Modules',
  project_key: 'KAN',
  start_date: '2026-11-01',
  due_date: '2026-11-20',
  module_ids: ['mod-1'],
  cycle_id: 'cyc-1',
};

describe('DatesCycleModulesRows', () => {
  it('renders dates and validates due_date < start_date on mount and on change', () => {
    const onUpdateDates = vi.fn();

    const { rerender } = render(
      <DatesCycleModulesRows
        issue={{
          ...baseIssue,
          start_date: '2026-11-15',
          due_date: '2026-11-10',
        }}
        modulesEnabled={true}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={onUpdateDates}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    expect(screen.getByRole('alert').textContent).toContain('Due date cannot be earlier than start date.');

    // Rerender with valid dates
    rerender(
      <DatesCycleModulesRows
        issue={baseIssue}
        modulesEnabled={true}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={onUpdateDates}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    expect(screen.queryByRole('alert')).toBeNull();

    // Change start date to later than due date
    const startInput = screen.getByLabelText('Start date');
    fireEvent.change(startInput, { target: { value: '2026-11-25' } });
    expect(screen.getByRole('alert').textContent).toContain('Due date cannot be earlier than start date.');

    // Change start date to earlier valid date
    fireEvent.change(startInput, { target: { value: '2026-11-05' } });
    expect(onUpdateDates).toHaveBeenCalledWith({ start_date: '2026-11-05', due_date: '2026-11-20' });

    // Change due date to earlier than start date
    const dueInput = screen.getByLabelText('Due date');
    fireEvent.change(dueInput, { target: { value: '2026-10-01' } });
    expect(screen.getByRole('alert').textContent).toContain('Due date cannot be earlier than start date.');

    // Change due date to valid later date
    fireEvent.change(dueInput, { target: { value: '2026-11-30' } });
    expect(onUpdateDates).toHaveBeenCalledWith({ start_date: '2026-11-01', due_date: '2026-11-30' });
  });

  it('renders overdue badge when due_date is in past and state is active', () => {
    render(
      <DatesCycleModulesRows
        issue={{
          ...baseIssue,
          start_date: '2026-01-01',
          due_date: '2026-01-10',
          state: { id: 's-started', name: 'In Progress', group: 'started' },
        }}
        modulesEnabled={true}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={vi.fn()}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    expect(screen.getByText('Overdue')).toBeDefined();
  });

  it('suppresses overdue badge when state group is completed or cancelled', () => {
    const { rerender } = render(
      <DatesCycleModulesRows
        issue={{
          ...baseIssue,
          start_date: '2026-01-01',
          due_date: '2026-01-10',
          state: { id: 's-done', name: 'Done', group: 'completed' },
        }}
        modulesEnabled={true}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={vi.fn()}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    expect(screen.queryByText('Overdue')).toBeNull();

    rerender(
      <DatesCycleModulesRows
        issue={{
          ...baseIssue,
          start_date: '2026-01-01',
          due_date: '2026-01-10',
          state: { id: 's-cancelled', name: 'Cancelled', group: 'cancelled' },
        }}
        modulesEnabled={true}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={vi.fn()}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    expect(screen.queryByText('Overdue')).toBeNull();
  });

  it('enforces S7.2 8f invariant: unmounts Modules row when modulesEnabled is false', () => {
    const { container, rerender } = render(
      <DatesCycleModulesRows
        issue={baseIssue}
        modulesEnabled={false}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={vi.fn()}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    expect(container.querySelector('[data-prop="modules"]')).toBeNull();

    rerender(
      <DatesCycleModulesRows
        issue={baseIssue}
        modulesEnabled={true}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={vi.fn()}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    expect(container.querySelector('[data-prop="modules"]')).not.toBeNull();
  });

  it('triggers onUpdateModules and onUpdateCycle including clearing values', () => {
    const onUpdateModules = vi.fn().mockResolvedValue(undefined);
    const onUpdateCycle = vi.fn().mockResolvedValue(undefined);

    render(
      <DatesCycleModulesRows
        issue={{
          ...baseIssue,
          modules: [{ id: 'mod-1', name: 'Auth' }],
          cycle: { id: 'cyc-3', name: 'Sprint 26' },
        }}
        modulesEnabled={true}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={vi.fn()}
        onUpdateModules={onUpdateModules}
        onUpdateCycle={onUpdateCycle}
      />,
    );

    const moduleSelect = screen.getByLabelText('Modules');
    fireEvent.change(moduleSelect, { target: { value: 'mod-2' } });
    expect(onUpdateModules).toHaveBeenCalledWith(['mod-2']);

    fireEvent.change(moduleSelect, { target: { value: '' } });
    expect(onUpdateModules).toHaveBeenCalledWith([]);

    const cycleSelect = screen.getByLabelText('Cycle');
    fireEvent.change(cycleSelect, { target: { value: 'cyc-2' } });
    expect(onUpdateCycle).toHaveBeenCalledWith('cyc-2');

    fireEvent.change(cycleSelect, { target: { value: '' } });
    expect(onUpdateCycle).toHaveBeenCalledWith(null);
  });

  it('disables inputs when canEdit is false', () => {
    render(
      <DatesCycleModulesRows
        issue={baseIssue}
        modulesEnabled={true}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={false}
        onUpdateDates={vi.fn()}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    expect(screen.getByLabelText<HTMLInputElement>('Start date').disabled).toBe(true);
    expect(screen.getByLabelText<HTMLInputElement>('Due date').disabled).toBe(true);
    expect(screen.getByLabelText<HTMLSelectElement>('Modules').disabled).toBe(true);
    expect(screen.getByLabelText<HTMLSelectElement>('Cycle').disabled).toBe(true);
  });

  it('handles clearing start date, clearing due date, and missing module/cycle fields', () => {
    const onUpdateDates = vi.fn();
    render(
      <DatesCycleModulesRows
        issue={{
          ...baseIssue,
          start_date: '2026-11-01',
          due_date: '2026-11-20',
          module_ids: undefined,
          modules: undefined,
          cycle_id: 'Sprint 24', // match by name
          cycle: undefined,
        }}
        modulesEnabled={true}
        projectModules={[]}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={onUpdateDates}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    const cycleSelect = screen.getByLabelText<HTMLSelectElement>('Cycle');
    expect(cycleSelect.value).toBe('cyc-1');

    const startInput = screen.getByLabelText('Start date');
    fireEvent.change(startInput, { target: { value: '' } });
    expect(onUpdateDates).toHaveBeenCalledWith({ start_date: null, due_date: '2026-11-20' });

    const dueInput = screen.getByLabelText('Due date');
    fireEvent.change(dueInput, { target: { value: '' } });
    expect(onUpdateDates).toHaveBeenCalledWith({ start_date: '2026-11-01', due_date: null });
  });

  it('handles start and due date changes when opposite date is null and cycle from issue.cycle.id', () => {
    const onUpdateDates = vi.fn();
    render(
      <DatesCycleModulesRows
        issue={{
          ...baseIssue,
          start_date: null,
          due_date: null,
          cycle_id: undefined,
          cycle: { id: 'cyc-4', name: 'Sprint 27' },
        }}
        modulesEnabled={true}
        projectModules={mockModules}
        projectCycles={mockCycles}
        canEdit={true}
        onUpdateDates={onUpdateDates}
        onUpdateModules={vi.fn()}
        onUpdateCycle={vi.fn()}
      />,
    );

    const cycleSelect = screen.getByLabelText<HTMLSelectElement>('Cycle');
    expect(cycleSelect.value).toBe('cyc-4');
    expect(screen.getByText(/Sprint 27 \(0\/5\)/)).toBeDefined();

    const startInput = screen.getByLabelText('Start date');
    fireEvent.change(startInput, { target: { value: '2026-11-01' } });
    expect(onUpdateDates).toHaveBeenCalledWith({ start_date: '2026-11-01', due_date: null });

    const dueInput = screen.getByLabelText('Due date');
    fireEvent.change(dueInput, { target: { value: '2026-11-20' } });
    expect(onUpdateDates).toHaveBeenCalledWith({ start_date: null, due_date: '2026-11-20' });
  });
});
