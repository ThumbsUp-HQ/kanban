/**
 * Unit tests for ColorPresetPicker and ColoredPill (KB-P3-AUDIT-23, KAN-505).
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
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
    expect(screen.getByTestId('color-preset-help-hint')).toBeDefined();
    unmount();

    render(<ColorPresetPicker value="#4f46e5" onChange={vi.fn()} testId="plain-id" />);
    expect(screen.getByTestId('plain-id-picker')).toBeDefined();
    expect(screen.getByTestId('plain-id-input')).toBeDefined();
    expect(screen.getByTestId('plain-id-help-hint')).toBeDefined();
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

  it('renders FieldHelpHint with #RRGGBB format guidance, #4f46e5 default value, and wiki docHref', () => {
    render(
      <ColorPresetPicker
        value="#4f46e5"
        onChange={vi.fn()}
        testId="state-color-input"
        label="State Color"
      />
    );

    const hintTrigger = screen.getByTestId('state-color-help-hint');
    expect(hintTrigger).toBeDefined();
    expect(hintTrigger.getAttribute('aria-label')).toBe('Help for State Color Color');

    act(() => {
      hintTrigger.focus();
    });

    const popover = screen.getByTestId('state-color-help-hint-popover');
    expect(popover).toBeDefined();
    expect(popover.textContent).toContain('State Color Color');
    expect(popover.textContent).toContain('#RRGGBB');
    expect(popover.textContent).toContain('12 WCAG-contrast preset hexes');
    expect(popover.textContent).toContain('Custom #RRGGBB hex');

    const defaultSection = screen.getByTestId('state-color-help-hint-default');
    expect(defaultSection.textContent).toContain('#4f46e5 (Indigo)');

    const docLink = screen.getByTestId<HTMLAnchorElement>('state-color-help-hint-doc-link');
    expect(docLink.getAttribute('href')).toBe(
      '/docs/enterprise-whitespace-and-kanban-board#color-presets-and-contrast-standards'
    );
  });

  it('supports custom FieldHelpHint props and hiding hint via showHelpHint=false', () => {
    const { rerender } = render(
      <ColorPresetPicker
        value="#2563eb"
        onChange={vi.fn()}
        testId="custom-help"
        helpTitle="Priority Color Guide"
        helpSummary="Choose an accessible priority color."
        defaultValue="#2563eb (Blue)"
        docHref="/docs/custom-colors#palette"
      />
    );

    const hintTrigger = screen.getByTestId('custom-help-help-hint');
    act(() => {
      hintTrigger.focus();
    });

    const popover = screen.getByTestId('custom-help-help-hint-popover');
    expect(popover.textContent).toContain('Priority Color Guide');
    expect(popover.textContent).toContain('Choose an accessible priority color.');
    expect(popover.textContent).toContain('#2563eb (Blue)');

    const docLink = screen.getByTestId<HTMLAnchorElement>('custom-help-help-hint-doc-link');
    expect(docLink.getAttribute('href')).toBe('/docs/custom-colors#palette');

    rerender(
      <ColorPresetPicker
        value="#2563eb"
        onChange={vi.fn()}
        testId="custom-help"
        showHelpHint={false}
      />
    );

    expect(screen.queryByTestId('custom-help-help-hint')).toBeNull();
  });

  it('verifies preset/hex selection non-regression in Light & Dark themes', () => {
    const handleLightChange = vi.fn();
    const { unmount } = render(
      <div data-theme="light">
        <ColorPresetPicker
          value="#4f46e5"
          onChange={handleLightChange}
          testId="light-picker-input"
          label="Light Theme State"
        />
      </div>
    );

    const lightSelect = screen.getByTestId<HTMLSelectElement>('light-picker-preset-select');
    expect(lightSelect.value).toBe('#4f46e5');
    fireEvent.change(lightSelect, { target: { value: '#059669' } });
    expect(handleLightChange).toHaveBeenCalledWith('#059669');

    const lightHex = screen.getByTestId('light-picker-input');
    fireEvent.change(lightHex, { target: { value: '#dc2626' } });
    expect(handleLightChange).toHaveBeenCalledWith('#dc2626');
    unmount();

    const handleDarkChange = vi.fn();
    render(
      <div data-theme="dark">
        <ColorPresetPicker
          value="#0891b2"
          onChange={handleDarkChange}
          testId="dark-picker-input"
          label="Dark Theme State"
        />
      </div>
    );

    const darkSelect = screen.getByTestId<HTMLSelectElement>('dark-picker-preset-select');
    expect(darkSelect.value).toBe('#0891b2');
    fireEvent.change(darkSelect, { target: { value: '#ea580c' } });
    expect(handleDarkChange).toHaveBeenCalledWith('#ea580c');

    const darkHex = screen.getByTestId('dark-picker-input');
    fireEvent.change(darkHex, { target: { value: '#7c3aed' } });
    expect(handleDarkChange).toHaveBeenCalledWith('#7c3aed');
  });
});
