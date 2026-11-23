// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { AdvancedSection } from './AdvancedSection';

describe('AdvancedSection UI Component Export (KB-ADVANCED-DISCLOSURE)', () => {
  it('renders correctly from src/ui/AdvancedSection', () => {
    render(
      <AdvancedSection title="UI Export Test" defaultOpen={true}>
        <div data-testid="ui-child">Exported content</div>
      </AdvancedSection>,
    );

    expect(screen.getByTestId('ui-child')).toBeDefined();
    expect(screen.getByText('UI Export Test')).toBeDefined();
  });
});
