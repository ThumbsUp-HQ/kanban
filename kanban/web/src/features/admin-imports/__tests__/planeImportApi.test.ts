// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, expect, it, vi, beforeEach } from 'vitest';
import * as clientModule from '../../../api/client';
import { submitPlaneImport } from '../planeImportApi';

describe('planeImportApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('submitPlaneImport calls POST /api/v1/admin/imports/plane with payload', async () => {
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
});
