// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

export type OutputFormatType =
  | 'text'
  | 'number'
  | 'badge'
  | 'markdown_snippet'
  | 'url'
  | 'json_table'
  | 'severity_pill';

export type CustomFieldTargetScope = 'PROJECT' | 'WORKSPACE' | 'SERVER';
export type CustomFieldCredentialMode = 'INVOKING_USER' | 'PROJECT_ADMIN_SP' | 'SERVER_ADMIN_SP';
export type CustomFieldTier = 'wasm' | 'nsjail';
export type CustomFieldApprovalStatus =
  | 'PENDING'
  | 'PENDING_SECOND_APPROVER'
  | 'APPROVED'
  | 'REVOKED';

export interface CustomFieldDefinition {
  id: string;
  workspace_id?: string;
  project_id?: string;
  slug: string;
  name: string;
  tier: CustomFieldTier;
  output_format: OutputFormatType;
  output_format_metadata: Record<string, unknown>;
  script_source?: string;
  wasm_module_sha256?: string | null;
  script_version?: number;
  target_scope: CustomFieldTargetScope;
  credential_mode: CustomFieldCredentialMode;
  egress_allowlist: string[];
  manifest_sha256?: string | null;
  is_enabled: boolean;
  approval_status?: CustomFieldApprovalStatus | null;
  required_approver_tier?: string | null;
  created_by_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CustomFieldExecutionResult {
  field_id: string;
  field_slug: string;
  field_name: string;
  output_format: OutputFormatType;
  output_format_metadata?: Record<string, unknown>;
  value: unknown;
  status: 'SUCCESS' | 'ERROR';
  error_code?: string;
  error_message?: string;
  tier: 'Wasmtime' | 'nsjail';
  token_scope: CustomFieldTargetScope;
  credential_mode: CustomFieldCredentialMode;
  last_latency_ms: number;
  computed_at: string;
}

export interface CustomFieldApproval {
  id: string;
  field_id: string;
  status: CustomFieldApprovalStatus;
  target_scope: CustomFieldTargetScope;
  credential_mode: CustomFieldCredentialMode;
  manifest_sha256: string;
  primary_approver_id?: string | null;
  secondary_approver_id?: string | null;
  justification: string;
  sp_warning_acknowledged?: boolean;
  revoked_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomFieldCreatePayload {
  slug: string;
  name: string;
  tier?: CustomFieldTier;
  output_format: OutputFormatType;
  output_format_metadata?: Record<string, unknown>;
  script_source: string;
  target_scope?: CustomFieldTargetScope;
  credential_mode?: CustomFieldCredentialMode;
  egress_allowlist?: string[];
  is_enabled?: boolean;
}

export interface CustomFieldUpdatePayload {
  name?: string;
  tier?: CustomFieldTier;
  output_format?: OutputFormatType;
  output_format_metadata?: Record<string, unknown>;
  script_source?: string;
  target_scope?: CustomFieldTargetScope;
  credential_mode?: CustomFieldCredentialMode;
  egress_allowlist?: string[];
  is_enabled?: boolean;
}

export const qk = {
  customFields: {
    project: (projectKey: string) => ['custom-fields', 'project', projectKey] as const,
    issue: (issueKey: string) => ['custom-fields', 'issue', issueKey] as const,
    approvals: (fieldId: string) => ['custom-fields', 'approvals', fieldId] as const,
  },
};

/**
 * Get CSRF token from cookie if available
 */
function getCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = /(?:^|;\s*)(?:__Host-)?kb_csrf=([^;]+)/.exec(document.cookie);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function getCsrfHeaders(): Record<string, string> {
  const token = getCsrfToken();
  return token ? { 'X-CSRF-Token': token } : {};
}

export interface ApiError extends Error {
  status: number;
  code?: string;
}

export function createApiError(message: string, status: number, code?: string): ApiError {
  const err = new Error(message) as ApiError;
  err.status = status;
  if (code !== undefined) {
    err.code = code;
  }
  return err;
}

/**
 * Parse error response safely
 */
async function parseErrorBody(res: Response): Promise<{ code?: string; detail?: string }> {
  try {
    return (await res.json()) as { code?: string; detail?: string };
  } catch {
    return {};
  }
}

/**
 * Fetch all custom field definitions visible for a project.
 */
export async function fetchProjectCustomFields(
  projectKey: string,
): Promise<CustomFieldDefinition[]> {
  const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectKey)}/custom-fields`);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error(`Failed to fetch custom fields: ${String(res.status)}`);
  }
  return (await res.json()) as CustomFieldDefinition[];
}

/**
 * Fetch cached/computed custom field execution values for an issue.
 */
export async function fetchIssueCustomFields(
  issueKey: string,
): Promise<CustomFieldExecutionResult[]> {
  const res = await fetch(`/api/v1/issues/${encodeURIComponent(issueKey)}/custom-fields`);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error(`Failed to fetch issue custom fields: ${String(res.status)}`);
  }
  return (await res.json()) as CustomFieldExecutionResult[];
}

/**
 * Force refresh execution of a custom field for an issue.
 */
export async function executeCustomField(
  issueKey: string,
  fieldId: string,
): Promise<CustomFieldExecutionResult> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getCsrfHeaders(),
  };

  const res = await fetch(
    `/api/v1/issues/${encodeURIComponent(issueKey)}/custom-fields/${encodeURIComponent(fieldId)}/execute`,
    {
      method: 'POST',
      headers,
    },
  );
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw createApiError(
      errorBody.code ?? `Execution failed with status ${String(res.status)}`,
      res.status,
      errorBody.code,
    );
  }
  return (await res.json()) as CustomFieldExecutionResult;
}

/**
 * Create a new custom field definition (admin only).
 */
export async function createCustomField(
  projectKey: string,
  body: CustomFieldCreatePayload,
): Promise<CustomFieldDefinition> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getCsrfHeaders(),
  };

  const res = await fetch(`/api/v1/projects/${encodeURIComponent(projectKey)}/custom-fields`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw createApiError(
      errorBody.detail ?? `Create failed with status ${String(res.status)}`,
      res.status,
      errorBody.code,
    );
  }
  return (await res.json()) as CustomFieldDefinition;
}

/**
 * Update an existing custom field definition (admin only).
 */
export async function updateCustomField(
  projectKey: string,
  fieldId: string,
  body: CustomFieldUpdatePayload,
): Promise<CustomFieldDefinition> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getCsrfHeaders(),
  };

  const res = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectKey)}/custom-fields/${encodeURIComponent(fieldId)}`,
    {
      method: 'PATCH',
      headers,
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw createApiError(
      errorBody.detail ?? `Update failed with status ${String(res.status)}`,
      res.status,
      errorBody.code,
    );
  }
  return (await res.json()) as CustomFieldDefinition;
}

/**
 * Delete a custom field definition (admin only).
 */
export async function deleteCustomField(projectKey: string, fieldId: string): Promise<void> {
  const headers: Record<string, string> = {
    ...getCsrfHeaders(),
  };

  const res = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectKey)}/custom-fields/${encodeURIComponent(fieldId)}`,
    {
      method: 'DELETE',
      headers,
    },
  );
  if (!res.ok && res.status !== 204) {
    throw new Error(`Delete failed with status ${String(res.status)}`);
  }
}

/**
 * Request escalation approval for a custom field.
 */
export async function requestFieldApproval(
  fieldId: string,
  body: { manifest_sha256: string; justification: string },
): Promise<CustomFieldApproval> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getCsrfHeaders(),
  };

  const res = await fetch(
    `/api/v1/custom-fields/${encodeURIComponent(fieldId)}/approval-requests`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw createApiError(
      errorBody.detail ?? `Approval request failed with status ${String(res.status)}`,
      res.status,
      errorBody.code,
    );
  }
  return (await res.json()) as CustomFieldApproval;
}

/**
 * Approve a custom field escalation request.
 */
export async function approveFieldEscalation(
  approvalId: string,
  body: { manifest_sha256: string; sp_warning_acknowledged?: boolean },
): Promise<CustomFieldApproval> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getCsrfHeaders(),
  };

  const res = await fetch(
    `/api/v1/custom-field-approvals/${encodeURIComponent(approvalId)}/approve`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) {
    const errorBody = await parseErrorBody(res);
    throw createApiError(
      errorBody.detail ?? `Approve failed with status ${String(res.status)}`,
      res.status,
      errorBody.code,
    );
  }
  return (await res.json()) as CustomFieldApproval;
}

/**
 * Fetch escalation approval history for a custom field.
 */
export async function fetchFieldApprovals(fieldId: string): Promise<CustomFieldApproval[]> {
  const res = await fetch(`/api/v1/custom-fields/${encodeURIComponent(fieldId)}/approvals`);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error(`Failed to fetch approvals: ${String(res.status)}`);
  }
  return (await res.json()) as CustomFieldApproval[];
}
