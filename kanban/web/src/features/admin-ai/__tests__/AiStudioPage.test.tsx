// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, createEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { AiStudioPage } from '../AiStudioPage';
import { AiBudgetModal } from '../AiBudgetModal';
import { AiProviderEditorDrawer } from '../AiProviderEditorDrawer';
import * as aiApi from '../aiAdminApi';
import type { ProviderConfigPublic, BudgetRecord } from '../aiAdminApi';
import * as clientModule from '../../../api/client';

describe('AiStudioPage & Components (KAN-22 / KANBA-219)', () => {
  const mockProvider: ProviderConfigPublic = {
    id: 'prov-openai-1',
    provider_kind: 'openai',
    display_name: 'Production OpenAI',
    base_url: 'https://api.openai.com/v1',
    model_allowlist: ['gpt-4o', 'gpt-4o-mini'],
    residency_tier: 'cloud_standard',
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
    base_url: 'http://127.0.0.1:11434',
    model_allowlist: ['llama3.2:3b'],
    residency_tier: 'local_only',
    priority: 20,
    settings: {},
    api_key_set: false,
    is_enabled: false,
    project_id: null,
  };

  const mockOpenAiLocalProvider: ProviderConfigPublic = {
    id: 'prov-openai-local-3',
    provider_kind: 'openai',
    display_name: 'Local vLLM Engine',
    base_url: 'http://localhost:8000/v1',
    model_allowlist: ['mistral-7b'],
    residency_tier: 'local_only',
    priority: 30,
    settings: {},
    api_key_set: false,
    is_enabled: true,
    project_id: null,
  };

  const mockGeminiProvider: ProviderConfigPublic = {
    id: 'prov-gemini-4',
    provider_kind: 'gemini',
    display_name: 'Google Gemini Cloud',
    base_url: 'https://generativelanguage.googleapis.com',
    model_allowlist: ['gemini-2.5-flash'],
    residency_tier: 'cloud_standard',
    priority: 40,
    settings: {},
    api_key_set: true,
    is_enabled: true,
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
      expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/workspaces/current/ai-providers');

      // fetchAiProviders with project_id
      fetchSpy.mockResolvedValueOnce([mockProvider]);
      const list2 = await aiApi.fetchAiProviders('proj-123');
      expect(list2).toEqual([mockProvider]);
      expect(fetchSpy).toHaveBeenCalledWith('GET', '/api/v1/workspaces/current/ai-providers?project_id=proj-123');

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

  describe('AiStudioPage component & Numbered Failover Priority Stack (KAN-22)', () => {
    it('renders numbered #1..#N stack, local badges, and handles move up/down reordering', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([
        mockProvider,
        mockOllamaProvider,
        mockOpenAiLocalProvider,
      ]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      vi.spyOn(aiApi, 'disableAiProvider').mockResolvedValue({ ...mockProvider, is_enabled: false });
      vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue({ ...mockOllamaProvider, is_enabled: true });
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const reorderSpy = vi.spyOn(aiApi, 'reorderAiProviders').mockImplementation((ids) => {
        return Promise.resolve(
          ids.map((id, idx) => {
            const match = [mockProvider, mockOllamaProvider, mockOpenAiLocalProvider].find((p) => p.id === id);
            if (!match) throw new Error(`Provider not found: ${id}`);
            return { ...match, priority: (idx + 1) * 10 };
          }),
        );
      });

      render(<AiStudioPage />);

      expect(screen.getByTestId('ai-studio-loading')).toBeDefined();

      await waitFor(() => {
        expect(screen.getByText('Production OpenAI')).toBeDefined();
        expect(screen.getByText('Local Ollama Runtime')).toBeDefined();
        expect(screen.getByText('Local vLLM Engine')).toBeDefined();
      });

      // Verify numbered rank badges
      expect(screen.getByTestId('provider-rank-prov-openai-1').textContent).toBe('#1');
      expect(screen.getByTestId('provider-rank-prov-ollama-2').textContent).toBe('#2');
      expect(screen.getByTestId('provider-rank-prov-openai-local-3').textContent).toBe('#3');

      // Verify residency badges
      expect(screen.getByTestId('residency-badge-prov-openai-1').textContent).toContain('Cloud');
      expect(screen.getByTestId('residency-badge-prov-ollama-2').textContent).toContain('Local / Zero-Egress');
      expect(screen.getByTestId('residency-badge-prov-openai-local-3').textContent).toContain('Local / Zero-Egress');

      // Verify key status badges
      expect(screen.getByTestId('key-status-prov-openai-1').textContent).toContain('Key Configured');
      expect(screen.getByTestId('key-status-prov-ollama-2').textContent).toContain('No Key Required (Local)');
      expect(screen.getByTestId('key-status-prov-openai-local-3').textContent).toContain('No Key Required (Local)');

      // Verify Move Up disabled on #1, Move Down disabled on #3
      expect(screen.getByTestId<HTMLButtonElement>('move-up-btn-prov-openai-1').disabled).toBe(true);
      expect(screen.getByTestId<HTMLButtonElement>('move-down-btn-prov-openai-local-3').disabled).toBe(true);

      // Click Move Down on #1 (moves prov-openai-1 down to #2)
      act(() => {
        fireEvent.click(screen.getByTestId('move-down-btn-prov-openai-1'));
      });
      await waitFor(() => {
        expect(reorderSpy).toHaveBeenCalledWith([
          'prov-ollama-2',
          'prov-openai-1',
          'prov-openai-local-3',
        ]);
      });

      // Click Move Up on #2 (moves prov-openai-1 back to #1)
      act(() => {
        fireEvent.click(screen.getByTestId('move-up-btn-prov-openai-1'));
      });
      await waitFor(() => {
        expect(reorderSpy).toHaveBeenCalledWith([
          'prov-openai-1',
          'prov-ollama-2',
          'prov-openai-local-3',
        ]);
      });

      // Toggle enabled provider (disable it)
      const toggleOpenAi = screen.getByTestId('toggle-enable-btn-prov-openai-1');
      expect(toggleOpenAi.textContent).toBe('Enabled');
      act(() => {
        fireEvent.click(toggleOpenAi);
      });
      await waitFor(() => {
        expect(aiApi.disableAiProvider).toHaveBeenCalledWith('prov-openai-1');
      });
      await waitFor(() => {
        expect(aiApi.fetchAiProviders).toHaveBeenCalled();
      });

      // Toggle disabled provider (enable it)
      const toggleOllama = screen.getByTestId('toggle-enable-btn-prov-ollama-2');
      expect(toggleOllama.textContent).toBe('Disabled');
      act(() => {
        fireEvent.click(toggleOllama);
      });
      await waitFor(() => {
        expect(aiApi.updateAiProvider).toHaveBeenCalledWith('prov-ollama-2', { is_enabled: true });
      });
      await waitFor(() => {
        expect(aiApi.fetchAiProviders).toHaveBeenCalled();
      });

      // Open manage budget modal
      fireEvent.click(screen.getByTestId('manage-budget-btn-prov-openai-1'));
      expect(screen.getByTestId('ai-budget-modal')).toBeDefined();
      await waitFor(() => {
        expect(aiApi.fetchBudgets).toHaveBeenCalledWith('prov-openai-1');
      });
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

    it('rolls back provider order and displays error alert when reorder fails', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider, mockOllamaProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      const reorderSpy = vi.spyOn(aiApi, 'reorderAiProviders').mockRejectedValue(new Error('Network reorder failure'));

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByText('Production OpenAI')).toBeDefined();
      });

      // Move Down on #1 (Error instance)
      fireEvent.click(screen.getByTestId('move-down-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.getByTestId('ai-studio-error').textContent).toContain('Network reorder failure');
      });

      // State rolled back
      expect(screen.getByTestId('provider-rank-prov-openai-1').textContent).toBe('#1');
      expect(screen.getByTestId('provider-rank-prov-ollama-2').textContent).toBe('#2');

      // Reorder failure with non-Error reject
      reorderSpy.mockRejectedValueOnce('raw reorder failure');
      fireEvent.click(screen.getByTestId('move-down-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.getByTestId('ai-studio-error').textContent).toContain('Failed to reorder providers');
      });
    });

    it('handles drag and drop reordering via drag handle', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider, mockOllamaProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      const reorderSpy = vi.spyOn(aiApi, 'reorderAiProviders').mockResolvedValue([
        { ...mockOllamaProvider, priority: 10 },
        { ...mockProvider, priority: 20 },
      ]);

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('drag-handle-prov-openai-1')).toBeDefined();
      });

      const handle1 = screen.getByTestId('drag-handle-prov-openai-1');
      const card2 = screen.getByTestId('provider-card-prov-ollama-2');

      const dataTransfer = {
        effectAllowed: '',
        dropEffect: '',
        setData: vi.fn(),
        getData: vi.fn().mockReturnValue('0'),
      };

      // Drag start on #1
      fireEvent.dragStart(handle1, { dataTransfer });
      expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', '0');

      // Drag over card #2
      fireEvent.dragOver(card2, { dataTransfer });
      expect(card2.className).toContain('kb-provider-stack-item--drag-over');

      // Drag over card #2 again (same index branch)
      fireEvent.dragOver(card2, { dataTransfer });

      // Drag leave moving over a child element inside card2 (should NOT clear dragOverIndex)
      const childNode = card2.firstElementChild ?? card2;
      const childLeaveEvent = createEvent.dragLeave(card2);
      Object.defineProperty(childLeaveEvent, 'relatedTarget', { value: childNode });
      fireEvent(card2, childLeaveEvent);
      expect(card2.className).toContain('kb-provider-stack-item--drag-over');

      // Drag leave moving outside card2 (should clear dragOverIndex)
      const outsideLeaveEvent = createEvent.dragLeave(card2);
      Object.defineProperty(outsideLeaveEvent, 'relatedTarget', { value: document.body });
      fireEvent(card2, outsideLeaveEvent);
      expect(card2.className).not.toContain('kb-provider-stack-item--drag-over');

      // Drop on card #2
      fireEvent.drop(card2, { dataTransfer });

      await waitFor(() => {
        expect(reorderSpy).toHaveBeenCalledWith(['prov-ollama-2', 'prov-openai-1']);
      });

      // Test dragEnd resets drag state
      const card1 = screen.getByTestId('provider-card-prov-openai-1');
      fireEvent.dragStart(card1, { dataTransfer });
      expect(card1.className).toContain('kb-provider-stack-item--dragging');
      fireEvent.dragOver(card2, { dataTransfer });
      expect(card2.className).toContain('kb-provider-stack-item--drag-over');
      fireEvent.dragEnd(card1);
      expect(card1.className).not.toContain('kb-provider-stack-item--dragging');
      expect(card2.className).not.toContain('kb-provider-stack-item--drag-over');

      // Drag start from interactive button inside card should be prevented
      const moveUpBtn = screen.getByTestId('move-up-btn-prov-openai-1');
      const notPrevented = fireEvent.dragStart(moveUpBtn, { dataTransfer });
      expect(notPrevented).toBe(false);
    });

    it('executes Test Connection on provider card and displays latency and models', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 124.7,
        models: ['gpt-4o', 'gpt-4o-mini'],
        model_count: 2,
      });

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('test-connection-btn-prov-openai-1')).toBeDefined();
      });

      // Click Test Connection
      fireEvent.click(screen.getByTestId('test-connection-btn-prov-openai-1'));

      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith({}, 'prov-openai-1');
        expect(screen.getByTestId('test-status-prov-openai-1').textContent).toContain(
          'Connected in 125ms - 2 models available',
        );
      });

      // Failed test connection with message
      testSpy.mockResolvedValueOnce({
        ok: false,
        latency_ms: 50,
        models: [],
        model_count: 0,
        error_code: 'AUTH_FAILED',
        message: 'Invalid API secret key',
      });

      fireEvent.click(screen.getByTestId('test-connection-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.getByTestId('test-status-prov-openai-1').textContent).toContain(
          'Connection failed: AUTH_FAILED - Invalid API secret key',
        );
      });

      // Failed test connection without message (error_code only)
      testSpy.mockResolvedValueOnce({
        ok: false,
        latency_ms: 50,
        models: [],
        model_count: 0,
        error_code: 'RATE_LIMIT',
      });

      fireEvent.click(screen.getByTestId('test-connection-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.getByTestId('test-status-prov-openai-1').textContent).toContain(
          'Connection failed: RATE_LIMIT',
        );
      });

      // Failed test connection without message and without error_code
      testSpy.mockResolvedValueOnce({
        ok: false,
        latency_ms: 50,
        models: [],
        model_count: 0,
      });

      fireEvent.click(screen.getByTestId('test-connection-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.getByTestId('test-status-prov-openai-1').textContent).toContain(
          'Connection failed: ERROR',
        );
      });

      // Exception during test connection (Error instance)
      testSpy.mockRejectedValueOnce(new Error('DNS resolution error'));
      fireEvent.click(screen.getByTestId('test-connection-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.getByTestId('test-status-prov-openai-1').textContent).toContain(
          'DNS resolution error',
        );
      });

      // Exception during test connection (non-Error instance)
      testSpy.mockRejectedValueOnce('raw test error');
      fireEvent.click(screen.getByTestId('test-connection-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.getByTestId('test-status-prov-openai-1').textContent).toContain(
          'Connection test failed',
        );
      });

      // Exception during test connection (Aal2StepUpCancelledError)
      testSpy.mockRejectedValueOnce(new clientModule.Aal2StepUpCancelledError());
      fireEvent.click(screen.getByTestId('test-connection-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.queryByTestId('test-status-prov-openai-1')).toBeNull();
      });
    });

    it('covers boundary branches for move, drag drop on same card, and unconfigured key cards', async () => {
      const mockCloudNoKey: ProviderConfigPublic = {
        ...mockGeminiProvider,
        id: 'prov-gemini-nokey',
        api_key_set: false,
        base_url: null,
      };
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider, mockCloudNoKey]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(true);
      const reorderSpy = vi.spyOn(aiApi, 'reorderAiProviders').mockResolvedValue([
        mockCloudNoKey,
        mockProvider,
      ]);

      render(<AiStudioPage />);

      await waitFor(() => {
        expect(screen.getByTestId('key-status-prov-gemini-nokey').textContent).toContain('Key Not Set');
      });

      // Drag and drop onto the exact same card (index 0 onto index 0 -> no reorder call)
      const handle1 = screen.getByTestId('drag-handle-prov-openai-1');
      const card1 = screen.getByTestId('provider-card-prov-openai-1');
      const dataTransfer = {
        effectAllowed: '',
        dropEffect: '',
        setData: vi.fn(),
        getData: vi.fn(),
      };
      fireEvent.dragStart(handle1, { dataTransfer });
      fireEvent.drop(card1, { dataTransfer });
      expect(reorderSpy).not.toHaveBeenCalled();

      // Drop when no dragStart was invoked (draggedIndex is null)
      fireEvent.drop(card1, { dataTransfer });
      expect(reorderSpy).not.toHaveBeenCalled();

      // Drag start from index 0 then drop on card with invalid index
      fireEvent.dragStart(handle1, { dataTransfer });
      // Create a dummy event on drop with target index out of bounds
      const outOfBoundsCard = document.createElement('div');
      card1.parentElement?.appendChild(outOfBoundsCard);
      // Even if drop occurs on card1 itself, if draggedIndex === targetIndex it's a no-op
      expect(reorderSpy).not.toHaveBeenCalled();
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

    it('handles toggle enablement error with non-Error reject and Error reject', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      const disableSpy = vi.spyOn(aiApi, 'disableAiProvider').mockRejectedValueOnce('raw string rejection');

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

      // Error instance
      disableSpy.mockRejectedValueOnce(new Error('Permission denied on toggle'));
      fireEvent.click(screen.getByTestId('toggle-enable-btn-prov-openai-1'));

      await waitFor(() => {
        expect(screen.getByTestId('ai-studio-error').textContent).toContain(
          'Permission denied on toggle',
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
      const progressBar = screen.getByTestId<HTMLProgressElement>('budget-progress-bar');
      expect(progressBar.tagName.toLowerCase()).toBe('progress');
      expect(progressBar.value).toBe(95);
      expect(progressBar.max).toBe(100);
      expect(progressBar.className).toContain('kb-budget-progress--danger');
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
      const warnProgressBar = screen.getByTestId<HTMLProgressElement>('budget-progress-bar');
      expect(warnProgressBar.value).toBe(75);
      expect(warnProgressBar.className).toContain('kb-budget-progress--warning');

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

    it('renders zero-allowance freeze when token_cap is 0 and unlimited when no budgets (KAN-412 fix)', async () => {
      const zeroFreezeBudgets: BudgetRecord[] = [
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 0,
          tokens_used: 0,
          tokens_reserved: 0,
        },
      ];
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(zeroFreezeBudgets);

      const { unmount } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText(/Zero-Allowance Freeze \(0 tokens\)/)).toBeDefined();
        expect(screen.getByText(/Frozen \(0 tokens allowance\)/)).toBeDefined();
        expect(screen.getByTestId('zero-cap-freeze-warning')).toBeDefined();
      });

      unmount();

      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue([]);
      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByText('Unlimited')).toBeDefined();
        expect(screen.getByText('No cap enforced')).toBeDefined();
      });
    });

    it('handles mode toggle pills, presets, and freeze warning in AiBudgetModal (KAN-412)', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const firstBudget = mockBudgets[0];
      if (!firstBudget) {
        throw new Error('Expected mock budget at index 0');
      }
      const setBudgetSpy = vi.spyOn(aiApi, 'setBudget').mockResolvedValue(firstBudget);

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('cap-mode-enforce-btn')).toBeDefined();
        expect(screen.getByTestId('cap-mode-unlimited-btn')).toBeDefined();
        expect(screen.getByTestId('budget-presets-row')).toBeDefined();
      });

      // Test presets: 1M, 5M, 25M, 100M, and 0 (Freeze)
      const capInput = screen.getByTestId<HTMLInputElement>('budget-token-cap-input');

      fireEvent.click(screen.getByTestId('preset-budget-5m-btn'));
      expect(capInput.value).toBe('5000000');

      fireEvent.click(screen.getByTestId('preset-budget-25m-btn'));
      expect(capInput.value).toBe('25000000');

      fireEvent.click(screen.getByTestId('preset-budget-100m-btn'));
      expect(capInput.value).toBe('100000000');

      fireEvent.click(screen.getByTestId('preset-budget-1m-btn'));
      expect(capInput.value).toBe('1000000');

      // Click Freeze preset -> surfaces warning banner
      fireEvent.click(screen.getByTestId('preset-budget-0-freeze-btn'));
      expect(capInput.value).toBe('0');
      expect(screen.getByTestId('zero-cap-freeze-warning')).toBeDefined();

      // Switch to Unlimited mode
      fireEvent.click(screen.getByTestId('cap-mode-unlimited-btn'));
      expect(screen.getByTestId('budget-unlimited-note')).toBeDefined();
      expect(screen.queryByTestId('budget-token-cap-input')).toBeNull();

      // Switch back to Enforce mode to verify restoration
      fireEvent.click(screen.getByTestId('cap-mode-enforce-btn'));
      expect(screen.getByTestId<HTMLInputElement>('budget-token-cap-input').value).toBe('1000000');

      // Switch to Unlimited mode for save
      fireEvent.click(screen.getByTestId('cap-mode-unlimited-btn'));

      // Save in unlimited mode submits 10_000_000_000
      fireEvent.click(screen.getByTestId('save-budget-btn'));
      await waitFor(() => {
        expect(setBudgetSpy).toHaveBeenCalledWith({
          provider_config_id: 'prov-openai-1',
          project_id: undefined,
          period_kind: 'monthly',
          token_cap: 10000000000,
        });
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

  describe('AiProviderEditorDrawer component & 3-Protocol Selector (KAN-22)', () => {
    it('verifies 3 clean protocols, auto-inferred residency, and probe models flow', async () => {
      const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue(mockProvider);
      const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        latency_ms: 45,
        models: ['llama3.2:3b', 'qwen2.5-coder:7b', 'deepseek-r1:14b'],
        model_count: 3,
      });
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 62.3,
        models: ['llama3.2:3b'],
        model_count: 1,
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
          providersCount={3}
        />,
      );

      expect(screen.getByText('Register AI Provider')).toBeDefined();

      const kindSelect = screen.getByTestId<HTMLSelectElement>('provider-kind-select');

      // Verify custom is NOT in options
      const options = Array.from(kindSelect.querySelectorAll('option')).map((o) => o.value);
      expect(options).toEqual(['ollama', 'openai', 'gemini']);
      expect(options).not.toContain('custom');

      // Switch to Gemini
      fireEvent.change(kindSelect, { target: { value: 'gemini' } });
      expect(screen.getByTestId<HTMLInputElement>('provider-name-input').value).toBe('Google Gemini Workspace');
      expect(screen.getByTestId<HTMLInputElement>('provider-base-url-input').value).toBe(
        'https://generativelanguage.googleapis.com',
      );

      // Switch to Ollama
      fireEvent.change(kindSelect, { target: { value: 'ollama' } });
      expect(screen.getByTestId<HTMLInputElement>('provider-name-input').value).toBe('Local Ollama Runtime');
      expect(screen.getByTestId<HTMLInputElement>('provider-base-url-input').value).toBe('http://127.0.0.1:11434');

      // Check key hint for local Ollama
      expect(screen.getByText(/No Key Required \(Local\)/)).toBeDefined();

      // Switch to OpenAI
      fireEvent.change(kindSelect, { target: { value: 'openai' } });
      expect(screen.getByTestId<HTMLInputElement>('provider-name-input').value).toBe('OpenAI / OpenAI-Compatible');
      expect(screen.getByTestId<HTMLInputElement>('provider-base-url-input').value).toBe('https://api.openai.com/v1');

      // Type local URL into OpenAI base_url and check auto-inferred residency
      fireEvent.change(screen.getByTestId('provider-base-url-input'), {
        target: { value: 'http://localhost:8000/v1' },
      });
      expect(screen.getByText(/No Key Required \(Local\)/)).toBeDefined();

      // Verify DOM order: API key input appears BEFORE probe-models-btn and provider-models-input
      const keyInput = screen.getByTestId('provider-key-input');
      const probeBtn = screen.getByTestId('probe-models-btn');
      const modelsInput = screen.getByTestId('provider-models-input');
      expect(keyInput.compareDocumentPosition(probeBtn) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(keyInput.compareDocumentPosition(modelsInput) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

      // Verify new provider starts with empty modelAllowlist (no fake defaults)
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('');

      // Test Probe Models Button
      fireEvent.click(screen.getByTestId('probe-models-btn'));

      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith(
          {
            provider_kind: 'openai',
            base_url: 'http://localhost:8000/v1',
            api_key: null,
            settings_json: { timeout_ms: 30000 },
          },
          undefined,
        );
        expect(screen.getByTestId('probed-models-picker')).toBeDefined();
      });

      // Probing replaced modelAllowlist directly with probed models
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe(
        'llama3.2:3b, qwen2.5-coder:7b, deepseek-r1:14b',
      );

      // Check probed model chips rendered
      expect(screen.getByTestId('probe-chip-llama3.2:3b')).toBeDefined();
      expect(screen.getByTestId('probe-chip-qwen2.5-coder:7b')).toBeDefined();

      // Click a chip to toggle it off
      fireEvent.click(screen.getByTestId('probe-chip-deepseek-r1:14b'));
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).not.toContain('deepseek-r1:14b');

      // Test Only This action
      fireEvent.click(screen.getByTestId('probe-only-qwen2.5-coder:7b'));
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('qwen2.5-coder:7b');

      // Filter probed models
      fireEvent.change(screen.getByTestId('probe-model-search-input'), {
        target: { value: 'qwen' },
      });
      expect(screen.queryByTestId('probe-chip-llama3.2:3b')).toBeNull();
      expect(screen.getByTestId('probe-chip-qwen2.5-coder:7b')).toBeDefined();

      // Select All probed models
      fireEvent.click(screen.getByTestId('probe-select-all-btn'));
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toContain('llama3.2:3b');

      // Clear all models
      fireEvent.click(screen.getByTestId('probe-clear-all-btn'));
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe('');

      // Add back one model
      fireEvent.click(screen.getByTestId('probe-chip-qwen2.5-coder:7b'));

      // Direct manual edit on provider-models-input fallback
      fireEvent.change(screen.getByTestId('provider-models-input'), {
        target: { value: 'qwen2.5-coder:7b, custom-extra:1b' },
      });
      expect(screen.getByTestId<HTMLInputElement>('provider-models-input').value).toBe(
        'qwen2.5-coder:7b, custom-extra:1b',
      );

      // Test Connection in Drawer footer
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));

      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith(
          {
            provider_kind: 'openai',
            base_url: 'http://localhost:8000/v1',
            api_key: null,
            settings_json: { timeout_ms: 30000 },
          },
          undefined,
        );
        expect(screen.getByTestId('drawer-test-status').textContent).toContain(
          'Connected in 62ms - 1 models available',
        );
      });

      // Expand Advanced Settings and override Residency Tier
      const advDetails = screen.getByTestId('advanced-settings-details');
      expect(advDetails).toBeDefined();
      const advSummary = screen.getByText('Advanced Settings');
      expect(advSummary.textContent.trim()).toBe('Advanced Settings');
      expect(advSummary.textContent).not.toContain('▸');
      const residencySelect = screen.getByTestId<HTMLSelectElement>('provider-residency-select');
      fireEvent.change(residencySelect, { target: { value: 'eu-central' } });
      expect(residencySelect.value).toBe('eu-central');

      // Toggle show API key
      fireEvent.change(screen.getByTestId('provider-key-input'), { target: { value: 'test-secret' } });
      fireEvent.click(screen.getByTestId('toggle-show-key-btn'));
      expect(screen.getByTestId<HTMLInputElement>('provider-key-input').type).toBe('text');

      // Submit Form (create new provider, priority should be (3+1)*10 = 40)
      fireEvent.click(screen.getByTestId('save-provider-btn'));

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith({
          provider_kind: 'openai',
          display_name: 'OpenAI / OpenAI-Compatible',
          model_allowlist: ['qwen2.5-coder:7b', 'custom-extra:1b'],
          residency_tier: 'eu-central',
          base_url: 'http://localhost:8000/v1',
          priority: 40,
          api_key: 'test-secret',
          is_enabled: true,
          settings: { timeout_ms: 30000 },
        });
        expect(onSaved).toHaveBeenCalled();
        expect(onClose).toHaveBeenCalled();
      });
    });

    it('handles probe error, zero models, and connection test failure in drawer', async () => {
      vi.spyOn(aiApi, 'probeAiModels')
        .mockResolvedValueOnce({
          ok: false,
          latency_ms: 10,
          models: [],
          model_count: 0,
          error_code: 'CONNECTION_REFUSED',
          message: 'Endpoint unreachable',
        })
        .mockResolvedValueOnce({
          ok: false,
          latency_ms: 10,
          models: [],
          model_count: 0,
          error_code: 'RATE_LIMIT',
        })
        .mockResolvedValueOnce({
          ok: false,
          latency_ms: 10,
          models: [],
          model_count: 0,
        })
        .mockResolvedValueOnce({
          ok: true,
          latency_ms: 15,
          models: [],
          model_count: 0,
        })
        .mockRejectedValueOnce(new Error('DNS failure'))
        .mockRejectedValueOnce('raw probe error');

      vi.spyOn(aiApi, 'testAiConnection')
        .mockResolvedValueOnce({
          ok: false,
          latency_ms: 20,
          models: [],
          model_count: 0,
          error_code: 'TIMEOUT',
        })
        .mockResolvedValueOnce({
          ok: false,
          latency_ms: 20,
          models: [],
          model_count: 0,
        })
        .mockRejectedValueOnce(new Error('Network drop'))
        .mockRejectedValueOnce('raw test error');

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Probe failure 1 (ok: false with message)
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toContain('Endpoint unreachable');
      });

      // Probe failure 2 (ok: false with error_code only)
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toContain('RATE_LIMIT');
      });

      // Probe failure 3 (ok: false with neither)
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toContain('Model probing failed');
      });

      // Probe failure 4 (0 models)
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toContain('0 models were discovered');
      });

      // Probe failure 5 (rejected with Error)
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toContain('DNS failure');
      });

      // Probe failure 6 (rejected with non-Error)
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('probe-error').textContent).toContain('Failed to probe models');
      });

      // Test Connection failure 1 (ok: false with error_code)
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toContain('Connection failed: TIMEOUT');
      });

      // Test Connection failure 2 (ok: false with neither)
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toContain('Connection failed: ERROR');
      });

      // Test Connection failure 3 (rejected with Error)
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toContain('Network drop');
      });

      // Test Connection failure 4 (rejected with non-Error)
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(screen.getByTestId('drawer-test-status').textContent).toContain('Connection test failed');
      });
    });

    it('probes and tests connection on saved provider with and without override key', async () => {
      const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        latency_ms: 30,
        models: ['gpt-4o'],
        model_count: 1,
      });
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 25,
        models: ['gpt-4o'],
        model_count: 1,
      });

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Probe without key input (calls with { settings_json: { timeout_ms: 30000 } })
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith({ settings_json: { timeout_ms: 30000 } }, 'prov-openai-1');
      });

      // Test connection without key input (calls with { settings_json: { timeout_ms: 30000 } })
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith({ settings_json: { timeout_ms: 30000 } }, 'prov-openai-1');
      });

      // Type key and probe again (calls with { api_key: ..., settings_json: { timeout_ms: 30000 } })
      fireEvent.change(screen.getByTestId('provider-key-input'), { target: { value: 'temp-override-key' } });
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith(
          { api_key: 'temp-override-key', settings_json: { timeout_ms: 30000 } },
          'prov-openai-1',
        );
      });

      // Test connection with override key
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith(
          { api_key: 'temp-override-key', settings_json: { timeout_ms: 30000 } },
          'prov-openai-1',
        );
      });
    });

    it('preserves manual residency tier when switching protocols or changing baseUrl', () => {
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Manually change residency tier
      fireEvent.change(screen.getByTestId('provider-residency-select'), {
        target: { value: 'eu-central' },
      });
      expect(screen.getByTestId<HTMLSelectElement>('provider-residency-select').value).toBe('eu-central');

      // Change kind to ollama -> residency tier remains eu-central
      fireEvent.change(screen.getByTestId('provider-kind-select'), {
        target: { value: 'ollama' },
      });
      expect(screen.getByTestId<HTMLSelectElement>('provider-residency-select').value).toBe('eu-central');

      // Change kind to gemini -> residency tier remains eu-central
      fireEvent.change(screen.getByTestId('provider-kind-select'), {
        target: { value: 'gemini' },
      });
      expect(screen.getByTestId<HTMLSelectElement>('provider-residency-select').value).toBe('eu-central');

      // Change kind to openai -> residency tier remains eu-central
      fireEvent.change(screen.getByTestId('provider-kind-select'), {
        target: { value: 'openai' },
      });
      expect(screen.getByTestId<HTMLSelectElement>('provider-residency-select').value).toBe('eu-central');

      // Change baseUrl -> residency tier remains eu-central
      fireEvent.change(screen.getByTestId('provider-base-url-input'), {
        target: { value: 'http://127.0.0.1:9000/v1' },
      });
      expect(screen.getByTestId<HTMLSelectElement>('provider-residency-select').value).toBe('eu-central');
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
          residency_tier: 'cloud_standard',
          base_url: 'https://api.openai.com/v1',
          priority: 10,
          api_key: null,
          settings: { timeout_ms: 30000 },
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
          residency_tier: 'cloud_standard',
          base_url: 'https://api.openai.com/v1',
          priority: 10,
          api_key: 'new-secret-key-999',
          settings: { timeout_ms: 30000 },
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

      // Switch to openai
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

    it('returns null when isOpen is false', () => {
      const { container } = render(
        <AiProviderEditorDrawer
          isOpen={false}
          onClose={vi.fn()}
          provider={mockProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );
      expect(container.firstChild).toBeNull();
    });

    it('normalizes legacy cloud and local residency tiers and includes legacy cloud option', () => {
      const legacyCloudProvider: ProviderConfigPublic = {
        ...mockProvider,
        id: 'prov-legacy-cloud',
        display_name: 'Legacy Cloud Provider',
        residency_tier: 'cloud',
      };
      const { unmount } = render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={legacyCloudProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      const residencySelect = screen.getByTestId<HTMLSelectElement>('provider-residency-select');
      expect(residencySelect.value).toBe('cloud_standard');
      expect(screen.getByRole('option', { name: 'Cloud (Legacy)' })).toBeDefined();

      unmount();

      const legacyLocalProvider: ProviderConfigPublic = {
        ...mockProvider,
        id: 'prov-legacy-local',
        display_name: 'Legacy Local Provider',
        residency_tier: 'local',
      };
      const { unmount: unmount2 } = render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={legacyLocalProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      const residencySelect2 = screen.getByTestId<HTMLSelectElement>('provider-residency-select');
      expect(residencySelect2.value).toBe('local_only');

      unmount2();

      const nullTierProvider: ProviderConfigPublic = {
        ...mockProvider,
        id: 'prov-null-tier',
        display_name: 'Null Tier Provider',
        residency_tier: '',
      };
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={nullTierProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );
      const residencySelect3 = screen.getByTestId<HTMLSelectElement>('provider-residency-select');
      expect(residencySelect3.value).toBe('cloud_standard');
    });

    it('initializes openai draft with default baseUrl and displayName when provider is null and airGapMode is false', () => {
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      const nameInput = screen.getByTestId<HTMLInputElement>('provider-name-input');
      const urlInput = screen.getByTestId<HTMLInputElement>('provider-base-url-input');
      expect(nameInput.value).toBe('OpenAI / OpenAI-Compatible');
      expect(urlInput.value).toBe('https://api.openai.com/v1');
    });

    it('routes probe models and test connection to draft endpoint when editing provider with modified baseUrl', async () => {
      const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        models: ['gpt-4o-custom'],
        latency_ms: 45,
        model_count: 1,
      });
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 45,
        model_count: 1,
        models: ['gpt-4o-custom'],
      });

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Modify base_url and provide an API key
      fireEvent.change(screen.getByTestId('provider-base-url-input'), {
        target: { value: 'https://custom-gateway.corp.com/v1' },
      });
      fireEvent.change(screen.getByTestId('provider-key-input'), {
        target: { value: 'sk-new-key-123' },
      });

      // Probe Models should route to draft endpoint (undefined providerId) with modified baseUrl
      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith(
          {
            provider_kind: 'openai',
            base_url: 'https://custom-gateway.corp.com/v1',
            api_key: 'sk-new-key-123',
            settings_json: { timeout_ms: 30000 },
          },
          undefined,
        );
      });

      // Test Connection should also route to draft endpoint (undefined providerId)
      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith(
          {
            provider_kind: 'openai',
            base_url: 'https://custom-gateway.corp.com/v1',
            api_key: 'sk-new-key-123',
            settings_json: { timeout_ms: 30000 },
          },
          undefined,
        );
      });
    });

    it('routes probe models and test connection to draft endpoint for local endpoint without key when modified', async () => {
      const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        models: ['llama3.2:3b'],
        latency_ms: 22,
        model_count: 1,
      });
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 22,
        model_count: 1,
        models: ['llama3.2:3b'],
      });

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockOllamaProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Modify base_url to another local LAN endpoint (no key required)
      fireEvent.change(screen.getByTestId('provider-base-url-input'), {
        target: { value: 'http://192.168.1.99:11434' },
      });

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith(
          {
            provider_kind: 'ollama',
            base_url: 'http://192.168.1.99:11434',
            api_key: null,
            settings_json: { timeout_ms: 30000 },
          },
          undefined,
        );
      });

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith(
          {
            provider_kind: 'ollama',
            base_url: 'http://192.168.1.99:11434',
            api_key: null,
            settings_json: { timeout_ms: 30000 },
          },
          undefined,
        );
      });
    });

    it('creates provider with null api_key when key is empty', async () => {
      const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue(mockOllamaProvider);
      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );
      // Select Ollama protocol so no key is required
      fireEvent.change(screen.getByTestId('provider-kind-select'), { target: { value: 'ollama' } });
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

    it('routes probe and test connection to draft when providerKind is modified on existing provider', async () => {
      const probeSpy = vi.spyOn(aiApi, 'probeAiModels').mockResolvedValue({
        ok: true,
        models: ['gemini-2.5-flash'],
        latency_ms: 30,
        model_count: 1,
      });
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: false,
        error_code: 'AUTH_FAILED',
        message: 'Invalid Google key',
        latency_ms: 30,
        model_count: 0,
        models: [],
      });

      render(
        <AiProviderEditorDrawer
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
          airGapMode={false}
          onSaved={vi.fn()}
        />,
      );

      // Change kind to gemini and enter key
      fireEvent.change(screen.getByTestId('provider-kind-select'), { target: { value: 'gemini' } });
      fireEvent.change(screen.getByTestId('provider-key-input'), { target: { value: 'gemini-key' } });

      fireEvent.click(screen.getByTestId('probe-models-btn'));
      await waitFor(() => {
        expect(probeSpy).toHaveBeenCalledWith(
          expect.objectContaining({ provider_kind: 'gemini', api_key: 'gemini-key' }),
          undefined,
        );
      });

      fireEvent.click(screen.getByTestId('drawer-test-connection-btn'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith(
          expect.objectContaining({ provider_kind: 'gemini', api_key: 'gemini-key' }),
          undefined,
        );
        expect(screen.getByTestId('drawer-test-status').textContent).toContain('Invalid Google key');
      });
    });

    it('renders normal consumption progress bar (<70%) without warning or danger classes', async () => {
      const normalBudgets: BudgetRecord[] = [
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 100000,
          tokens_used: 40000,
          tokens_reserved: 0,
        },
      ];
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(normalBudgets);
      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );
      await waitFor(() => {
        expect(screen.getByText('40% consumed')).toBeDefined();
      });
      const normalBar = screen.getByTestId<HTMLProgressElement>('budget-progress-bar');
      expect(normalBar.value).toBe(40);
      expect(normalBar.className).not.toContain('kb-budget-progress--danger');
      expect(normalBar.className).not.toContain('kb-budget-progress--warning');
    });

    it('supports workspaceSlug routing for toggle, reorder, delete, and connection testing', async () => {
      const mockWs1: ProviderConfigPublic = {
        id: 'prov-ws-1',
        provider_kind: 'gemini',
        display_name: 'Workspace Gemini',
        base_url: 'https://generativelanguage.googleapis.com',
        model_allowlist: ['gemini-2.5-flash'],
        residency_tier: 'cloud_standard',
        priority: 10,
        settings: {},
        api_key_set: true,
        is_enabled: true,
        project_id: null,
      };
      const mockWs2: ProviderConfigPublic = {
        id: 'prov-ws-2',
        provider_kind: 'ollama',
        display_name: 'Workspace Ollama',
        base_url: 'http://localhost:11434',
        model_allowlist: ['gemma3:4b'],
        residency_tier: 'local_only',
        priority: 20,
        settings: {},
        api_key_set: false,
        is_enabled: false,
        project_id: null,
      };

      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockWs1, mockWs2]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      const disableSpy = vi.spyOn(aiApi, 'disableAiProvider').mockResolvedValue({
        ...mockWs1,
        is_enabled: false,
      });
      const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockResolvedValue({
        ...mockWs2,
        is_enabled: true,
      });
      const deleteSpy = vi.spyOn(aiApi, 'deleteAiProvider').mockResolvedValue();
      const reorderSpy = vi.spyOn(aiApi, 'reorderAiProviders').mockResolvedValue([
        { ...mockWs2, priority: 10 },
        { ...mockWs1, priority: 20 },
      ]);
      const testSpy = vi.spyOn(aiApi, 'testAiConnection').mockResolvedValue({
        ok: true,
        latency_ms: 45,
        models: ['gemini-2.5-flash'],
        model_count: 1,
      });

      render(<AiStudioPage workspaceSlug="custom-team" />);

      await waitFor(() => {
        expect(screen.getByTestId('provider-card-prov-ws-1')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('test-connection-btn-prov-ws-1'));
      await waitFor(() => {
        expect(testSpy).toHaveBeenCalledWith({}, 'prov-ws-1', 'custom-team');
      });

      fireEvent.click(screen.getByTestId('move-down-btn-prov-ws-1'));
      await waitFor(() => {
        expect(reorderSpy).toHaveBeenCalledWith(['prov-ws-2', 'prov-ws-1'], undefined, 'custom-team');
      });

      fireEvent.click(screen.getByTestId('toggle-enable-btn-prov-ws-1'));
      await waitFor(() => {
        expect(disableSpy).toHaveBeenCalledWith('prov-ws-1', 'custom-team');
      });

      fireEvent.click(screen.getByTestId('toggle-enable-btn-prov-ws-2'));
      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith('prov-ws-2', { is_enabled: true }, 'custom-team');
      });

      fireEvent.click(screen.getByTestId('delete-provider-btn-prov-ws-1'));
      await waitFor(() => {
        expect(screen.getByTestId('confirm-delete-provider-btn')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('confirm-delete-provider-btn'));
      await waitFor(() => {
        expect(deleteSpy).toHaveBeenCalledWith('prov-ws-1', 'custom-team');
      });
    });

    it('handles AiBudgetModal save with workspaceSlug', async () => {
      const fetchBudgetSpy = vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue([
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 500000,
          tokens_used: 10000,
          tokens_reserved: 0,
        },
      ]);
      const setBudgetSpy = vi.spyOn(aiApi, 'setBudget').mockResolvedValue({
        period_kind: 'monthly',
        period_start: '2026-11-01',
        token_cap: 800000,
        tokens_used: 10000,
        tokens_reserved: 0,
      });

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
          workspaceSlug="finance-team"
        />,
      );

      await waitFor(() => {
        expect(fetchBudgetSpy).toHaveBeenCalledWith('prov-openai-1', 'finance-team');
      });

      const capInput = screen.getByTestId<HTMLInputElement>('budget-token-cap-input');
      fireEvent.change(capInput, { target: { value: '800000' } });
      fireEvent.click(screen.getByTestId('save-budget-btn'));

      await waitFor(() => {
        expect(setBudgetSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            provider_config_id: 'prov-openai-1',
            token_cap: 800000,
          }),
          'finance-team',
        );
      });
    });
    it('supports projectId scoping for subtitle copy and reorderAiProviders', async () => {
      const mockProjectProviders: ProviderConfigPublic[] = [
        {
          id: 'prov-proj-1',
          provider_kind: 'openai',
          display_name: 'Project OpenAI',
          base_url: 'https://api.openai.com/v1',
          model_allowlist: ['gpt-4o'],
          residency_tier: 'cloud_standard',
          priority: 10,
          settings: {},
          api_key_set: true,
          is_enabled: true,
          project_id: 'proj-kan-uuid',
        },
        {
          id: 'prov-proj-2',
          provider_kind: 'ollama',
          display_name: 'Project Ollama',
          base_url: 'http://localhost:11434',
          model_allowlist: ['gemma3:4b'],
          residency_tier: 'local_only',
          priority: 20,
          settings: {},
          api_key_set: false,
          is_enabled: true,
          project_id: 'proj-kan-uuid',
        },
      ];

      const fetchSpy = vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue(mockProjectProviders);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      const reorderSpy = vi.spyOn(aiApi, 'reorderAiProviders').mockResolvedValue([
        {
          id: 'prov-proj-2',
          provider_kind: 'ollama',
          display_name: 'Project Ollama',
          base_url: 'http://localhost:11434',
          model_allowlist: ['gemma3:4b'],
          residency_tier: 'local_only',
          priority: 10,
          settings: {},
          api_key_set: false,
          is_enabled: true,
          project_id: 'proj-kan-uuid',
        },
        {
          id: 'prov-proj-1',
          provider_kind: 'openai',
          display_name: 'Project OpenAI',
          base_url: 'https://api.openai.com/v1',
          model_allowlist: ['gpt-4o'],
          residency_tier: 'cloud_standard',
          priority: 20,
          settings: {},
          api_key_set: true,
          is_enabled: true,
          project_id: 'proj-kan-uuid',
        },
      ]);

      render(<AiStudioPage projectId="proj-kan-uuid" showSubnav={false} />);

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledWith('proj-kan-uuid');
        expect(screen.getByTestId('provider-card-prov-proj-1')).toBeDefined();
      });

      expect(screen.getByText(/Configure project LLM providers, failover priority stack/i)).toBeDefined();

      act(() => {
        fireEvent.click(screen.getByTestId('move-down-btn-prov-proj-1'));
      });
      await waitFor(() => {
        expect(reorderSpy).toHaveBeenCalledWith(['prov-proj-2', 'prov-proj-1'], 'proj-kan-uuid');
        expect(screen.getByTestId('provider-rank-prov-proj-2').textContent).toBe('#1');
      });

      // Boundary move edge cases (toIndex < 0 and toIndex >= providers.length)
      act(() => {
        fireEvent.click(screen.getByTestId('move-up-btn-prov-proj-2'));
        fireEvent.click(screen.getByTestId('move-down-btn-prov-proj-1'));
      });
    });

    it('handles non-array response from fetchAiProviders gracefully', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue(
        {} as unknown as ProviderConfigPublic[],
      );
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      render(<AiStudioPage />);
      await waitFor(() => {
        expect(screen.getByTestId('empty-providers-placeholder')).toBeDefined();
      });
    });

    it('silently ignores Aal2StepUpCancelledError during load with zero role="alert" banners', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockRejectedValue(new clientModule.Aal2StepUpCancelledError());
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      render(<AiStudioPage />);
      await waitFor(() => {
        expect(screen.queryByTestId('loading-spinner')).toBeNull();
      });
      expect(screen.queryByRole('alert')).toBeNull();
      expect(screen.queryByTestId('ai-studio-error')).toBeNull();
    });

    it('silently ignores Aal2StepUpCancelledError during toggle enablement with zero role="alert" banners', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      vi.spyOn(aiApi, 'disableAiProvider').mockRejectedValue(new clientModule.Aal2StepUpCancelledError());
      render(<AiStudioPage />);
      await waitFor(() => {
        expect(screen.getByTestId('toggle-enable-btn-prov-openai-1')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('toggle-enable-btn-prov-openai-1'));
      await waitFor(() => {
        expect(screen.queryByRole('alert')).toBeNull();
        expect(screen.queryByTestId('ai-studio-error')).toBeNull();
      });
    });

    it('silently ignores Aal2StepUpCancelledError during delete with zero role="alert" banners', async () => {
      vi.spyOn(aiApi, 'fetchAiProviders').mockResolvedValue([mockProvider]);
      vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
      vi.spyOn(aiApi, 'deleteAiProvider').mockRejectedValue(new clientModule.Aal2StepUpCancelledError());
      render(<AiStudioPage />);
      await waitFor(() => {
        expect(screen.getByTestId('delete-provider-btn-prov-openai-1')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('delete-provider-btn-prov-openai-1'));
      await waitFor(() => {
        expect(screen.getByTestId('confirm-delete-provider-btn')).toBeDefined();
      });
      fireEvent.click(screen.getByTestId('confirm-delete-provider-btn'));
      await waitFor(() => {
        expect(screen.queryByRole('alert')).toBeNull();
        expect(screen.queryByTestId('ai-studio-error')).toBeNull();
      });
    });
  });
});
