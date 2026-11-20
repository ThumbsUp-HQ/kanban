// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { FLAVOR_DETAILS, FlavorDecisionMatrix } from '../FlavorDecisionMatrix';

describe('FlavorDecisionMatrix Component (KAN-15, KB-P3-AUDIT-09)', () => {
  it('renders matrix header and collapsed by default', () => {
    render(<FlavorDecisionMatrix />);

    expect(screen.getByTestId('flavor-decision-matrix')).toBeDefined();
    expect(screen.getByText('Which Flavor Should I Use?')).toBeDefined();
    expect(screen.queryByTestId('flavor-matrix-content')).toBeNull();
  });

  it('toggles open and closed via toggle button', () => {
    render(<FlavorDecisionMatrix />);

    const toggleBtn = screen.getByTestId('toggle-flavor-matrix-btn');
    expect(toggleBtn.textContent).toBe('Compare Flavors');

    // Click to open
    act(() => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.getByTestId('flavor-matrix-content')).toBeDefined();
    expect(toggleBtn.textContent).toBe('Hide Matrix');

    // Click to close
    act(() => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.queryByTestId('flavor-matrix-content')).toBeNull();
  });

  it('supports controlled isOpen and onToggle props', () => {
    const handleToggle = vi.fn();
    const { rerender } = render(
      <FlavorDecisionMatrix isOpen={false} onToggle={handleToggle} />,
    );

    const toggleBtn = screen.getByTestId('toggle-flavor-matrix-btn');
    act(() => {
      fireEvent.click(toggleBtn);
    });
    expect(handleToggle).toHaveBeenCalledTimes(1);

    // Rerender as open
    rerender(<FlavorDecisionMatrix isOpen={true} onToggle={handleToggle} />);
    expect(screen.getByTestId('flavor-matrix-content')).toBeDefined();
  });

  it('renders all 4 flavors with respective latency bounds and descriptions', () => {
    render(<FlavorDecisionMatrix isOpen={true} />);

    expect(FLAVOR_DETAILS).toHaveLength(4);

    const scalarCard = screen.getByTestId('flavor-card-scalar');
    expect(scalarCard.textContent).toContain('<1ms');
    expect(scalarCard.textContent).toContain('Scalar Value');

    const formulaCard = screen.getByTestId('flavor-card-formula');
    expect(formulaCard.textContent).toContain('<5ms');
    expect(formulaCard.textContent).toContain('Formula Expression');

    const wasmCard = screen.getByTestId('flavor-card-wasm');
    expect(wasmCard.textContent).toContain('<25ms');
    expect(wasmCard.textContent).toContain('WebAssembly');

    const nsjailCard = screen.getByTestId('flavor-card-nsjail');
    expect(nsjailCard.textContent).toContain('<=3,000ms');
    expect(nsjailCard.textContent).toContain('Project Rollup / nsjail');
  });

  it('calls onSelectFlavor when select button is clicked and highlights selected flavor', () => {
    const handleSelect = vi.fn();
    render(
      <FlavorDecisionMatrix
        isOpen={true}
        selectedFlavor="formula"
        onSelectFlavor={handleSelect}
      />,
    );

    const formulaCard = screen.getByTestId('flavor-card-formula');
    expect(formulaCard.className).toContain('flavor-matrix-card--selected');

    const selectBtn = screen.getByTestId('select-flavor-btn-wasm');
    act(() => {
      fireEvent.click(selectBtn);
    });
    expect(handleSelect).toHaveBeenCalledWith('wasm');

    const selectedBtn = screen.getByTestId('select-flavor-btn-formula');
    expect(selectedBtn.textContent).toBe('Selected');
  });
});
