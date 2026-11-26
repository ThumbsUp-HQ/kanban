// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import {
  AiProviderEditorDrawer,
  computeNextApiKey,
  MASK_BULLET,
} from '../AiProviderEditorDrawer';
import * as aiApi from '../aiAdminApi';
import type { ProviderConfigPublic } from '../aiAdminApi';
import { Aal2StepUpCancelledError } from '../../../api/client';
import * as webSudoModule from '../../../components/help/WebSudoModalHost';

describe('AiProviderEditorDrawer (KAN-60 / KB-AI-STUDIO-01 & KAN-400)', () => {
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

  const mockProviderWithFullSettings: ProviderConfigPublic = {
    id: 'prov-full-1',
    provider_kind: 'openai',
    display_name: 'OpenAI Full Settings',
    base_url: 'https://api.openai.com/v1',
    model_allowlist: ['gpt-4o'],
    residency_tier: 'cloud', // tests legacy 'cloud' -> 'cloud_standard'
    priority: 20,
    settings: {
      timeout_ms: 20000,
      temperature: 0.5,
      top_p: 0.8,
      max_tokens: 2048,
      mtls_client_cert_pem: '-----BEGIN CERTIFICATE-----\nCERT\n-----END CERTIFICATE-----',
    },
    api_key_set: true,
    is_enabled: true,
    project_id: null,
  };

  const mockProviderLocalTier: ProviderConfigPublic = {
    id: 'prov-local-1',
    provider_kind: 'ollama',
    display_name: 'Local Ollama',
    base_url: 'http://127.0.0.1:11434',
    model_allowlist: ['llama3.2:3b'],
    residency_tier: 'local', // tests legacy 'local' -> 'local_only'
    priority: 30,
    settings: {},
    api_key_set: false,
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
    expect(screen.getByLabelText(/API Secret Key/i, { selector: 'input' })).toBeDefined();

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
    expect(screen.getByLabelText(/API Secret Key/i, { selector: 'input' })).toBeDefined();

    // Switching providerKind to ollama displays optional hint
    fireEvent.change(kindSelect, { target: { value: 'ollama' } });
    expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('');
    expect(screen.getByLabelText(/API Secret Key/i, { selector: 'input' })).toBeDefined();

    // Switching back to openai
    fireEvent.change(kindSelect, { target: { value: 'openai' } });
    expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('');
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
    expect(timeoutInput.max).toBe('600000');
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

    // Toggle chip back on (covers exists === false in toggleModel)
    fireEvent.click(screen.getByTestId('probe-chip-gemini-2.5-pro'));
    expect(modelsInput.value).toBe('gemini-2.5-flash-lite, gemini-2.5-flash, gemini-2.5-pro');

    // Toggle off again before save
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

  it('Case 2: renders provider type with temperature and mTLS certs collapsed in AdvancedSection', () => {
    render(
      <AiProviderEditorDrawer
        isOpen={true}
        onClose={vi.fn()}
        provider={null}
        airGapMode={false}
        onSaved={vi.fn()}
      />,
    );

    // Provider Kind select is visible at top level
    const kindSelect = screen.getByTestId('provider-kind-select');
    expect(kindSelect).toBeDefined();

    // Advanced section is present and collapsed by default
    const advancedSection = screen.getByTestId('advanced-settings-details');
    expect(advancedSection).toBeDefined();
    expect(advancedSection.hasAttribute('open')).toBe(false);

    // Expand the advanced section
    const toggle = screen.getByTestId('advanced-settings-details-toggle');
    fireEvent.click(toggle);

    expect(advancedSection.hasAttribute('open')).toBe(true);

    // Temperature and mTLS cert fields are now accessible
    expect(screen.getByTestId('provider-temperature-input')).toBeDefined();
    expect(screen.getByTestId('provider-mtls-cert-input')).toBeDefined();
  });

  // =========================================================================
  // KAN-400: Browser Password-Manager Suppression & Zero input[type=password]
  // =========================================================================

  describe('KAN-400: Browser Password-Manager Suppression & Masking', () => {
    it('renders form and inputs with strict password-manager suppression attributes and zero input[type=password]', () => {
      const { container } = render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // 1. Form must declare autoComplete="off" and data-form-type="other"
      const form = container.querySelector('form');
      expect(form).not.toBeNull();
      expect(form?.getAttribute('autocomplete')).toBe('off');
      expect(form?.getAttribute('data-form-type')).toBe('other');

      // 2. provider-name-input must have anti-credential-manager attributes
      const nameInput = screen.getByTestId('provider-name-input');
      expect(nameInput.getAttribute('type')).toBe('text');
      expect(nameInput.getAttribute('autocomplete')).toBe('off');
      expect(nameInput.getAttribute('data-1p-ignore')).toBe('true');
      expect(nameInput.getAttribute('data-lpignore')).toBe('true');
      expect(nameInput.getAttribute('data-bwignore')).toBe('true');
      expect(nameInput.getAttribute('data-form-type')).toBe('other');

      // 3. provider-key-input must strictly be type="text" and have ignore attributes
      const keyInput = screen.getByTestId('provider-key-input');
      expect(keyInput.getAttribute('type')).toBe('text');
      expect(keyInput.getAttribute('autocomplete')).toBe('off');
      expect(keyInput.getAttribute('spellcheck')).toBe('false');
      expect(keyInput.getAttribute('autocorrect')).toBe('off');
      expect(keyInput.getAttribute('autocapitalize')).toBe('off');
      expect(keyInput.getAttribute('inputmode')).toBe('text');
      expect(keyInput.getAttribute('data-1p-ignore')).toBe('true');
      expect(keyInput.getAttribute('data-lpignore')).toBe('true');
      expect(keyInput.getAttribute('data-bwignore')).toBe('true');
      expect(keyInput.getAttribute('data-form-type')).toBe('other');

      // 4. In both masked and revealed states, ZERO input[type=password] elements exist anywhere in the drawer
      expect(container.querySelectorAll('input[type="password"]').length).toBe(0);

      // Toggle show key to revealed state
      const toggleBtn = screen.getByTestId('toggle-show-key-btn');
      fireEvent.click(toggleBtn);
      expect(keyInput.getAttribute('type')).toBe('text');
      expect(container.querySelectorAll('input[type="password"]').length).toBe(0);

      // Toggle back to masked state
      fireEvent.click(toggleBtn);
      expect(keyInput.getAttribute('type')).toBe('text');
      expect(container.querySelectorAll('input[type="password"]').length).toBe(0);
    });

    it('Chromium / WebKit mode (CSS.supports true): applies .kb-masked-api-key without modifying DOM value', async () => {
      // Mock Chromium CSS.supports('-webkit-text-security', 'disc') === true
      const origCSS = globalThis.CSS;
      globalThis.CSS = {
        supports: vi.fn().mockImplementation((prop: string, val: string) => {
          return prop === '-webkit-text-security' && val === 'disc';
        }),
      } as unknown as typeof CSS;

      const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue({
        ...mockExistingProvider,
        id: 'prov-created-1',
      });
      const onSaved = vi.fn();
      const onClose = vi.fn();

      try {
        render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={onClose}
            provider={null}
            airGapMode={false}
            onSaved={onSaved}
          />,
        );

        const keyInput = screen.getByTestId<HTMLInputElement>('provider-key-input');
        const toggleBtn = screen.getByTestId('toggle-show-key-btn');

        // Enter key in Chromium mode
        fireEvent.change(keyInput, { target: { value: 'sk-chromium-gemini-secret-12345' } });

        // DOM value stays exact plaintext while .kb-masked-api-key handles visual masking natively
        expect(keyInput.value).toBe('sk-chromium-gemini-secret-12345');
        expect(keyInput.className).toContain('kb-masked-api-key');

        // Toggle revealed -> .kb-masked-api-key removed
        fireEvent.click(toggleBtn);
        expect(keyInput.value).toBe('sk-chromium-gemini-secret-12345');
        expect(keyInput.className).not.toContain('kb-masked-api-key');

        // Toggle back to masked -> .kb-masked-api-key re-added
        fireEvent.click(toggleBtn);
        expect(keyInput.value).toBe('sk-chromium-gemini-secret-12345');
        expect(keyInput.className).toContain('kb-masked-api-key');

        // Submit form -> uncorrupted exact api_key submitted
        fireEvent.click(screen.getByTestId('save-provider-btn'));

        await waitFor(() => {
          expect(createSpy).toHaveBeenCalledWith(
            expect.objectContaining({
              api_key: 'sk-chromium-gemini-secret-12345',
            }),
          );
          expect(onSaved).toHaveBeenCalled();
          expect(onClose).toHaveBeenCalled();
        });
      } finally {
        globalThis.CSS = origCSS;
      }
    });

    it('Firefox / Gecko mode (CSS.supports false): renders bullet mask and submits exact uncorrupted api_key', async () => {
      // Mock Firefox where CSS.supports returns false
      const origCSS = globalThis.CSS;
      globalThis.CSS = {
        supports: vi.fn().mockReturnValue(false),
      } as unknown as typeof CSS;

      const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue({
        ...mockExistingProvider,
        id: 'prov-created-ff',
      });
      const onSaved = vi.fn();
      const onClose = vi.fn();

      try {
        render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={onClose}
            provider={null}
            airGapMode={false}
            onSaved={onSaved}
          />,
        );

        const keyInput = screen.getByTestId<HTMLInputElement>('provider-key-input');
        const toggleBtn = screen.getByTestId('toggle-show-key-btn');

        // Enter key in Firefox mode
        const testKey = 'sk-firefox-test-key-999';
        fireEvent.change(keyInput, { target: { value: testKey } });

        // When masked, DOM value displays exact bullets matching key length
        expect(keyInput.value).toBe(MASK_BULLET.repeat(testKey.length));
        expect(keyInput.className).toContain('kb-masked-api-key');

        // Reveal key -> displays plaintext
        fireEvent.click(toggleBtn);
        expect(keyInput.value).toBe(testKey);
        expect(keyInput.className).not.toContain('kb-masked-api-key');

        // Re-mask key -> displays bullets again
        fireEvent.click(toggleBtn);
        expect(keyInput.value).toBe(MASK_BULLET.repeat(testKey.length));
        expect(keyInput.className).toContain('kb-masked-api-key');

        // Submit form -> submits exact plaintext key, NEVER bullet glyphs!
        fireEvent.click(screen.getByTestId('save-provider-btn'));

        await waitFor(() => {
          expect(createSpy).toHaveBeenCalledWith(
            expect.objectContaining({
              api_key: testKey,
            }),
          );
          expect(onSaved).toHaveBeenCalled();
          expect(onClose).toHaveBeenCalled();
        });
      } finally {
        globalThis.CSS = origCSS;
      }
    });

    it('Firefox / Gecko mode: handles character typing, backspace, and pasting over masked input', () => {
      const origCSS = globalThis.CSS;
      globalThis.CSS = {
        supports: vi.fn().mockReturnValue(false),
      } as unknown as typeof CSS;

      try {
        render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={vi.fn()}
            provider={null}
            airGapMode={false}
            onSaved={vi.fn()}
          />,
        );

        const keyInput = screen.getByTestId<HTMLInputElement>('provider-key-input');
        const toggleBtn = screen.getByTestId('toggle-show-key-btn');

        // 1. Initial typing from empty
        fireEvent.change(keyInput, { target: { value: 'abc' } });
        expect(keyInput.value).toBe('•••');

        // 2. Typing 'd' at end of masked value
        fireEvent.change(keyInput, {
          target: { value: '•••d', selectionStart: 4 },
        });
        expect(keyInput.value).toBe('••••');

        // Reveal to verify 'abcd'
        fireEvent.click(toggleBtn);
        expect(keyInput.value).toBe('abcd');
        fireEvent.click(toggleBtn); // re-mask

        // 3. Backspace at end (cursor at 3, value is '•••')
        fireEvent.change(keyInput, {
          target: { value: '•••', selectionStart: 3 },
        });
        expect(keyInput.value).toBe('•••');
        fireEvent.click(toggleBtn);
        expect(keyInput.value).toBe('abc');
        fireEvent.click(toggleBtn); // re-mask

        // 4. Backspace in middle (deleting 'b', cursor at 1, value is '••')
        fireEvent.change(keyInput, {
          target: { value: '••', selectionStart: 1 },
        });
        expect(keyInput.value).toBe('••');
        fireEvent.click(toggleBtn);
        expect(keyInput.value).toBe('ac');
        fireEvent.click(toggleBtn); // re-mask

        // 5. Pasting replacement token over whole masked string
        fireEvent.change(keyInput, {
          target: { value: 'pasted-replacement-secret', selectionStart: 25 },
        });
        expect(keyInput.value).toBe(MASK_BULLET.repeat('pasted-replacement-secret'.length));
        fireEvent.click(toggleBtn);
        expect(keyInput.value).toBe('pasted-replacement-secret');

        // 6. Clear input completely
        fireEvent.change(keyInput, {
          target: { value: '', selectionStart: 0 },
        });
        expect(keyInput.value).toBe('');
      } finally {
        globalThis.CSS = origCSS;
      }
    });
  });

  // =========================================================================
  // computeNextApiKey Unit Tests
  // =========================================================================

  describe('computeNextApiKey unit logic', () => {
    it('handles empty inputs and identical mask', () => {
      expect(computeNextApiKey('', '')).toBe('');
      expect(computeNextApiKey('', 'new-key')).toBe('new-key');
      expect(computeNextApiKey('existing', '')).toBe('');
      expect(computeNextApiKey('abc', '•••')).toBe('abc');
    });

    it('handles typing append, prepend, and middle insertion', () => {
      expect(computeNextApiKey('abc', '•••d', 4)).toBe('abcd');
      expect(computeNextApiKey('abc', 'd•••', 1)).toBe('dabc');
      expect(computeNextApiKey('abcd', '••X••', 3)).toBe('abXcd');
    });

    it('handles backspace and deletion with cursor positions', () => {
      expect(computeNextApiKey('abcd', '•••', 3)).toBe('abc');
      expect(computeNextApiKey('abcd', '•••', 2)).toBe('abd');
      expect(computeNextApiKey('abcd', '•••', 1)).toBe('acd');
      expect(computeNextApiKey('abcd', '•••', 0)).toBe('bcd');
      expect(computeNextApiKey('abcd', '••', 1)).toBe('ad');
      expect(computeNextApiKey('abcd', '•••', null)).toBe('abc'); // default to end delete
      expect(computeNextApiKey('abcd', '•••', -1)).toBe('abc');
      expect(computeNextApiKey('abcd', '•••', 10)).toBe('abc');
    });

    it('handles full replacement paste and partial paste replacement', () => {
      expect(computeNextApiKey('old-secret', 'completely-new-token', 20)).toBe('completely-new-token');
      expect(computeNextApiKey('abcd', '•XYZ•', 4)).toBe('aXYZd');
      expect(computeNextApiKey('abcd', '••••••', 6)).toBe('abcd••');
    });
  });

  // =========================================================================
  // Comprehensive Branch & Function Coverage Booster
  // =========================================================================

  describe('Comprehensive Coverage Booster', () => {
    it('returns null when isOpen is false', () => {
      const { container } = render(
        <AiProviderEditorDrawer
          isOpen={false}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );
      expect(container.firstChild).toBeNull();
    });

    it('displays error and halts submit when display name is blank', async () => {
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      const nameInput = screen.getByTestId('provider-name-input');
      fireEvent.change(nameInput, { target: { value: '   ' } });
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('provider-editor-error')).toBeDefined();
        expect(screen.getByTestId('provider-editor-error').textContent).toContain('Display name is required');
      });
    });

    it('enforces Air-Gap mode restrictions against cloud providers', async () => {
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={true} // airGapMode active
          onSaved={vi.fn()}
        />,
      );

      // Default kind in airGapMode is ollama
      const kindSelect = screen.getByTestId<HTMLSelectElement>('provider-kind-select');
      expect(kindSelect.value).toBe('ollama');
      expect(screen.getByTestId('drawer-air-gap-alert')).toBeDefined();

      // Attempting to change to openai displays error
      fireEvent.change(kindSelect, { target: { value: 'openai' } });
      expect(screen.getByTestId('provider-editor-error').textContent).toContain(
        'Air-Gap mode prohibits configuring cloud providers',
      );

      // Submitting while in invalid air gap state prevents save
      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('provider-editor-error').textContent).toContain(
          'Air-Gap mode prohibits configuring cloud providers',
        );
      });

      // Switching to gemini also displays error
      fireEvent.change(kindSelect, { target: { value: 'gemini' } });
      expect(screen.getByTestId('provider-editor-error').textContent).toContain(
        'Air-Gap mode prohibits configuring cloud providers',
      );

      // Switching back to ollama clears error
      fireEvent.change(kindSelect, { target: { value: 'ollama' } });
      expect(screen.queryByTestId('provider-editor-error')).toBeNull();
    });

    it('hydrates full settings from existing provider and saves with updated key', async () => {
      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockProviderWithFullSettings);
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={onClose}
          provider={mockProviderWithFullSettings}
          airGapMode={false}
          onSaved={onSaved}
        />,
      );

      // Verify hydration of full settings
      expect(screen.getByTestId<HTMLInputElement>('provider-temperature-input').value).toBe('0.5');
      expect(screen.getByTestId<HTMLInputElement>('provider-top-p-input').value).toBe('0.8');
      expect(screen.getByTestId<HTMLInputElement>('provider-max-tokens-input').value).toBe('2048');
      expect(screen.getByTestId<HTMLTextAreaElement>('provider-mtls-cert-input').value).toContain('CERT');

      // Enter a new API key without checking clear key (covers else if (apiKey.trim()) branch)
      const keyInput = screen.getByTestId('provider-key-input');
      fireEvent.change(keyInput, { target: { value: 'sk-updated-new-secret' } });

      // Save
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        const lastCall = updateSpy.mock.lastCall;
        expect(lastCall?.[0]).toBe('prov-full-1');
        expect(lastCall?.[1].api_key).toBe('sk-updated-new-secret');
        expect(lastCall?.[1].residency_tier).toBe('cloud_standard');
        expect(lastCall?.[1].settings).toMatchObject({
          temperature: 0.5,
          top_p: 0.8,
          max_tokens: 2048,
        });
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('hydrates local residency tier and handles clearExistingKey toggle', async () => {
      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockProviderLocalTier);

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProviderLocalTier}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      const residencySelect = screen.getByTestId<HTMLSelectElement>('provider-residency-select');
      expect(residencySelect.value).toBe('local_only');

      // Save
      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          'prov-local-1',
          expect.objectContaining({
            residency_tier: 'local_only',
          }),
        );
      });
    });

    it('handles clear-key checkbox toggled on and then toggled off', async () => {
      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockExistingProvider);

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockExistingProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      const clearCheckbox = screen.getByTestId<HTMLInputElement>('clear-key-checkbox');

      // Check on -> clearExistingKey true
      fireEvent.click(clearCheckbox);
      expect(clearCheckbox.checked).toBe(true);

      // Check off -> clearExistingKey false (covers if (e.target.checked) false branch)
      fireEvent.click(clearCheckbox);
      expect(clearCheckbox.checked).toBe(false);

      // Save provider without key change -> api_key omitted in update payload
      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        const lastCall = updateSpy.mock.lastCall;
        expect(lastCall?.[0]).toBe('prov-existing-1');
        expect(lastCall?.[1].api_key).toBeUndefined();
      });
    });

    it('handles numeric input parsing fallbacks when empty string is provided', () => {
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Expand advanced
      fireEvent.click(screen.getByTestId('advanced-settings-details-toggle'));

      // 1. Timeout ms fallback
      const timeoutInput = screen.getByTestId<HTMLInputElement>('provider-timeout-ms-input');
      fireEvent.change(timeoutInput, { target: { value: '' } });
      expect(timeoutInput.value).toBe('30000');

      // 2. Temperature fallback
      const tempInput = screen.getByTestId<HTMLInputElement>('provider-temperature-input');
      fireEvent.change(tempInput, { target: { value: '' } });
      expect(tempInput.value).toBe('0.7');

      // 3. Top-P fallback
      const topPInput = screen.getByTestId<HTMLInputElement>('provider-top-p-input');
      fireEvent.change(topPInput, { target: { value: '' } });
      expect(topPInput.value).toBe('1');

      // 4. Max Tokens fallback
      const maxTokensInput = screen.getByTestId<HTMLInputElement>('provider-max-tokens-input');
      fireEvent.change(maxTokensInput, { target: { value: '' } });
      expect(maxTokensInput.value).toBe('4096');
    });

    it('handles probe models and test connection for existing provider without draft modifications', async () => {
      const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        latency_ms: 15,
        models: ['probed-model-1'],
        model_count: 1,
      });
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 22,
        models: ['probed-model-1'],
        model_count: 1,
      });

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockExistingProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Probe existing provider
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            settings_json: { timeout_ms: 45000 },
          }),
          'prov-existing-1',
        );
      });

      // Test connection existing provider
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            settings_json: { timeout_ms: 45000 },
          }),
          'prov-existing-1',
        );
      });
    });

    it('handles non-Error rejection on save, probe, and test connection', async () => {
      vi.spyOn(aiApi, 'createAiProvider').mockRejectedValueOnce('raw string error on create');
      vi.spyOn(aiApi, 'probeAiModels').mockRejectedValueOnce('raw string error on probe');
      vi.spyOn(aiApi, 'testAiConnection').mockRejectedValueOnce('raw string error on test');

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Probe non-Error catch
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toContain('Failed to probe models');
      });

      // Test connection non-Error catch
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toContain('Connection test failed');
      });

      // Save non-Error catch
      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('provider-editor-error').textContent).toContain('Failed to save provider configuration');
      });
    });

    it('handles server error response without message on test connection', async () => {
      vi.spyOn(aiApi, 'testAiConnection').mockResolvedValueOnce({
        ok: false,
        latency_ms: 10,
        models: [],
        model_count: 0,
        error_code: 'ERR_UNAVAILABLE',
        // message intentionally omitted
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

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toBe(
          'Connection failed: ERR_UNAVAILABLE',
        );
      });
    });

    it('handles AAL2 step-up cancellation and AIR_GAP_EGRESS_DENIED fallback on probe and test connection', async () => {
      const aal2CancelError = new Error('Step-up cancelled');
      aal2CancelError.name = 'Aal2StepUpCancelledError';

      vi.spyOn(aiApi, 'probeAiModels').mockRejectedValueOnce(aal2CancelError);
      vi.spyOn(aiApi, 'testAiConnection').mockRejectedValueOnce(aal2CancelError);

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      expect(screen.queryByTestId('probe-error')).toBeNull();

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toContain('Testing connection...');
      });

      // Test AIR_GAP_EGRESS_DENIED fallback message
      vi.spyOn(aiApi, 'testAiConnection').mockResolvedValueOnce({
        ok: false,
        latency_ms: 10,
        models: [],
        model_count: 0,
        error_code: 'AIR_GAP_EGRESS_DENIED',
      });

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toContain(
          'Egress denied by Air-Gap policy: cloud endpoints cannot be contacted.',
        );
      });
    });

    it('handles probe error response without message on probe models', async () => {
      vi.spyOn(aiApi, 'probeAiModels').mockResolvedValueOnce({
        ok: false,
        latency_ms: 10,
        models: [],
        model_count: 0,
        error_code: 'CODE_PROBE_FAILED',
        // message intentionally omitted
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

      fireEvent.click(screen.getByTestId('probe-models-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toBe('CODE_PROBE_FAILED');
      });
    });

    it('handles probed models filter with zero matching items', async () => {
      vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        latency_ms: 60,
        models: ['gpt-4o'],
        model_count: 1,
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

      fireEvent.click(screen.getByTestId('probe-models-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('probed-models-picker')).toBeDefined();
      });

      // Filter with non-matching pattern
      fireEvent.change(screen.getByTestId('probe-model-search-input'), {
        target: { value: 'nonexistent-model-xyz' },
      });

      expect(screen.getByText('No matching models found.')).toBeDefined();
    });

    it('invokes onClose when clicking close or cancel buttons', () => {
      const onClose = vi.fn();
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={onClose}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('close-provider-drawer-btn'));
      expect(onClose).toHaveBeenCalledTimes(1);

      fireEvent.click(screen.getByTestId('cancel-provider-drawer-btn'));
      expect(onClose).toHaveBeenCalledTimes(2);
    });

    it('calculates priority when providersCount is provided', async () => {
      const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue({
        ...mockExistingProvider,
        id: 'prov-with-count',
      });

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
          providersCount={4} // next priority: (4 + 1) * 10 = 50
        />,
      );

      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            priority: 50,
          }),
        );
      });
    });

    it('auto-infers residency tier when changing baseUrl and not overridden', () => {
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Expand advanced
      fireEvent.click(screen.getByTestId('advanced-settings-details-toggle'));
      const residencySelect = screen.getByTestId<HTMLSelectElement>('provider-residency-select');
      const baseUrlInput = screen.getByTestId('provider-base-url-input');

      // Change baseUrl to local address -> inferred as local_only
      fireEvent.change(baseUrlInput, { target: { value: 'http://127.0.0.1:8000/v1' } });
      expect(residencySelect.value).toBe('local_only');

      // Change baseUrl back to cloud -> inferred as cloud_standard
      fireEvent.change(baseUrlInput, { target: { value: 'https://api.openai.com/v1' } });
      expect(residencySelect.value).toBe('cloud_standard');
    });

    it('handles manual model allowlist edit, mtls cert, and advanced parameter modification and save', async () => {
      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockExistingProvider);

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockExistingProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Manual model input edit (covers onChange on provider-models-input)
      const modelsInput = screen.getByTestId('provider-models-input');
      fireEvent.change(modelsInput, { target: { value: 'custom-model-alpha, custom-model-beta' } });

      // Expand advanced
      fireEvent.click(screen.getByTestId('advanced-settings-details-toggle'));

      // Change mtls cert
      const mtlsInput = screen.getByTestId('provider-mtls-cert-input');
      fireEvent.change(mtlsInput, { target: { value: '-----BEGIN CERTIFICATE-----\nFOO\n-----END CERTIFICATE-----' } });

      // Change residency select
      const residencySelect = screen.getByTestId('provider-residency-select');
      fireEvent.change(residencySelect, { target: { value: 'eu-central' } });

      // Change temperature, top-p, max-tokens
      fireEvent.change(screen.getByTestId('provider-temperature-input'), { target: { value: '0.3' } });
      fireEvent.change(screen.getByTestId('provider-top-p-input'), { target: { value: '0.4' } });
      fireEvent.change(screen.getByTestId('provider-max-tokens-input'), { target: { value: '1024' } });

      // Save
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        const lastCall = updateSpy.mock.lastCall;
        expect(lastCall?.[0]).toBe('prov-existing-1');
        expect(lastCall?.[1].model_allowlist).toEqual(['custom-model-alpha', 'custom-model-beta']);
        expect(lastCall?.[1].residency_tier).toBe('eu-central');
        expect(lastCall?.[1].settings).toMatchObject({
          temperature: 0.3,
          top_p: 0.4,
          max_tokens: 1024,
          mtls_client_cert_pem: '-----BEGIN CERTIFICATE-----\nFOO\n-----END CERTIFICATE-----',
        });
      });
    });

    it('probes and tests connection when endpoint is modified on existing provider with api key', async () => {
      const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        latency_ms: 30,
        models: ['model-draft-1'],
        model_count: 1,
      });
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 25,
        models: ['model-draft-1'],
        model_count: 1,
      });

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockExistingProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Modify baseUrl and apiKey on existing provider
      fireEvent.click(screen.getByTestId('advanced-settings-details-toggle'));
      fireEvent.change(screen.getByTestId('provider-base-url-input'), {
        target: { value: 'https://new-endpoint.api.com' },
      });
      fireEvent.change(screen.getByTestId('provider-key-input'), {
        target: { value: 'sk-new-key-draft' },
      });

      // Probe models (useDraftEndpoint === true)
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            base_url: 'https://new-endpoint.api.com',
            api_key: 'sk-new-key-draft',
          }),
          undefined, // draft endpoint has no targetProviderId
        );
      });

      // Test connection (useDraftEndpoint === true)
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            base_url: 'https://new-endpoint.api.com',
            api_key: 'sk-new-key-draft',
          }),
          undefined,
        );
      });
    });

    it('handles probe failure with empty error fields and clear models button', async () => {
      vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: false,
        latency_ms: 10,
        models: [],
        model_count: 0,
        error_code: null,
        message: null,
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

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toBe('Model probing failed');
      });
    });

    it('covers kind change on existing provider and non-draft probe with apiKey', async () => {
      const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        latency_ms: 10,
        models: ['model-1'],
        model_count: 1,
      });
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 10,
        models: ['model-1'],
        model_count: 1,
      });

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockExistingProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Change kind on existing provider (covers isEditing branch in handleKindChange)
      const kindSelect = screen.getByTestId('provider-kind-select');
      fireEvent.change(kindSelect, { target: { value: 'openai' } });

      // Enter key without modifying baseUrl (isEndpointModified is true because providerKind modified)
      const keyInput = screen.getByTestId('provider-key-input');
      fireEvent.change(keyInput, { target: { value: 'sk-existing-reauth' } });

      // Probe models
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalled();
      });

      // Test connection
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalled();
      });
    });

    it('covers non-draft probe and connection test with apiKey typed on existing provider', async () => {
      const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        latency_ms: 10,
        models: ['m1'],
        model_count: 1,
      });
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 10,
        models: ['m1'],
        model_count: 1,
      });

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockExistingProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Enter apiKey on existing provider without changing endpoint
      // isEndpointModified is false -> useDraftEndpoint is false
      fireEvent.change(screen.getByTestId('provider-key-input'), {
        target: { value: 'sk-direct-key' },
      });

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            api_key: 'sk-direct-key',
          }),
          'prov-existing-1',
        );
      });

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            api_key: 'sk-direct-key',
          }),
          'prov-existing-1',
        );
      });
    });

    it('submits null base_url when base_url input is empty on create and update', async () => {
      const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue(mockExistingProvider);
      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockExistingProvider);

      // 1. Create with empty base_url
      const { unmount } = render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('advanced-settings-details-toggle'));
      fireEvent.change(screen.getByTestId('provider-base-url-input'), { target: { value: '   ' } });
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            base_url: null,
          }),
        );
      });

      unmount();

      // 2. Update with empty base_url
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockExistingProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('advanced-settings-details-toggle'));
      fireEvent.change(screen.getByTestId('provider-base-url-input'), { target: { value: '' } });
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          'prov-existing-1',
          expect.objectContaining({
            base_url: null,
          }),
        );
      });
    });

    it('handles test connection error response without error_code', async () => {
      vi.spyOn(aiApi, 'testAiConnection').mockResolvedValueOnce({
        ok: false,
        latency_ms: 10,
        models: [],
        model_count: 0,
        error_code: null,
        message: 'Network socket closed',
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

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toBe(
          'Connection failed: ERROR - Network socket closed',
        );
      });
    });

    it('submits api_key null when clearExistingKey is checked on update', async () => {
      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockExistingProvider);
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockExistingProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('clear-key-checkbox'));
      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          'prov-existing-1',
          expect.objectContaining({ api_key: null }),
        );
      });
    });

    it('handles probe models returning zero models warning message', async () => {
      vi.spyOn(aiApi, 'probeAiModels').mockResolvedValueOnce({
        ok: true,
        latency_ms: 10,
        models: [],
        model_count: 0,
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

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toContain(
          'Connected successfully, but 0 models were discovered.',
        );
      });
    });

    it('handles Error instance on save and surfaces error.message', async () => {
      vi.spyOn(aiApi, 'createAiProvider').mockRejectedValueOnce(new Error('KMS encryption timeout'));

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('provider-editor-error').textContent).toContain('KMS encryption timeout');
      });
    });

    it('handles probe error with res.message', async () => {
      vi.spyOn(aiApi, 'probeAiModels').mockResolvedValueOnce({
        ok: false,
        latency_ms: 10,
        models: [],
        model_count: 0,
        error_code: null,
        message: 'Endpoint rejected TLS handshake',
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

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toBe('Endpoint rejected TLS handshake');
      });
    });

    it('creates local ollama provider with api_key null when empty key', async () => {
      const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue(mockProviderLocalTier);

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={true}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            provider_kind: 'ollama',
            api_key: null,
          }),
        );
      });
    });

    it('clears models allowlist when clicking probe-clear-all-btn', async () => {
      vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        latency_ms: 10,
        models: ['gpt-4o', 'o1'],
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

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-clear-all-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('probe-clear-all-btn'));
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('');
    });

    it('supports workspaceSlug routing for create and update provider', async () => {
      const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue({
        id: 'new-prov-id',
        provider_kind: 'openai',
        display_name: 'Custom OpenAi',
        base_url: 'https://api.openai.com/v1',
        model_allowlist: ['gpt-4o'],
        residency_tier: 'cloud_standard',
        priority: 10,
        settings: {},
        api_key_set: true,
        is_enabled: true,
        project_id: null,
      });

      const onSaved = vi.fn();
      const onClose = vi.fn();

      const { rerender } = render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={onClose}
          provider={null}
          airGapMode={false}
          onSaved={onSaved}
          workspaceSlug="engineering"
        />,
      );

      fireEvent.change(screen.getByTestId('provider-name-input'), {
        target: { value: 'Custom OpenAi' },
      });
      fireEvent.change(screen.getByTestId('provider-key-input'), {
        target: { value: 'sk-proj-test123456789' },
      });
      fireEvent.change(screen.getByTestId('provider-models-input'), {
        target: { value: 'gpt-4o' },
      });

      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({ display_name: 'Custom OpenAi' }),
          'engineering',
        );
      });

      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue({
        id: 'existing-prov-id',
        provider_kind: 'openai',
        display_name: 'Updated OpenAi',
        base_url: 'https://api.openai.com/v1',
        model_allowlist: ['gpt-4o'],
        residency_tier: 'cloud_standard',
        priority: 10,
        settings: {},
        api_key_set: true,
        is_enabled: true,
        project_id: null,
      });

      const existingProvider: ProviderConfigPublic = {
        id: 'existing-prov-id',
        provider_kind: 'openai',
        display_name: 'Existing OpenAi',
        base_url: 'https://api.openai.com/v1',
        model_allowlist: ['gpt-4o'],
        residency_tier: 'cloud_standard',
        priority: 10,
        settings: {},
        api_key_set: true,
        is_enabled: true,
        project_id: null,
      };

      rerender(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={onClose}
          provider={existingProvider}
          airGapMode={false}
          onSaved={onSaved}
          workspaceSlug="engineering"
        />,
      );

      fireEvent.change(screen.getByTestId('provider-name-input'), {
        target: { value: 'Updated OpenAi' },
      });

      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          'existing-prov-id',
          expect.objectContaining({ display_name: 'Updated OpenAi' }),
          'engineering',
        );
      });
    });

    it('silently ignores Aal2StepUpCancelledError on save and test connection (KAN-404)', async () => {
      const cancelErr = new Aal2StepUpCancelledError();
      vi.spyOn(aiApi, 'createAiProvider').mockRejectedValue(cancelErr);
      vi.spyOn(aiApi, 'testAiConnection').mockRejectedValue(cancelErr);

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.queryByText('Connection test failed')).toBeNull();
      });

      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(screen.queryByText('Failed to save provider configuration')).toBeNull();
      });
    });

    it('handles test connection and save with projectId, workspaceSlug, and non-Error failures', async () => {
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockRejectedValue('Raw string error');
      const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue({
        ...mockExistingProvider,
        id: 'new-prov-1',
      });
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={onClose}
          provider={null}
          airGapMode={false}
          onSaved={onSaved}
          projectId="proj-test-1"
          workspaceSlug="ws-test-slug"
        />,
      );

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByText('Connection test failed')).toBeDefined();
      });
      expect(testSpy).toHaveBeenCalledWith(
        expect.objectContaining({ project_id: 'proj-test-1' }),
        undefined,
        'ws-test-slug',
      );

      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({ project_id: 'proj-test-1' }),
          'ws-test-slug',
        );
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('tests connection on existing provider with null base_url and projectId', async () => {
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 10,
        model_count: 2,
        models: ['m1'],
      });
      const provNullBase: ProviderConfigPublic = {
        ...mockExistingProvider,
        base_url: null,
      };

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={provNullBase}
          airGapMode={false}
          onSaved={vi.fn()}
          projectId="proj-existing-test"
        />,
      );

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByText(/Connected in 10ms/)).toBeDefined();
      });
      expect(testSpy).toHaveBeenCalledWith(
        expect.objectContaining({ project_id: 'proj-existing-test' }),
        provNullBase.id,
      );
    });

    it('applies 1-click presets for ollama, openai, and gemini', () => {
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Verify preset buttons exist
      expect(screen.getByTestId('preset-ollama-btn')).toBeDefined();
      expect(screen.getByTestId('preset-openai-btn')).toBeDefined();
      expect(screen.getByTestId('preset-gemini-btn')).toBeDefined();

      // Click Ollama preset
      fireEvent.click(screen.getByTestId('preset-ollama-btn'));
      expect(screen.getByTestId<HTMLSelectElement>('provider-kind-select').value).toBe('ollama');
      expect(screen.getByTestId<HTMLInputElement>('provider-name-input').value).toBe('Local Ollama Runtime');
      expect(screen.getByTestId<HTMLInputElement>('provider-base-url-input').value).toBe('http://127.0.0.1:11434');
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('llama3.2, qwen2.5-coder');

      // Click OpenAI preset
      fireEvent.click(screen.getByTestId('preset-openai-btn'));
      expect(screen.getByTestId<HTMLSelectElement>('provider-kind-select').value).toBe('openai');
      expect(screen.getByTestId<HTMLInputElement>('provider-name-input').value).toBe('OpenAI / OpenAI-Compatible');
      expect(screen.getByTestId<HTMLInputElement>('provider-base-url-input').value).toBe('https://api.openai.com/v1');
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('gpt-4o, gpt-4o-mini');

      // Click Gemini preset
      fireEvent.click(screen.getByTestId('preset-gemini-btn'));
      expect(screen.getByTestId<HTMLSelectElement>('provider-kind-select').value).toBe('gemini');
      expect(screen.getByTestId<HTMLInputElement>('provider-name-input').value).toBe('Google Gemini Workspace');
      expect(screen.getByTestId<HTMLInputElement>('provider-base-url-input').value).toBe('https://generativelanguage.googleapis.com');
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('gemini-2.5-pro, gemini-2.5-flash');
    });

    it('disables cloud presets and options in air-gap mode', () => {
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={true}
          onSaved={vi.fn()}
        />,
      );

      const openaiBtn = screen.getByTestId<HTMLButtonElement>('preset-openai-btn');
      const geminiBtn = screen.getByTestId<HTMLButtonElement>('preset-gemini-btn');
      expect(openaiBtn.disabled).toBe(true);
      expect(geminiBtn.disabled).toBe(true);

      const selectEl = screen.getByTestId<HTMLSelectElement>('provider-kind-select');
      const openaiOpt = selectEl.querySelector<HTMLOptionElement>('option[value="openai"]');
      const geminiOpt = selectEl.querySelector<HTMLOptionElement>('option[value="gemini"]');
      expect(openaiOpt).not.toBeNull();
      expect(geminiOpt).not.toBeNull();
      expect(openaiOpt?.disabled).toBe(true);
      expect(geminiOpt?.disabled).toBe(true);
      expect(openaiOpt?.textContent).toContain('(Blocked by Air-Gap Policy)');
      expect(geminiOpt?.textContent).toContain('(Blocked by Air-Gap Policy)');
    });

    it('surfaces AIR_GAP_EGRESS_DENIED on probe and test connection', async () => {
      vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: false,
        error_code: 'AIR_GAP_EGRESS_DENIED',
        message: 'Egress to external host 142.250.80.46 prohibited by air-gap firewall',
        models: [],
        latency_ms: 0,
        model_count: 0,
      });
      vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: false,
        error_code: 'AIR_GAP_EGRESS_DENIED',
        message: 'Egress to external host 142.250.80.46 prohibited by air-gap firewall',
        models: [],
        latency_ms: 0,
        model_count: 0,
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

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toContain('Egress to external host');
      });

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toContain('Connection failed: Egress to external host');
      });
    });

    it('silently ignores Aal2StepUpCancelledError on probe models', async () => {
      vi.spyOn(aiApi, 'probeAiModels').mockRejectedValue(new Aal2StepUpCancelledError());

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.queryByTestId('probe-loading')).toBeNull();
      });
      expect(screen.queryByTestId('probe-error')).toBeNull();
    });

    it('sets isDirty in edit mode when modifying modelAllowlist, timeoutMs, sampling parameters, or mtlsCertPem', () => {
      const keepaliveSpy = vi.spyOn(webSudoModule, 'useAal2DirtyKeepalive');
      try {
        render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={vi.fn()}
            provider={mockProviderWithFullSettings}
            airGapMode={false}
            onSaved={vi.fn()}
          />,
        );
        expect(keepaliveSpy).toHaveBeenCalledWith(false);

        // Expand advanced settings accordion
        fireEvent.click(screen.getByTestId('advanced-settings-details-toggle'));

        // Modify model allowlist
        const modelsInput = screen.getByTestId('provider-models-input');
        fireEvent.change(modelsInput, { target: { value: 'gpt-4o, gpt-4o-mini' } });
        expect(keepaliveSpy).toHaveBeenCalledWith(true);

        // Modify timeout
        const timeoutInput = screen.getByTestId('provider-timeout-ms-input');
        fireEvent.change(timeoutInput, { target: { value: '35000' } });

        // Modify temperature
        const tempInput = screen.getByTestId('provider-temperature-input');
        fireEvent.change(tempInput, { target: { value: '0.9' } });

        // Modify top_p
        const topPInput = screen.getByTestId('provider-top-p-input');
        fireEvent.change(topPInput, { target: { value: '0.95' } });

        // Modify max_tokens
        const maxTokensInput = screen.getByTestId('provider-max-tokens-input');
        fireEvent.change(maxTokensInput, { target: { value: '8192' } });

        // Modify mtlsCertPem
        const mtlsInput = screen.getByTestId('provider-mtls-cert-input');
        fireEvent.change(mtlsInput, { target: { value: '-----BEGIN CERTIFICATE-----\nNEW\n-----END CERTIFICATE-----' } });

        // Save button is present and ready
        const saveBtn = screen.getByTestId('save-provider-btn');
        expect(saveBtn).toBeDefined();
        expect(keepaliveSpy).toHaveBeenCalledWith(true);
      } finally {
        keepaliveSpy.mockRestore();
      }
    });

    describe('KAN-452: Mention Default Values in AiProviderEditorDrawer Inputs', () => {
      it.each(['light', 'dark'] as const)(
        'renders explicit default URLs in label, hint, and FieldHelpHint across ollama, openai, and gemini in %s theme without breaking submission',
        async (theme) => {
          document.documentElement.setAttribute('data-theme', theme);
          const onSaved = vi.fn();
          const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue({
            id: 'prov-new',
            provider_kind: 'gemini',
            display_name: 'Test Gemini',
            base_url: 'https://generativelanguage.googleapis.com',
            model_allowlist: ['gemini-2.5-flash'],
            residency_tier: 'cloud_standard',
            priority: 1,
            settings: {},
            api_key_set: true,
            is_enabled: true,
          });

          try {
            render(
              <AiProviderEditorDrawer
                isOpen={true}
                onClose={vi.fn()}
                provider={null}
                airGapMode={false}
                onSaved={onSaved}
              />,
            );

            const kindSelect = screen.getByTestId<HTMLSelectElement>('provider-kind-select');
            const helpBtn = screen.getByTestId('provider-base-url-help');
            expect(helpBtn).toBeDefined();

            // 1. Initial default (openai when airGapMode=false)
            expect(kindSelect.value).toBe('openai');
            const labelEl = document.querySelector('label[for="provider-base-url-input"]');
            expect(labelEl?.textContent).toContain('(Default: https://api.openai.com/v1)');
            expect(screen.getByText(/Default OpenAI: https:\/\/api\.openai\.com\/v1/)).toBeDefined();

            act(() => {
              helpBtn.focus();
            });
            expect(screen.getByTestId('provider-base-url-help-popover')).toBeDefined();
            expect(screen.getByTestId('provider-base-url-help-default').textContent).toContain('https://api.openai.com/v1');
            expect(screen.getByTestId('provider-base-url-help-popover').textContent).toContain('Ollama (Default: http://127.0.0.1:11434)');
            expect(screen.getByTestId('provider-base-url-help-popover').textContent).toContain('OpenAI (Default: https://api.openai.com/v1)');
            expect(screen.getByTestId('provider-base-url-help-popover').textContent).toContain('Gemini (Default: https://generativelanguage.googleapis.com)');

            act(() => {
              helpBtn.blur();
            });
            expect(screen.queryByTestId('provider-base-url-help-popover')).toBeNull();

            // 2. Switch to Ollama
            fireEvent.change(kindSelect, { target: { value: 'ollama' } });
            expect(labelEl?.textContent).toContain('(Default: http://127.0.0.1:11434)');
            expect(screen.getByText(/Default Ollama: http:\/\/127\.0\.0\.1:11434/)).toBeDefined();

            act(() => {
              helpBtn.focus();
            });
            expect(screen.getByTestId('provider-base-url-help-default').textContent).toContain('http://127.0.0.1:11434');

            act(() => {
              helpBtn.blur();
            });

            // 3. Switch to Gemini
            fireEvent.change(kindSelect, { target: { value: 'gemini' } });
            expect(labelEl?.textContent).toContain('(Default: https://generativelanguage.googleapis.com)');
            expect(screen.getByText(/Default Google Gemini endpoint: https:\/\/generativelanguage\.googleapis\.com/)).toBeDefined();

            act(() => {
              helpBtn.focus();
            });
            expect(screen.getByTestId('provider-base-url-help-default').textContent).toContain('https://generativelanguage.googleapis.com');

            act(() => {
              helpBtn.blur();
            });

            // 4. Fill required fields and submit to verify form submission non-regression
            fireEvent.change(screen.getByTestId('provider-name-input'), { target: { value: 'Test Gemini' } });
            fireEvent.change(screen.getByTestId('provider-key-input'), { target: { value: 'secret-gemini-key' } });
            fireEvent.click(screen.getByTestId('save-provider-btn'));

            await waitFor(() => {
              expect(createSpy).toHaveBeenCalledWith(
                expect.objectContaining({
                  provider_kind: 'gemini',
                  display_name: 'Test Gemini',
                  api_key: 'secret-gemini-key',
                }),
              );
              expect(onSaved).toHaveBeenCalled();
            });
          } finally {
            document.documentElement.removeAttribute('data-theme');
            createSpy.mockRestore();
          }
        },
      );

      it('renders Ollama default URL in Air-Gap mode as initial state', () => {
        render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={vi.fn()}
            provider={null}
            airGapMode={true}
            onSaved={vi.fn()}
          />,
        );

        const kindSelect = screen.getByTestId<HTMLSelectElement>('provider-kind-select');
        expect(kindSelect.value).toBe('ollama');
        const labelEl = document.querySelector('label[for="provider-base-url-input"]');
        expect(labelEl?.textContent).toContain('(Default: http://127.0.0.1:11434)');
        expect(screen.getByText(/Default Ollama: http:\/\/127\.0\.0\.1:11434/)).toBeDefined();

        const helpBtn = screen.getByTestId('provider-base-url-help');
        act(() => {
          helpBtn.focus();
        });
        expect(screen.getByTestId('provider-base-url-help-default').textContent).toContain('http://127.0.0.1:11434');
      });
    });

    describe('KAN-449: FieldHelpHints and CSS token styling in AiProviderEditorDrawer', () => {
      it('renders FieldHelpHint components across display name, API key, model allowlist, mTLS, and residency tier', () => {
        render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={vi.fn()}
            provider={null}
            airGapMode={false}
            onSaved={vi.fn()}
          />,
        );

        // Name & Key hints
        const nameHelp = screen.getByTestId('provider-name-help');
        expect(nameHelp.getAttribute('aria-label')).toBe('Help for Display Name');
        expect(nameHelp.getAttribute('aria-haspopup')).toBe('dialog');

        const keyHelp = screen.getByTestId('provider-key-help');
        expect(keyHelp.getAttribute('aria-label')).toBe('Help for API Secret Key');

        const modelsHelp = screen.getByTestId('provider-models-help');
        expect(modelsHelp.getAttribute('aria-label')).toBe('Help for Model Allowlist');

        // Open Advanced Section
        fireEvent.click(screen.getByTestId('advanced-settings-details-toggle'));

        const mtlsHelp = screen.getByTestId('provider-mtls-cert-help');
        expect(mtlsHelp.getAttribute('aria-label')).toBe('Help for mTLS Client Certificate PEM');

        const residencyHelp = screen.getByTestId('provider-residency-help');
        expect(residencyHelp.getAttribute('aria-label')).toBe('Help for Data Residency Tier');

        expect(document.querySelectorAll('label button.field-help-hint').length).toBe(0);

        // Verify popover interaction on provider-name-help
        act(() => {
          nameHelp.focus();
        });
        expect(screen.getByTestId('provider-name-help-popover')).toBeDefined();
        expect(screen.getByTestId('provider-name-help-popover').textContent).toContain(
          'Human-readable label for this AI provider instance.',
        );

        fireEvent.keyDown(screen.getByTestId('provider-name-help-popover'), { key: 'Escape' });
        expect(screen.queryByTestId('provider-name-help-popover')).toBeNull();
      });

      it('enforces clean CSS class styling with zero inline style props on model grid and mTLS', () => {
        const { container } = render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={vi.fn()}
            provider={null}
            airGapMode={false}
            onSaved={vi.fn()}
          />,
        );

        fireEvent.click(screen.getByTestId('advanced-settings-details-toggle'));

        const grid = container.querySelector('.kb-model-params-grid');
        expect(grid).not.toBeNull();
        expect(grid?.getAttribute('style')).toBeNull();

        const mtlsTextarea = screen.getByTestId('provider-mtls-cert-input');
        expect(mtlsTextarea.classList.contains('kb-form-textarea--mono')).toBe(true);
        expect(mtlsTextarea.getAttribute('style')).toBeNull();
      });

      it('validates cutoff timeout bounds on form submission', async () => {
        render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={vi.fn()}
            provider={null}
            airGapMode={false}
            onSaved={vi.fn()}
          />,
        );

        fireEvent.change(screen.getByTestId('provider-name-input'), {
          target: { value: 'Valid Name' },
        });
        fireEvent.change(screen.getByTestId('provider-key-input'), {
          target: { value: 'sk-test' },
        });
        fireEvent.change(screen.getByTestId('provider-timeout-ms-input'), {
          target: { value: '500' },
        });

        fireEvent.submit(screen.getByTestId('save-provider-btn'));

        await waitFor(() => {
          expect(screen.getByText(/Cutoff timeout must be between 1,000 and 600,000 ms/i)).toBeDefined();
        });

        fireEvent.change(screen.getByTestId('provider-timeout-ms-input'), {
          target: { value: '700000' },
        });
        fireEvent.submit(screen.getByTestId('save-provider-btn'));

        await waitFor(() => {
          expect(screen.getByText(/Cutoff timeout must be between 1,000 and 600,000 ms/i)).toBeDefined();
        });
      });
    });

    describe('KAN-451: Standardized Drawer Footer Action Button Order and Cadence', () => {
      it('verifies standardized button cadence: [Test Connection] (left) -> [Cancel] -> [Save Provider] (right)', () => {
        const { container } = render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={vi.fn()}
            provider={null}
            airGapMode={false}
            onSaved={vi.fn()}
          />,
        );

        const footer = container.querySelector('.kb-modal-footer.kb-drawer-footer');
        expect(footer).not.toBeNull();
        expect(footer?.getAttribute('style')).toBeNull();

        const leftGroup = container.querySelector('.kb-drawer-footer-actions-left');
        const rightGroup = container.querySelector('.kb-drawer-footer-actions-right');
        expect(leftGroup).not.toBeNull();
        expect(rightGroup).not.toBeNull();

        const testBtn = screen.getByTestId('drawer-test-connection-btn');
        const cancelBtn = screen.getByTestId('cancel-provider-drawer-btn');
        const saveBtn = screen.getByTestId('save-provider-btn');

        expect(leftGroup?.contains(testBtn)).toBe(true);
        expect(rightGroup?.contains(cancelBtn)).toBe(true);
        expect(rightGroup?.contains(saveBtn)).toBe(true);

        // Verify order in right group: Cancel before Save
        if (!rightGroup) throw new Error('rightGroup not found');
        const rightButtons = Array.from(rightGroup.querySelectorAll('button'));
        expect(rightButtons[0]).toBe(cancelBtn);
        expect(rightButtons[1]).toBe(saveBtn);

        // Overall DOM order
        if (!footer) throw new Error('footer not found');
        const allButtons: HTMLElement[] = Array.from(footer.querySelectorAll('button'));
        const testIdx = allButtons.indexOf(testBtn);
        const cancelIdx = allButtons.indexOf(cancelBtn);
        const saveIdx = allButtons.indexOf(saveBtn);
        expect(testIdx).toBeLessThan(cancelIdx);
        expect(cancelIdx).toBeLessThan(saveIdx);
      });

      it('verifies action button clicks and onClose callbacks', () => {
        const onClose = vi.fn();
        render(
          <AiProviderEditorDrawer
            isOpen={true}
            onClose={onClose}
            provider={null}
            airGapMode={false}
            onSaved={vi.fn()}
          />,
        );

        fireEvent.click(screen.getByTestId('cancel-provider-drawer-btn'));
        expect(onClose).toHaveBeenCalledTimes(1);

        fireEvent.click(screen.getByTestId('close-provider-drawer-btn'));
        expect(onClose).toHaveBeenCalledTimes(2);
      });
    });
  });
});
