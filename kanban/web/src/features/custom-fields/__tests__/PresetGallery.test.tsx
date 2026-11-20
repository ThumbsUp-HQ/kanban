// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { PresetGallery } from '../PresetGallery';
import { STARTER_PRESETS } from '../presets';

describe('PresetGallery Component (KAN-15, KB-P3-AUDIT-09)', () => {
  it('renders all 6 presets and header with count', () => {
    const handleApply = vi.fn();
    render(<PresetGallery onApplyPreset={handleApply} />);

    expect(screen.getByTestId('preset-gallery-section')).toBeDefined();
    expect(screen.getByText('6 Presets Available')).toBeDefined();

    for (const preset of STARTER_PRESETS) {
      expect(screen.getByTestId(`preset-card-${preset.slug}`)).toBeDefined();
    }
  });

  it('filters presets by flavor using filter bar', () => {
    const handleApply = vi.fn();
    render(<PresetGallery onApplyPreset={handleApply} />);

    // Click WebAssembly filter
    act(() => {
      fireEvent.click(screen.getByTestId('preset-filter-wasm'));
    });

    expect(screen.getByTestId('preset-card-cvss-score')).toBeDefined();
    expect(screen.queryByTestId('preset-card-blocker-count')).toBeNull();

    // Click Formula filter
    act(() => {
      fireEvent.click(screen.getByTestId('preset-filter-formula'));
    });

    expect(screen.getByTestId('preset-card-blocker-count')).toBeDefined();
    expect(screen.queryByTestId('preset-card-cvss-score')).toBeNull();

    // Click All filter
    act(() => {
      fireEvent.click(screen.getByTestId('preset-filter-all'));
    });

    expect(screen.getByTestId('preset-card-cvss-score')).toBeDefined();
    expect(screen.getByTestId('preset-card-blocker-count')).toBeDefined();
  });

  it('applies preset immediately when form is not dirty', () => {
    const handleApply = vi.fn();
    render(<PresetGallery onApplyPreset={handleApply} isDirty={false} />);

    const useBtn = screen.getByTestId('use-preset-btn-cvss-score');
    act(() => {
      fireEvent.click(useBtn);
    });

    expect(handleApply).toHaveBeenCalledTimes(1);
    expect(handleApply).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'cvss-score', slug: 'cvss-score' }),
    );
    expect(screen.queryByTestId('preset-dirty-confirm-dialog')).toBeNull();
  });

  it('opens confirmation dialog on Use Preset when form is dirty', () => {
    const handleApply = vi.fn();
    render(<PresetGallery onApplyPreset={handleApply} isDirty={true} />);

    const useBtn = screen.getByTestId('use-preset-btn-blocker-count');
    act(() => {
      fireEvent.click(useBtn);
    });

    // Confirmation dialog open
    const dialog = screen.getByTestId('preset-dirty-confirm-dialog');
    expect(dialog).toBeDefined();
    expect(screen.getByTestId('preset-dirty-warning-text').textContent).toContain(
      'Blocker Count',
    );
    expect(handleApply).not.toHaveBeenCalled();

    // Cancel overwrite
    const cancelBtn = screen.getByTestId('preset-cancel-overwrite-btn');
    act(() => {
      fireEvent.click(cancelBtn);
    });

    expect(screen.queryByTestId('preset-dirty-confirm-dialog')).toBeNull();
    expect(handleApply).not.toHaveBeenCalled();
  });

  it('applies preset after confirming overwrite when form is dirty', () => {
    const handleApply = vi.fn();
    render(<PresetGallery onApplyPreset={handleApply} isDirty={true} />);

    const useBtn = screen.getByTestId('use-preset-btn-sub-issue-completion');
    act(() => {
      fireEvent.click(useBtn);
    });

    const confirmBtn = screen.getByTestId('preset-confirm-overwrite-btn');
    act(() => {
      fireEvent.click(confirmBtn);
    });

    expect(handleApply).toHaveBeenCalledTimes(1);
    expect(handleApply).toHaveBeenCalledWith(
      expect.objectContaining({ slug: 'sub-issue-completion' }),
    );
    expect(screen.queryByTestId('preset-dirty-confirm-dialog')).toBeNull();
  });

  it('renders undo strip and handles undo and dismiss callbacks', () => {
    const handleApply = vi.fn();
    const handleUndo = vi.fn();
    const handleDismiss = vi.fn();

    render(
      <PresetGallery
        onApplyPreset={handleApply}
        appliedPresetName="Days Until Due / SLA Breach"
        onUndo={handleUndo}
        onDismissUndo={handleDismiss}
      />,
    );

    const undoStrip = screen.getByTestId('preset-undo-strip');
    expect(undoStrip.textContent).toContain('Days Until Due / SLA Breach');

    const undoBtn = screen.getByTestId('preset-undo-btn');
    act(() => {
      fireEvent.click(undoBtn);
    });
    expect(handleUndo).toHaveBeenCalledTimes(1);

    const dismissBtn = screen.getByTestId('preset-dismiss-undo-btn');
    act(() => {
      fireEvent.click(dismissBtn);
    });
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
