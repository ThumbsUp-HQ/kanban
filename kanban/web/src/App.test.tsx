import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { App } from './App';

describe('App component', () => {
  it('renders and getByTestId("app-root") contains heading text Kanban', () => {
    render(<App />);
    const appRoot = screen.getByTestId('app-root');
    expect(appRoot).toBeDefined();
    expect(appRoot.textContent).toContain('Kanban');
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading.textContent).toBe('Kanban');
  });
});
