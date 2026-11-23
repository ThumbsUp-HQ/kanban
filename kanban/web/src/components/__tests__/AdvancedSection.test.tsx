// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React, { useState } from 'react';
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
});
