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
