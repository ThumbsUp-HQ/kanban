import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useSystemStatus, fetchSystemStatus } from './useSystemStatus';

describe('features/system/useSystemStatus', () => {
  it('calls underlying fetchSystemStatus and useSystemStatus', async () => {
    const mockData = {
      deployment_mode: 'multi_container' as const,
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
    };

    vi.spyOn(window, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(mockData), { status: 200 }),
    );

    const res = await fetchSystemStatus();
    expect(res).toEqual(mockData);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useSystemStatus(), { wrapper });
    expect(result.current).toBeDefined();
  });
});
