import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { IssuesWorkspaceRoute } from './routes';
import { FIXTURE_12_ISSUES } from '../features/views/fixtures';

describe('IssuesWorkspaceRoute', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/projects/KAN/issues');
  });

  it('mounts and renders default ListView', () => {
    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    expect(screen.getByText('Backlog')).toBeDefined();
  });

  it('renders TableView when layout=table in search params', () => {
    window.history.pushState({}, '', '/projects/KAN/issues?layout=table');

    render(
      <IssuesWorkspaceRoute
        projectKey="KAN"
        modulesEnabled={true}
        initialIssues={FIXTURE_12_ISSUES}
      />
    );

    expect(screen.getByRole('table')).toBeDefined();
  });
});
