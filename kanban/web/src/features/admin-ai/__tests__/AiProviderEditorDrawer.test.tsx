// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { AiProviderEditorDrawer } from '../AiProviderEditorDrawer';
import * as aiApi from '../aiAdminApi';
import type { ProviderConfigPublic } from '../aiAdminApi';

describe('AiProviderEditorDrawer (KAN-60 / KB-AI-STUDIO-01)', () => {
  const mockExistingProvider: ProviderConfigPublic = {
    id: 'prov-existing-1',
    provider_kind: 'gemini',
    display_name: 'Google Gemini Workspace',
    base_url: 'https://generativelanguage.googleapis.com',
    model_allowlist: ['qwen2.5-coder:7b', 'llama3.2:3b'], // stale defaults to be stripped
    residency_tier: 'cloud_standard',
    priority: 10,
    settings: {
      timeout_ms: 45000,
    },
    api_key_set: true,
    is_enabled: true,
    project_id: null,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('enforces DOM order: provider-key-input appears BEFORE probe-models-btn and provider-models-input', () => {
    render(
      <AiProviderEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        provider={null}
        airGapMode={false}
        onSaved={vi.fn()}
      />,
    );

    const keyInput = screen.getByTestId('provider-key-input');
    const probeBtn = screen.getByTestId('probe-models-btn');
    const modelsInput = screen.getByTestId('provider-models-input');
    const baseUrlInput = screen.getByTestId('provider-base-url-input');

    // Key input must appear before baseUrlInput, probeBtn, and modelsInput
    expect(keyInput.compareDocumentPosition(baseUrlInput) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(keyInput.compareDocumentPosition(probeBtn) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(keyInput.compareDocumentPosition(modelsInput) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('initializes new provider with empty modelAllowlist and prominent API Secret Key label', () => {
    render(
      <AiProviderEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        provider={null}
        airGapMode={false}
        onSaved={vi.fn()}
      />,
    );

    // Initial provider is openai (airGapMode=false) -> Prominent "API Secret Key" label
    expect(screen.getByLabelText('API Secret Key')).toBeDefined();

    // Initial modelAllowlist must be empty string (no hardcoded qwen2.5 or gpt-4o defaults)
    const modelsInput = screen.getByTestId<HTMLInputElement>('provider-models-input');
    expect(modelsInput.value).toBe('');
    expect(modelsInput.placeholder).toBe(
      'Click Probe Models above to populate from server, or enter model IDs',
    );

    // Switching providerKind to gemini keeps modelAllowlist empty
    const kindSelect = screen.getByTestId('provider-kind-select');
    fireEvent.change(kindSelect, { target: { value: 'gemini' } });
    expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('');
    expect(screen.getByLabelText('API Secret Key')).toBeDefined();

    // Switching providerKind to ollama displays optional hint
    fireEvent.change(kindSelect, { target: { value: 'ollama' } });
    expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('');
    expect(screen.getByLabelText('API Secret Key (Optional for Local Endpoints)')).toBeDefined();
  });

  it('hydrates Cutoff Timeout (ms) from existing provider and saves updated timeout', async () => {
    const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockExistingProvider);
    const onSaved = vi.fn();
    const onClose = vi.fn();

    render(
      <AiProviderEditorDrawer
        isOpen={true}
        onClose={onClose}
        provider={mockExistingProvider}
        airGapMode={false}
        onSaved={onSaved}
      />,
    );

    const timeoutInput = screen.getByTestId<HTMLInputElement>('provider-timeout-ms-input');
    expect(timeoutInput.value).toBe('45000');
    expect(timeoutInput.min).toBe('1000');
    expect(timeoutInput.max).toBe('300000');
    expect(timeoutInput.step).toBe('1000');

    // Change timeout to 15000
    fireEvent.change(timeoutInput, { target: { value: '15000' } });
    expect(timeoutInput.value).toBe('15000');

    // Submit form
    fireEvent.click(screen.getByTestId('save-provider-btn'));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'prov-existing-1',
        expect.objectContaining({
          settings: {
            timeout_ms: 15000,
          },
        }),
      );
      expect(onSaved).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('replaces modelAllowlist exclusively with probed models and strips stale defaults', async () => {
    const probedModelsList = [
      'gemini-2.5-flash-lite',
      'gemini-2.5-flash',
      'gemini-2.5-pro',
    ];
    const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
      ok: true,
      latency_ms: 112,
      models: probedModelsList,
      model_count: 3,
    });
    const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockExistingProvider);

    render(
      <AiProviderEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        provider={mockExistingProvider} // has stale defaults: ['qwen2.5-coder:7b', 'llama3.2:3b']
        airGapMode={false}
        onSaved={vi.fn()}
      />,
    );

    // Stale models initially present in input
    const modelsInput = screen.getByTestId<HTMLInputElement>('provider-models-input');
    expect(modelsInput.value).toBe('qwen2.5-coder:7b, llama3.2:3b');

    // Probe models
    fireEvent.click(screen.getByTestId('probe-models-btn'));

    await waitFor(() => {
      expect(probeSpy).toHaveBeenCalledWith(
        {
          settings_json: { timeout_ms: 45000 },
        },
        'prov-existing-1',
      );
    });

    // Stale defaults must be stripped and replaced exclusively with probed models
    await waitFor(() => {
      expect(modelsInput.value).toBe(
        'gemini-2.5-flash-lite, gemini-2.5-flash, gemini-2.5-pro',
      );
    });
    expect(modelsInput.value).not.toContain('qwen2.5-coder:7b');
    expect(modelsInput.value).not.toContain('llama3.2:3b');

    // Test "Only This" button for gemini-2.5-flash-lite
    expect(screen.getByTestId('probe-only-gemini-2.5-flash-lite')).toBeDefined();
    fireEvent.click(screen.getByTestId('probe-only-gemini-2.5-flash-lite'));
    expect(modelsInput.value).toBe('gemini-2.5-flash-lite');

    // Click "Select All Probed" restores all probed models without any fake defaults
    fireEvent.click(screen.getByTestId('probe-select-all-btn'));
    expect(modelsInput.value).toBe(
      'gemini-2.5-flash-lite, gemini-2.5-flash, gemini-2.5-pro',
    );
    expect(modelsInput.value).not.toContain('qwen2.5-coder:7b');

    // Toggle chip off (e.g. gemini-2.5-pro)
    fireEvent.click(screen.getByTestId('probe-chip-gemini-2.5-pro'));
    expect(modelsInput.value).toBe('gemini-2.5-flash-lite, gemini-2.5-flash');

    // Save and verify payload
    fireEvent.click(screen.getByTestId('save-provider-btn'));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        'prov-existing-1',
        expect.objectContaining({
          model_allowlist: ['gemini-2.5-flash-lite', 'gemini-2.5-flash'],
          settings: { timeout_ms: 45000 },
        }),
      );
    });
  });

  it('passes configured timeout_ms during draft probe and connection test', async () => {
    const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
      ok: true,
      latency_ms: 40,
      models: ['nemotron-3-super:latest', 'gemma3:4b'],
      model_count: 2,
    });
    const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
      ok: true,
      latency_ms: 38,
      models: ['nemotron-3-super:latest', 'gemma3:4b'],
      model_count: 2,
    });

    render(
      <AiProviderEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        provider={null}
        airGapMode={false}
        onSaved={vi.fn()}
      />,
    );

    // Set custom cutoff timeout 25000
    fireEvent.change(screen.getByTestId('provider-timeout-ms-input'), {
      target: { value: '25000' },
    });

    // Probe models
    fireEvent.click(screen.getByTestId('probe-models-btn'));

    await waitFor(() => {
      expect(probeSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          settings_json: { timeout_ms: 25000 },
        }),
        undefined,
      );
    });

    // Test connection
    fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));

    await waitFor(() => {
      expect(testSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          settings_json: { timeout_ms: 25000 },
        }),
        undefined,
      );
    });
  });
});
