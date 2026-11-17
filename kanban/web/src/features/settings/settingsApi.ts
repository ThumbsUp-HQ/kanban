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
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  disabled_tools?: string[];
  allowed_tools?: string[] | null;
  allowed_cidrs?: string[] | null;
  raw_key?: string | undefined;
}

export interface McpKeyListResponse {
  keys: McpApiKeyItem[];
}

export interface MintMcpKeyRequest {
  label: string;
  surface: 'agent' | 'docs' | 'admin';
  scopes: string[];
  scope_tier?: ScopeTier | undefined;
  allowed_projects?: string[] | undefined;
  expires_in_days?: number | null | undefined;
  unlimited?: boolean | undefined;
  confirm_unlimited?: boolean | undefined;
  disabled_tools?: string[] | undefined;
  allowed_tools?: string[] | undefined;
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

function normalizeMcpKeyItem(
  raw: Partial<McpApiKeyItem> & { id: string; surface: 'agent' | 'docs' | 'admin' },
  fallbackLabel?: string,
): McpApiKeyItem {
  return {
    id: raw.id,
    label: raw.label ?? fallbackLabel ?? raw.display_hint ?? 'MCP Key',
    display_hint: raw.display_hint ?? '',
    surface: raw.surface,
    scope_tier: raw.scope_tier ?? 'personal_user',
    scopes: raw.scopes ?? [],
    allowed_projects: raw.allowed_projects ?? null,
    created_at: raw.created_at ?? '',
    expires_at: raw.expires_at ?? null,
    last_used_at: raw.last_used_at ?? null,
    revoked_at: raw.revoked_at ?? null,
    disabled_tools: raw.disabled_tools ?? [],
    allowed_tools: raw.allowed_tools ?? null,
    ...(raw.raw_key !== undefined ? { raw_key: raw.raw_key } : {}),
  };
}

export async function fetchPersonalMcpKeys(): Promise<McpApiKeyItem[]> {
  const res = (await apiFetch('GET', '/api/v1/auth/mcp-keys' as never)) as
    | McpKeyListResponse
    | McpApiKeyItem[];
  const items = Array.isArray(res) ? res : res.keys;
  return items.map((item) => normalizeMcpKeyItem(item));
}

export async function mintPersonalMcpKey(
  payload: MintMcpKeyRequest,
): Promise<McpApiKeyItem> {
  const created = (await apiFetch('POST', '/api/v1/auth/mcp-keys' as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as McpApiKeyItem;
  return normalizeMcpKeyItem(created, payload.label);
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
