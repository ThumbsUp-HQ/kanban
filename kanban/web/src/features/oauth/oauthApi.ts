// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export interface DeviceCodeInfoResponse {
  user_code: string;
  client_name: string;
  client_id: string;
  resource: string;
  surface: 'agent' | 'docs' | 'admin';
  requested_scopes: string[];
  allowed_projects: string[] | null;
  expires_at: string;
}

export interface DeviceActivateRequest {
  user_code: string;
  approved: boolean;
  scopes?: string[] | undefined;
  allowed_projects?: string[] | undefined;
}

export interface DeviceActivateResponse {
  status: 'approved' | 'denied';
  grant_id?: string;
}

export async function fetchDeviceCodeInfo(userCode: string): Promise<DeviceCodeInfoResponse> {
  return (await apiFetch('GET', '/api/v1/oauth/device/info' as never, {
    query: { user_code: userCode },
  })) as DeviceCodeInfoResponse;
}

export async function submitDeviceActivation(
  payload: DeviceActivateRequest,
): Promise<DeviceActivateResponse> {
  return (await apiFetch('POST', '/api/v1/oauth/device/activate' as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as DeviceActivateResponse;
}

export type OAuthClientStatus =
  | 'active'
  | 'pending_admin_approval'
  | 'suspended'
  | 'disabled'
  | 'revoked';

export interface OAuthClientItem {
  client_id: string;
  client_name?: string | null | undefined;
  client_type: 'confidential' | 'public';
  token_endpoint_auth_method?:
    | 'none'
    | 'private_key_jwt'
    | 'client_secret_basic'
    | 'client_secret_post'
    | undefined;
  redirect_uris: string[];
  status: OAuthClientStatus;
  client_secret?: string | undefined;
  client_secret_prefix?: string | null | undefined;
  created_at: string;
  updated_at?: string | null | undefined;
}

export interface AdminOAuthClientsParams {
  status?: OAuthClientStatus | 'all' | undefined;
  q?: string | undefined;
  limit?: number | undefined;
  offset?: number | undefined;
  envelope?: boolean | undefined;
}

export interface AdminOAuthClientsEnvelope {
  items: OAuthClientItem[];
  total: number;
  limit: number;
  offset: number;
}

export async function fetchAdminOAuthClients(
  params?: AdminOAuthClientsParams,
): Promise<OAuthClientItem[] | AdminOAuthClientsEnvelope> {
  const query: Record<string, string | number | boolean> = {};
  if (params?.status && params.status !== 'all') {
    query.status = params.status;
  }
  if (params?.q) {
    query.q = params.q;
  }
  if (params?.limit !== undefined) {
    query.limit = params.limit;
  }
  if (params?.offset !== undefined) {
    query.offset = params.offset;
  }
  if (params?.envelope !== undefined) {
    query.envelope = params.envelope;
  }

  const opts = Object.keys(query).length > 0 ? { query } : undefined;
  if (opts) {
    return (await apiFetch('GET', '/api/v1/admin/oauth-clients' as never, opts)) as
      | OAuthClientItem[]
      | AdminOAuthClientsEnvelope;
  }
  return (await apiFetch('GET', '/api/v1/admin/oauth-clients' as never)) as
    | OAuthClientItem[]
    | AdminOAuthClientsEnvelope;
}

export interface PatchOAuthClientRequest {
  status?: OAuthClientStatus | undefined;
  client_name?: string | undefined;
  redirect_uris?: string[] | undefined;
}

export async function patchAdminOAuthClient(
  clientId: string,
  payload: PatchOAuthClientRequest,
): Promise<void> {
  await apiFetch('PATCH', '/api/v1/admin/oauth-clients/{client_id}' as never, {
    params: { client_id: clientId },
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  });
}

export interface RegisterOAuthClientRequest {
  client_name?: string | undefined;
  redirect_uris: string[];
  client_type?: 'public' | 'confidential' | undefined;
  token_endpoint_auth_method?:
    | 'none'
    | 'private_key_jwt'
    | 'client_secret_basic'
    | 'client_secret_post'
    | undefined;
  grant_types?: string[] | undefined;
  response_types?: string[] | undefined;
}

export async function registerAdminOAuthClient(
  payload: RegisterOAuthClientRequest,
): Promise<OAuthClientItem> {
  return (await apiFetch('POST', '/api/v1/admin/oauth-clients' as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as OAuthClientItem;
}

export async function deleteAdminOAuthClient(
  clientId: string,
  opts?: { permanent?: boolean },
): Promise<void> {
  const query = opts?.permanent ? { permanent: true } : undefined;
  await apiFetch('DELETE', '/api/v1/admin/oauth-clients/{client_id}' as never, {
    params: { client_id: clientId },
    ...(query ? { query } : {}),
  });
}

export interface BulkDeleteOAuthClientsRequest {
  client_ids?: string[];
  purge_unused_dcr?: boolean;
  purge_revoked?: boolean;
}

export interface BulkDeleteOAuthClientsResponse {
  deleted_count: number;
  deleted_client_ids: string[];
}

export async function bulkDeleteAdminOAuthClients(
  payload: BulkDeleteOAuthClientsRequest,
): Promise<BulkDeleteOAuthClientsResponse> {
  return (await apiFetch('POST', '/api/v1/admin/oauth-clients/bulk-delete' as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as BulkDeleteOAuthClientsResponse;
}
