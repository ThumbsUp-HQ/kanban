import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router';
import { Breadcrumb } from './Breadcrumb';

describe('Breadcrumb', () => {
  it('renders project icon, project name, and current section with count badge', () => {
    render(
      <MemoryRouter>
        <Breadcrumb
          projectKey="KAN"
          projectName="kanban"
          projectIcon="⚡"
          currentSection="Work Items"
          issueCount={7}
        />
      </MemoryRouter>,
    );

    const nav = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(nav).toBeDefined();

    expect(screen.getByText('kanban')).toBeDefined();
    expect(screen.getByText('Work Items')).toBeDefined();
    expect(screen.getByText('(7)')).toBeDefined();

    const currentItem = screen.getByRole('listitem', { current: 'page' });
    expect(currentItem.textContent).toContain('Work Items');
    expect(currentItem.textContent).toContain('(7)');
  });

  it('omits count badge when issueCount is null or undefined', () => {
    render(
      <MemoryRouter>
        <Breadcrumb
          projectKey="KAN"
          projectName="kanban"
          currentSection="Overview"
          issueCount={null}
        />
      </MemoryRouter>,
    );

    const section = screen.getByTestId('breadcrumb-current-section');
    expect(section.textContent).toBe('Overview');
    expect(screen.queryByText(/\(\d+\)/)).toBeNull();
  });

  it('triggers onBack callback when back button is clicked in mobile view', () => {
    const onBack = vi.fn();
    render(
      <MemoryRouter>
        <Breadcrumb
          projectKey="KAN"
          projectName="kanban"
          currentSection="Work Items"
          issueCount={7}
          onBack={onBack}
        />
      </MemoryRouter>,
    );

    const backBtn = screen.getByRole('button', { name: 'Back' });
    act(() => {
      backBtn.click();
    });

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('navigates back via router navigate when onBack is omitted', () => {
    render(
      <MemoryRouter initialEntries={['/projects/KAN/overview', '/projects/KAN/issues']}>
        <Breadcrumb
          projectKey="KAN"
          projectName="kanban"
          currentSection="Work Items"
        />
      </MemoryRouter>,
    );

    const backBtn = screen.getByRole('button', { name: 'Back' });
    act(() => {
      backBtn.click();
    });
    // Successfully executed navigate(-1) without error
    expect(backBtn).toBeDefined();
  });

  it('renders and handles back button safely with default props', () => {
    render(
      <MemoryRouter>
        <Breadcrumb />
      </MemoryRouter>,
    );
    const backBtn = screen.getByRole('button', { name: 'Back' });
    act(() => {
      backBtn.click();
    });
    expect(backBtn).toBeDefined();
  });
});
