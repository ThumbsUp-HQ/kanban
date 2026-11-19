// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { CustomFieldsStudio } from '../CustomFieldsStudio';

vi.mock('../CustomFieldDefinitionEditor', () => ({
  CustomFieldDefinitionEditor: (props: { projectKey: string; isAdmin: boolean }) => (
    <div data-testid="mock-editor">
      projectKey={props.projectKey}, isAdmin={String(props.isAdmin)}
    </div>
  ),
}));

describe('CustomFieldsStudio', () => {
  it('renders CustomFieldsStudio wrapper with default props', () => {
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CustomFieldsStudio />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const studio = screen.getByTestId('custom-fields-studio');
    expect(studio).toBeDefined();
    expect(screen.getByTestId('mock-editor').textContent).toContain('projectKey=DEFAULT, isAdmin=true');
  });

  it('renders CustomFieldsStudio with explicit projectKey and readOnly=true', () => {
    const queryClient = new QueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CustomFieldsStudio projectKey="DEMO" readOnly={true} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId('mock-editor').textContent).toContain('projectKey=DEMO, isAdmin=false');
  });
});
