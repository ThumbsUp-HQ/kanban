import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { ColumnConfigurator } from './ColumnConfigurator';
import { getDefaultColumns, type TableColumnId } from './tableColumns';

describe('ColumnConfigurator', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders trigger button with count and opens/closes dialog', () => {
    const defaultCols = getDefaultColumns(true);
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={defaultCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    const trigger = screen.getByRole('button', { name: /Columns/i });
    expect(trigger).toBeDefined();
    expect(trigger.textContent).toContain(`Columns (${String(defaultCols.length)}/12)`);

    // Click trigger opens dialog
    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: /Configure table columns/i });
    expect(dialog).toBeDefined();

    // Click inside dialog keeps it open
    fireEvent.mouseDown(dialog);
    expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();

    // Close button (✕) closes dialog
    const closeBtn = screen.getByRole('button', { name: /Close column configuration/i });
    fireEvent.click(closeBtn);
    expect(screen.queryByRole('dialog', { name: /Configure table columns/i })).toBeNull();

    // Reopen and click outside
    fireEvent.click(trigger);
    expect(screen.getByRole('dialog', { name: /Configure table columns/i })).toBeDefined();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('dialog', { name: /Configure table columns/i })).toBeNull();
  });

  it('keeps locked columns (Key, Summary) disabled and toggles optional columns', () => {
    const defaultCols = getDefaultColumns(true);
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={defaultCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

    // Key and Summary checkboxes must be disabled
    const keyCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: 'Key' });
    const summaryCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: 'Summary' });
    expect(keyCheckbox.disabled).toBe(true);
    expect(summaryCheckbox.disabled).toBe(true);

    // Start date is initially unchecked in defaults; toggle it on
    const startDateCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: 'Start date' });
    expect(startDateCheckbox.checked).toBe(false);

    fireEvent.click(startDateCheckbox);
    expect(onChange).toHaveBeenCalled();
    const call0 = onChange.mock.calls[0];
    expect(call0).toBeDefined();
    const lastCalledWith = call0?.[0] as TableColumnId[];
    expect(lastCalledWith).toContain('start_date');

    // Cycle is initially checked; toggle it off
    const cycleCheckbox = screen.getByRole<HTMLInputElement>('checkbox', { name: 'Cycle' });
    expect(cycleCheckbox.checked).toBe(true);

    fireEvent.click(cycleCheckbox);
    const call1 = onChange.mock.calls[1];
    expect(call1).toBeDefined();
    const secondCall = call1?.[0] as TableColumnId[];
    expect(secondCall).not.toContain('cycle');
  });

  it('reorders columns up and down and persists to localStorage', () => {
    const initialCols: TableColumnId[] = ['key', 'summary', 'state', 'priority', 'assignees', 'due_date'];
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={initialCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

    // Move State down
    const moveStateDownBtn = screen.getByRole<HTMLButtonElement>('button', { name: /Move State down/i });
    expect(moveStateDownBtn.disabled).toBe(false);
    fireEvent.click(moveStateDownBtn);
    expect(onChange).toHaveBeenCalled();

    // Move Due date up (before Assignees)
    const moveDueUpBtn = screen.getByRole<HTMLButtonElement>('button', { name: /Move Due date up/i });
    expect(moveDueUpBtn.disabled).toBe(false);

    fireEvent.click(moveDueUpBtn);
    expect(onChange).toHaveBeenCalled();
  });

  it('resets columns to defaults when Reset defaults is clicked', () => {
    const customCols: TableColumnId[] = ['key', 'summary', 'state'];
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={customCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

    const resetBtn = screen.getByRole('button', { name: /Reset defaults/i });
    fireEvent.click(resetBtn);

    expect(onChange).toHaveBeenCalledWith(getDefaultColumns(true));
  });

  it('unmounts Modules completely when modulesEnabled is false', () => {
    const defaultCols = getDefaultColumns(false);
    const onChange = vi.fn();

    render(
      <ColumnConfigurator
        columns={defaultCols}
        onChange={onChange}
        projectKey="KAN"
        modulesEnabled={false}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Columns/i }));

    // Modules should not be in DOM at all
    expect(screen.queryByLabelText(/Modules/i)).toBeNull();
    const trigger = screen.getByRole('button', { name: /Columns/i });
    expect(trigger.textContent).toContain(`Columns (${String(defaultCols.length)}/11)`);
  });
});
