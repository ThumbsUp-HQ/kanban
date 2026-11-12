import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { ViewHost, VIEW_REGISTRY } from './viewRegistry';
import { FIXTURE_12_ISSUES } from './fixtures';

describe('viewRegistry', () => {
  it('registers list, table, calendar, and timeline views', () => {
    expect(VIEW_REGISTRY.list).toBeDefined();
    expect(VIEW_REGISTRY.table).toBeDefined();
    expect(VIEW_REGISTRY.calendar).toBeDefined();
    expect(VIEW_REGISTRY.timeline).toBeDefined();
  });

  it('renders ListView when layout is list or unspecified', () => {
    render(
      <ViewHost
        layout="list"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    // List section header
    expect(screen.getByText('Backlog')).toBeDefined();
  });

  it('renders TableView when layout is table', () => {
    render(
      <ViewHost
        layout="table"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByRole('table')).toBeDefined();
    expect(screen.getByRole('columnheader', { name: /Key/i })).toBeDefined();
  });

  it('renders CalendarView when layout is calendar', () => {
    render(
      <ViewHost
        layout="calendar"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByTestId('calendar-view')).toBeDefined();
  });

  it('renders TimelineView when layout is timeline', () => {
    render(
      <ViewHost
        layout="timeline"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByTestId('timeline-view')).toBeDefined();
  });

  it('falls back to ListView on unknown layout', () => {
    render(
      <ViewHost
        layout="unknown_layout"
        issues={FIXTURE_12_ISSUES}
        projectKey="KAN"
        modulesEnabled={true}
      />
    );

    expect(screen.getByText('Backlog')).toBeDefined();
  });
});
