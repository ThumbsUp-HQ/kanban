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

  it('downloadPortableExport includes X-CSRF-Token if getCsrfToken returns a token', async () => {
    vi.spyOn(clientModule, 'getCsrfToken').mockReturnValueOnce('existing-csrf-token');
    const mockBlob = new Blob(['data'], { type: 'application/gzip' });
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      status: 200,
      blob: () => Promise.resolve(mockBlob),
    } as unknown as Response);

    await downloadPortableExport({});
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/admin/exports/portable',
      expect.objectContaining({
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/gzip, application/octet-stream, application/json',
          'X-CSRF-Token': 'existing-csrf-token',
        },
      }),
    );
  });

  it('downloadPortableExport handles 403 CSRF refresh and retries successfully', async () => {
    vi.spyOn(clientModule, 'getCsrfToken').mockReturnValueOnce('stale-token');
    const bootstrapSpy = vi.spyOn(clientModule, 'bootstrapCsrfToken').mockResolvedValueOnce('fresh-token');
    const mockBlob = new Blob(['data'], { type: 'application/gzip' });

    const fetchSpy = vi.spyOn(global, 'fetch')
      .mockResolvedValueOnce({
        ok: false,
        status: 403,
      } as unknown as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        blob: () => Promise.resolve(mockBlob),
      } as unknown as Response);

    const blob = await downloadPortableExport({});
    expect(bootstrapSpy).toHaveBeenCalledWith(undefined, true);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(blob).toBe(mockBlob);
  });

  it('downloadPortableExport handles 403 CSRF refresh returning undefined without retrying', async () => {
    vi.spyOn(clientModule, 'getCsrfToken').mockReturnValueOnce('stale-token');
    vi.spyOn(clientModule, 'bootstrapCsrfToken').mockResolvedValueOnce(undefined as unknown as string);

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 403,
      json: () => Promise.resolve({ detail: 'CSRF token missing' }),
    } as unknown as Response);

    await expect(downloadPortableExport({})).rejects.toThrow('CSRF token missing');
  });

  it('downloadPortableExport extracts error message from error or message fields or fallback', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ message: 'Invalid workspace slug' }),
    } as unknown as Response);
    await expect(downloadPortableExport({})).rejects.toThrow('Invalid workspace slug');

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ error: 'Bad request format' }),
    } as unknown as Response);
    await expect(downloadPortableExport({})).rejects.toThrow('Bad request format');

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ unknown_prop: 'something' }),
    } as unknown as Response);
    await expect(downloadPortableExport({})).rejects.toThrow('Export failed with HTTP 400');

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 502,
      json: () => Promise.reject(new Error('Non-JSON gateway error')),
    } as unknown as Response);
    await expect(downloadPortableExport({})).rejects.toThrow('Export failed with HTTP 502');
  });
});
