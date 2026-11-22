/**
 * System Status Hook (KB-P3-34, S6.2).
 * Queries /api/v1/system/status to determine deployment mode, air-gap, and persistence.
 */

import { useContext, useEffect } from 'react';
import {
  QueryClient,
  QueryClientContext,
  useQuery,
  type UseQueryResult,
} from '@tanstack/react-query';
import { qk } from '../api/queryKeys';

let fallbackClient: QueryClient | null = null;
function getFallbackQueryClient(): QueryClient {
  fallbackClient ??= new QueryClient();
  return fallbackClient;
}

export interface SystemStatus {
  readonly deployment_mode:
    | 'standalone_embedded_pg'
    | 'standalone'
    | 'production_multi_container'
    | 'multi_container';
  readonly persistent_volume: boolean;
  readonly air_gap_mode: boolean;
  readonly local_llm_endpoint_host: string | null;
  readonly version?: string | null;
  readonly openapi_version?: string | null;
  readonly git_commit?: string | null;
  readonly is_server_admin?: boolean;
  readonly allow_unlimited_mcp_keys?: boolean;
  readonly data_mount_point?: string | null;
  readonly data_mount_fstype?: string | null;
  readonly tier_b_sandbox_available?: boolean;
  readonly supported_custom_field_tiers?: readonly string[];
  readonly sandbox_unavailable_reason?: string | null;
}

export async function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  const res = await fetch('/api/v1/system/status', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
    ...(signal ? { signal } : {}),
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch system status: ${String(res.status)}`);
  }
  return (await res.json()) as SystemStatus;
}

export function useSystemStatus(): UseQueryResult<SystemStatus> {
  const contextClient = useContext(QueryClientContext);
  const queryClient = contextClient ?? getFallbackQueryClient();

  useEffect(() => {
    if (!contextClient) return;
    const handleStatusChanged = (): void => {
      void queryClient.invalidateQueries({ queryKey: ['system', 'status'] });
    };
    window.addEventListener('kb:system-status-changed', handleStatusChanged);
    return () => {
      window.removeEventListener('kb:system-status-changed', handleStatusChanged);
    };
  }, [contextClient, queryClient]);

  return useQuery(
    {
      queryKey: qk.systemStatus(),
      queryFn: ({ signal }) => fetchSystemStatus(signal),
      staleTime: 60000,
      enabled: Boolean(contextClient),
    },
    queryClient,
  );
}
