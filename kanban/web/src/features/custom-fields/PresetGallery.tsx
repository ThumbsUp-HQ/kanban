// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { useState, type JSX } from 'react';
import { useSystemStatus } from '../../app/useSystemStatus';
import type { FieldFlavor } from './api';
import { STARTER_PRESETS, type CustomFieldPreset } from './presets';

export interface PresetGalleryProps {
  onApplyPreset: (preset: CustomFieldPreset) => void;
  isDirty?: boolean;
  onUndo?: () => void;
  appliedPresetName?: string | null;
  onDismissUndo?: () => void;
  tierBAvailable?: boolean;
}

/**
 * 6-Preset Starter Gallery (KAN-15, KB-P3-AUDIT-09).
 * Provides 1-click starter templates, when-to-use guidance,
 * and a non-destructive dirty-form confirmation and undo strip.
 */
export function PresetGallery({
  onApplyPreset,
  isDirty = false,
  onUndo,
  appliedPresetName,
  onDismissUndo,
  tierBAvailable,
}: PresetGalleryProps): JSX.Element {
  const { data: systemStatus } = useSystemStatus();
  const isTierBAvailable = tierBAvailable ?? (systemStatus?.tier_b_sandbox_available !== false);

  const [filter, setFilter] = useState<FieldFlavor | 'all'>('all');
  const [pendingPreset, setPendingPreset] = useState<CustomFieldPreset | null>(null);

  const filteredPresets = STARTER_PRESETS.filter((p) => {
    if (filter === 'all') return true;
    return p.flavor === filter;
  });

  const handlePresetClick = (preset: CustomFieldPreset) => {
    if (isDirty) {
      setPendingPreset(preset);
    } else {
      onApplyPreset(preset);
    }
  };

  const handleConfirmApply = () => {
    if (pendingPreset) {
      onApplyPreset(pendingPreset);
      setPendingPreset(null);
    }
  };

  const handleCancelApply = () => {
    setPendingPreset(null);
  };

  return (
    <section
      className="preset-gallery-section"
      aria-label="Starter Presets Gallery"
      data-testid="preset-gallery-section"
    >
      <div className="preset-gallery-header">
        <div className="preset-gallery-title-row">
          <span className="preset-gallery-icon" aria-hidden="true">
            📦
          </span>
          <h4 className="preset-gallery-title">1-Click Starter Presets</h4>
          <span className="preset-gallery-count">{STARTER_PRESETS.length} Presets Available</span>
        </div>

        {/* Filter Bar */}
        <div className="preset-gallery-filters" role="group" aria-label="Filter presets by flavor">
          {(['all', 'formula', 'wasm', 'nsjail'] as const).map((flavorOption) => (
            <button
              key={flavorOption}
              type="button"
              className={`preset-gallery-filter-btn ${
                filter === flavorOption ? 'preset-gallery-filter-btn--active' : ''
              }`}
              onClick={() => {
                setFilter(flavorOption);
              }}
              data-testid={`preset-filter-${flavorOption}`}
            >
              {flavorOption === 'all'
                ? 'All Presets'
                : flavorOption === 'wasm'
                  ? 'WebAssembly'
                  : flavorOption.charAt(0).toUpperCase() + flavorOption.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Undo Strip */}
      {appliedPresetName && (
        <div
          className="preset-undo-strip"
          role="status"
          data-testid="preset-undo-strip"
        >
          <span className="preset-undo-text">
            Applied preset <strong>{appliedPresetName}</strong>.
          </span>
          <div className="preset-undo-actions">
            {onUndo && (
              <button
                type="button"
                className="custom-field-btn custom-field-btn--secondary custom-field-btn--sm preset-undo-btn"
                onClick={onUndo}
                data-testid="preset-undo-btn"
              >
                Undo
              </button>
            )}
            {onDismissUndo && (
              <button
                type="button"
                className="preset-undo-dismiss-btn"
                onClick={onDismissUndo}
                aria-label="Dismiss undo notification"
                data-testid="preset-dismiss-undo-btn"
              >
                ✕
              </button>
            )}
          </div>
        </div>
      )}

      {/* Grid of 6 Presets */}
      <div className="preset-gallery-grid" role="list">
        {filteredPresets.map((preset) => {
          const isPresetDisabled =
            !isTierBAvailable && (preset.flavor === 'nsjail' || preset.tier === 'nsjail');
          return (
            <div
              key={preset.id}
              className={`preset-card ${isPresetDisabled ? 'preset-card--disabled' : ''}`}
              role="listitem"
              data-testid={`preset-card-${preset.slug}`}
            >
              <div className="preset-card-header">
                <h5 className="preset-card-title">{preset.name}</h5>
                <div className="preset-card-badges">
                  <span className={`preset-badge preset-badge--${preset.flavor}`}>
                    {preset.flavor}
                  </span>
                  <span className="preset-badge preset-badge--latency">
                    {preset.latency}
                  </span>
                  {isPresetDisabled && (
                    <span
                      className="preset-badge preset-badge--unavailable"
                      data-testid={`preset-unavailable-${preset.slug}`}
                    >
                      Multi-Container Compose Required
                    </span>
                  )}
                </div>
              </div>

              <p className="preset-card-desc">{preset.description}</p>

              <div className="preset-card-when">
                <span className="preset-card-when-label">When to use:</span>
                <p className="preset-card-when-text">{preset.whenToUse}</p>
              </div>

              <div className="preset-card-meta">
                <span className="preset-card-format-pill">
                  Format: <strong className="mono">{preset.outputFormat}</strong>
                </span>
                <span className="preset-card-tier-pill">
                  Tier: <strong className="mono">{preset.tier}</strong>
                </span>
              </div>

              <div className="preset-card-footer">
                <button
                  type="button"
                  className="custom-field-btn custom-field-btn--primary custom-field-btn--sm preset-card-apply-btn"
                  onClick={() => {
                    handlePresetClick(preset);
                  }}
                  disabled={isPresetDisabled}
                  title={isPresetDisabled ? 'Multi-Container Compose Required' : undefined}
                  data-testid={`use-preset-btn-${preset.slug}`}
                >
                  Use Preset
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Dirty Form Confirmation Dialog */}
      {pendingPreset && (
        <div
          className="custom-field-modal-overlay"
          role="dialog"
          aria-modal="true"
          data-testid="preset-dirty-confirm-dialog"
        >
          <div className="custom-field-modal">
            <h4 className="custom-field-modal-title">Confirm Overwrite Unsaved Changes</h4>
            <p className="custom-field-modal-warning-text" data-testid="preset-dirty-warning-text">
              You have unsaved changes in the editor. Applying the preset{' '}
              <strong>{pendingPreset.name}</strong> will overwrite your current edits.
            </p>
            <div className="custom-field-modal-actions">
              <button
                type="button"
                className="custom-field-btn custom-field-btn--secondary"
                onClick={handleCancelApply}
                data-testid="preset-cancel-overwrite-btn"
              >
                Cancel
              </button>
              <button
                type="button"
                className="custom-field-btn custom-field-btn--primary"
                onClick={handleConfirmApply}
                data-testid="preset-confirm-overwrite-btn"
              >
                Apply Preset
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
