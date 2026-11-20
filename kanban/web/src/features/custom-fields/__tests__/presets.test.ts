// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, expect, it } from 'vitest';
import { DEFAULT_WASM_BASE64, STARTER_PRESETS } from '../presets';

describe('Custom Field Starter Presets (KAN-15, KB-P3-AUDIT-09)', () => {
  it('contains exactly 6 starter presets with required fields', () => {
    expect(STARTER_PRESETS).toHaveLength(6);

    const expectedIds = [
      'cvss-score',
      'total-project-issues',
      'days-until-due-sla',
      'blocker-count',
      'sub-issue-completion',
      'git-pr-link',
    ];

    expect(STARTER_PRESETS.map((p) => p.id)).toEqual(expectedIds);
  });

  it('verifies all presets have valid slugs, JSON metadata, and non-empty scripts', () => {
    const slugPattern = /^[a-z0-9][a-z0-9-]{1,62}$/;

    for (const preset of STARTER_PRESETS) {
      expect(preset.name.trim().length).toBeGreaterThan(0);
      expect(preset.slug).toMatch(slugPattern);
      expect(preset.description.trim().length).toBeGreaterThan(0);
      expect(preset.whenToUse.trim().length).toBeGreaterThan(0);
      expect(preset.scriptSource.trim().length).toBeGreaterThan(0);
      expect(preset.latency.trim().length).toBeGreaterThan(0);

      // JSON metadata must parse cleanly
      expect(() => {
        JSON.parse(preset.metadataText);
      }).not.toThrow();

      // Tier and flavor pairing validation
      if (preset.flavor === 'nsjail') {
        expect(preset.tier).toBe('nsjail');
      } else {
        expect(preset.tier).toBe('wasm');
      }
    }
  });

  it('verifies DEFAULT_WASM_BASE64 is non-empty base64 string', () => {
    expect(DEFAULT_WASM_BASE64.length).toBeGreaterThan(0);
    // Base64 regex check
    expect(/^[A-Za-z0-9+/=]+$/.test(DEFAULT_WASM_BASE64)).toBe(true);
  });
});
