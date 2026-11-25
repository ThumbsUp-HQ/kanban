// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { apiFetch } from '../../api/client';

export interface ProviderConfigPublic {
  id: string;
  provider_kind: string;
  display_name: string;
  base_url?: string | null;
  model_allowlist: string[];
  residency_tier: string;
  priority: number;
  settings: Record<string, unknown>;
  api_key_set: boolean;
  is_enabled: boolean;
  project_id?: string | null;
}

export interface ProviderConfigCreate {
  provider_kind: string;
  display_name: string;
  model_allowlist?: string[];
  residency_tier?: string;
  base_url?: string | null;
  priority?: number;
  settings?: Record<string, unknown>;
  project_id?: string | null;
  is_enabled?: boolean;
  api_key?: string | null;
}

export interface ProviderConfigUpdate {
  display_name?: string;
  model_allowlist?: string[];
  residency_tier?: string;
  base_url?: string | null;
  priority?: number;
  settings?: Record<string, unknown>;
  is_enabled?: boolean;
  api_key?: string | null;
}

export interface BudgetRecord {
  period_kind: 'daily' | 'monthly';
  period_start: string;
  token_cap: number;
  tokens_used: number;
  tokens_reserved: number;
}

export interface BudgetSetRequest {
  provider_config_id: string;
  project_id?: string | null | undefined;
  period_kind: 'daily' | 'monthly';
  token_cap: number;
}

export async function fetchAiProviders(
  projectId?: string,
  workspace = 'current',
): Promise<ProviderConfigPublic[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  return (await apiFetch(
    'GET',
    `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers${query}` as never,
  )) as ProviderConfigPublic[];
}

export async function fetchAiProvider(
  providerId: string,
  workspace = 'current',
): Promise<ProviderConfigPublic> {
  return (await apiFetch(
    'GET',
    `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/${encodeURIComponent(providerId)}` as never,
  )) as ProviderConfigPublic;
}

export async function createAiProvider(
  payload: ProviderConfigCreate,
  workspace = 'current',
): Promise<ProviderConfigPublic> {
  return (await apiFetch(
    'POST',
    `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers` as never,
    { body: payload },
  )) as ProviderConfigPublic;
}

export async function updateAiProvider(
  providerId: string,
  payload: ProviderConfigUpdate,
  workspace = 'current',
): Promise<ProviderConfigPublic> {
  return (await apiFetch(
    'PATCH',
    `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/${encodeURIComponent(providerId)}` as never,
    {
      body: payload,
    },
  )) as ProviderConfigPublic;
}

export async function disableAiProvider(
  providerId: string,
  workspace = 'current',
): Promise<ProviderConfigPublic> {
  return (await apiFetch(
    'POST',
    `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/${encodeURIComponent(providerId)}:disable` as never,
  )) as ProviderConfigPublic;
}

export async function deleteAiProvider(
  providerId: string,
  workspace = 'current',
): Promise<void> {
  await apiFetch(
    'DELETE',
    `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/${encodeURIComponent(providerId)}` as never,
  );
}

export async function fetchBudgets(
  providerConfigId: string,
  workspace = 'current',
): Promise<BudgetRecord[]> {
  return (await apiFetch(
    'GET',
    `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/budgets?provider_config_id=${encodeURIComponent(providerConfigId)}` as never,
  )) as BudgetRecord[];
}

export async function setBudget(
  payload: BudgetSetRequest,
  workspace = 'current',
): Promise<BudgetRecord> {
  return (await apiFetch(
    'PUT',
    `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/budgets` as never,
    { body: payload },
  )) as BudgetRecord;
}

export interface ProviderProbeRequest {
  provider_kind?: string;
  base_url?: string | null;
  api_key?: string | null;
  settings_json?: Record<string, unknown> | null;
  project_id?: string | null;
}

export function isLocalEndpoint(providerKind: string, baseUrl?: string | null): boolean {
  if (providerKind === 'ollama') return true;
  if (!baseUrl?.trim()) return false;
  try {
    const parsed = new URL(baseUrl.trim());
    const hostname = parsed.hostname.toLowerCase().replace(/^\[|\]$/g, '');
    if (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname === '::1' ||
      hostname.endsWith('.local') ||
      hostname.endsWith('.lan') ||
      hostname.endsWith('.internal')
    ) {
      return true;
    }
    const parts = hostname.split('.').map((p) => Number(p));
    if (parts.length === 4 && parts.every((p) => !isNaN(p) && p >= 0 && p <= 255)) {
      if (parts[0] === 127) return true;
      if (parts[0] === 10) return true;
      if (parts[0] === 172 && parts[1] !== undefined && parts[1] >= 16 && parts[1] <= 31) return true;
      if (parts[0] === 192 && parts[1] === 168) return true;
      if (parts[0] === 169 && parts[1] === 254) return true;
    }
    if (hostname.startsWith('fc') || hostname.startsWith('fd') || hostname === '::1') {
      return true;
    }
  } catch {
    const raw = baseUrl.trim().toLowerCase();
    if (raw.includes('localhost') || raw.includes('127.0.0.1')) return true;
  }
  return false;
}

export function inferResidencyTier(
  providerKind: string,
  baseUrl?: string | null,
): 'local_only' | 'cloud_standard' {
  return isLocalEndpoint(providerKind, baseUrl) ? 'local_only' : 'cloud_standard';
}

export interface ProviderProbeResult {
  ok: boolean;
  latency_ms: number;
  models: string[];
  model_count: number;
  error_code?: string | null;
  message?: string | null;
}

export async function fetchAirGapMode(workspace = 'current'): Promise<boolean> {
  try {
    const res = (await apiFetch(
      'GET',
      `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/settings` as never,
    )) as { air_gap_mode?: boolean };
    return Boolean(res.air_gap_mode);
  } catch {
    return false;
  }
}

export async function reorderAiProviders(
  orderedIds: string[],
  projectId?: string,
  workspace = 'current',
): Promise<ProviderConfigPublic[]> {
  return (await apiFetch(
    'PUT',
    `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/order` as never,
    {
      body: { ordered_ids: orderedIds, project_id: projectId ?? undefined },
    },
  )) as ProviderConfigPublic[];
}

export async function probeAiModels(
  payload: ProviderProbeRequest,
  providerId?: string,
  workspace = 'current',
): Promise<ProviderProbeResult> {
  const path = providerId
    ? `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/${encodeURIComponent(providerId)}/probe-models`
    : `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/probe-models`;
  return (await apiFetch('POST', path as never, { body: payload })) as ProviderProbeResult;
}

export async function testAiConnection(
  payload: ProviderProbeRequest,
  providerId?: string,
  workspace = 'current',
): Promise<ProviderProbeResult> {
  const path = providerId
    ? `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/${encodeURIComponent(providerId)}/test-connection`
    : `/api/v1/workspaces/${encodeURIComponent(workspace)}/ai-providers/test-connection`;
  return (await apiFetch('POST', path as never, { body: payload })) as ProviderProbeResult;
}
