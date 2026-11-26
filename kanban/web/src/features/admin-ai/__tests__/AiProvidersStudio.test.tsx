// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { AiStudioPage } from '../AiStudioPage';
import * as aiApi from '../aiAdminApi';
import type { ProviderConfigPublic } from '../aiAdminApi';

describe('AiProvidersStudio Immediate Refetch & Optimistic Rendering (KAN-434)', () => {
  const sampleSavedProvider: ProviderConfigPublic = {
    id: 'prov-created-434',
    provider_kind: 'openai',
    display_name: 'Newly Created Fast Provider',
    base_url: 'https://api.openai.com/v1',
    model_allowlist: ['gpt-4o'],
    residency_tier: 'cloud_standard',
    priority: 10,
    settings: {},
    api_key_set: true,
    is_enabled: true,
    project_id: null,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('immediately renders newly created provider card without requiring page reload even if background refetch lags or returns empty', async () => {
    // Provide an empty response on refetches to simulate race / read-replica lag
    vi.spyOn(aiApi, 'fetchAiProviders').mockImplementation(() => Promise.resolve([]));
    vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
    const createSpy = vi.spyOn(aiApi, 'createAiProvider').mockResolvedValue(sampleSavedProvider);

    render(<AiStudioPage />);

    // Initially shows empty state
    await waitFor(() => {
      expect(screen.getByTestId('empty-providers-placeholder')).toBeDefined();
    });

    // 2. Click "+ Register Provider" button to open drawer
    const addBtn = screen.getByTestId('register-provider-btn');
    fireEvent.click(addBtn);

    // 3. Drawer is open; fill display name
    await waitFor(() => {
      expect(screen.getByTestId('provider-name-input')).toBeDefined();
    });

    const nameInput = screen.getByTestId('provider-name-input');
    fireEvent.change(nameInput, { target: { value: 'Newly Created Fast Provider' } });

    // 4. Submit form
    const saveBtn = screen.getByTestId('save-provider-btn');
    act(() => {
      fireEvent.click(saveBtn);
    });

    expect(createSpy).toHaveBeenCalled();

    // 5. Newly created provider card MUST immediately render in DOM, without page reload!
    await waitFor(() => {
      expect(screen.getByText('Newly Created Fast Provider')).toBeDefined();
    });

    // The empty state message must NOT be shown
    expect(screen.queryByTestId('empty-providers-placeholder')).toBeNull();
  });

  it('updates provider card immediately when updating an existing provider', async () => {
    let currentProviders = [sampleSavedProvider];
    vi.spyOn(aiApi, 'fetchAiProviders').mockImplementation(() => Promise.resolve(currentProviders));
    vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);

    const updatedProvider: ProviderConfigPublic = {
      ...sampleSavedProvider,
      display_name: 'Renamed Provider 434',
    };
    const updateSpy = vi.spyOn(aiApi, 'updateAiProvider').mockImplementation(() => {
      currentProviders = [updatedProvider];
      return Promise.resolve(updatedProvider);
    });

    render(<AiStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Newly Created Fast Provider')).toBeDefined();
    });

    // Click edit on the provider card
    const editBtn = screen.getByTestId('edit-provider-btn-prov-created-434');
    fireEvent.click(editBtn);

    await waitFor(() => {
      expect(screen.getByTestId('provider-name-input')).toBeDefined();
    });

    const nameInput = screen.getByTestId('provider-name-input');
    fireEvent.change(nameInput, { target: { value: 'Renamed Provider 434' } });

    const saveBtn = screen.getByTestId('save-provider-btn');
    act(() => {
      fireEvent.click(saveBtn);
    });

    expect(updateSpy).toHaveBeenCalled();

    // Should immediately display renamed title
    await waitFor(() => {
      expect(screen.getByText('Renamed Provider 434')).toBeDefined();
    });
  });

  it('removes deleted provider card immediately and removes it from recent saved cache', async () => {
    let currentProviders = [sampleSavedProvider];
    vi.spyOn(aiApi, 'fetchAiProviders').mockImplementation(() => Promise.resolve(currentProviders));
    vi.spyOn(aiApi, 'fetchAirGapMode').mockResolvedValue(false);
    const deleteSpy = vi.spyOn(aiApi, 'deleteAiProvider').mockImplementation((id: string) => {
      currentProviders = currentProviders.filter((p) => p.id !== id);
      return Promise.resolve();
    });

    render(<AiStudioPage />);

    await waitFor(() => {
      expect(screen.getByText('Newly Created Fast Provider')).toBeDefined();
    });

    // Click delete
    const deleteBtn = screen.getByTestId('delete-provider-btn-prov-created-434');
    fireEvent.click(deleteBtn);

    // Confirm dialog appears
    await waitFor(() => {
      expect(screen.getByTestId('delete-provider-modal')).toBeDefined();
    });

    const confirmBtn = screen.getByTestId('confirm-delete-provider-btn');
    act(() => {
      fireEvent.click(confirmBtn);
    });

    expect(deleteSpy).toHaveBeenCalledWith('prov-created-434');

    await waitFor(() => {
      expect(screen.queryByText('Newly Created Fast Provider')).toBeNull();
    });
  });
});
