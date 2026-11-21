// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export type ImportSource = 'plane' | 'jira' | 'github' | 'linear';

export interface GenericImportRequest {
  bundle_name?: string | null | undefined;
  bundle_data?: unknown;
  project_key?: string | null | undefined;
  dry_run: boolean;
  user_map?: Record<string, string> | undefined;
  workspace_slug?: string | null | undefined;
}

export type PlaneImportRequest = GenericImportRequest;

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

export interface PortableExportRequest {
  workspace_slug?: string | null | undefined;
  scrub_text?: boolean | undefined;
}

export async function submitImport(
  source: ImportSource,
  payload: GenericImportRequest,
): Promise<ImportDiffReport> {
  const endpoint = `/api/v1/admin/imports/${source}`;
  return (await apiFetch('POST', endpoint as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as ImportDiffReport;
}

export async function submitPlaneImport(
  payload: PlaneImportRequest,
): Promise<ImportDiffReport> {
  return submitImport('plane', payload);
}

export async function submitJiraImport(
  payload: GenericImportRequest,
): Promise<ImportDiffReport> {
  return submitImport('jira', payload);
}

export async function submitGitHubImport(
  payload: GenericImportRequest,
): Promise<ImportDiffReport> {
  return submitImport('github', payload);
}

export async function submitLinearImport(
  payload: GenericImportRequest,
): Promise<ImportDiffReport> {
  return submitImport('linear', payload);
}

export async function downloadPortableExport(
  req: PortableExportRequest,
): Promise<Blob> {
  const response = await fetch('/api/v1/admin/exports/portable', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/gzip, application/octet-stream, application/json',
    },
    credentials: 'same-origin',
    body: JSON.stringify({
      workspace_slug: req.workspace_slug ?? undefined,
      scrub: Boolean(req.scrub_text),
    }),
  });
  if (!response.ok) {
    let errMsg = `Export failed with HTTP ${String(response.status)}`;
    try {
      const errJson = (await response.json()) as { detail?: string };
      if (errJson.detail) errMsg = errJson.detail;
    } catch {
      // fallback
    }
    throw new Error(errMsg);
  }
  return await response.blob();
}
