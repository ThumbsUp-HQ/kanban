// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentOnboardingPromptCard } from '../AgentOnboardingPromptCard';
import * as personalSettingsApi from '../personalSettingsApi';
import * as clipboardUtil from '../../../utils/clipboard';

vi.mock('../personalSettingsApi', async () => {
  const actual = await vi.importActual('../personalSettingsApi');
  return {
    ...actual,
    fetchUserPreferences: vi.fn(),
    updateUserPreferences: vi.fn(),
  };
});

vi.mock('../../../utils/clipboard', () => ({
  copyToClipboard: vi.fn().mockResolvedValue(true),
}));

describe('AgentOnboardingPromptCard component', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderCard = (projectKey?: string) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <AgentOnboardingPromptCard projectKey={projectKey} />
      </QueryClientProvider>,
    );
  };

  it('renders card with default values and local folder persistence', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'local_only',
        execution_mode: 'swarm',
        model_strategy: 'quota_sipping_flash',
        qa_rigor: 'strict_forensic',
        custom_notes: '',
      },
    });

    renderCard();

    expect(screen.getByTestId('agent-onboarding-prompt-card')).toBeDefined();
    expect(screen.getByRole('heading', { name: /Agent Onboarding Prompt/ })).toBeDefined();

    const scopeSelect = screen.getByTestId('pref-scope-select') as HTMLSelectElement;
    expect(scopeSelect.value).toBe('local_only');

    const preview = screen.getByTestId('agent-onboarding-prompt-preview');
    expect(preview.textContent).toContain('strictly to the local project folder');
    expect(preview.textContent).toContain('do NOT modify global home/system directories');

    // Warning banner should NOT be present when local_only
    expect(screen.queryByTestId('onboarding-scope-warning')).toBeNull();
  });

  it('renders warning banner and updates prompt when switching to global_allowed', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'local_only',
        execution_mode: 'swarm',
        model_strategy: 'quota_sipping_flash',
        qa_rigor: 'strict_forensic',
        custom_notes: '',
      },
    });

    renderCard();

    const scopeSelect = screen.getByTestId('pref-scope-select') as HTMLSelectElement;
    fireEvent.change(scopeSelect, { target: { value: 'global_allowed' } });

    expect(scopeSelect.value).toBe('global_allowed');
    expect(screen.getByTestId('onboarding-scope-warning')).toBeDefined();

    const preview = screen.getByTestId('agent-onboarding-prompt-preview');
    expect(preview.textContent).toContain('global workstation directories');
  });

  it('updates form controls and prompt preview when changing options', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'local_only',
        execution_mode: 'swarm',
        model_strategy: 'quota_sipping_flash',
        qa_rigor: 'strict_forensic',
        custom_notes: '',
      },
    });

    renderCard('KAN-403');

    // Project key context is included in prompt
    const preview = screen.getByTestId('agent-onboarding-prompt-preview');
    expect(preview.textContent).toContain('for project KAN-403');

    // Change Execution Mode
    const execSelect = screen.getByTestId('pref-exec-mode-select') as HTMLSelectElement;
    fireEvent.change(execSelect, { target: { value: 'teamwork' } });
    expect(execSelect.value).toBe('teamwork');

    // Change Model Strategy
    const modelSelect = screen.getByTestId('pref-model-strat-select') as HTMLSelectElement;
    fireEvent.change(modelSelect, { target: { value: 'hybrid' } });
    expect(modelSelect.value).toBe('hybrid');

    // Change QA Rigor
    const qaSelect = screen.getByTestId('pref-qa-rigor-select') as HTMLSelectElement;
    fireEvent.change(qaSelect, { target: { value: 'standard' } });
    expect(qaSelect.value).toBe('standard');

    // Change Custom Notes
    const notesInput = screen.getByTestId('pref-custom-notes-input') as HTMLTextAreaElement;
    fireEvent.change(notesInput, { target: { value: 'Special note for agent.' } });
    expect(notesInput.value).toBe('Special note for agent.');
    expect(preview.textContent).toContain('Notes: Special note for agent.');
  });

  it('copies prompt to clipboard with feedback', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'local_only',
        execution_mode: 'swarm',
        model_strategy: 'quota_sipping_flash',
        qa_rigor: 'strict_forensic',
        custom_notes: '',
      },
    });

    renderCard();

    const copyBtn = screen.getByTestId('copy-agent-onboarding-prompt-btn');
    fireEvent.click(copyBtn);

    expect(clipboardUtil.copyToClipboard).toHaveBeenCalledWith(
      expect.stringContaining('strictly to the local project folder'),
    );

    await waitFor(() => {
      expect(screen.getByText('Copied Prompt!')).toBeDefined();
    });
  });

  it('saves preferences successfully via mutation', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'local_only',
        execution_mode: 'swarm',
        model_strategy: 'quota_sipping_flash',
        qa_rigor: 'strict_forensic',
        custom_notes: '',
      },
    });

    vi.mocked(personalSettingsApi.updateUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'local_only',
        execution_mode: 'teamwork',
        model_strategy: 'hybrid',
        qa_rigor: 'standard',
        custom_notes: 'Updated note',
      },
    });

    renderCard();

    const saveBtn = screen.getByTestId('save-agent-onboarding-prefs-btn') as HTMLButtonElement;
    await waitFor(() => {
      expect(saveBtn.disabled).toBe(false);
    });

    const execSelect = screen.getByTestId('pref-exec-mode-select');
    fireEvent.change(execSelect, { target: { value: 'teamwork' } });

    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(personalSettingsApi.updateUserPreferences).toHaveBeenCalledWith({
        agent_onboarding_prefs: {
          scope: 'local_only',
          execution_mode: 'teamwork',
          model_strategy: 'quota_sipping_flash',
          qa_rigor: 'strict_forensic',
          custom_notes: '',
        },
      });
      expect(screen.getByTestId('onboarding-save-success')).toBeDefined();
      expect(screen.getByText('Preferences saved successfully.')).toBeDefined();
    });
  });

  it('displays error alert when saving preferences fails', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'local_only',
        execution_mode: 'swarm',
        model_strategy: 'quota_sipping_flash',
        qa_rigor: 'strict_forensic',
        custom_notes: '',
      },
    });

    vi.mocked(personalSettingsApi.updateUserPreferences).mockRejectedValueOnce(
      new Error('Network error saving preferences'),
    );

    renderCard();

    const saveBtn = screen.getByTestId('save-agent-onboarding-prefs-btn') as HTMLButtonElement;
    await waitFor(() => {
      expect(saveBtn.disabled).toBe(false);
    });

    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByTestId('onboarding-save-error')).toBeDefined();
      expect(screen.getByText('Network error saving preferences')).toBeDefined();
    });
  });

  it('displays fallback error message when error is not an Error instance', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'local_only',
        execution_mode: 'swarm',
        model_strategy: 'quota_sipping_flash',
        qa_rigor: 'strict_forensic',
        custom_notes: '',
      },
    });

    vi.mocked(personalSettingsApi.updateUserPreferences).mockRejectedValueOnce('raw string error');

    renderCard();

    const saveBtn = screen.getByTestId('save-agent-onboarding-prefs-btn') as HTMLButtonElement;
    await waitFor(() => {
      expect(saveBtn.disabled).toBe(false);
    });

    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByTestId('onboarding-save-error')).toBeDefined();
      expect(screen.getByText('Failed to save preferences.')).toBeDefined();
    });
  });

  it('clears save success message after timeout', async () => {
    let timerCallback: (() => void) | null = null;
    const originalSetTimeout = globalThis.setTimeout;
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation((fn: any, ms?: number, ...args: any[]) => {
      if (ms === 3000) {
        timerCallback = fn;
        return 999 as any;
      }
      return originalSetTimeout(fn, ms, ...args);
    });

    try {
      vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
        principal_id: '01a2-test',
        workspace_id: '01a2-ws',
        agent_onboarding_prefs: {
          scope: 'local_only',
          execution_mode: 'swarm',
          model_strategy: 'quota_sipping_flash',
          qa_rigor: 'strict_forensic',
          custom_notes: '',
        },
      });

      vi.mocked(personalSettingsApi.updateUserPreferences).mockResolvedValueOnce({
        principal_id: '01a2-test',
        workspace_id: '01a2-ws',
        agent_onboarding_prefs: {
          scope: 'local_only',
          execution_mode: 'swarm',
          model_strategy: 'quota_sipping_flash',
          qa_rigor: 'strict_forensic',
          custom_notes: '',
        },
      });

      renderCard();

      const saveBtn = screen.getByTestId('save-agent-onboarding-prefs-btn');
      await waitFor(() => {
        expect((saveBtn as HTMLButtonElement).disabled).toBe(false);
      });

      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(screen.getByTestId('onboarding-save-success')).toBeDefined();
      });

      expect(timerCallback).not.toBeNull();
      act(() => {
        timerCallback!();
      });

      expect(screen.queryByTestId('onboarding-save-success')).toBeNull();
    } finally {
      timeoutSpy.mockRestore();
    }
  });

  it('resets copied state after timeout and handles copy failure', async () => {
    let copyTimerCallback: (() => void) | null = null;
    const originalSetTimeout = globalThis.setTimeout;
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation((fn: any, ms?: number, ...args: any[]) => {
      if (ms === 2000) {
        copyTimerCallback = fn;
        return 888 as any;
      }
      return originalSetTimeout(fn, ms, ...args);
    });

    try {
      vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
        principal_id: '01a2-test',
        workspace_id: '01a2-ws',
        agent_onboarding_prefs: {
          scope: 'local_only',
          execution_mode: 'swarm',
          model_strategy: 'quota_sipping_flash',
          qa_rigor: 'strict_forensic',
          custom_notes: '',
        },
      });

      renderCard();

      const copyBtn = screen.getByTestId('copy-agent-onboarding-prompt-btn');

      // Test successful copy with reset timeout
      fireEvent.click(copyBtn);
      await waitFor(() => {
        expect(copyBtn.textContent).toContain('Copied Prompt!');
      });

      expect(copyTimerCallback).not.toBeNull();
      act(() => {
        copyTimerCallback!();
      });

      expect(copyBtn.textContent).toContain('Copy Agent Onboarding Prompt');

      // Test failed copy (when copyToClipboard returns false)
      vi.mocked(clipboardUtil.copyToClipboard).mockResolvedValueOnce(false);
      fireEvent.click(copyBtn);

      await waitFor(() => {
        expect(copyBtn.textContent).toContain('Copy Agent Onboarding Prompt');
      });
    } finally {
      timeoutSpy.mockRestore();
    }
  });

  it('handles partial prefData gracefully', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'global_allowed',
        // custom_notes, execution_mode, etc. undefined
      } as any,
    });

    renderCard();

    await waitFor(() => {
      const scopeSelect = screen.getByTestId('pref-scope-select') as HTMLSelectElement;
      expect(scopeSelect.value).toBe('global_allowed');
      const notes = screen.getByTestId('pref-custom-notes-input') as HTMLTextAreaElement;
      expect(notes.value).toBe('');
    });
  });

  it('shows saving indicator while mutation is pending', async () => {
    let resolveMutation: ((val: any) => void) | null = null;
    const mutationPromise = new Promise((resolve) => {
      resolveMutation = resolve;
    });

    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'local_only',
        execution_mode: 'swarm',
        model_strategy: 'quota_sipping_flash',
        qa_rigor: 'strict_forensic',
        custom_notes: '',
      },
    });

    vi.mocked(personalSettingsApi.updateUserPreferences).mockImplementationOnce(
      () => mutationPromise as any,
    );

    renderCard();

    const saveBtn = screen.getByTestId('save-agent-onboarding-prefs-btn') as HTMLButtonElement;
    await waitFor(() => {
      expect(saveBtn.disabled).toBe(false);
    });

    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(saveBtn.textContent).toBe('Saving...');
      expect(saveBtn.disabled).toBe(true);
    });

    act(() => {
      if (resolveMutation) {
        resolveMutation({
          principal_id: '01a2-test',
          workspace_id: '01a2-ws',
          agent_onboarding_prefs: {
            scope: 'local_only',
            execution_mode: 'swarm',
            model_strategy: 'quota_sipping_flash',
            qa_rigor: 'strict_forensic',
            custom_notes: '',
          },
        });
      }
    });

    await waitFor(() => {
      expect(saveBtn.textContent).toBe('💾 Save Preferences');
    });
  });

  it('handles empty prefData response gracefully', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce(null as any);

    renderCard();

    await waitFor(() => {
      const scopeSelect = screen.getByTestId('pref-scope-select') as HTMLSelectElement;
      expect(scopeSelect.value).toBe('local_only');
    });
  });

  it('renders and self-heals with fallback QueryClientProvider when mounted outside provider', async () => {
    render(<AgentOnboardingPromptCard />);
    expect(screen.getByTestId('agent-onboarding-prompt-card')).toBeDefined();
  });
});
