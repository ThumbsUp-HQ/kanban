/**
 * Unit tests for ColorPresetPicker and ColoredPill (KB-P3-AUDIT-23).
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import {
  ColorPresetPicker,
  ColoredPill,
  sanitizeHexColor,
  findPresetByHex,
} from '../ColorPresetPicker';

describe('ColorPresetPicker and Palette Utils', () => {
  it('sanitizes valid and invalid hex codes correctly', () => {
    expect(sanitizeHexColor('#2563eb')).toBe('#2563eb');
    expect(sanitizeHexColor('#FFFFFF')).toBe('#ffffff');
    expect(sanitizeHexColor('  #059669  ')).toBe('#059669');
    expect(sanitizeHexColor('invalid')).toBe('#4f46e5');
    expect(sanitizeHexColor('#12345')).toBe('#4f46e5');
    expect(sanitizeHexColor('')).toBe('#4f46e5');
    expect(sanitizeHexColor(null)).toBe('#4f46e5');
    expect(sanitizeHexColor(undefined)).toBe('#4f46e5');
    expect(sanitizeHexColor('bad', '#dc2626')).toBe('#dc2626');
  });

  it('finds preset by hex code correctly', () => {
    const preset = findPresetByHex('#4f46e5');
    expect(preset).toBeDefined();
    expect(preset?.name).toBe('Indigo');

    const upper = findPresetByHex('#4F46E5');
    expect(upper?.name).toBe('Indigo');

    const notFound = findPresetByHex('#112233');
    expect(notFound).toBeUndefined();
  });

  it('renders with default preset selected and handles change via dropdown', () => {
    const handleChange = vi.fn();
    render(
      <ColorPresetPicker
        value="#2563eb"
        onChange={handleChange}
        testId="state-color-input"
        label="State Color"
      />
    );

    expect(screen.getByText('State Color')).toBeDefined();
    const select = screen.getByTestId<HTMLSelectElement>('state-color-preset-select');
    expect(select.value).toBe('#2563eb');

    // Change to Emerald (#059669)
    fireEvent.change(select, { target: { value: '#059669' } });
    expect(handleChange).toHaveBeenCalledWith('#059669');

    // Selecting 'custom' does not trigger onChange
    handleChange.mockClear();
    fireEvent.change(select, { target: { value: 'custom' } });
    expect(handleChange).not.toHaveBeenCalled();

    // Selecting unknown value does not trigger onChange
    fireEvent.change(select, { target: { value: '#unknown' } });
    expect(handleChange).not.toHaveBeenCalled();
  });

  it('renders custom color and handles text input and color picker changes', () => {
    const handleChange = vi.fn();
    render(
      <ColorPresetPicker
        value="#334455"
        onChange={handleChange}
        testId="custom-color"
      />
    );

    const select = screen.getByTestId<HTMLSelectElement>('custom-color-preset-select');
    expect(select.value).toBe('custom');

    const colorPicker = screen.getByTestId('custom-color-color-picker');
    fireEvent.change(colorPicker, { target: { value: '#dc2626' } });
    expect(handleChange).toHaveBeenCalledWith('#dc2626');

    const hexInput = screen.getByTestId('custom-color-input');
    fireEvent.change(hexInput, { target: { value: '#7c3aed' } });
    expect(handleChange).toHaveBeenCalledWith('#7c3aed');
  });

  it('respects disabled prop across all interactive elements', () => {
    render(
      <ColorPresetPicker
        value="#4f46e5"
        onChange={vi.fn()}
        testId="disabled-test"
        disabled={true}
      />
    );

    expect(screen.getByTestId('disabled-test-preset-select').hasAttribute('disabled')).toBe(true);
    expect(screen.getByTestId('disabled-test-color-picker').hasAttribute('disabled')).toBe(true);
    expect(screen.getByTestId('disabled-test-input').hasAttribute('disabled')).toBe(true);
  });

  it('uses default testId when none is provided and handles testId without -input', () => {
    const { unmount } = render(<ColorPresetPicker value="#4f46e5" onChange={vi.fn()} />);
    expect(screen.getByTestId('color-preset-picker')).toBeDefined();
    unmount();

    render(<ColorPresetPicker value="#4f46e5" onChange={vi.fn()} testId="plain-id" />);
    expect(screen.getByTestId('plain-id-picker')).toBeDefined();
    expect(screen.getByTestId('plain-id-input')).toBeDefined();
  });

  it('renders ColoredPill with custom text, preset fallback, and null fallback', () => {
    const { rerender } = render(
      <ColoredPill colorHex="#4f46e5" testId="pill-1" />
    );
    expect(screen.getByTestId('pill-1').textContent).toContain('Indigo');

    rerender(<ColoredPill colorHex="#112233" testId="pill-1" />);
    expect(screen.getByTestId('pill-1').textContent).toContain('#112233');

    rerender(<ColoredPill colorHex="#059669" text="Custom Status" testId="pill-1" />);
    expect(screen.getByTestId('pill-1').textContent).toContain('Custom Status');

    rerender(<ColoredPill colorHex={null} testId="pill-1" />);
    expect(screen.getByTestId('pill-1').textContent).toContain('Indigo');
  });
});
