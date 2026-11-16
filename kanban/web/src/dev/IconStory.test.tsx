import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IconStory } from './IconStory';

describe('IconStory (KB-UX-02)', () => {
  it('renders all sections: priorities, states, rings, modules, and SVG registry', () => {
    render(<IconStory />);

    expect(screen.getByTestId('icon-story')).toBeDefined();
    expect(screen.getByTestId('section-priorities')).toBeDefined();
    expect(screen.getByTestId('section-states')).toBeDefined();
    expect(screen.getByTestId('section-rings')).toBeDefined();
    expect(screen.getByTestId('section-modules')).toBeDefined();
    expect(screen.getByTestId('section-svg-registry')).toBeDefined();

    // Priorities
    expect(screen.getByTestId('priority-card-urgent')).toBeDefined();
    expect(screen.getByTestId('priority-card-low')).toBeDefined();

    // State badges
    expect(screen.getByText('Backlog')).toBeDefined();
    expect(screen.getByText('Todo')).toBeDefined();
    expect(screen.getByText('In Progress')).toBeDefined();
    expect(screen.getByText('Done')).toBeDefined();
    expect(screen.getByText('Cancelled')).toBeDefined();

    // Modules
    expect(screen.getByText('Auth Core')).toBeDefined();
    expect(screen.getByText('Kanban Board')).toBeDefined();
  });
});
