// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export type ScopeTier = 'personal_user' | 'project' | 'workspace' | 'global' | 'server';
export type OwnerKind = 'personal_user' | 'service_bot';

export interface McpApiKeyItem {
  id: string;
  label: string;
  display_hint: string;
  surface: 'agent' | 'docs' | 'admin';
  scope_tier: ScopeTier;
  owner_kind?: OwnerKind | undefined;
  scopes: string[];
  allowed_projects: string[] | null;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  disabled_tools?: string[];
  allowed_tools?: string[] | null;
  allowed_cidrs?: string[] | null;
  capability_mask?: number | undefined;
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
  owner_kind?: OwnerKind | undefined;
  project_ref?: string | undefined;
  allowed_projects?: string[] | undefined;
  expires_in_days?: number | null | undefined;
  unlimited?: boolean | undefined;
  confirm_unlimited?: boolean | undefined;
  disabled_tools?: string[] | undefined;
  allowed_tools?: string[] | undefined;
  capability_mask?: number | undefined;
  allowed_cidrs?: string[] | null | undefined;
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
    allowed_cidrs: raw.allowed_cidrs ?? null,
    ...(raw.capability_mask !== undefined ? { capability_mask: raw.capability_mask } : {}),
    ...(raw.owner_kind !== undefined ? { owner_kind: raw.owner_kind } : {}),
    ...(raw.raw_key !== undefined ? { raw_key: raw.raw_key } : {}),
  };
}

export interface FetchMcpKeysOptions {
  view?: 'mine' | 'governance' | undefined;
  scope_tier?: string | undefined;
  project_ref?: string | undefined;
  surface?: string | undefined;
}

export async function fetchUnifiedMcpKeys(options?: FetchMcpKeysOptions): Promise<McpApiKeyItem[]> {
  const query = new URLSearchParams();
  if (options?.view) query.set('view', options.view);
  if (options?.scope_tier && options.scope_tier !== 'all') {
    query.set('scope_tier', options.scope_tier);
  }
  if (options?.project_ref) query.set('project_ref', options.project_ref);
  if (options?.surface) query.set('surface', options.surface);

  const qs = query.toString();
  const endpoint = `/api/v1/mcp-keys${qs ? `?${qs}` : ''}`;
  const res = (await apiFetch('GET', endpoint as never)) as
    | McpKeyListResponse
    | McpApiKeyItem[];
  const items = Array.isArray(res) ? res : res.keys;
  return items.map((item) => normalizeMcpKeyItem(item));
}

export async function mintUnifiedMcpKey(payload: MintMcpKeyRequest): Promise<McpApiKeyItem> {
  const created = (await apiFetch('POST', '/api/v1/mcp-keys' as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as McpApiKeyItem;
  return normalizeMcpKeyItem(created, payload.label);
}

export async function revokeUnifiedMcpKey(keyId: string): Promise<void> {
  await apiFetch('DELETE', '/api/v1/mcp-keys/{key_id}' as never, {
    params: { key_id: keyId },
  });
}

export async function fetchPersonalMcpKeys(tier?: string): Promise<McpApiKeyItem[]> {
  const endpoint = tier === 'global' ? '/api/v1/admin/mcp-keys' : '/api/v1/auth/mcp-keys';
  const res = (await apiFetch('GET', endpoint as never)) as
    | McpKeyListResponse
    | McpApiKeyItem[];
  const items = Array.isArray(res) ? res : res.keys;
  return items.map((item) => normalizeMcpKeyItem(item));
}

export async function mintPersonalMcpKey(
  payload: MintMcpKeyRequest,
  tier?: string,
): Promise<McpApiKeyItem> {
  const endpoint = tier === 'global' ? '/api/v1/admin/mcp-keys' : '/api/v1/auth/mcp-keys';
  const created = (await apiFetch('POST', endpoint as never, {
    body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json' },
  })) as McpApiKeyItem;
  return normalizeMcpKeyItem(created, payload.label);
}

export async function revokePersonalMcpKey(keyId: string, tier?: string): Promise<void> {
  const endpoint =
    tier === 'global'
      ? '/api/v1/admin/mcp-keys/{key_id}'
      : '/api/v1/auth/mcp-keys/{key_id}';
  await apiFetch('DELETE', endpoint as never, {
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
