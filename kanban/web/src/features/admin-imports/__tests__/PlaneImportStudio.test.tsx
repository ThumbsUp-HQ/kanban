// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { PlaneImportStudio, extractEntityCounts } from '../PlaneImportStudio';
import * as planeImportApi from '../planeImportApi';
import { Aal2StepUpCancelledError } from '../../../api/client';

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
    expect(extractEntityCounts(12345)).toBeNull();
    const arrCounts = extractEntityCounts([{ id: '1' }, { id: '2' }]);
    expect(arrCounts?.issues).toBe(2);
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
      'Migration Import Studio',
    );
    expect(screen.getByTestId('studio-title').textContent).not.toContain(
      'Plane Migration Import Studio',
    );
    expect(screen.getByTestId('studio-title').textContent.trim()).toBe(
      'Migration Import Studio',
    );

    // Verify studio title remains "Migration Import Studio" when switching sources
    fireEvent.click(screen.getByTestId('source-jira-btn'));
    expect(screen.getByTestId('studio-title').textContent.trim()).toBe('Migration Import Studio');
    expect(screen.getByTestId('studio-title').textContent).not.toContain('Plane Migration');

    fireEvent.click(screen.getByTestId('source-github-btn'));
    expect(screen.getByTestId('studio-title').textContent.trim()).toBe('Migration Import Studio');
    expect(screen.getByTestId('studio-title').textContent).not.toContain('Plane Migration');

    fireEvent.click(screen.getByTestId('source-linear-btn'));
    expect(screen.getByTestId('studio-title').textContent.trim()).toBe('Migration Import Studio');
    expect(screen.getByTestId('studio-title').textContent).not.toContain('Plane Migration');

    fireEvent.click(screen.getByTestId('source-plane-btn'));
    expect(screen.getByTestId('studio-title').textContent.trim()).toBe('Migration Import Studio');
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

    // File input with valid file triggers handleFileChange
    fireEvent.change(fileInput, { target: { files: [file] } });
    await waitFor(() => {
      expect(screen.getByText(/export\.json/)).toBeDefined();
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

    expect(screen.getByTestId('studio-title').textContent).toBe('Migration Import Studio');

    // Click Jira
    fireEvent.click(screen.getByTestId('source-jira-btn'));
    expect(screen.getByTestId('studio-title').textContent).toBe('Migration Import Studio');
    expect(screen.getByTestId('target-project-key-input')).toBeDefined();

    // Click GitHub
    fireEvent.click(screen.getByTestId('source-github-btn'));
    expect(screen.getByTestId('studio-title').textContent).toBe('Migration Import Studio');

    // Click Linear
    fireEvent.click(screen.getByTestId('source-linear-btn'));
    expect(screen.getByTestId('studio-title').textContent).toBe('Migration Import Studio');

    // Click back to Plane
    fireEvent.click(screen.getByTestId('source-plane-btn'));
    expect(screen.getByTestId('studio-title').textContent).toBe('Migration Import Studio');
    expect(screen.queryByTestId('target-project-key-input')).toBeNull();
  });

  it('configures accept and placeholder dynamically for Linear CSV and JSON', () => {
    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    const fileInput = screen.getByTestId('file-input');
    expect(fileInput.getAttribute('accept')).toBe('.json,application/json');

    // Select Linear
    fireEvent.click(screen.getByTestId('source-linear-btn'));
    expect(fileInput.getAttribute('accept')).toBe('.csv,text/csv,.json,application/json');

    // Switch to paste mode
    fireEvent.click(screen.getByTestId('mode-paste-btn'));
    const textarea = screen.getByTestId('paste-textarea');
    expect(textarea.getAttribute('placeholder')).toContain('Linear');

    // Paste CSV
    const sampleCsv = 'id,title,state\nENG-1,First Task,Todo\nENG-2,Second Task,Done';
    fireEvent.change(textarea, { target: { value: sampleCsv } });
    expect(screen.queryByTestId('error-alert')).toBeNull();
    expect(screen.getByTestId('stat-issues').textContent).toContain('2');
  });

  it('triggers Portable Workspace Export download with workspace slug and scrub checkbox', async () => {
    const mockBlob = new Blob(['tar.gz bytes'], { type: 'application/gzip' });
    const exportSpy = vi
      .spyOn(planeImportApi, 'downloadPortableExport')
      .mockResolvedValue(mockBlob);

    // Mock createObjectURL and revokeObjectURL
    window.URL.createObjectURL = vi.fn().mockReturnValue('blob:http://test/123');
    window.URL.revokeObjectURL = vi.fn();

    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('portable-export-panel')).toBeDefined();

    // Input workspace slug
    fireEvent.change(screen.getByTestId('export-workspace-slug-input'), {
      target: { value: 'acme-corp' },
    });

    // Toggle scrub checkbox
    const scrubCheckbox = screen.getByTestId('export-scrub-checkbox');
    fireEvent.click(scrubCheckbox);

    // Click download export button
    fireEvent.click(screen.getByTestId('export-download-btn'));

    await waitFor(() => {
      expect(exportSpy).toHaveBeenCalledWith({
        workspace_slug: 'acme-corp',
        scrub_text: true,
      });
      expect(screen.getByTestId('export-success-alert').textContent).toContain(
        'Successfully downloaded kanban-acme-corp-portable.tar.gz',
      );
    });
  });

  it('updates advanced import options and handles dropzone events', () => {
    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    // Switch to Jira to display target project key input
    fireEvent.click(screen.getByTestId('source-jira-btn'));
    const projInput = screen.getByTestId('target-project-key-input');
    fireEvent.change(projInput, { target: { value: 'MIGPROJ' } });
    expect((projInput as HTMLInputElement).value).toBe('MIGPROJ');

    // CUT orphan options controls must not be rendered
    expect(screen.queryByTestId('import-batch-size-input')).toBeNull();
    expect(screen.queryByTestId('import-conflict-strategy-select')).toBeNull();
    expect(screen.queryByTestId('import-preserve-uuids-checkbox')).toBeNull();

    const userMapping = screen.getByTestId('import-user-mapping-json');
    fireEvent.change(userMapping, { target: { value: '{"old-uuid": "@admin"}' } });
    expect((userMapping as HTMLTextAreaElement).value).toBe('{"old-uuid": "@admin"}');

    // Test invalid JSON validation
    fireEvent.change(userMapping, { target: { value: '{invalid-json' } });
    expect(screen.getByTestId('import-user-mapping-error')).toBeDefined();

    // Reset to valid JSON
    fireEvent.change(userMapping, { target: { value: '{"old-uuid": "@admin"}' } });
    expect(screen.queryByTestId('import-user-mapping-error')).toBeNull();

    // Dropzone drag over and drag leave
    const dropzone = screen.getByTestId('dropzone-area');
    fireEvent.dragOver(dropzone);
    expect(dropzone.classList.contains('kb-plane-dropzone-active')).toBe(true);

    fireEvent.dragLeave(dropzone);
    expect(dropzone.classList.contains('kb-plane-dropzone-active')).toBe(false);

    // Dropzone click triggers file input click
    const fileInput = screen.getByTestId('file-input');
    const clickSpy = vi.spyOn(fileInput, 'click');
    fireEvent.click(dropzone);
    expect(clickSpy).toHaveBeenCalled();
  });

  it('executes dry-run preview and live import for Jira source via submitImport', async () => {
    const submitImportSpy = vi
      .spyOn(planeImportApi, 'submitImport')
      .mockResolvedValue(sampleReport);

    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );

    // Switch to Jira
    fireEvent.click(screen.getByTestId('source-jira-btn'));
    fireEvent.click(screen.getByTestId('mode-paste-btn'));
    fireEvent.change(screen.getByTestId('paste-textarea'), {
      target: { value: JSON.stringify({ issues: [{ key: 'JIRA-1' }] }) },
    });

    // Run dry-run
    fireEvent.click(screen.getByTestId('run-dry-run-btn'));
    await waitFor(() => {
      expect(submitImportSpy).toHaveBeenCalledWith(
        'jira',
        expect.objectContaining({ dry_run: true }),
      );
      expect(screen.getByTestId('dry-run-preview-section')).toBeDefined();
    });

    // Run live import
    fireEvent.click(screen.getByTestId('execute-import-btn'));
    await waitFor(() => {
      expect(submitImportSpy).toHaveBeenCalledWith(
        'jira',
        expect.objectContaining({ dry_run: false }),
      );
      expect(screen.getByTestId('import-done-section')).toBeDefined();
    });
  });

  it('displays error and halts when dry-run is triggered with invalid userMappingJson', () => {
    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId('mode-paste-btn'));
    const textarea = screen.getByTestId('paste-textarea');
    fireEvent.change(textarea, { target: { value: JSON.stringify({ issues: [{ id: '1' }] }) } });

    const userMapping = screen.getByTestId('import-user-mapping-json');
    // Test array non-object JSON
    fireEvent.change(userMapping, { target: { value: '[1, 2, 3]' } });
    expect(screen.getByText(/User mapping must be a JSON object/i)).toBeDefined();

    // Test malformed JSON
    fireEvent.change(userMapping, { target: { value: '{invalid-json' } });

    const dryRunBtn = screen.getByTestId('run-dry-run-btn');
    fireEvent.click(dryRunBtn);
    expect(screen.getAllByText(/Invalid User Mapping JSON/i).length).toBeGreaterThan(0);
  });

  it('silently ignores Aal2StepUpCancelledError during import with zero role="alert" banners (KAN-404)', async () => {
    vi.spyOn(planeImportApi, 'submitPlaneImport').mockRejectedValue(
      new Aal2StepUpCancelledError(),
    );
    render(
      <MemoryRouter initialEntries={['/admin/imports']}>
        <PlaneImportStudio />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId('mode-paste-btn'));
    const textarea = screen.getByTestId('paste-textarea');
    fireEvent.change(textarea, { target: { value: JSON.stringify(sampleBundle) } });

    fireEvent.click(screen.getByTestId('run-dry-run-btn'));
    await waitFor(() => {
      expect(screen.queryByRole('alert')).toBeNull();
    });
  });

  it('binds .kb-plane-mode-active to semantic tokens without low-contrast hexes (KAN-529)', () => {
    const cssPath = path.resolve(import.meta.dirname, '../PlaneImportStudio.css');
    const cssContent = fs.readFileSync(cssPath, 'utf8');

    // Verify .kb-plane-mode-active uses semantic tokens
    const activeRuleMatch = /\.kb-plane-mode-active\s*\{([^}]+)\}/.exec(cssContent);
    expect(activeRuleMatch).not.toBeNull();
    const activeRule = activeRuleMatch ? activeRuleMatch[1] : '';

    expect(activeRule).toContain('background-color: var(--bg-accent-subtle);');
    expect(activeRule).toContain('border-color: var(--badge-fg);');
    expect(activeRule).toContain('color: var(--badge-fg);');
    expect(activeRule).toContain('font-weight: 600;');

    // Verify no low-contrast hex values in .kb-plane-mode-active
    expect(activeRule).not.toContain('#58a6ff');
    expect(activeRule).not.toContain('#388bfd');

    // Verify .kb-plane-mode-active:hover prevents hover state from overriding active tab contrast
    const hoverRuleMatch = /\.kb-plane-mode-active:hover\s*\{([^}]+)\}/.exec(cssContent);
    expect(hoverRuleMatch).not.toBeNull();
    const hoverRule = hoverRuleMatch ? hoverRuleMatch[1] : '';
    expect(hoverRule).toContain('background-color: var(--bg-accent-subtle);');
    expect(hoverRule).toContain('border-color: var(--badge-fg);');
    expect(hoverRule).toContain('color: var(--badge-fg);');

    // Verify alert, warning, and button tokens
    expect(cssContent).toMatch(/\.kb-plane-warnings-box\s*\{[^}]*var\(--warn-bg\)/);
    expect(cssContent).toMatch(/\.kb-plane-warnings-box\s*\{[^}]*var\(--border-warning\)/);
    expect(cssContent).toMatch(/\.kb-plane-warnings-title\s*\{[^}]*var\(--warn-fg\)/);
    expect(cssContent).toMatch(/\.kb-plane-alert-error\s*\{[^}]*var\(--danger-bg\)/);
    expect(cssContent).toMatch(/\.kb-plane-alert-error\s*\{[^}]*var\(--border-danger\)/);
    expect(cssContent).toMatch(/\.kb-plane-alert-error\s*\{[^}]*var\(--danger-fg\)/);
    expect(cssContent).toMatch(/\.kb-plane-alert-success\s*\{[^}]*var\(--bg-success-subtle\)/);
    expect(cssContent).toMatch(/\.kb-plane-alert-success\s*\{[^}]*var\(--border-success\)/);
    expect(cssContent).toMatch(/\.kb-plane-alert-success\s*\{[^}]*var\(--text-success\)/);
    expect(cssContent).toMatch(/\.kb-plane-btn-primary\s*\{[^}]*var\(--accent-primary\)/);
    expect(cssContent).toMatch(/\.kb-plane-btn-primary\s*\{[^}]*var\(--accent-primary-fg\)/);
    expect(cssContent).toMatch(/\.kb-plane-btn-execute\s*\{[^}]*var\(--accent-primary\)/);
    expect(cssContent).toMatch(/\.kb-plane-btn-execute\s*\{[^}]*var\(--accent-primary-fg\)/);

    // Verify mobile responsive wrapping on mode row and container padding
    expect(cssContent).toMatch(/\.kb-plane-mode-row\s*\{[^}]*flex-wrap:\s*wrap;/);
    expect(cssContent).toMatch(/\.kb-plane-import-container\s*\{[^}]*padding:\s*16px;/);
  });

  it('switches import source and mode selection tabs cleanly across light and dark themes (KAN-529)', () => {
    for (const theme of ['light', 'dark']) {
      document.documentElement.setAttribute('data-theme', theme);

      const { unmount } = render(
        <MemoryRouter initialEntries={['/admin/imports']}>
          <PlaneImportStudio />
        </MemoryRouter>,
      );

      // Initially, plane source button is active
      const planeBtn = screen.getByTestId('source-plane-btn');
      const jiraBtn = screen.getByTestId('source-jira-btn');
      const githubBtn = screen.getByTestId('source-github-btn');
      const linearBtn = screen.getByTestId('source-linear-btn');

      expect(planeBtn.className).toContain('kb-plane-mode-active');
      expect(jiraBtn.className).not.toContain('kb-plane-mode-active');
      expect(githubBtn.className).not.toContain('kb-plane-mode-active');
      expect(linearBtn.className).not.toContain('kb-plane-mode-active');

      // Switch to Jira
      fireEvent.click(jiraBtn);
      expect(jiraBtn.className).toContain('kb-plane-mode-active');
      expect(planeBtn.className).not.toContain('kb-plane-mode-active');

      // Switch to GitHub Issues
      fireEvent.click(githubBtn);
      expect(githubBtn.className).toContain('kb-plane-mode-active');
      expect(jiraBtn.className).not.toContain('kb-plane-mode-active');

      // Switch to Linear
      fireEvent.click(linearBtn);
      expect(linearBtn.className).toContain('kb-plane-mode-active');
      expect(githubBtn.className).not.toContain('kb-plane-mode-active');

      // Switch back to Plane
      fireEvent.click(planeBtn);
      expect(planeBtn.className).toContain('kb-plane-mode-active');
      expect(linearBtn.className).not.toContain('kb-plane-mode-active');

      // Test input mode tabs (Upload vs Paste)
      const uploadModeBtn = screen.getByTestId('mode-upload-btn');
      const pasteModeBtn = screen.getByTestId('mode-paste-btn');

      expect(uploadModeBtn.className).toContain('kb-plane-mode-active');
      expect(pasteModeBtn.className).not.toContain('kb-plane-mode-active');

      fireEvent.click(pasteModeBtn);
      expect(pasteModeBtn.className).toContain('kb-plane-mode-active');
      expect(uploadModeBtn.className).not.toContain('kb-plane-mode-active');

      fireEvent.click(uploadModeBtn);
      expect(uploadModeBtn.className).toContain('kb-plane-mode-active');
      expect(pasteModeBtn.className).not.toContain('kb-plane-mode-active');

      unmount();
    }
    document.documentElement.removeAttribute('data-theme');
  });
});
