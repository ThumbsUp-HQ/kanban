/**
 * Copyright 2026 Kanban Platform Contributors
 * Apache-2.0 License. See LICENSE for details.
 *
 * REST API Client for Report Templates and Multi-Format Export Engine (KB-JINJA-REPORTS).
 */

export interface ReportTemplate {
  id: string;
  workspace_id: string;
  project_id?: string | null | undefined;
  slug: string;
  name: string;
  description?: string | null | undefined;
  is_builtin: boolean;
  template_markdown: string;
  parameters_schema_json: Array<{
    name: string;
    label: string;
    type: string;
    default?: string | undefined;
    required?: boolean | undefined;
  }> | Record<string, unknown>;
  csv_columns_json: Array<{ header: string; expr: string }>;
  allowed_formats: string[];
  created_by_user_id?: string | null | undefined;
  created_at: string;
  updated_at: string;
}

export interface ReportPreviewResponse {
  rendered_content: string;
  format: string;
  issue_count: number;
}

export interface GenerateReportParams {
  template_ref: string;
  format: string;
  parameters?: Record<string, unknown> | undefined;
  issue_ids?: string[] | undefined;
  filter_query?: string | undefined;
  zip_password?: string | undefined;
}

function getCsrfTokenFromCookie(): string | null {
  if (typeof document === 'undefined') {
    return null;
  }
  const match = /(?:^|;\s*)(?:__Host-kb_csrf|kb_csrf)=([^;]+)/.exec(document.cookie);
  const token = match?.[1];
  return token ? decodeURIComponent(token) : null;
}

function buildHeaders(extraHeaders: Record<string, string> = {}): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...extraHeaders,
  };
  const csrf = getCsrfTokenFromCookie();
  if (csrf) {
    headers['x-kb-csrf'] = csrf;
  }
  return headers;
}

export async function fetchReportTemplates(
  workspaceRef: string,
  projectRef?: string | undefined,
): Promise<ReportTemplate[]> {
  const query = projectRef ? `?project_ref=${encodeURIComponent(projectRef)}` : '';
  const res = await fetch(`/api/v1/workspaces/${encodeURIComponent(workspaceRef)}/report-templates${query}`, {
    method: 'GET',
    headers: buildHeaders(),
  });
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to fetch report templates: ${res.statusText}`);
  }
  const data = await res.json();
  return data.items || [];
}

export async function fetchReportTemplate(
  workspaceRef: string,
  templateRef: string,
): Promise<ReportTemplate> {
  const res = await fetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceRef)}/report-templates/${encodeURIComponent(templateRef)}`,
    {
      method: 'GET',
      headers: buildHeaders(),
    },
  );
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to fetch report template: ${res.statusText}`);
  }
  return await res.json();
}

export async function createReportTemplate(
  workspaceRef: string,
  payload: {
    slug: string;
    name: string;
    description?: string | undefined;
    project_id?: string | undefined;
    template_markdown: string;
    parameters_schema_json?: Record<string, unknown> | Array<unknown> | undefined;
    csv_columns_json?: Array<{ header: string; expr: string }> | undefined;
    allowed_formats?: string[] | undefined;
  },
): Promise<ReportTemplate> {
  const res = await fetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceRef)}/report-templates`,
    {
      method: 'POST',
      headers: buildHeaders(),
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to create report template: ${res.statusText}`);
  }
  return await res.json();
}

export async function updateReportTemplate(
  workspaceRef: string,
  templateRef: string,
  payload: {
    name?: string | undefined;
    description?: string | undefined;
    template_markdown?: string | undefined;
    parameters_schema_json?: Record<string, unknown> | Array<unknown> | undefined;
    csv_columns_json?: Array<{ header: string; expr: string }> | undefined;
    allowed_formats?: string[] | undefined;
  },
): Promise<ReportTemplate> {
  const res = await fetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceRef)}/report-templates/${encodeURIComponent(templateRef)}`,
    {
      method: 'PATCH',
      headers: buildHeaders(),
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to update report template: ${res.statusText}`);
  }
  return await res.json();
}

export async function deleteReportTemplate(
  workspaceRef: string,
  templateRef: string,
): Promise<void> {
  const res = await fetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceRef)}/report-templates/${encodeURIComponent(templateRef)}`,
    {
      method: 'DELETE',
      headers: buildHeaders(),
    },
  );
  if (!res.ok && res.status !== 204) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to delete report template: ${res.statusText}`);
  }
}

export async function previewReport(
  workspaceRef: string,
  params: {
    template_ref?: string | undefined;
    template_markdown?: string | undefined;
    project_ref?: string | undefined;
    parameters?: Record<string, unknown> | undefined;
    issue_ids?: string[] | undefined;
    format?: string | undefined;
  },
): Promise<ReportPreviewResponse> {
  const res = await fetch(
    `/api/v1/workspaces/${encodeURIComponent(workspaceRef)}/reports/preview`,
    {
      method: 'POST',
      headers: buildHeaders(),
      body: JSON.stringify(params),
    },
  );
  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to render preview: ${res.statusText}`);
  }
  return await res.json();
}

export async function generateReport(
  target: { workspaceRef?: string | undefined; projectRef?: string | undefined },
  params: GenerateReportParams,
): Promise<{ blob: Blob; filename: string }> {
  let url: string;
  if (target.projectRef) {
    url = `/api/v1/projects/${encodeURIComponent(target.projectRef)}/reports/generate`;
  } else if (target.workspaceRef) {
    url = `/api/v1/workspaces/${encodeURIComponent(target.workspaceRef)}/reports/generate`;
  } else {
    throw new Error('Either projectRef or workspaceRef must be supplied to generate report.');
  }

  const res = await fetch(url, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(params),
  });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || `Failed to generate report export: ${res.statusText}`);
  }

  const disposition = res.headers.get('content-disposition') || '';
  let filename = `report.${params.format.toLowerCase()}`;
  const match = /filename=["']?([^"';]+)["']?/.exec(disposition);
  const matchedFilename = match?.[1];
  if (matchedFilename) {
    filename = matchedFilename;
  }

  const blob = await res.blob();
  return { blob, filename };
}
