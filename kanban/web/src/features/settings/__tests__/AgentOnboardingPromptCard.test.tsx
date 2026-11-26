// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AgentOnboardingPromptCard } from '../AgentOnboardingPromptCard';
import * as personalSettingsApi from '../personalSettingsApi';
import * as clipboardUtil from '../../../utils/clipboard';
import { registerShellPanel, ShellPanelsProvider } from '../../../app/shellPanels';

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
    vi.resetAllMocks();
    vi.mocked(clipboardUtil.copyToClipboard).mockResolvedValue(true);
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValue({
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

  it('renders card with default values and local folder persistence', () => {
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

    const scopeSelect = screen.getByTestId<HTMLSelectElement>('pref-scope-select');
    expect(scopeSelect.value).toBe('local_only');

    const preview = screen.getByTestId('agent-onboarding-prompt-preview');
    expect(preview.textContent).toContain('strictly to the local project folder');
    expect(preview.textContent).toContain('do NOT modify global home/system directories');

    // Warning banner should NOT be present when local_only
    expect(screen.queryByTestId('onboarding-scope-warning')).toBeNull();
  });

  it('renders warning banner and updates prompt when switching to global_allowed', () => {
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

    const scopeSelect = screen.getByTestId<HTMLSelectElement>('pref-scope-select');
    fireEvent.change(scopeSelect, { target: { value: 'global_allowed' } });

    expect(scopeSelect.value).toBe('global_allowed');
    expect(screen.getByTestId('onboarding-scope-warning')).toBeDefined();

    const preview = screen.getByTestId('agent-onboarding-prompt-preview');
    expect(preview.textContent).toContain('global workstation directories');
  });

  it('updates form controls and prompt preview when changing options', () => {
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
    expect(preview.textContent).toContain('Execution Mode (default: Swarm)');
    expect(preview.textContent).toContain('Model/Quota Strategy (default: Quota-Sipping Flash 3.8)');
    expect(preview.textContent).toContain('QA Rigor (default: Strict Forensic reality-checker)');

    // Change Execution Mode
    const execSelect = screen.getByTestId<HTMLSelectElement>('pref-exec-mode-select');
    fireEvent.change(execSelect, { target: { value: 'teamwork' } });
    expect(execSelect.value).toBe('teamwork');
    expect(preview.textContent).toContain('Execution Mode (default: Teamwork)');

    // Change Model Strategy
    const modelSelect = screen.getByTestId<HTMLSelectElement>('pref-model-strat-select');
    fireEvent.change(modelSelect, { target: { value: 'hybrid' } });
    expect(modelSelect.value).toBe('hybrid');
    expect(preview.textContent).toContain('Model/Quota Strategy (default: Hybrid)');

    // Change QA Rigor
    const qaSelect = screen.getByTestId<HTMLSelectElement>('pref-qa-rigor-select');
    fireEvent.change(qaSelect, { target: { value: 'standard' } });
    expect(qaSelect.value).toBe('standard');
    expect(preview.textContent).toContain('QA Rigor (default: Standard)');

    // Change Custom Notes
    const notesInput = screen.getByTestId<HTMLTextAreaElement>('pref-custom-notes-input');
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

    const saveBtn = screen.getByTestId<HTMLButtonElement>('save-agent-onboarding-prefs-btn');
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

    const saveBtn = screen.getByTestId<HTMLButtonElement>('save-agent-onboarding-prefs-btn');
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

    const saveBtn = screen.getByTestId<HTMLButtonElement>('save-agent-onboarding-prefs-btn');
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

    const saveBtn = screen.getByTestId<HTMLButtonElement>('save-agent-onboarding-prefs-btn');
    await waitFor(() => {
      expect(saveBtn.disabled).toBe(false);
    });

    vi.useFakeTimers();
    try {
      await act(async () => {
        fireEvent.click(saveBtn);
        await vi.advanceTimersByTimeAsync(0);
      });

      expect(screen.getByTestId('onboarding-save-success')).toBeDefined();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3100);
      });

      expect(screen.queryByTestId('onboarding-save-success')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('resets copied state after timeout and handles copy failure', async () => {
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
    expect(copyBtn.textContent).toContain('Copy Agent Onboarding Prompt');

    vi.useFakeTimers();
    try {
      await act(async () => {
        fireEvent.click(copyBtn);
        await vi.advanceTimersByTimeAsync(0);
      });

      expect(copyBtn.textContent).toContain('Copied Prompt!');

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });

      expect(copyBtn.textContent).toContain('Copy Agent Onboarding Prompt');

      // Test copy failure (returns false)
      vi.mocked(clipboardUtil.copyToClipboard).mockResolvedValueOnce(false);
      await act(async () => {
        fireEvent.click(copyBtn);
        await vi.advanceTimersByTimeAsync(0);
      });

      expect(copyBtn.textContent).toContain('Copy Agent Onboarding Prompt');
    } finally {
      vi.useRealTimers();
    }
  });

  it('handles custom notes gracefully when empty', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockResolvedValueOnce({
      principal_id: '01a2-test',
      workspace_id: '01a2-ws',
      agent_onboarding_prefs: {
        scope: 'global_allowed',
        execution_mode: 'swarm',
        model_strategy: 'quota_sipping_flash',
        qa_rigor: 'strict_forensic',
        custom_notes: '',
      },
    });

    renderCard();

    await waitFor(() => {
      const scopeSelect = screen.getByTestId<HTMLSelectElement>('pref-scope-select');
      expect(scopeSelect.value).toBe('global_allowed');
      const notes = screen.getByTestId<HTMLTextAreaElement>('pref-custom-notes-input');
      expect(notes.value).toBe('');
    });
  });

  it('shows saving indicator while mutation is pending', async () => {
    let resolveMutation: ((val: personalSettingsApi.UserPreferencesResponse) => void) | null = null;
    const mutationPromise = new Promise<personalSettingsApi.UserPreferencesResponse>((resolve) => {
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
      () => mutationPromise,
    );

    renderCard();

    const saveBtn = screen.getByTestId<HTMLButtonElement>('save-agent-onboarding-prefs-btn');
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

  it('handles error in fetchUserPreferences gracefully', async () => {
    vi.mocked(personalSettingsApi.fetchUserPreferences).mockRejectedValueOnce(
      new Error('Failed to load preferences'),
    );

    renderCard();

    await waitFor(() => {
      const scopeSelect = screen.getByTestId<HTMLSelectElement>('pref-scope-select');
      expect(scopeSelect.value).toBe('local_only');
    });
  });

  it('renders and self-heals with fallback QueryClientProvider when mounted outside provider', () => {
    render(<AgentOnboardingPromptCard />);
    expect(screen.getByTestId('agent-onboarding-prompt-card')).toBeDefined();
  });

  describe('WCAG AA contrast & button styling (KAN-521)', () => {
    it('renders and copies cleanly in Light theme', async () => {
      document.documentElement.setAttribute('data-theme', 'light');
      try {
        renderCard();
        const copyBtn = screen.getByTestId('copy-agent-onboarding-prompt-btn');
        expect(copyBtn).toBeDefined();
        expect(copyBtn.className).toContain('kb-agent-onboarding-btn-primary');
        expect(copyBtn.textContent).toContain('Copy Agent Onboarding Prompt');

        fireEvent.click(copyBtn);
        expect(clipboardUtil.copyToClipboard).toHaveBeenCalled();
        await waitFor(() => {
          expect(copyBtn.textContent).toContain('Copied Prompt!');
        });
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    });

    it('renders and copies cleanly in Dark theme', async () => {
      document.documentElement.setAttribute('data-theme', 'dark');
      try {
        renderCard();
        const copyBtn = screen.getByTestId('copy-agent-onboarding-prompt-btn');
        expect(copyBtn).toBeDefined();
        expect(copyBtn.className).toContain('kb-agent-onboarding-btn-primary');
        expect(copyBtn.textContent).toContain('Copy Agent Onboarding Prompt');

        fireEvent.click(copyBtn);
        expect(clipboardUtil.copyToClipboard).toHaveBeenCalled();
        await waitFor(() => {
          expect(copyBtn.textContent).toContain('Copied Prompt!');
        });
      } finally {
        document.documentElement.removeAttribute('data-theme');
      }
    });

    it('asserts AgentOnboardingPromptCard.css enforces WCAG AA contrast tokens without low-contrast dark overrides', () => {
      const cssPath = path.resolve(__dirname, '../AgentOnboardingPromptCard.css');
      expect(fs.existsSync(cssPath)).toBe(true);
      const css = fs.readFileSync(cssPath, 'utf8');

      // Primary button uses accent tokens
      expect(css).toMatch(/\.kb-agent-onboarding-btn-primary\s*\{[^}]*background:\s*var\(--accent-primary/);
      expect(css).toMatch(/\.kb-agent-onboarding-btn-primary\s*\{[^}]*color:\s*var\(--accent-primary-fg/);
      expect(css).toMatch(/\.kb-agent-onboarding-btn-primary\s*\{[^}]*border:\s*1px solid var\(--accent-primary/);

      // Primary button hover uses brand-primary-hover without opacity: 0.9 reduction
      expect(css).toMatch(/\.kb-agent-onboarding-btn-primary:hover:not\(:disabled\)\s*\{[^}]*background:\s*var\(--brand-primary-hover/);
      expect(css).toMatch(/\.kb-agent-onboarding-btn-primary:hover:not\(:disabled\)\s*\{[^}]*border-color:\s*var\(--brand-primary-hover/);
      expect(css).not.toMatch(/\.kb-agent-onboarding-btn-primary:hover:not\(:disabled\)\s*\{[^}]*opacity:/);

      // Focus-visible outline
      expect(css).toMatch(/\.kb-agent-onboarding-btn-primary:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--focus-ring/);
      expect(css).toMatch(/\.kb-agent-onboarding-btn-secondary:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--focus-ring/);

      // Dark theme rules use var(--badge-fg) for high contrast (>= 4.5:1)
      expect(css).toMatch(/\[data-theme="dark"\]\s+\.kb-agent-onboarding-btn-secondary[^{]*\{[^}]*color:\s*var\(--badge-fg/);
      expect(css).toMatch(/\[data-theme="dark"\]\s+\.kb-agent-onboarding-btn-secondary[^{]*\{[^}]*background:\s*var\(--bg-surface-raised/);
      expect(css).toMatch(/\[data-theme="dark"\]\s+\.kb-agent-onboarding-btn-secondary[^{]*\{[^}]*border:\s*1px solid var\(--border-subtle/);

      // No low-contrast dark mode text overrides like rgb(37, 99, 235) on dark background
      expect(css).not.toMatch(/\[data-theme="dark"\][^{]*\{[^}]*color:\s*(?:rgb\(37,\s*99,\s*235\)|#2563eb)/);

      // Success alert uses high-contrast text: var(--ok-fg, #047857) in light, var(--ok-fg, #34d399) in dark
      expect(css).toMatch(/\.kb-agent-onboarding-alert-success\s*\{[^}]*color:\s*var\(--ok-fg,\s*#047857\)/);
      expect(css).toMatch(/\[data-theme="dark"\]\s+\.kb-agent-onboarding-alert-success\s*\{[^}]*color:\s*var\(--ok-fg/);

      // Foreign .kb-mcp-copy-prompt-btn rule should not exist in AgentOnboardingPromptCard.css (owned by McpAccessStudio.css)
      expect(css).not.toContain('.kb-mcp-copy-prompt-btn');

      // No forbidden unicode em-dash or en-dash
      expect(css).not.toContain('\u2014');
      expect(css).not.toContain('\u2013');
    });
  });

  describe('StudioDocLink Header Integration (KAN-520)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renders agent-onboarding-doc-link with correct href, label, and ARIA title in Light and Dark themes', () => {
      for (const theme of ['light', 'dark'] as const) {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = renderCard();

        const docLink = screen.getByTestId('agent-onboarding-doc-link');
        expect(docLink).toBeDefined();
        expect(docLink.getAttribute('href')).toBe(
          '/docs/multi-provider-ai-engine-and-runners#agent-onboarding',
        );
        expect(docLink.getAttribute('aria-label')).toBe('Agent Onboarding Documentation');
        expect(docLink.textContent).toContain('Documentation ->');

        const headerActions = docLink.closest('.kb-agent-onboarding-header-actions');
        expect(headerActions).not.toBeNull();
        expect(headerActions?.closest('.kb-agent-onboarding-card-header')).not.toBeNull();

        unmount();
      }
    });

    it('supports keyboard focus on StudioDocLink with appropriate accessibility attributes', () => {
      renderCard();

      const docLink = screen.getByTestId('agent-onboarding-doc-link');
      docLink.focus();
      expect(document.activeElement).toBe(docLink);
      expect(docLink.tagName.toLowerCase()).toBe('a');
      expect(docLink.getAttribute('aria-label')).toBe('Agent Onboarding Documentation');
    });

    it('opens in-app help panel when wrapped in ShellPanelsProvider and clicked', () => {
      const unregister = registerShellPanel('help', ({ arg }) => (
        <div data-testid="in-app-help-panel">
          Help Drawer for {(arg as { href?: string } | undefined)?.href} - Title: {(arg as { title?: string } | undefined)?.title}
        </div>
      ));

      try {
        render(
          <QueryClientProvider client={queryClient}>
            <ShellPanelsProvider>
              <AgentOnboardingPromptCard />
            </ShellPanelsProvider>
          </QueryClientProvider>,
        );

        const docLink = screen.getByTestId('agent-onboarding-doc-link');
        fireEvent.click(docLink);

        const helpPanel = screen.getByTestId('in-app-help-panel');
        expect(helpPanel).toBeDefined();
        expect(helpPanel.textContent).toContain(
          '/docs/multi-provider-ai-engine-and-runners#agent-onboarding',
        );
        expect(helpPanel.textContent).toContain('Agent Onboarding Documentation');

        // Card should remain rendered and interactive
        expect(screen.getByTestId('copy-agent-onboarding-prompt-btn')).toBeDefined();
      } finally {
        unregister();
      }
    });

    it('asserts AgentOnboardingPromptCard.tsx contains zero inline style attributes', () => {
      const tsxPath = path.resolve(__dirname, '../AgentOnboardingPromptCard.tsx');
      expect(fs.existsSync(tsxPath)).toBe(true);
      const tsxContent = fs.readFileSync(tsxPath, 'utf8');

      // Verify zero inline style={{}}
      expect(tsxContent).not.toMatch(/style=\{\{/);
      expect(tsxContent).not.toMatch(/style=\{/);
    });

    it('asserts AgentOnboardingPromptCard.css provides white-space nowrap and responsive flex-wrap for header action bar', () => {
      const cssPath = path.resolve(__dirname, '../AgentOnboardingPromptCard.css');
      expect(fs.existsSync(cssPath)).toBe(true);
      const css = fs.readFileSync(cssPath, 'utf8');

      // Header container has flex and flex-wrap
      expect(css).toMatch(/\.kb-agent-onboarding-card-header\s*\{[^}]*display:\s*flex;/);
      expect(css).toMatch(/\.kb-agent-onboarding-card-header\s*\{[^}]*flex-wrap:\s*wrap;/);

      // Header main and actions
      expect(css).toMatch(/\.kb-agent-onboarding-header-main\s*\{[^}]*flex:\s*1\s+1\s+280px;/);
      expect(css).toMatch(/\.kb-agent-onboarding-header-actions\s*\{[^}]*white-space:\s*nowrap;/);
      expect(css).toMatch(/\.kb-agent-onboarding-header-actions\s*\{[^}]*display:\s*flex;/);

      // Responsive mobile query
      expect(css).toMatch(/@media\s*\([^)]*max-width:\s*480px\)\s*\{/);
      expect(css).toMatch(/\.kb-agent-onboarding-header-main\s*\{[^}]*flex:\s*0\s+1\s+auto;/);
      expect(css).toMatch(/\.kb-agent-onboarding-header-actions\s*\{[^}]*flex-wrap:\s*wrap;/);

      // No forbidden unicode dashes
      expect(css).not.toContain('\u2014');
      expect(css).not.toContain('\u2013');
    });
  });
});
