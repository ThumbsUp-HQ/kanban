// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export interface RemoteRunnerResponse {
  id: string;
  workspace_id: string;
  pool_slug: string;
  hostname: string;
  client_cert_sha256_hex: string;
  cert_expires_at: string;
  capabilities: Record<string, unknown>;
  status: string;
  last_heartbeat_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface MintEnrollmentTokenRequest {
  pool_slug: string;
  ttl_seconds?: number;
}

export interface EnrollmentTokenResponse {
  id: string;
  pool_slug: string;
  enrollment_token: string;
  expires_at: string;
  created_at: string;
}

export async function fetchRemoteRunners(
  poolSlug?: string,
  status?: string,
): Promise<RemoteRunnerResponse[]> {
  const params = new URLSearchParams();
  if (poolSlug) params.append('pool_slug', poolSlug);
  if (status) params.append('status', status);
  const qs = params.toString() ? `?${params.toString()}` : '';
  return (await apiFetch(
    'GET',
    `/api/v1/admin/agent-runners${qs}` as never,
  )) as RemoteRunnerResponse[];
}

export async function mintEnrollmentToken(
  payload: MintEnrollmentTokenRequest,
): Promise<EnrollmentTokenResponse> {
  return (await apiFetch('POST', '/api/v1/admin/agent-runners/enrollment-tokens' as never, {
    body: payload,
  })) as EnrollmentTokenResponse;
}

export async function revokeRemoteRunner(
  runnerId: string,
): Promise<{ id: string; status: string; revoked_at: string }> {
  return (await apiFetch(
    'POST',
    `/api/v1/admin/agent-runners/${encodeURIComponent(runnerId)}:revoke` as never,
  )) as { id: string; status: string; revoked_at: string };
}
