/**
 * System Status Hook (KB-P3-34, S6.2).
 * Queries /api/v1/system/status to determine deployment mode, air-gap, and persistence.
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { qk } from '../api/queryKeys';

export interface SystemStatus {
  readonly deployment_mode: 'standalone_embedded_pg' | 'standalone' | 'multi_container';
  readonly persistent_volume: boolean;
  readonly air_gap_mode: boolean;
  readonly local_llm_endpoint_host: string | null;
  readonly is_server_admin?: boolean;
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
  return useQuery({
    queryKey: qk.systemStatus(),
    queryFn: ({ signal }) => fetchSystemStatus(signal),
    staleTime: 60000,
  });
}
