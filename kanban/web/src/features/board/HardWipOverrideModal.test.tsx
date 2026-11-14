import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HardWipOverrideModal } from './HardWipOverrideModal.tsx';
import type { BoardWorkflowState } from './boardApi.ts';

const mockState: BoardWorkflowState = {
  id: 'state-1',
  name: 'In Progress',
  group: 'started',
  sort_order: 1,
  wip_hard_limit: 3,
};

describe('HardWipOverrideModal', () => {
  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <HardWipOverrideModal
        isOpen={false}
        state={mockState}
        count={3}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with title, count, and disabled submit button initially', () => {
    render(
      <HardWipOverrideModal
        isOpen={true}
        state={mockState}
        count={3}
        onCancel={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByText('Hard WIP Limit Exceeded')).toBeDefined();
    expect(screen.getByText(/3 \/ 3/)).toBeDefined();

    const submitBtn = screen.getByRole<HTMLButtonElement>('button', { name: /Override & move/i });
    expect(submitBtn.disabled).toBe(true);
  });

  it('enforces 10-char minimum constraint on reason input', () => {
    const onSubmit = vi.fn();
    render(
      <HardWipOverrideModal
        isOpen={true}
        state={mockState}
        count={3}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    const textarea = screen.getByRole('textbox');
    const submitBtn = screen.getByRole<HTMLButtonElement>('button', { name: /Override & move/i });

    // 9 chars -> disabled
    fireEvent.change(textarea, { target: { value: '123456789' } });
    expect(submitBtn.disabled).toBe(true);
    expect(screen.getByText(/requires at least 10 characters/i)).toBeDefined();

    // 10 chars -> enabled
    fireEvent.change(textarea, { target: { value: '1234567890' } });
    expect(submitBtn.disabled).toBe(false);

    // Submit
    fireEvent.click(submitBtn);
    expect(onSubmit).toHaveBeenCalledWith('1234567890');
  });

  it('triggers onCancel when Cancel button is clicked', () => {
    const onCancel = vi.fn();
    render(
      <HardWipOverrideModal
        isOpen={true}
        state={mockState}
        count={3}
        onCancel={onCancel}
        onSubmit={vi.fn()}
      />,
    );

    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('prevents submit when reason is invalid (form submission event)', () => {
    const onSubmit = vi.fn();
    const { container } = render(
      <HardWipOverrideModal
        isOpen={true}
        state={mockState}
        count={3}
        onCancel={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    const form = container.querySelector('form');
    if (form) {
      fireEvent.submit(form);
    }
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
