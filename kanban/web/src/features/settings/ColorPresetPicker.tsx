/**
 * Color Preset Picker and Palette Components (KB-P3-AUDIT-23).
 *
 * Implements 12 WCAG-contrast preset colors, live SVG circle swatches,
 * and advanced color picker synchronization with strict CSP style-src 'self'
 * compliance (zero inline style props).
 */

import React, { type JSX } from 'react';
import './ColorPresetPicker.css';

export interface ColorPreset {
  name: string;
  hex: string;
}

export const COLOR_PRESETS: readonly ColorPreset[] = [
  { name: 'Slate', hex: '#64748b' },
  { name: 'Indigo', hex: '#4f46e5' },
  { name: 'Blue', hex: '#2563eb' },
  { name: 'Cyan', hex: '#0891b2' },
  { name: 'Teal', hex: '#0d9488' },
  { name: 'Emerald', hex: '#059669' },
  { name: 'Amber', hex: '#d97706' },
  { name: 'Orange', hex: '#ea580c' },
  { name: 'Rose', hex: '#e11d48' },
  { name: 'Red', hex: '#dc2626' },
  { name: 'Purple', hex: '#7c3aed' },
  { name: 'Pink', hex: '#db2777' },
] as const;

export function sanitizeHexColor(hex?: string | null, fallback = '#4f46e5'): string {
  if (!hex) return fallback;
  const trimmed = hex.trim();
  return /^#[0-9a-fA-F]{6}$/.test(trimmed) ? trimmed.toLowerCase() : fallback;
}

export function findPresetByHex(hex: string): ColorPreset | undefined {
  const norm = sanitizeHexColor(hex);
  return COLOR_PRESETS.find((p) => p.hex.toLowerCase() === norm);
}

export interface ColorPresetPickerProps {
  value: string;
  onChange: (hex: string) => void;
  label?: string;
  testId?: string;
  disabled?: boolean;
}

export function ColorPresetPicker({
  value,
  onChange,
  label,
  testId,
  disabled = false,
}: ColorPresetPickerProps): JSX.Element {
  const safeHex = sanitizeHexColor(value);
  const matchedPreset = findPresetByHex(value);
  const isCustom = !matchedPreset;

  const baseId = testId
    ? testId.endsWith('-input')
      ? testId.slice(0, -6)
      : testId
    : 'color-preset';
  const hexInputId = testId?.endsWith('-input') ? testId : `${baseId}-input`;
  const selectId = `${baseId}-preset-select`;
  const colorPickerId = `${baseId}-color-picker`;
  const swatchId = `${baseId}-swatch`;

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selected = e.target.value;
    if (selected === 'custom') {
      // Keep existing hex or fallback
      return;
    }
    const found = COLOR_PRESETS.find((p) => p.hex === selected);
    if (found) {
      onChange(found.hex);
    }
  };

  return (
    <div className="kb-color-picker-wrapper" data-testid={`${baseId}-picker`}>
      {label && <span className="kb-input-label">{label}</span>}
      <span className="kb-color-swatch-badge" data-testid={swatchId} title={`Color: ${safeHex}`}>
        <svg
          className="kb-swatch-circle"
          width="14"
          height="14"
          viewBox="0 0 14 14"
          aria-hidden="true"
        >
          <circle cx="7" cy="7" r="6" fill={safeHex} />
        </svg>
      </span>

      <select
        data-testid={selectId}
        className="kb-color-preset-select"
        value={isCustom ? 'custom' : matchedPreset.hex}
        onChange={handleSelectChange}
        disabled={disabled}
        aria-label="Color Presets"
      >
        {COLOR_PRESETS.map((p) => (
          <option key={p.hex} value={p.hex}>
            {p.name} ({p.hex})
          </option>
        ))}
        <option value="custom">Advanced Color Picker...</option>
      </select>

      <input
        type="color"
        data-testid={colorPickerId}
        className="kb-color-native-input"
        value={safeHex}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        disabled={disabled}
        title="Choose custom color"
        aria-label="Custom color picker"
      />

      <input
        type="text"
        data-testid={hexInputId}
        className="kb-color-hex-input"
        placeholder="#RRGGBB"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        disabled={disabled}
        maxLength={7}
        aria-label="Hex color code"
      />
    </div>
  );
}

export interface ColoredPillProps {
  colorHex?: string | null;
  text?: string;
  testId?: string;
}

export function ColoredPill({
  colorHex,
  text,
  testId,
}: ColoredPillProps): JSX.Element {
  const safeHex = sanitizeHexColor(colorHex);
  const matched = findPresetByHex(colorHex ?? '');
  const displayText = text ?? (matched ? matched.name : safeHex);

  return (
    <span className="kb-colored-pill" data-testid={testId} title={`Color: ${safeHex}`}>
      <svg
        className="kb-swatch-circle"
        width="10"
        height="10"
        viewBox="0 0 10 10"
        aria-hidden="true"
      >
        <circle cx="5" cy="5" r="4" fill={safeHex} />
      </svg>
      <span className="kb-colored-pill-text">{displayText}</span>
    </span>
  );
}
