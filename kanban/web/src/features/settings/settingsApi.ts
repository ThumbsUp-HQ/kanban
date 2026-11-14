// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export type ScopeTier = 'personal_user' | 'project' | 'workspace' | 'global';

export interface McpApiKeyItem {
  id: string;
  label: string;
  display_hint: string;
  surface: 'agent' | 'docs' | 'admin';
  scope_tier: ScopeTier;
  scopes: string[];
  allowed_projects: string[] | null;
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  raw_key?: string | undefined;
}

export interface McpKeyListResponse {
  keys: McpApiKeyItem[];
}

export interface MintMcpKeyRequest {
  label: string;
  surface: 'agent' | 'docs' | 'admin';
  scopes: string[];
  allowed_projects?: string[] | undefined;
  expires_in_days: number;
}

export interface OAuthConnectedApp {
  id: string;
  client_id: string;
  client_name?: string | undefined;
  surface: string;
  scopes: string[];
  allowed_projects: string[] | null;
  created_at: string;
  revoked_at: string | null;
}

export async function fetchPersonalMcpKeys(): Promise<McpApiKeyItem[]> {
  const res = (await apiFetch('GET', '/api/v1/auth/mcp-keys' as never)) as McpKeyListResponse | McpApiKeyItem[];
  if (Array.isArray(res)) {
    return res;
  }
  return res.keys;
}

export async function mintPersonalMcpKey(
  payload: MintMcpKeyRequest,
): Promise<McpApiKeyItem> {
  return (await apiFetch('POST', '/api/v1/auth/mcp-keys' as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as McpApiKeyItem;
}

export async function revokePersonalMcpKey(keyId: string): Promise<void> {
  await apiFetch('DELETE', '/api/v1/auth/mcp-keys/{key_id}' as never, {
    params: { key_id: keyId },
  });
}

export async function fetchConnectedApps(): Promise<OAuthConnectedApp[]> {
  return (await apiFetch('GET', '/api/v1/auth/oauth-grants' as never)) as OAuthConnectedApp[];
}

export async function revokeConnectedApp(grantId: string): Promise<void> {
  await apiFetch('DELETE', '/api/v1/auth/oauth-grants/{grant_id}' as never, {
    params: { grant_id: grantId },
  });
}
