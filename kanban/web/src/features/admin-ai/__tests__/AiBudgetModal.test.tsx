// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { registerShellPanel, ShellPanelsProvider } from '../../../app/shellPanels';
import { AiBudgetModal } from '../AiBudgetModal';
import * as aiApi from '../aiAdminApi';
import type { ProviderConfigPublic, BudgetRecord } from '../aiAdminApi';

describe('AiBudgetModal Component (KAN-447)', () => {
  const mockProvider: ProviderConfigPublic = {
    id: 'prov-openai-test-447',
    provider_kind: 'openai',
    display_name: 'Test OpenAI Provider',
    base_url: 'https://api.openai.com/v1',
    model_allowlist: ['gpt-4o'],
    residency_tier: 'cloud_standard',
    priority: 10,
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
      period_start: '2026-11-26',
      token_cap: 50000,
      tokens_used: 10000,
      tokens_reserved: 0,
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
    document.documentElement.removeAttribute('data-theme');
  });

  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  describe('Positive Rendering and Modal Footer Cadence', () => {
    it('renders modal footer with Cancel label on budget-cancel-btn matching universal cadence', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-cancel-btn')).toBeDefined();
      });

      const cancelBtn = screen.getByTestId('budget-cancel-btn');
      expect(cancelBtn.textContent.trim()).toBe('Cancel');

      // Header button retains close dialog aria-label and symbol
      const headerCloseBtn = screen.getByTestId('close-budget-modal-btn');
      expect(headerCloseBtn.getAttribute('aria-label')).toBe('Close dialog');
      expect(headerCloseBtn.textContent.trim()).toBe('✕');

      // Save button is present in footer alongside Cancel button
      const saveBtn = screen.getByTestId('save-budget-btn');
      expect(saveBtn).toBeDefined();
      expect(saveBtn.textContent.trim()).toBe('Save Token Cap');
    });

    it('returns null when isOpen is false or provider is null', () => {
      const { container: closedContainer } = render(
        <AiBudgetModal
          isOpen={false}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );
      expect(closedContainer.firstChild).toBeNull();

      const { container: noProviderContainer } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={null}
        />,
      );
      expect(noProviderContainer.firstChild).toBeNull();
    });
  });

  describe('Click and Escape Dismissal Non-Regression', () => {
    it('calls onClose when clicking the Cancel footer button', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const onClose = vi.fn();

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={onClose}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-cancel-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('budget-cancel-btn'));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('calls onClose when clicking the header close button', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const onClose = vi.fn();

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={onClose}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('close-budget-modal-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('close-budget-modal-btn'));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('calls onClose when pressing Escape key', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const onClose = vi.fn();

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={onClose}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('ai-budget-modal')).toBeDefined();
      });

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('does not call onClose when pressing other keys like Enter or Space', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const onClose = vi.fn();

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={onClose}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('ai-budget-modal')).toBeDefined();
      });

      fireEvent.keyDown(window, { key: 'Enter' });
      fireEvent.keyDown(window, { key: ' ' });
      fireEvent.keyDown(window, { key: 'ArrowDown' });
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  describe('Save Budget Submission Non-Regression', () => {
    it('submits updated token cap successfully and triggers onBudgetUpdated callback', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const setBudgetSpy = vi.spyOn(aiApi, 'setBudget').mockResolvedValue({
        period_kind: 'monthly',
        period_start: '2026-11-01',
        token_cap: 3000000,
        tokens_used: 250000,
        tokens_reserved: 50000,
      });
      const onBudgetUpdated = vi.fn();

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
          onBudgetUpdated={onBudgetUpdated}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-token-cap-input')).toBeDefined();
      });

      const input = screen.getByTestId('budget-token-cap-input');
      fireEvent.change(input, { target: { value: '3000000' } });

      const saveBtn = screen.getByTestId('save-budget-btn');
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(setBudgetSpy).toHaveBeenCalledWith({
          provider_config_id: 'prov-openai-test-447',
          project_id: undefined,
          period_kind: 'monthly',
          token_cap: 3000000,
        });
        expect(onBudgetUpdated).toHaveBeenCalledTimes(1);
      });
    });

    it('supports unlimited quota mode submission', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const setBudgetSpy = vi.spyOn(aiApi, 'setBudget').mockResolvedValue({
        period_kind: 'monthly',
        period_start: '2026-11-01',
        token_cap: 10000000000,
        tokens_used: 250000,
        tokens_reserved: 50000,
      });

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('cap-mode-unlimited-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('cap-mode-unlimited-btn'));
      fireEvent.click(screen.getByTestId('save-budget-btn'));

      await waitFor(() => {
        expect(setBudgetSpy).toHaveBeenCalledWith({
          provider_config_id: 'prov-openai-test-447',
          project_id: undefined,
          period_kind: 'monthly',
          token_cap: 10000000000,
        });
      });
    });

    it('validates negative or non-numeric token cap without calling setBudget', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const setBudgetSpy = vi.spyOn(aiApi, 'setBudget');

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

      const input = screen.getByTestId('budget-token-cap-input');
      fireEvent.change(input, { target: { value: '-500' } });
      fireEvent.click(screen.getByTestId('save-budget-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('budget-error').textContent).toContain('Token cap must be a non-negative integer');
      });
      expect(setBudgetSpy).not.toHaveBeenCalled();
    });
  });

  describe('Light and Dark Theme Rendering', () => {
    it('renders cleanly in light mode with Cancel button clearly styled', async () => {
      document.documentElement.setAttribute('data-theme', 'light');
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);

      const { container } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-cancel-btn')).toBeDefined();
      });

      const cancelBtn = screen.getByTestId('budget-cancel-btn');
      expect(cancelBtn.textContent.trim()).toBe('Cancel');
      expect(cancelBtn.className).toContain('kb-btn-secondary');
      expect(container.querySelector('.kb-modal-card')).not.toBeNull();
    });

    it('renders cleanly in dark mode with Cancel button clearly styled', async () => {
      document.documentElement.setAttribute('data-theme', 'dark');
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);

      const { container } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-cancel-btn')).toBeDefined();
      });

      const cancelBtn = screen.getByTestId('budget-cancel-btn');
      expect(cancelBtn.textContent.trim()).toBe('Cancel');
      expect(cancelBtn.className).toContain('kb-btn-secondary');
      expect(container.querySelector('.kb-modal-card')).not.toBeNull();
    });
  });

  describe('StudioDocLink Header Integration and ARIA Verification (KAN-457)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renders ai-budget-doc-link with correct href, title, and aria-label in modal header actions group in Light and Dark themes', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);

      for (const theme of ['light', 'dark'] as const) {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = render(
          <AiBudgetModal
            isOpen={true}
            onClose={vi.fn()}
            provider={mockProvider}
          />,
        );

        await waitFor(() => {
          expect(screen.getByTestId('ai-budget-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('ai-budget-doc-link');
        expect(docLink).toBeDefined();
        expect(docLink.getAttribute('href')).toBe('/docs/multi-provider-ai-engine-and-runners#budget-caps');
        expect(docLink.getAttribute('aria-label')).toBe('Token Budget and Circuit Breaker Guide');
        expect(docLink.textContent).toContain('Documentation ->');

        // Confirm modal accessibility attributes
        const modal = screen.getByTestId('ai-budget-modal');
        expect(modal.getAttribute('role')).toBe('dialog');
        expect(modal.getAttribute('aria-modal')).toBe('true');
        expect(modal.getAttribute('aria-labelledby')).toBe('budget-modal-title');

        // Confirm header actions container wraps both doc link and close button
        const headerActions = docLink.closest('.kb-modal-header-actions');
        expect(headerActions).not.toBeNull();
        if (!headerActions) throw new Error('headerActions is null');

        const closeBtn = headerActions.querySelector('[data-testid="close-budget-modal-btn"]');
        expect(closeBtn).not.toBeNull();

        unmount();
      }
    });

    it('supports keyboard focus navigation to the doc link', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('ai-budget-doc-link')).toBeDefined();
      });

      const docLink = screen.getByTestId('ai-budget-doc-link');
      docLink.focus();
      expect(document.activeElement).toBe(docLink);
    });

    it('opens in-app help panel via ShellPanelsProvider without closing modal state', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const unregister = registerShellPanel('help', ({ arg }) => (
        <div data-testid="in-app-help-panel">
          Help Drawer for {(arg as { href?: string } | undefined)?.href}
        </div>
      ));

      try {
        render(
          <ShellPanelsProvider>
            <AiBudgetModal
              isOpen={true}
              onClose={vi.fn()}
              provider={mockProvider}
            />
          </ShellPanelsProvider>,
        );

        await waitFor(() => {
          expect(screen.getByTestId('ai-budget-doc-link')).toBeDefined();
        });

        const docLink = screen.getByTestId('ai-budget-doc-link');
        fireEvent.click(docLink);

        const helpPanel = screen.getByTestId('in-app-help-panel');
        expect(helpPanel).toBeDefined();
        expect(helpPanel.textContent).toContain('/docs/multi-provider-ai-engine-and-runners#budget-caps');

        // Modal title remains visible and functional
        expect(screen.getByText('Token Budget & Usage Ledger')).toBeDefined();
      } finally {
        unregister();
      }
    });

    it('handles presets, period selection, and zero-cap freeze alert', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('preset-budget-1m-btn')).toBeDefined();
      });

      const input = screen.getByTestId<HTMLInputElement>('budget-token-cap-input');

      // Click 5M preset
      fireEvent.click(screen.getByTestId('preset-budget-5m-btn'));
      expect(input.value).toBe('5000000');

      // Click 25M preset
      fireEvent.click(screen.getByTestId('preset-budget-25m-btn'));
      expect(input.value).toBe('25000000');

      // Click 100M preset
      fireEvent.click(screen.getByTestId('preset-budget-100m-btn'));
      expect(input.value).toBe('100000000');

      // Click 1M preset
      fireEvent.click(screen.getByTestId('preset-budget-1m-btn'));
      expect(input.value).toBe('1000000');

      // Click 0 (Freeze) preset
      fireEvent.click(screen.getByTestId('preset-budget-0-freeze-btn'));
      expect(input.value).toBe('0');
      expect(screen.getByTestId('zero-cap-freeze-warning')).toBeDefined();
      expect(screen.getByTestId('zero-cap-freeze-warning').textContent).toContain('Hard AI Freeze');

      // Change accounting period
      const periodSelect = screen.getByTestId<HTMLSelectElement>('budget-period-select');
      fireEvent.change(periodSelect, { target: { value: 'daily' } });
      expect(periodSelect.value).toBe('daily');
    });

    it('handles budget save with workspaceSlug and error states', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValue(mockBudgets);
      const setBudgetSpy = vi.spyOn(aiApi, 'setBudget').mockResolvedValue({
        period_kind: 'monthly',
        period_start: '2026-11-01',
        token_cap: 5000000,
        tokens_used: 0,
        tokens_reserved: 0,
      });

      render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
          workspaceSlug="engineering"
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('save-budget-btn')).toBeDefined();
      });

      fireEvent.click(screen.getByTestId('preset-budget-5m-btn'));
      fireEvent.click(screen.getByTestId('save-budget-btn'));

      await waitFor(() => {
        expect(setBudgetSpy).toHaveBeenCalledWith(
          {
            provider_config_id: 'prov-openai-test-447',
            project_id: undefined,
            period_kind: 'monthly',
            token_cap: 5000000,
          },
          'engineering',
        );
      });

      // Error saving
      setBudgetSpy.mockRejectedValueOnce(new Error('Network error writing budget'));
      fireEvent.click(screen.getByTestId('save-budget-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('budget-error').textContent).toContain('Network error writing budget');
      });

      // Non-Error thrown saving
      setBudgetSpy.mockRejectedValueOnce('raw string error');
      fireEvent.click(screen.getByTestId('save-budget-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('budget-error').textContent).toContain('Failed to update token budget cap');
      });
    });

    it('handles budget initial load errors and empty initial records', async () => {
      vi.spyOn(aiApi, 'fetchBudgets').mockRejectedValueOnce(new Error('Failed to reach backend'));

      const { unmount: unmountError } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-error').textContent).toContain('Failed to reach backend');
      });

      unmountError();

      // Non-Error thrown loading
      vi.spyOn(aiApi, 'fetchBudgets').mockRejectedValueOnce('raw fetch error');
      const { unmount: unmountRawError } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={mockProvider}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-error').textContent).toContain('Failed to load budgets');
      });

      unmountRawError();

      // Empty budgets fallback
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValueOnce([]);
      const { unmount: unmountEmpty } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={{ ...mockProvider, id: 'prov-empty-budgets' }}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-unlimited-note')).toBeDefined();
      });

      // Switch back to enforce mode from unlimited
      fireEvent.click(screen.getByTestId('cap-mode-enforce-btn'));
      expect(screen.getByTestId('budget-token-cap-input')).toBeDefined();

      unmountEmpty();

      // Initial budget cap >= 10000000000 (starts in unlimited mode)
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValueOnce([
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 10000000000,
          tokens_used: 100,
          tokens_reserved: 0,
        },
      ]);
      const { unmount: unmountUnlimited } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={{ ...mockProvider, id: 'prov-unlimited-ceiling' }}
        />,
      );

      await waitFor(() => {
        expect(screen.getByTestId('budget-unlimited-note')).toBeDefined();
      });

      unmountUnlimited();

      // High consumption thresholds (75% warning, 95% danger, zero freeze)
      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValueOnce([
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 100000,
          tokens_used: 95000,
          tokens_reserved: 0,
        },
      ]);
      const { unmount: unmountDanger } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={{ ...mockProvider, id: 'prov-danger' }}
        />,
      );
      await waitFor(() => {
        expect(screen.getByTestId('budget-progress-bar').className).toContain('kb-budget-progress--danger');
      });
      unmountDanger();

      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValueOnce([
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 100000,
          tokens_used: 75000,
          tokens_reserved: 0,
        },
      ]);
      const { unmount: unmountWarning } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={{ ...mockProvider, id: 'prov-warning' }}
        />,
      );
      await waitFor(() => {
        expect(screen.getByTestId('budget-progress-bar').className).toContain('kb-budget-progress--warning');
      });
      unmountWarning();

      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValueOnce([
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 100000,
          tokens_used: 100000,
          tokens_reserved: 0,
        },
      ]);
      const { unmount: unmountZeroRemaining } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={{ ...mockProvider, id: 'prov-zero-remaining' }}
        />,
      );
      await waitFor(() => {
        expect(screen.getByText('0 tokens remaining')).toBeDefined();
      });
      unmountZeroRemaining();

      vi.spyOn(aiApi, 'fetchBudgets').mockResolvedValueOnce([
        {
          period_kind: 'monthly',
          period_start: '2026-11-01',
          token_cap: 0,
          tokens_used: 0,
          tokens_reserved: 0,
        },
      ]);
      const { unmount: unmountZero } = render(
        <AiBudgetModal
          isOpen={true}
          onClose={vi.fn()}
          provider={{ ...mockProvider, id: 'prov-zero' }}
        />,
      );
      await waitFor(() => {
        expect(screen.getByText('Frozen (0 tokens allowance)')).toBeDefined();
      });
      unmountZero();
    });
  });
});
