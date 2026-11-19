// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export interface PlaneImportRequest {
  bundle_name?: string | null | undefined;
  bundle_data?: Record<string, unknown> | null | undefined;
  dry_run: boolean;
  user_map?: Record<string, string> | undefined;
  workspace_slug?: string | null | undefined;
}

export interface ImportDiffReport {
  to_create: number;
  to_update: number;
  unchanged: number;
  sequence_high_water_mark: number;
  unmapped_members: string[];
  rewritten_attachments: number;
  invalid_link_count: number;
  warnings: string[];
}

export async function submitPlaneImport(
  payload: PlaneImportRequest,
): Promise<ImportDiffReport> {
  return (await apiFetch('POST', '/api/v1/admin/imports/plane' as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as ImportDiffReport;
}
