/**
 * Re-export useSystemStatus hook from app layer (KAN-12, KB-P3-AUDIT-06).
 */

import {
  useSystemStatus as useAppSystemStatus,
  fetchSystemStatus as fetchAppSystemStatus,
  type SystemStatus,
} from '../../app/useSystemStatus';

export type { SystemStatus };

export async function fetchSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return await fetchAppSystemStatus(signal);
}

export function useSystemStatus() {
  return useAppSystemStatus();
}
