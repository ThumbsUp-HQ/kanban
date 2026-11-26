// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React, { useState } from 'react';
import * as fs from 'node:fs';
import * as path from 'node:path';
import DefaultAdvancedSection, { AdvancedSection } from '../AdvancedSection';

describe('AdvancedSection Component (KB-ADVANCED-DISCLOSURE / KAN-319)', () => {
  it('re-exports DefaultAdvancedSection identically', () => {
    expect(DefaultAdvancedSection).toBe(AdvancedSection);
  });

  it('defaults to collapsed with aria-expanded="false" and renders children inside DOM', () => {
    render(
      <AdvancedSection title="Advanced Settings">
        <div data-testid="advanced-child">Hidden Child Content</div>
      </AdvancedSection>,
    );

    const toggle = screen.getByTestId('advanced-section-toggle');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    const details = screen.getByTestId('advanced-section');
    expect(details.hasAttribute('open')).toBe(false);
    expect(screen.getByTestId('advanced-child')).toBeDefined();
    expect(screen.getByText('Advanced Settings')).toBeDefined();
  });

  it('renders defaultOpen={true} in expanded state', () => {
    render(
      <AdvancedSection title="Expanded Section" defaultOpen={true}>
        <span>Visible Body</span>
      </AdvancedSection>,
    );

    const toggle = screen.getByTestId('advanced-section-toggle');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');

    const details = screen.getByTestId('advanced-section');
    expect(details.hasAttribute('open')).toBe(true);
    expect(screen.getByText('Visible Body')).toBeDefined();
  });

  it('toggles open/collapsed state upon click', () => {
    const onToggle = vi.fn();
    render(
      <AdvancedSection title="Toggle Section" onToggle={onToggle}>
        <input data-testid="field-1" defaultValue="secret" />
      </AdvancedSection>,
    );

    const toggle = screen.getByTestId('advanced-section-toggle');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    // Click to open
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(onToggle).toHaveBeenCalledWith(true);

    // Click to close
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(onToggle).toHaveBeenCalledWith(false);
  });

  it('toggles open/collapsed state with Enter and Space keyboard navigation', () => {
    const onToggle = vi.fn();
    render(
      <AdvancedSection title="Keyboard Section" onToggle={onToggle}>
        <span>Keyboard Content</span>
      </AdvancedSection>,
    );

    const toggle = screen.getByTestId('advanced-section-toggle');

    // Non-toggle keys do not trigger toggle
    fireEvent.keyDown(toggle, { key: 'ArrowDown' });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(onToggle).not.toHaveBeenCalled();

    // Enter key toggles open
    fireEvent.keyDown(toggle, { key: 'Enter' });
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(onToggle).toHaveBeenCalledWith(true);

    // Space key toggles closed
    fireEvent.keyDown(toggle, { key: ' ' });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(onToggle).toHaveBeenCalledWith(false);
  });

  it('toggles expand/collapse correctly in light theme container', () => {
    const onToggle = vi.fn();
    render(
      <div data-theme="light">
        <AdvancedSection title="Light Theme Section" onToggle={onToggle}>
          <div data-testid="light-content">Light Content</div>
        </AdvancedSection>
      </div>,
    );

    const toggle = screen.getByTestId('advanced-section-toggle');
    const details = screen.getByTestId('advanced-section');
    const chevron = toggle.querySelector('.kb-advanced-chevron');
    const content = details.querySelector('.kb-advanced-content');

    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(details.className).not.toContain('kb-advanced-section--open');
    expect(chevron?.className).not.toContain('kb-advanced-chevron--open');

    // Explicit verification of role="region" and aria-label
    expect(content?.getAttribute('role')).toBe('region');
    expect(content?.getAttribute('aria-label')).toBe('Light Theme Section');

    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(details.className).toContain('kb-advanced-section--open');
    expect(chevron?.className).toContain('kb-advanced-chevron--open');
    expect(onToggle).toHaveBeenCalledWith(true);

    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(details.className).not.toContain('kb-advanced-section--open');
    expect(chevron?.className).not.toContain('kb-advanced-chevron--open');
  });

  it('toggles expand/collapse correctly in dark theme container', () => {
    const onToggle = vi.fn();
    render(
      <div data-theme="dark">
        <AdvancedSection title="Dark Theme Section" onToggle={onToggle}>
          <div data-testid="dark-content">Dark Content</div>
        </AdvancedSection>
      </div>,
    );

    const toggle = screen.getByTestId('advanced-section-toggle');
    const details = screen.getByTestId('advanced-section');
    const chevron = toggle.querySelector('.kb-advanced-chevron');
    const content = details.querySelector('.kb-advanced-content');

    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(details.className).not.toContain('kb-advanced-section--open');
    expect(chevron?.className).not.toContain('kb-advanced-chevron--open');

    // Explicit verification of role="region" and aria-label
    expect(content?.getAttribute('role')).toBe('region');
    expect(content?.getAttribute('aria-label')).toBe('Dark Theme Section');

    fireEvent.keyDown(toggle, { key: 'Enter' });
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(details.className).toContain('kb-advanced-section--open');
    expect(chevron?.className).toContain('kb-advanced-chevron--open');
    expect(onToggle).toHaveBeenCalledWith(true);

    fireEvent.keyDown(toggle, { key: ' ' });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(details.className).not.toContain('kb-advanced-section--open');
    expect(chevron?.className).not.toContain('kb-advanced-chevron--open');
  });

  it('renders active overrides badge when activeOverridesCount or activeOverrideCount > 0', () => {
    const { rerender } = render(
      <AdvancedSection title="Overrides Test" activeOverridesCount={3}>
        <div>Options</div>
      </AdvancedSection>,
    );

    const badge = screen.getByTestId('advanced-active-badge');
    expect(badge.textContent).toBe('3 custom settings active');
    expect(badge.getAttribute('data-collapsed')).toBe('true');

    // Singular count formatting
    rerender(
      <AdvancedSection title="Overrides Test" activeOverrideCount={1}>
        <div>Options</div>
      </AdvancedSection>,
    );
    expect(screen.getByTestId('advanced-active-badge').textContent).toBe(
      '1 custom setting active',
    );

    // Custom badgeLabel override
    rerender(
      <AdvancedSection
        title="Overrides Test"
        activeOverridesCount={2}
        badgeLabel="2 overrides applied"
      >
        <div>Options</div>
      </AdvancedSection>,
    );
    expect(screen.getByTestId('advanced-active-badge').textContent).toBe(
      '2 overrides applied',
    );

    // No badge when count is 0
    rerender(
      <AdvancedSection title="Overrides Test" activeOverridesCount={0}>
        <div>Options</div>
      </AdvancedSection>,
    );
    expect(screen.queryByTestId('advanced-active-badge')).toBeNull();
  });

  it('auto-expands when hasErrors transitions to true', () => {
    function ErrorHarness() {
      const [hasErrors, setHasErrors] = useState(false);
      return (
        <div>
          <button
            type="button"
            data-testid="trigger-error"
            onClick={() => {
              setHasErrors(true);
            }}
          >
            Trigger Error
          </button>
          <AdvancedSection title="Validated Section" hasErrors={hasErrors}>
            <span data-testid="error-target">Error Target Field</span>
          </AdvancedSection>
        </div>
      );
    }

    render(<ErrorHarness />);
    const toggle = screen.getByTestId('advanced-section-toggle');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(screen.getByTestId('trigger-error'));
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
  });

  it('supports controlled isOpen prop', () => {
    const onToggle = vi.fn();
    const { rerender } = render(
      <AdvancedSection
        title="Controlled Section"
        isOpen={false}
        onToggle={onToggle}
      >
        <span>Controlled Body</span>
      </AdvancedSection>,
    );

    const toggle = screen.getByTestId('advanced-section-toggle');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(toggle);
    expect(onToggle).toHaveBeenCalledWith(true);

    rerender(
      <AdvancedSection
        title="Controlled Section"
        isOpen={true}
        onToggle={onToggle}
      >
        <span>Controlled Body</span>
      </AdvancedSection>,
    );
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
  });

  it('renders summary description, custom testId, id, and className', () => {
    render(
      <AdvancedSection
        title="Network Restrictions"
        summary="Configure CIDR allowlists and proxies"
        id="custom-adv-id"
        className="my-custom-class"
        testId="net-adv"
      >
        <span>Network Settings</span>
      </AdvancedSection>,
    );

    const details = screen.getByTestId('net-adv');
    expect(details.id).toBe('custom-adv-id');
    expect(details.className).toContain('my-custom-class');
    expect(screen.getByText('Network Restrictions')).toBeDefined();
    expect(
      screen.getByText('Configure CIDR allowlists and proxies'),
    ).toBeDefined();
  });

  describe('CSS theme tokens and fallback audit (KAN-445)', () => {
    const cssPath = path.resolve(__dirname, '../../ui/AdvancedSection.css');
    const cssContent = fs.readFileSync(cssPath, 'utf8');

    it('contains zero mismatched hardcoded fallback colors', () => {
      expect(cssContent).not.toContain('#e2e8f0');
      expect(cssContent).not.toContain('#334155');
      expect(cssContent).not.toContain('#0f172a');
      expect(cssContent).not.toContain('#1e293b');
      expect(cssContent).not.toContain('#f8fafc');
      expect(cssContent).not.toContain('#f1f5f9');
    });

    it('uses canonical theme tokens for container, header, chevron, focus ring, and badge', () => {
      expect(cssContent).toContain('var(--border-subtle, #e5e7eb)');
      expect(cssContent).toContain('var(--border-subtle, #2d333f)');
      expect(cssContent).toContain('var(--bg-card-subtle)');
      expect(cssContent).toContain('var(--border-color-focus)');
      expect(cssContent).toContain('var(--bg-surface)');
      expect(cssContent).toContain('var(--focus-ring, #2563eb)');
      expect(cssContent).toContain('var(--fg-muted)');
      expect(cssContent).toContain('var(--fg-primary)');
      expect(cssContent).toContain('var(--fg-secondary)');
      expect(cssContent).toContain('var(--badge-bg)');
      expect(cssContent).toContain('var(--badge-fg)');
      expect(cssContent).toContain('var(--badge-border)');
    });

    it('standardizes .kb-advanced-content spacing and border', () => {
      expect(cssContent).toMatch(
        /\.kb-advanced-content\s*\{[^}]*border-top:\s*1px\s+solid\s+var\(--border-subtle,\s*#e5e7eb\);/,
      );
      expect(cssContent).toMatch(
        /\.kb-advanced-content\s*\{[^}]*padding:\s*var\(--space-4,\s*16px\);/,
      );
      expect(cssContent).toMatch(
        /\.kb-advanced-content\s*\{[^}]*display:\s*flex;/,
      );
      expect(cssContent).toMatch(
        /\.kb-advanced-content\s*\{[^}]*flex-direction:\s*column;/,
      );
      expect(cssContent).toMatch(
        /\.kb-advanced-content\s*\{[^}]*gap:\s*var\(--space-3,\s*12px\);/,
      );
      expect(cssContent).toMatch(
        /:where\(\[data-theme=['"]dark['"]\]\)\s+\.kb-advanced-content\s*\{[^}]*border-top-color:\s*var\(--border-subtle,\s*#2d333f\);/,
      );
    });

    it('avoids redundant dark theme re-declarations', () => {
      // Base rules already handle variables via CSS inheritance
      expect(cssContent).not.toContain("[data-theme='dark'] .kb-advanced-chevron--open");
      expect(cssContent).not.toContain("[data-theme='dark'] .kb-advanced-title");
      expect(cssContent).not.toContain("[data-theme='dark'] .kb-advanced-desc");
      expect(cssContent).not.toContain("[data-theme='dark'] .kb-advanced-badge");
      expect(cssContent).not.toContain("[data-theme='dark'] .kb-advanced-section--open");
    });

    it('guards open state specificity over dark theme border-color', () => {
      // Must use compound class to ensure higher specificity than dark theme base rule
      expect(cssContent).toContain('.kb-advanced-section.kb-advanced-section--open');
      expect(cssContent).toContain(":where([data-theme='dark']) .kb-advanced-section");
      expect(cssContent).toMatch(
        /\.kb-advanced-section\.kb-advanced-section--open\s*\{[^}]*border-color:\s*var\(--border-color-focus\);/,
      );
    });
  });
});
