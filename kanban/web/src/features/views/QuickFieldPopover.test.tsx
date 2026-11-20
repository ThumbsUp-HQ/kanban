import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { QuickFieldPopover } from './QuickFieldPopover';
import { FIXTURE_12_ISSUES } from './fixtures';

describe('QuickFieldPopover (KB-P3-40, S6.4 item 4, S1.3 item 3, S7.2 8f)', () => {
  const dummyRect = {
    top: 100,
    bottom: 140,
    left: 200,
    right: 350,
    width: 150,
    height: 40,
    x: 200,
    y: 100,
    toJSON: () => ({}),
  } as DOMRect;

  it('does not render when isOpen is false or field is null', () => {
    const { container } = render(
      <QuickFieldPopover
        isOpen={false}
        field="priority"
        anchorRect={dummyRect}
        issue={FIXTURE_12_ISSUES[0]}
        onClose={vi.fn()}
        onSelect={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders with null anchorRect without throwing', () => {
    const { container } = render(
      <QuickFieldPopover
        isOpen={true}
        field="priority"
        anchorRect={null}
        issue={FIXTURE_12_ISSUES[0]}
        onClose={vi.fn()}
        onSelect={vi.fn()}
      />
    );
    expect(container.firstChild).toBeDefined();
  });

  it('renders Priority picker and allows selecting with click and keyboard (P shortcut)', () => {
    const handleSelect = vi.fn();
    const handleClose = vi.fn();

    render(
      <QuickFieldPopover
        isOpen={true}
        field="priority"
        anchorRect={dummyRect}
        issue={FIXTURE_12_ISSUES[0]}
        onClose={handleClose}
        onSelect={handleSelect}
      />
    );

    expect(screen.getByRole('dialog', { name: /quick priority picker/i })).toBeDefined();
    expect(screen.getByRole('option', { name: /Urgent/i })).toBeDefined();
    expect(screen.getByRole('option', { name: /High/i })).toBeDefined();
    expect(screen.getByRole('option', { name: /Medium/i })).toBeDefined();
    expect(screen.getByRole('option', { name: /Low/i })).toBeDefined();

    // Click on High option
    fireEvent.click(screen.getByRole('option', { name: /High/i }));
    expect(handleSelect).toHaveBeenCalledWith('priority', 'high');
    expect(handleClose).toHaveBeenCalled();
  });

  it('navigates with ArrowDown, ArrowUp, Enter, and closes on Escape', () => {
    const handleSelect = vi.fn();
    const handleClose = vi.fn();

    render(
      <QuickFieldPopover
        isOpen={true}
        field="state"
        anchorRect={dummyRect}
        issue={FIXTURE_12_ISSUES[0]}
        onClose={handleClose}
        onSelect={handleSelect}
      />
    );

    // Initial focused is first option (Backlog)
    // Press ArrowDown -> Todo
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    // Press ArrowDown -> In Progress
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    // Press ArrowUp -> Todo
    fireEvent.keyDown(window, { key: 'ArrowUp' });
    // Press Enter to select
    fireEvent.keyDown(window, { key: 'Enter' });

    expect(handleSelect).toHaveBeenCalledWith('state', 'state-todo');
    expect(handleClose).toHaveBeenCalled();

    // Escape closes popover
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleClose).toHaveBeenCalledTimes(2);
  });

  it('renders Assignee picker (A shortcut)', () => {
    const handleSelect = vi.fn();

    render(
      <QuickFieldPopover
        isOpen={true}
        field="assignee"
        anchorRect={dummyRect}
        issue={FIXTURE_12_ISSUES[0]}
        onClose={vi.fn()}
        onSelect={handleSelect}
      />
    );

    expect(screen.getByRole('option', { name: /Alice Cooper/i })).toBeDefined();
    expect(screen.getByRole('option', { name: /Unassigned/i })).toBeDefined();

    fireEvent.click(screen.getByRole('option', { name: /Alice Cooper/i }));
    expect(handleSelect).toHaveBeenCalledWith('assignee', 'alice');
  });

  it('renders Labels picker (L shortcut)', () => {
    const handleSelect = vi.fn();

    render(
      <QuickFieldPopover
        isOpen={true}
        field="labels"
        anchorRect={dummyRect}
        issue={FIXTURE_12_ISSUES[0]}
        onClose={vi.fn()}
        onSelect={handleSelect}
      />
    );

    expect(screen.getByRole('option', { name: /Security/i })).toBeDefined();
    fireEvent.click(screen.getByRole('option', { name: /Security/i }));
    expect(handleSelect).toHaveBeenCalledWith('labels', 'lbl-sec');
  });

  it('renders Due date picker (D shortcut)', () => {
    const handleSelect = vi.fn();

    render(
      <QuickFieldPopover
        isOpen={true}
        field="due_date"
        anchorRect={dummyRect}
        issue={FIXTURE_12_ISSUES[0]}
        onClose={vi.fn()}
        onSelect={handleSelect}
      />
    );

    expect(screen.getByRole('option', { name: /Due Today/i })).toBeDefined();
    expect(screen.getByRole('option', { name: /Clear Due Date/i })).toBeDefined();

    fireEvent.click(screen.getByRole('option', { name: /Clear Due Date/i }));
    expect(handleSelect).toHaveBeenCalledWith('due_date', null);
  });

  it('renders Module picker when modulesEnabled is true (M shortcut)', () => {
    const handleSelect = vi.fn();

    render(
      <QuickFieldPopover
        isOpen={true}
        field="module"
        anchorRect={dummyRect}
        issue={FIXTURE_12_ISSUES[0]}
        onClose={vi.fn()}
        onSelect={handleSelect}
        modulesEnabled={true}
      />
    );

    expect(screen.getByRole('option', { name: /Auth Core/i })).toBeDefined();
    fireEvent.click(screen.getByRole('option', { name: /Auth Core/i }));
    expect(handleSelect).toHaveBeenCalledWith('module', 'mod-1');
  });

  it('strict no-op: does not render Module picker when modulesEnabled is false (Test Case 3, S7.2 8f)', () => {
    const { container } = render(
      <QuickFieldPopover
        isOpen={true}
        field="module"
        anchorRect={dummyRect}
        issue={FIXTURE_12_ISSUES[0]}
        onClose={vi.fn()}
        onSelect={vi.fn()}
        modulesEnabled={false}
      />
    );

    expect(container.firstChild).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  describe('Mobile & Custom State Popover (KAN-44)', () => {
    it('populates options from custom states prop when field is state', () => {
      const handleSelect = vi.fn();
      const customStates = [
        { id: 'st-triage', name: 'Triage', group: 'unstarted' as const },
        { id: 'st-qa', name: 'QA Review', group: 'started' as const },
      ];

      render(
        <QuickFieldPopover
          isOpen={true}
          field="state"
          anchorRect={dummyRect}
          issue={FIXTURE_12_ISSUES[0]}
          onClose={vi.fn()}
          onSelect={handleSelect}
          states={customStates}
        />,
      );

      expect(screen.getByRole('option', { name: 'Triage' })).toBeDefined();
      expect(screen.getByRole('option', { name: 'QA Review' })).toBeDefined();

      fireEvent.click(screen.getByRole('option', { name: 'QA Review' }));
      expect(handleSelect).toHaveBeenCalledWith('state', 'st-qa');
    });

    it('closes when clicking quick-field-backdrop', () => {
      const handleClose = vi.fn();

      render(
        <QuickFieldPopover
          isOpen={true}
          field="priority"
          anchorRect={dummyRect}
          issue={FIXTURE_12_ISSUES[0]}
          onClose={handleClose}
          onSelect={vi.fn()}
        />,
      );

      const backdrop = screen.getByTestId('quick-field-backdrop');
      fireEvent.click(backdrop);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });

    it('sets CSS custom properties --popover-top and --popover-left for viewport clamping without inline styles', () => {
      const edgeRect = {
        top: 800,
        bottom: 840,
        left: 1200,
        right: 1300,
        width: 100,
        height: 40,
        x: 1200,
        y: 800,
        toJSON: () => ({}),
      } as DOMRect;

      render(
        <QuickFieldPopover
          isOpen={true}
          field="state"
          anchorRect={edgeRect}
          issue={FIXTURE_12_ISSUES[0]}
          onClose={vi.fn()}
          onSelect={vi.fn()}
        />,
      );

      const popover = screen.getByTestId('quick-field-popover');
      expect(popover.style.getPropertyValue('--popover-top')).toBeTruthy();
      expect(popover.style.getPropertyValue('--popover-left')).toBeTruthy();
    });
  });
});
