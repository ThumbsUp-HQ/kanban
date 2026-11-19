// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { AiStudioPage } from '../AiStudioPage';
import { AiBudgetModal } from '../AiBudgetModal';
import { AiProviderEditorDrawer } from '../AiProviderEditorDrawer';
import * as aiApi from '../aiAdminApi';
import type { ProviderConfigPublic, BudgetRecord } from '../aiAdminApi';
import * as clientModule from '../../../api/client';

describe('AiStudioPage & Components (KANBA-219)', () => {
  const mockProvider: ProviderConfigPublic = {
    id: 'prov-openai-1',
    provider_kind: 'openai',
    display_name: 'Production OpenAI',
    base_url: 'https://api.openai.com/v1',
    model_allowlist: ['gpt-4o', 'gpt-4o-mini'],
    residency_tier: 'default',
    priority: 10,
    settings: {},
    api_key_set: true,
    is_enabled: true,
    project_id: null,
  };

  const mockOllamaProvider: ProviderConfigPublic = {
    id: 'prov-ollama-2',
    provider_kind: 'ollama',
    display_name: 'Local Ollama Runtime',
    base_url: 'http://localhost:11434',
    model_allowlist: ['llama3.2:3b'],
    residency_tier: 'local',
    priority: 20,
    settings: {},
    api_key_set: false,
    is_enabled: false,
    project_id: null,
  };

  const mockBudgets: BudgetRecord[] = [
    {
      period_kind: 'monthly',
      period_start: '2026-11-01',
      token_cap: 1000000,
      tokens_used: 250000,
      tokens_reserved: 50000,
    },
    {
      period_kind: 'daily',
      period_start: '2026-11-18',
      token_cap: 50000,
      tokens_used: 10000,
      tokens_reserved: 0,
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('aiAdminApi functions', () => {
    it('exercises all API helper methods directly with apiFetch mock', async () => {
      const fetchSpy = vi.spyOn(clientModule, 'apiFetch').mockResolvedValue([mockProvider]);

      // fetchAiProviders
      const list1 = await aiApi.fetchAiProviders();
      expect(list1).toEqual([mockProvider]);
      expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/ai/providers');

      // fetchAiProviders with project_id
      fetchSpy.mockResolvedValueOnce([mockProvider]);
      const list2 = await aiApi.fetchAiProviders('proj-123');
      expect(list2).toEqual([mockProvider]);
      expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/admin/ai/providers?project_id=proj-123');

      // fetchAiProvider
      fetchSpy.mockResolvedValueOnce(mockProvider);
      const single = await aiApi.fetchAiProvider('prov-openai-1');
      expect(single.id).toBe('prov-openai-1');

      // createAiProvider
      fetchSpy.mockResolvedValueOnce(mockProvider);
      const created = await aiApi.createAiProvider({
        provider_kind: 'openai',
        display_name: 'Test',
      });
      expect(created.display_name).toBe('Production OpenAI');

      // updateAiProvider
      fetchSpy.mockResolvedValueOnce(mockProvider);
      const updated = await aiApi.updateAiProvider('prov-openai-1', { display_name: 'Updated' });
      expect(updated.id).toBe('prov-openai-1');

      // deleteAiProvider
      fetchSpy.mockResolvedValueOnce(undefined);
      await aiApi.deleteAiProvider('prov-openai-1');

      // disableAiProvider
      fetchSpy.mockResolvedValueOnce({ ...mockProvider, is_enabled: false });
      const disabled = await aiApi.disableAiProvider('prov-openai-1');
      expect(disabled.is_enabled).toBe(false);

      // fetchBudgets
      fetchSpy.mockResolvedValueOnce(mockBudgets);
      const bList = await aiApi.fetchBudgets('prov-openai-1');
      expect(bList).toEqual(mockBudgets);

      // setBudget
      const budget0 = mockBudgets[0];
      if (!budget0) throw new Error('missing budget fixture');
      fetchSpy.mockResolvedValueOnce(budget0);
      const setB = await aiApi.setBudget({
        provider_config_id: 'prov-openai-1',
        period_kind: 'monthly',
        token_cap: 2000000,
      });
      expect(setB.token_cap).toBe(1000000);

      // fetchAirGapMode true
      fetchSpy.mockResolvedValueOnce({ air_gap_mode: true });
      expect(await aiApi.fetchAirGapMode()).toBe(true);

      // fetchAirGapMode false
      fetchSpy.mockResolvedValueOnce({ air_gap_mode: false });
      expect(await aiApi.fetchAirGapMode()).toBe(false);

      // fetchAirGapMode exception fallback
      fetchSpy.mockRejectedValueOnce(new Error('Network error'));
      expect(await aiApi.fetchAirGapMode()).toBe(false);
    });
  });

  describe('AiStudioPage component', () => {
    it('renders provider cards and handles toggle enablement and modals', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider, mockOllamaProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      vi.spyOn(aiApi, 'disableAiProvider').mockResolvedValue({ ...mockProvider, is_enabled: false });
      vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue({ ...mockOllamaProvider, is_enabled: true });
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);

      render(<AiStudioPage />);

      expect(screen.getByTestId('ai-studio-loading')).toBeDefined();

      await waitFor(() => {
        expect(screen.getByText('Production OpenAI')).toBeDefined();
        expect(screen.getByText('Local Ollama Runtime')).toBeDefined();
      });

      // Air gap banner should not be present
      expect(screen.queryByTestId('air-gap-active-banner')).toBeNull();

      // Toggle enabled provider (disable it)
      const toggleOpenAi = screen.getByTestId('toggle-enable-btn-prov-openai-1');
      expect(toggleOpenAi.textContent).toBe('Enabled');
      fireEvent.click(toggleOpenAi);
      await waitFor(() => {
        expect(aiApi.disableAiProvider).toHaveBeenCalledWith('prov-openai-1');
      });

      // Toggle disabled provider (enable it)
      const toggleOllama = screen.getByTestId('toggle-enable-btn-prov-ollama-2');
      expect(toggleOllama.textContent).toBe('Disabled');
      fireEvent.click(toggleOllama);
      await waitFor(() => {
        expect(aiApi.updateAiProvider).toHaveBeenCalledWith('prov-ollama-2', { is_enabled: true });
      });

      // Open manage budget modal
      fireEvent.click(screen.getByTestId('manage-budget-btn-prov-openai-1'));
      expect(screen.getByTestId('ai-budget-modal')).toBeDefined();
      fireEvent.click(screen.getByTestId('close-budget-modal-btn'));
      expect(screen.queryByTestId('ai-budget-modal')).toBeNull();

      // Open edit drawer
      fireEvent.click(screen.getByTestId('edit-provider-btn-prov-openai-1'));
      expect(screen.getByTestId('ai-provider-editor-drawer')).toBeDefined();
      fireEvent.click(screen.getByTestId('close-provider-drawer-btn'));
      expect(screen.queryByTestId('ai-provider-editor-drawer')).toBeNull();

      // Open register provider drawer
      fireEvent.click(screen.getByTestId('register-provider-btn'));
      expect(screen.getByTestId('ai-provider-editor-drawer')).toBeDefined();
      fireEvent.click(screen.getByTestId('cancel-provider-drawer-btn'));
      expect(screen.queryByTestId('ai-provider-editor-drawer')).toBeNull();
    });

    it('renders air-gap banner and blocks cloud provider activation when air-gap mode is active', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider, mockOllamaProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(true);

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('air-gap-active-banner')).toBeDefined();
      });

      expect(screen.getByText('Enterprise Air-Gap Mode Active')).toBeDefined();
      expect(screen.getByText('⚠️ Blocked by Air-Gap mode')).toBeDefined();
    });

    it('renders empty placeholder when no providers exist', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('empty-providers-placeholder')).toBeDefined();
      });
    });

    it('renders error message when loading fails', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockRejectedValue(new Error('Network offline'));
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('ai-studio-error').textContent).toContain('Network offline');
      });
    });

    it('handles delete provider workflow with confirmation modal and error catch', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      const deleteSpy = vi.spyOn(aiApi, 'deleteAiProvider').mockResolvedValue(undefined);

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('delete-provider-btn-prov-openai-1')).toBeDefined();
      });

      // Click delete opens modal
      fireEvent.click(screen.getByTestId('delete-provider-btn-prov-openai-1'));
      expect(screen.getByTestId('delete-provider-modal')).toBeDefined();

      // Cancel delete
      fireEvent.click(screen.getByTestId('cancel-delete-provider-btn'));
      expect(screen.queryByTestId('delete-provider-modal')).toBeNull();

      // Open and confirm delete
      fireEvent.click(screen.getByTestId('delete-provider-btn-prov-openai-1'));
      fireEvent.click(screen.getByTestId('confirm-delete-provider-btn'));

      await waitFor(() => {
        expect(deleteSpy).toHaveBeenCalledWith('prov-openai-1');
      });

      // Handle delete error
      deleteSpy.mockRejectedValueOnce(new Error('Deletion rejected'));
      fireEvent.click(screen.getByTestId('delete-provider-btn-prov-openai-1'));
      fireEvent.click(screen.getByTestId('confirm-delete-provider-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('ai-studio-error').textContent).toContain('Deletion rejected');
      });
    });

    it('handles toggle enablement error with non-Error reject', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      vi.spyOn(aiApi, 'disableAiProvider').mockRejectedValue('raw string rejection');

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('toggle-enable-btn-prov-openai-1')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('toggle-enable-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.getByTestId('ai-studio-error').textContent).toContain(
          'Failed to toggle provider enablement',
        );
      });
    });

    it('handles delete failure with non-Error reject', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      vi.spyOn(aiApi, 'deleteAiProvider').mockRejectedValue('raw error');

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('delete-provider-btn-prov-openai-1')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('delete-provider-btn-prov-openai-1'));
      fireEvent.click(screen.getByTestId('confirm-delete-provider-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('ai-studio-error').textContent).toContain('Failed to delete provider');
      });
    });

    it('handles load error with non-Error reject', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockRejectedValue('offline');
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('ai-studio-error').textContent).toContain('Failed to load AI providers');
      });
    });
  });

  describe('AiBudgetModal component', () => {
    it('renders budget ledger stats and updates token cap', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const firstBudget = mockBudgets[0];
      if (!firstBudget) throw new Error('Missing mock budget');
      vi.spyOn(aiApi, 'setBudget').mockResolvedValue(firstBudget);
      const onUpdated = vi.fn();
      const onClose = vi.fn();

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={onClose}
          provider={mockProvider}
          onBudgetUpdated={onUpdated}
        />,
      );

      expect(screen.getByTestId('budget-loading')).toBeDefined();

      await waitFor(() => {
        expect(screen.getByTestId('budget-ledger-summary')).toBeDefined();
      });

      expect(screen.getByText(/250,000/)).toBeDefined();
      expect(screen.getByText(/1,000,000 tokens/)).toBeDefined();
      expect(screen.getByText(/30% consumed/)).toBeDefined();

      // Change period to daily
      const periodSelect = screen.getByTestId('budget-period-select');
      fireEvent.change(periodSelect, { target: { value: 'daily' } });

      // Change cap
      const capInput = screen.getByTestId('budget-token-cap-input');
      fireEvent.change(capInput, { target: { value: '2000000' } });

      // Submit form
      fireEvent.click(screen.getByTestId('save-budget-btn'));

      await waitFor(() => {
        expect(aiApi.setBudget).toHaveBeenCalledWith({
          provider_config_id: 'prov-openai-1',
          project_id: undefined,
          period_kind: 'daily',
          token_cap: 2000000,
        });
        expect(onUpdated).toHaveBeenCalled();
      });

      // Close modal
      fireEvent.click(screen.getByTestId('budget-cancel-btn'));
      expect(onClose).toHaveBeenCalled();
    });

    it('renders high consumption bar and handles budget fetch error', async () => {
      const highConsumptionBudgets: BudgetRecord[] = [
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 100000,
          tokens_used: 95000,
          tokens_reserved: 0,
        },
      ];
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(highConsumptionBudgets);

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText('95% consumed')).toBeDefined();
      });
    });

    it('renders warning consumption bar (75%) and quota exhausted message', async () => {
      const warnBudgets: BudgetRecord[] = [
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 100000,
          tokens_used: 75000,
          tokens_reserved: 0,
        },
      ];
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(warnBudgets);

      const { rerender } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText('75% consumed')).toBeDefined();
      });

      // Quota exhausted (used >= cap)
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue([
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 100000,
          tokens_used: 100000,
          tokens_reserved: 0,
        },
      ]);
      rerender(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={{ ...mockProvider, id: 'prov-openai-exhausted' }}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText('0 tokens remaining')).toBeDefined();
      });
    });

    it('renders unlimited cap when token_cap is 0', async () => {
      const unlimitedBudgets: BudgetRecord[] = [
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 0,
          tokens_used: 0,
          tokens_reserved: 0,
        },
      ];
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(unlimitedBudgets);

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText('Unlimited')).toBeDefined();
      });
    });

    it('handles unmount during load in AiStudioPage and AiBudgetModal (resolve and reject)', () => {
      let resolveProv!: (v: ProviderConfigPublic[]) => void;
      vi.spyOn(aiApi, 'fetchAiProviders').mockReturnValue(
        new Promise((resolve) => { resolveProv = resolve; }),
      );
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      const page1 = render(<AiStudioPage />);
      page1.unmount();
      resolveProv([mockProvider]);

      let rejectProv!: (e: unknown) => void;
      vi.spyOn(aiApi, 'fetchAiProviders').mockReturnValue(
        new Promise((_, reject) => { rejectProv = reject; }),
      );
      const page2 = render(<AiStudioPage />);
      page2.unmount();
      rejectProv(new Error('unmounted prov reject'));

      let resolveBudgets!: (v: BudgetRecord[]) => void;
      vi.spyOn(aiApi, 'fetchBudgets').mockReturnValue(
        new Promise((resolve) => { resolveBudgets = resolve; }),
      );
      const modal1 = render(<AiBudgetModal isOpen={true} onClose={vi.fn()} provider={mockProvider} />);
      modal1.unmount();
      resolveBudgets(mockBudgets);

      let rejectBudgets!: (e: unknown) => void;
      vi.spyOn(aiApi, 'fetchBudgets').mockReturnValue(
        new Promise((_, reject) => { rejectBudgets = reject; }),
      );
      const modal2 = render(<AiBudgetModal isOpen={true} onClose={vi.fn()} provider={mockProvider} />);
      modal2.unmount();
      rejectBudgets(new Error('unmounted budget reject'));
    });

    it('handles daily only budget record fallback', async () => {
      const dailyOnly: BudgetRecord[] = [
        {
          period_kind: 'daily',
          period_start: '2026-11-18',
          token_cap: 30000,
          tokens_used: 5000,
          tokens_reserved: 0,
        },
      ];
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(dailyOnly);

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId<HTMLInputElement>('budget-token-cap-input').value).toBe('30000');
        expect(screen.getByTestId<HTMLSelectElement>('budget-period-select').value).toBe('daily');
      });
    });

    it('handles Error instance and non-Error rejection on budget load and save', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockRejectedValue('raw failure');

      const { rerender } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-error').textContent).toContain('Failed to load budgets');
      });

      // Error instance
      vi.spyOn(aiApi, 'fetchBudgets').mockRejectedValue(new Error('Ledger unreachable'));
      rerender(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={{ ...mockProvider, id: 'prov-openai-err' }}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-error').textContent).toContain('Ledger unreachable');
      });
    });

    it('displays error on negative token cap or failed setBudget', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      vi.spyOn(aiApi, 'setBudget').mockRejectedValue(new Error('Quota freeze'));

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-token-cap-input')).toBeDefined();
      });

      fireEvent.change(screen.getByTestId('budget-token-cap-input'), { target: { value: '-50' } });
      fireEvent.click(screen.getByTestId('save-budget-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('budget-error').textContent).toContain('non-negative');
      });

      // Submit valid number to trigger setBudget error
      fireEvent.change(screen.getByTestId('budget-token-cap-input'), { target: { value: '500' } });
      fireEvent.click(screen.getByTestId('save-budget-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('budget-error').textContent).toContain('Quota freeze');
      });
    });

    it('returns null when isOpen is false', () => {
      const { container } = render(
        <AiBudgetModal isOpen={false} onClose={vi.fn()} provider={mockProvider} />,
      );
      expect(container.firstChild).toBeNull();
    });
  });

  describe('AiProviderEditorDrawer component', () => {
    it('creates a new AI provider with residency and priority inputs', async () => {
      vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue(mockProvider);
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={onClose}
          provider={null}
          airGapMode={false}
          onSaved={onSaved}
        />,
      );

      expect(screen.getByText('Register AI Provider')).toBeDefined();

      // Change kind to gemini
      const kindSelect = screen.getByTestId('provider-kind-select');
      fireEvent.change(kindSelect, { target: { value: 'gemini' } });

      expect(screen.getByTestId<HTMLInputElement>('provider-name-input').value).toBe(
        'Google Gemini Workspace',
      );

      // Change kind to ollama
      fireEvent.change(kindSelect, { target: { value: 'ollama' } });
      expect(screen.getByTestId<HTMLInputElement>('provider-base-url-input').value).toBe(
        'http://localhost:11434',
      );

      // Change kind to custom
      fireEvent.change(kindSelect, { target: { value: 'custom' } });

      // Enter details
      fireEvent.change(screen.getByTestId('provider-name-input'), {
        target: { value: 'Custom Endpoint' },
      });
      fireEvent.change(screen.getByTestId('provider-base-url-input'), {
        target: { value: 'https://ai.example.com/v1' },
      });
      fireEvent.change(screen.getByTestId('provider-models-input'), {
        target: { value: 'custom-model-1, custom-model-2' },
      });
      fireEvent.change(screen.getByTestId('provider-residency-select'), {
        target: { value: 'eu-central' },
      });
      fireEvent.change(screen.getByTestId('provider-priority-input'), {
        target: { value: '50' },
      });
      fireEvent.change(screen.getByTestId('provider-key-input'), {
        target: { value: 'secret-key-123' },
      });

      // Toggle show key
      fireEvent.click(screen.getByTestId('toggle-show-key-btn'));
      expect(screen.getByTestId<HTMLInputElement>('provider-key-input').type).toBe('text');

      // Submit
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(aiApi.createAiProvider).toHaveBeenCalledWith({
          provider_kind: 'custom',
          display_name: 'Custom Endpoint',
          base_url: 'https://ai.example.com/v1',
          model_allowlist: ['custom-model-1', 'custom-model-2'],
          residency_tier: 'eu-central',
          priority: 50,
          api_key: 'secret-key-123',
          is_enabled: true,
        });
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('updates an existing provider with write-only key custody and clear key checkbox', async () => {
      vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockProvider);
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={onClose}
          provider={mockProvider}
          airGapMode={false}
          onSaved={onSaved}
        />,
      );

      expect(screen.getByText('Edit Production OpenAI')).toBeDefined();
      expect(screen.getByTestId('clear-key-checkbox')).toBeDefined();

      // Check clear key checkbox
      fireEvent.click(screen.getByTestId('clear-key-checkbox'));
      expect(screen.getByTestId<HTMLInputElement>('provider-key-input').disabled).toBe(true);

      // Uncheck clear key checkbox
      fireEvent.click(screen.getByTestId('clear-key-checkbox'));
      expect(screen.getByTestId<HTMLInputElement>('provider-key-input').disabled).toBe(false);

      // Re-check it
      fireEvent.click(screen.getByTestId('clear-key-checkbox'));

      // Submit update
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(aiApi.updateAiProvider).toHaveBeenCalledWith('prov-openai-1', {
          display_name: 'Production OpenAI',
          model_allowlist: ['gpt-4o', 'gpt-4o-mini'],
          residency_tier: 'default',
          base_url: 'https://api.openai.com/v1',
          priority: 10,
          api_key: null,
        });
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('updates an existing provider with new api key and handles non-Error save failure', async () => {
      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockProvider);
      const onSaved = vi.fn();
      const onClose = vi.fn();

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={onClose}
          provider={mockProvider}
          airGapMode={false}
          onSaved={onSaved}
        />,
      );

      // Enter a new API key without clearing
      fireEvent.change(screen.getByTestId('provider-key-input'), {
        target: { value: 'new-secret-key-999' },
      });

      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith('prov-openai-1', {
          display_name: 'Production OpenAI',
          model_allowlist: ['gpt-4o', 'gpt-4o-mini'],
          residency_tier: 'default',
          base_url: 'https://api.openai.com/v1',
          priority: 10,
          api_key: 'new-secret-key-999',
        });
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });

      // Non-Error rejection
      updateSpy.mockRejectedValueOnce('raw db update failure');
      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('provider-editor-error').textContent).toContain(
          'Failed to save provider configuration',
        );
      });
    });

    it('blocks cloud provider registration on direct form submit when air-gap mode is active', async () => {
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={true}
          onSaved={vi.fn()}
        />,
      );

      // Switch to custom (which is not disabled)
      fireEvent.change(screen.getByTestId('provider-kind-select'), {
        target: { value: 'custom' },
      });
      // Switch back to openai
      fireEvent.change(screen.getByTestId('provider-kind-select'), {
        target: { value: 'openai' },
      });

      // Submit form directly
      const form = screen.getByTestId('provider-name-input').closest('form');
      if (!form) throw new Error('Form not found');
      fireEvent.submit(form);

      await waitFor(() => {
        expect(screen.getByTestId('provider-editor-error').textContent).toContain('Air-Gap mode prohibits');
      });
    });

    it('validates empty display name and handles api save error', async () => {
      vi.spyOn(aiApi, 'createAiProvider').mockRejectedValue(new Error('Duplicate provider name'));

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
        target: { value: '   ' },
      });
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('provider-editor-error').textContent).toContain('Display name is required');
      });

      // Enter valid name and trigger save error
      fireEvent.change(screen.getByTestId('provider-name-input'), {
        target: { value: 'Duplicate' },
      });
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('provider-editor-error').textContent).toContain('Duplicate provider name');
      });
    });

    it('updates provider preserving key and leaving base_url empty', async () => {
      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue(mockProvider);
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );
      fireEvent.change(screen.getByTestId('provider-base-url-input'), { target: { value: '' } });
      fireEvent.click(screen.getByTestId('save-provider-btn'));
      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          'prov-openai-1',
          expect.objectContaining({
            base_url: null,
          }),
        );
      });
    });
  });
});
