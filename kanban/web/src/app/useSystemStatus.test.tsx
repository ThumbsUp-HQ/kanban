import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useSystemStatus, fetchSystemStatus } from './useSystemStatus';

describe('useSystemStatus', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetchSystemStatus returns parsed status when response is ok', async () => {
    const mockData = {
      deployment_mode: 'multi_container',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: 'http://ollama:11434',
    };

    vi.spyOn(window, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockData), { status: 200 }),
    );

    const result = await fetchSystemStatus();
    expect(result).toEqual(mockData);
  });

  it('fetchSystemStatus throws error when response is not ok', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValueOnce(
      new Response('Internal error', { status: 500 }),
    );

    await expect(fetchSystemStatus()).rejects.toThrow(
      'Failed to fetch system status: 500',
    );
  });

  it('useSystemStatus hook queries and returns data', async () => {
    const mockData = {
      deployment_mode: 'standalone',
      persistent_volume: false,
      air_gap_mode: true,
      local_llm_endpoint_host: null,
    };

    vi.spyOn(window, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(mockData), { status: 200 }),
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useSystemStatus(), { wrapper });

    await waitFor(() => { expect(result.current.isSuccess).toBe(true); });
    expect(result.current.data).toEqual(mockData);
  });
});
