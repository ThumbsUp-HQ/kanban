// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as client from '../../../api/client';
import {
  createAiProvider,
  deleteAiProvider,
  disableAiProvider,
  fetchAirGapMode,
  fetchAiProvider,
  fetchAiProviders,
  fetchBudgets,
  inferResidencyTier,
  isLocalEndpoint,
  probeAiModels,
  reorderAiProviders,
  setBudget,
  testAiConnection,
  updateAiProvider,
} from '../aiAdminApi';

describe('aiAdminApi tests (KAN-21)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetchAirGapMode calls /api/v1/workspaces/{workspace}/ai-providers/settings and returns air_gap_mode boolean', async () => {
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValueOnce({
      air_gap_mode: true,
    });

    const result = await fetchAirGapMode();
    expect(result).toBe(true);
    expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/workspaces/current/ai-providers/settings');

    fetchSpy.mockResolvedValueOnce({ air_gap_mode: false });
    expect(await fetchAirGapMode('my-team')).toBe(false);
    expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/workspaces/my-team/ai-providers/settings');

    fetchSpy.mockRejectedValueOnce(new Error('Network error'));
    expect(await fetchAirGapMode()).toBe(false);
  });

  it('reorderAiProviders calls PUT /api/v1/workspaces/current/ai-providers/order with ordered_ids', async () => {
    const mockReturnedProviders = [
      { id: 'id-1', priority: 10, display_name: 'Provider 1' },
      { id: 'id-2', priority: 20, display_name: 'Provider 2' },
    ];
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValueOnce(mockReturnedProviders);

    const orderedIds = ['id-1', 'id-2'];
    const res = await reorderAiProviders(orderedIds);
    expect(res).toEqual(mockReturnedProviders);
    expect(fetchSpy).toHaveBeenCalledWith('PUT', '/api/v1/workspaces/current/ai-providers/order', {
      body: { ordered_ids: orderedIds, project_id: undefined },
    });
  });

  it('probeAiModels calls unsaved and saved probe endpoints correctly', async () => {
    const mockProbeResult = {
      ok: true,
      latency_ms: 45.2,
      models: ['qwen2.5-coder:7b', 'llama3.2:3b'],
      model_count: 2,
      error_code: null,
      message: 'Successfully connected',
    };
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue(mockProbeResult);

    // Unsaved draft probe
    const resDraft = await probeAiModels({
      provider_kind: 'ollama',
      base_url: 'http://127.0.0.1:11434',
    });
    expect(resDraft).toEqual(mockProbeResult);
    expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/workspaces/current/ai-providers/probe-models', {
      body: {
        provider_kind: 'ollama',
        base_url: 'http://127.0.0.1:11434',
      },
    });

    // Saved provider probe
    const resSaved = await probeAiModels(
      { provider_kind: 'openai' },
      'p-1234-uuid',
    );
    expect(resSaved).toEqual(mockProbeResult);
    expect(fetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/workspaces/current/ai-providers/p-1234-uuid/probe-models',
      {
        body: { provider_kind: 'openai' },
      },
    );
  });

  it('testAiConnection calls unsaved and saved test-connection endpoints correctly', async () => {
    const mockTestResult = {
      ok: true,
      latency_ms: 32.1,
      models: ['gpt-4o'],
      model_count: 1,
      error_code: null,
      message: 'Connection successful',
    };
    const fetchSpy = vi.spyOn(client, 'apiFetch').mockResolvedValue(mockTestResult);

    // Unsaved draft test
    const resDraft = await testAiConnection({
      provider_kind: 'openai',
      base_url: 'https://api.openai.com/v1',
      api_key: 'sk-test',
    });
    expect(resDraft).toEqual(mockTestResult);
    expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/workspaces/current/ai-providers/test-connection', {
      body: {
        provider_kind: 'openai',
        base_url: 'https://api.openai.com/v1',
        api_key: 'sk-test',
      },
    });

    // Saved provider test
    const resSaved = await testAiConnection(
      { provider_kind: 'gemini' },
      'p-5678-uuid',
    );
    expect(resSaved).toEqual(mockTestResult);
    expect(fetchSpy).toHaveBeenCalledWith(
      'POST',
      '/api/v1/workspaces/current/ai-providers/p-5678-uuid/test-connection',
      {
        body: { provider_kind: 'gemini' },
      },
    );
  });

  it('exercises CRUD endpoints in aiAdminApi', async () => {
    const mockProvider = {
      id: 'prov-1',
      provider_kind: 'ollama',
      display_name: 'Local Ollama',
      model_allowlist: ['qwen2.5-coder:7b'],
      residency_tier: 'local',
      priority: 10,
      settings: {},
      api_key_set: false,
      is_enabled: true,
    };
    const fetchSpy = vi.spyOn(client, 'apiFetch');

    // fetchAiProviders
    fetchSpy.mockResolvedValueOnce([mockProvider]);
    expect(await fetchAiProviders()).toEqual([mockProvider]);
    expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/workspaces/current/ai-providers');

    // fetchAiProviders with projectId
    fetchSpy.mockResolvedValueOnce([mockProvider]);
    expect(await fetchAiProviders('proj-123')).toEqual([mockProvider]);
    expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/workspaces/current/ai-providers?project_id=proj-123');

    // fetchAiProvider
    fetchSpy.mockResolvedValueOnce(mockProvider);
    expect(await fetchAiProvider('prov-1')).toEqual(mockProvider);
    expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/workspaces/current/ai-providers/prov-1');

    // createAiProvider
    fetchSpy.mockResolvedValueOnce(mockProvider);
    expect(await createAiProvider({ provider_kind: 'ollama', display_name: 'Local' })).toEqual(mockProvider);
    expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/workspaces/current/ai-providers', {
      body: { provider_kind: 'ollama', display_name: 'Local' },
    });

    // updateAiProvider
    fetchSpy.mockResolvedValueOnce(mockProvider);
    expect(await updateAiProvider('prov-1', { display_name: 'Updated' })).toEqual(mockProvider);
    expect(fetchSpy).toHaveBeenCalledWith('PATCH', '/api/v1/workspaces/current/ai-providers/prov-1', {
      body: { display_name: 'Updated' },
    });

    // disableAiProvider
    fetchSpy.mockResolvedValueOnce(mockProvider);
    expect(await disableAiProvider('prov-1')).toEqual(mockProvider);
    expect(fetchSpy).toHaveBeenCalledWith('POST', '/api/v1/workspaces/current/ai-providers/prov-1:disable');

    // deleteAiProvider
    fetchSpy.mockResolvedValueOnce(undefined);
    await deleteAiProvider('prov-1');
    expect(fetchSpy).toHaveBeenCalledWith('DELETE', '/api/v1/workspaces/current/ai-providers/prov-1');

    // fetchBudgets
    const mockBudget = {
      period_kind: 'daily',
      period_start: '2026-11-19',
      token_cap: 100000,
      tokens_used: 120,
      tokens_reserved: 0,
    };
    fetchSpy.mockResolvedValueOnce([mockBudget]);
    expect(await fetchBudgets('prov-1')).toEqual([mockBudget]);
    expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/workspaces/current/ai-providers/budgets?provider_config_id=prov-1');

    // setBudget
    fetchSpy.mockResolvedValueOnce(mockBudget);
    expect(await setBudget({ provider_config_id: 'prov-1', period_kind: 'daily', token_cap: 100000 })).toEqual(mockBudget);
    expect(fetchSpy).toHaveBeenCalledWith('PUT', '/api/v1/workspaces/current/ai-providers/budgets', {
      body: { provider_config_id: 'prov-1', period_kind: 'daily', token_cap: 100000 },
    });
  });

  describe('isLocalEndpoint and inferResidencyTier (KAN-22)', () => {
    it('correctly classifies local vs cloud endpoints across protocols and addresses', () => {
      // Ollama is always local
      expect(isLocalEndpoint('ollama', null)).toBe(true);
      expect(isLocalEndpoint('ollama', '')).toBe(true);
      expect(isLocalEndpoint('ollama', 'http://127.0.0.1:11434')).toBe(true);
      expect(isLocalEndpoint('ollama', 'https://remote-box.org:11434')).toBe(true);

      // Loopback
      expect(isLocalEndpoint('openai', 'http://localhost:8000/v1')).toBe(true);
      expect(isLocalEndpoint('openai', 'http://127.0.0.1:11434')).toBe(true);
      expect(isLocalEndpoint('openai', 'http://[::1]:8000/v1')).toBe(true);

      // RFC 1918 IPv4
      expect(isLocalEndpoint('openai', 'http://10.0.1.5:8000/v1')).toBe(true);
      expect(isLocalEndpoint('openai', 'http://172.16.0.1:8000')).toBe(true);
      expect(isLocalEndpoint('openai', 'http://172.31.255.255:8000')).toBe(true);
      expect(isLocalEndpoint('openai', 'http://172.15.0.1:8000')).toBe(false);
      expect(isLocalEndpoint('openai', 'http://172.32.0.1:8000')).toBe(false);
      expect(isLocalEndpoint('openai', 'http://192.168.1.100:11434')).toBe(true);
      expect(isLocalEndpoint('openai', 'http://169.254.10.10:8000')).toBe(true);

      // LAN hostnames
      expect(isLocalEndpoint('openai', 'http://gpu-rig.local:8000/v1')).toBe(true);
      expect(isLocalEndpoint('openai', 'http://cluster.lan:8000')).toBe(true);
      expect(isLocalEndpoint('openai', 'http://inference.internal:8000')).toBe(true);

      // IPv6 ULA
      expect(isLocalEndpoint('openai', 'http://[fc00::1]:8000/v1')).toBe(true);
      expect(isLocalEndpoint('openai', 'http://[fd12:3456::1]:8000/v1')).toBe(true);

      // Public / Cloud
      expect(isLocalEndpoint('openai', 'https://api.openai.com/v1')).toBe(false);
      expect(isLocalEndpoint('gemini', 'https://generativelanguage.googleapis.com')).toBe(false);
      expect(isLocalEndpoint('openai', 'https://1.1.1.1:8000')).toBe(false);
      expect(isLocalEndpoint('openai', null)).toBe(false);
      expect(isLocalEndpoint('openai', '')).toBe(false);
      expect(isLocalEndpoint('gemini', undefined)).toBe(false);

      // Invalid URL fallback handling
      expect(isLocalEndpoint('openai', 'not-a-valid-url-localhost-proxy')).toBe(true);
      expect(isLocalEndpoint('openai', 'not-a-valid-url-remote')).toBe(false);
    });

    it('infers residency tier as local_only or cloud_standard', () => {
      expect(inferResidencyTier('ollama', null)).toBe('local_only');
      expect(inferResidencyTier('openai', 'http://127.0.0.1:8000/v1')).toBe('local_only');
      expect(inferResidencyTier('openai', 'http://192.168.1.50:11434')).toBe('local_only');
      expect(inferResidencyTier('openai', 'https://api.openai.com/v1')).toBe('cloud_standard');
      expect(inferResidencyTier('gemini', 'https://generativelanguage.googleapis.com')).toBe('cloud_standard');
      expect(inferResidencyTier('gemini', null)).toBe('cloud_standard');
    });
  });
});
