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

export type OAuthClientStatus = 'active' | 'suspended' | 'disabled' | 'revoked';

export interface OAuthClientItem {
  client_id: string;
  client_name?: string | null | undefined;
  client_type: 'confidential' | 'public';
  redirect_uris: string[];
  status: OAuthClientStatus;
  created_at: string;
  updated_at?: string | null | undefined;
}

export interface PatchOAuthClientRequest {
  status?: OAuthClientStatus | undefined;
  client_name?: string | undefined;
  redirect_uris?: string[] | undefined;
}

export async function fetchAdminOAuthClients(): Promise<OAuthClientItem[]> {
  return (await apiFetch('GET', '/api/v1/admin/oauth-clients' as never)) as OAuthClientItem[];
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

export async function deleteAdminOAuthClient(clientId: string): Promise<void> {
  await apiFetch('DELETE', '/api/v1/admin/oauth-clients/{client_id}' as never, {
    params: { client_id: clientId },
  });
}
