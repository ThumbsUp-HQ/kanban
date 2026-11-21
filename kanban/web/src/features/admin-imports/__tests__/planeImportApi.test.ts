// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import * as clientModule from '../../../api/client';
import {
  submitPlaneImport,
  submitJiraImport,
  submitGitHubImport,
  submitLinearImport,
  submitImport,
  downloadPortableExport,
} from '../planeImportApi';

describe('planeImportApi', () => {
  const mockReport = {
    to_create: 10,
    to_update: 2,
    unchanged: 1,
    sequence_high_water_mark: 13,
    unmapped_members: [],
    rewritten_attachments: 0,
    invalid_link_count: 0,
    warnings: [],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('submitPlaneImport calls POST /api/v1/admin/imports/plane with payload', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce(mockReport);

    const res = await submitPlaneImport({
      dry_run: true,
      bundle_data: { projects: [] },
    });

    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/admin/imports/plane', {
      body: JSON.stringify({
        dry_run: true,
        bundle_data: { projects: [] },
      }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res).toEqual(mockReport);
  });

  it('submitJiraImport calls POST /api/v1/admin/imports/jira', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce(mockReport);
    const res = await submitJiraImport({
      dry_run: true,
      bundle_data: { issues: [] },
      project_key: 'JIRA',
    });
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/admin/imports/jira', {
      body: JSON.stringify({
        dry_run: true,
        bundle_data: { issues: [] },
        project_key: 'JIRA',
      }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res).toEqual(mockReport);
  });

  it('submitGitHubImport calls POST /api/v1/admin/imports/github', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce(mockReport);
    const res = await submitGitHubImport({
      dry_run: false,
      bundle_data: [],
      project_key: 'GH',
    });
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/admin/imports/github', {
      body: JSON.stringify({
        dry_run: false,
        bundle_data: [],
        project_key: 'GH',
      }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res).toEqual(mockReport);
  });

  it('submitLinearImport calls POST /api/v1/admin/imports/linear', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce(mockReport);
    const res = await submitLinearImport({
      dry_run: true,
      bundle_data: 'id,title,state\n1,Issue,Done',
      project_key: 'LIN',
    });
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/admin/imports/linear', {
      body: JSON.stringify({
        dry_run: true,
        bundle_data: 'id,title,state\n1,Issue,Done',
        project_key: 'LIN',
      }),
      headers: { 'Content-Type': 'application/json' },
    });
    expect(res).toEqual(mockReport);
  });

  it('submitImport dispatches to specified source', async () => {
    const spy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValueOnce(mockReport);
    await submitImport('jira', { dry_run: true });
    expect(spy).toHaveBeenCalledWith('POST', '/api/v1/admin/imports/jira', {
      body: JSON.stringify({ dry_run: true }),
      headers: { 'Content-Type': 'application/json' },
    });
  });

  it('downloadPortableExport sends request to /api/v1/admin/exports/portable and returns blob', async () => {
    const mockBlob = new Blob(['tar.gz payload'], { type: 'application/gzip' });
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      status: 200,
      blob: async () => {
        await Promise.resolve();
        return mockBlob;
      },
    } as unknown as Response);

    const blob = await downloadPortableExport({
      workspace_slug: 'test-ws',
      scrub_text: true,
    });

    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/admin/exports/portable', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/gzip, application/octet-stream, application/json',
      },
      credentials: 'same-origin',
      body: JSON.stringify({
        workspace_slug: 'test-ws',
        scrub: true,
      }),
    });
    expect(blob).toBe(mockBlob);
  });

  it('downloadPortableExport throws error on non-ok status', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => {
        await Promise.resolve();
        return { detail: 'Disk full' };
      },
    } as unknown as Response);

    await expect(downloadPortableExport({})).rejects.toThrow('Disk full');
  });
});
