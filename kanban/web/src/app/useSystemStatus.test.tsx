import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
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

  it('subscribes to kb:system-status-changed event and invalidates query cache', async () => {
    const mockData1 = {
      deployment_mode: 'multi_container',
      persistent_volume: true,
      air_gap_mode: false,
      local_llm_endpoint_host: null,
    };
    const mockData2 = {
      ...mockData1,
      air_gap_mode: true,
    };

    const fetchSpy = vi.spyOn(window, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(mockData1), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(mockData2), { status: 200 }));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const addEventListenerSpy = vi.spyOn(window, 'addEventListener');
    const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');

    const { result, unmount } = renderHook(() => useSystemStatus(), { wrapper });

    await waitFor(() => { expect(result.current.isSuccess).toBe(true); });
    expect(result.current.data?.air_gap_mode).toBe(false);
    expect(addEventListenerSpy).toHaveBeenCalledWith('kb:system-status-changed', expect.any(Function));

    // Dispatch custom event
    act(() => {
      window.dispatchEvent(new CustomEvent('kb:system-status-changed'));
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    await waitFor(() => {
      expect(result.current.data?.air_gap_mode).toBe(true);
    });

    unmount();
    expect(removeEventListenerSpy).toHaveBeenCalledWith('kb:system-status-changed', expect.any(Function));
  });
});
