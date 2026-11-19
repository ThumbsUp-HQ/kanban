import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ShortcutsCheatSheetModal } from './ShortcutsCheatSheetModal';

describe('ShortcutsCheatSheetModal', () => {
  it('does not render when isOpen is false', () => {
    const { container } = render(
      <ShortcutsCheatSheetModal isOpen={false} onClose={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders all shortcut categories and entries when open', () => {
    render(<ShortcutsCheatSheetModal isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(screen.getByText('Keyboard Shortcuts')).toBeDefined();
    expect(screen.getByText('Navigation')).toBeDefined();
    expect(screen.getByText('Board & Work Items')).toBeDefined();
    expect(screen.getByText('Actions')).toBeDefined();

    expect(screen.getByText('Open command palette & hybrid search')).toBeDefined();
    expect(screen.getByText('Toggle sidebar navigation rail')).toBeDefined();
    expect(screen.getByText('Quick create new work item')).toBeDefined();
  });

  it('calls onClose when clicking close button, got it button, or backdrop', () => {
    const onClose = vi.fn();
    render(<ShortcutsCheatSheetModal isOpen={true} onClose={onClose} />);

    fireEvent.click(screen.getByTestId('shortcuts-modal-close-btn'));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'Got it' }));
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByTestId('shortcuts-modal-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it('closes on Escape key press and restores previous focus', () => {
    const trigger = document.createElement('button');
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const onClose = vi.fn();
    const { rerender } = render(
      <ShortcutsCheatSheetModal isOpen={true} onClose={onClose} />,
    );

    fireEvent.keyDown(window, { key: 'Tab' });
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(<ShortcutsCheatSheetModal isOpen={false} onClose={onClose} />);
    expect(document.activeElement).toBe(trigger);
    document.body.removeChild(trigger);
  });
});
