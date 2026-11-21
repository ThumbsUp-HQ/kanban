// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { PlaneImportStudio, extractEntityCounts } from '../PlaneImportStudio';
import * as planeImportApi from '../planeImportApi';

const sampleBundle = {
  projects: [{ id: 'p1', identifier: 'KB', name: 'Kanban Project' }],
  states: [{ id: 's1', name: 'Backlog', group: 'backlog' }],
  issues: [
    { id: 'i1', sequence_id: 1, name: 'First Issue', state: 's1' },
    { id: 'i2', sequence_id: 2, name: 'Second Issue', state: 's1' },
  ],
  cycles: [{ id: 'c1', name: 'Sprint 1' }],
  modules: [{ id: 'm1', name: 'Module A' }],
  issue_comments: [{ id: 'cm1', comment_html: '<p>Hello</p>' }],
  members: [{ id: 'u1', email: 'test@example.com' }],
};

const sampleReport: planeImportApi.ImportDiffReport = {
  to_create: 2,
  to_update: 0,
  unchanged: 0,
  sequence_high_water_mark: 2,
  unmapped_members: ['unknown-user-id'],
  rewritten_attachments: 0,
  invalid_link_count: 0,
  warnings: ['Attachment rewrites not supported in offline mock'],
};

describe('PlaneImportStudio & extractEntityCounts', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('extractEntityCounts returns null for empty/null bundle, and counts arrays correctly', () => {
    expect(extractEntityCounts(null)).toBeNull();
    expect(extractEntityCounts({})).toEqual({
      projects: 0,
      states: 0,
      issues: 0,
      cycles: 0,
      modules: 0,
      comments: 0,
      members: 0,
    });
    const counts = extractEntityCounts(sampleBundle);
    expect(counts).toEqual({
      projects: 1,
      states: 1,
      issues: 2,
      cycles: 1,
      modules: 1,
      comments: 1,
      members: 1,
    });
  });

  it('renders Step 1 with upload and paste modes', () => {
    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('studio-title').textContent).toContain(
      'Plane Migration Import Studio',
    );
    expect(screen.getByTestId('dropzone-area')).toBeDefined();

    // Trigger dry-run without bundle
    fireEvent.click(screen.getByTestId('run-dry-run-btn'));
    expect(screen.getByTestId('error-alert').textContent).toContain(
      'Please upload or paste a valid Plane JSON export bundle.',
    );

    // Switch to paste mode
    fireEvent.click(screen.getByTestId('mode-paste-btn'));
    expect(screen.getByTestId('paste-textarea')).toBeDefined();

    // Switch back to upload mode
    fireEvent.click(screen.getByTestId('mode-upload-btn'));
    expect(screen.getByTestId('dropzone-area')).toBeDefined();
  });

  it('parses pasted JSON and displays detected entity metrics', async () => {
    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('mode-paste-btn'));
    const textarea = screen.getByTestId('paste-textarea');

    // Invalid JSON
    fireEvent.change(textarea, { target: { value: '{ invalid json ' } });
    expect(screen.getByTestId('error-alert')).toBeDefined();

    // Valid JSON but array instead of object
    fireEvent.change(textarea, { target: { value: '[]' } });
    expect(screen.getByTestId('error-alert').textContent).toContain(
      'Plane export bundle must be a JSON object with entity arrays.',
    );

    // Valid JSON
    fireEvent.change(textarea, { target: { value: JSON.stringify(sampleBundle) } });
    expect(screen.queryByTestId('error-alert')).toBeNull();

    await waitFor(() => {
      expect(screen.getByTestId('entity-metrics-preview')).toBeDefined();
      expect(screen.getByTestId('stat-issues').textContent).toContain('2');
      expect(screen.getByTestId('stat-projects').textContent).toContain('1');
    });

    // Empty string resets preview
    fireEvent.change(textarea, { target: { value: '' } });
    expect(screen.queryByTestId('entity-metrics-preview')).toBeNull();
  });

  it('executes dry-run preview and navigates back to input', async () => {
    const importSpy = vi
      .spyOn(planeImportApi, 'submitPlaneImport')
      .mockResolvedValue(sampleReport);

    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('mode-paste-btn'));
    const textarea = screen.getByTestId('paste-textarea');
    fireEvent.change(textarea, { target: { value: JSON.stringify(sampleBundle) } });

    // Optional workspace slug
    fireEvent.change(screen.getByTestId('target-ws-slug-input'), {
      target: { value: 'custom-ws' },
    });

    fireEvent.click(screen.getByTestId('run-dry-run-btn'));

    await waitFor(() => {
      expect(importSpy).toHaveBeenCalledWith({
        bundle_data: sampleBundle,
        dry_run: true,
        workspace_slug: 'custom-ws',
      });
      expect(screen.getByTestId('dry-run-preview-section')).toBeDefined();
      expect(screen.getByTestId('diff-to-create').textContent).toContain('2');
      expect(screen.getByTestId('warnings-box')).toBeDefined();
      expect(screen.getByTestId('unmapped-members-box')).toBeDefined();
    });

    // Click back to input
    fireEvent.click(screen.getByTestId('back-to-input-btn'));
    expect(screen.getByTestId('import-input-section')).toBeDefined();
  });

  it('executes live import to completion with progress and summary', async () => {
    vi.spyOn(planeImportApi, 'submitPlaneImport')
      .mockResolvedValueOnce(sampleReport) // Dry-run
      .mockResolvedValueOnce(sampleReport); // Live run

    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('mode-paste-btn'));
    fireEvent.change(screen.getByTestId('paste-textarea'), {
      target: { value: JSON.stringify(sampleBundle) },
    });
    fireEvent.click(screen.getByTestId('run-dry-run-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('execute-import-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('execute-import-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('import-done-section')).toBeDefined();
      expect(screen.getByTestId('success-banner')).toBeDefined();
    });

    // Click import another
    fireEvent.click(screen.getByTestId('import-another-btn'));
    expect(screen.getByTestId('import-input-section')).toBeDefined();
  });

  it('handles dry-run and live import execution errors cleanly', async () => {
    vi.spyOn(planeImportApi, 'submitPlaneImport')
      .mockRejectedValueOnce(new Error('Dry-run network failure'))
      .mockResolvedValueOnce(sampleReport) // for next dry-run
      .mockRejectedValueOnce(new Error('Transaction lock timeout')); // for live run

    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('mode-paste-btn'));
    fireEvent.change(screen.getByTestId('paste-textarea'), {
      target: { value: JSON.stringify(sampleBundle) },
    });

    // Dry-run failure
    fireEvent.click(screen.getByTestId('run-dry-run-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Dry-run network failure');
    });

    // Successful dry-run
    fireEvent.click(screen.getByTestId('run-dry-run-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('execute-import-btn')).toBeDefined();
    });

    // Live run failure
    fireEvent.click(screen.getByTestId('execute-import-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain('Transaction lock timeout');
      expect(screen.getByTestId('dry-run-preview-section')).toBeDefined();
    });

    // Non-Error failure fallback
    fireEvent.click(screen.getByTestId('back-to-input-btn'));
    vi.spyOn(planeImportApi, 'submitPlaneImport')
      .mockRejectedValueOnce('Raw dry-run error')
      .mockResolvedValueOnce(sampleReport)
      .mockRejectedValueOnce('Raw execute error');

    fireEvent.click(screen.getByTestId('run-dry-run-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain(
        'Failed to execute Plane dry-run simulation.',
      );
    });

    fireEvent.click(screen.getByTestId('run-dry-run-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('execute-import-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('execute-import-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('error-alert').textContent).toContain(
        'Plane live import execution failed.',
      );
    });
  });

  it('handles drag over, drag leave, and drop events', async () => {
    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    const dropzone = screen.getByTestId('dropzone-area');
    fireEvent.dragOver(dropzone);
    expect(dropzone.className).toContain('kb-plane-dropzone-active');

    fireEvent.dragLeave(dropzone);
    expect(dropzone.className).not.toContain('kb-plane-dropzone-active');

    // Empty drop
    fireEvent.drop(dropzone, {
      dataTransfer: {
        files: [],
      },
    });

    // File input with no files
    const fileInput = screen.getByTestId('file-input');
    fireEvent.change(fileInput, { target: { files: [] } });

    const file = new File([JSON.stringify(sampleBundle)], 'export.json', {
      type: 'application/json',
    });

    fireEvent.drop(dropzone, {
      dataTransfer: {
        files: [file],
      },
    });

    await waitFor(() => {
      expect(screen.getByText(/export\.json/)).toBeDefined();
    });
  });

  it('switches between Plane, Jira, GitHub, and Linear source selectors', () => {
    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('studio-title').textContent).toContain('Plane Migration Import Studio');

    // Click Jira
    fireEvent.click(screen.getByTestId('source-jira-btn'));
    expect(screen.getByTestId('studio-title').textContent).toContain('Jira Migration Import Studio');
    expect(screen.getByTestId('target-project-key-input')).toBeDefined();

    // Click GitHub
    fireEvent.click(screen.getByTestId('source-github-btn'));
    expect(screen.getByTestId('studio-title').textContent).toContain('GitHub Migration Import Studio');

    // Click Linear
    fireEvent.click(screen.getByTestId('source-linear-btn'));
    expect(screen.getByTestId('studio-title').textContent).toContain('Linear Migration Import Studio');

    // Click back to Plane
    fireEvent.click(screen.getByTestId('source-plane-btn'));
    expect(screen.getByTestId('studio-title').textContent).toContain('Plane Migration Import Studio');
    expect(screen.queryByTestId('target-project-key-input')).toBeNull();
  });
});
