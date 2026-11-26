// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React, { act } from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DryRunDrawer } from '../DryRunDrawer';
import type { DryRunResponse, DryRunPayload } from '../api';
import { ShellPanelsProvider, registerShellPanel } from '../../../app/shellPanels';

describe('DryRunDrawer (KB-P5-24)', () => {
  let writeTextSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextSpy,
      },
    });
  });

  it('does not render when isOpen is false', () => {
    const { container } = render(
      <DryRunDrawer
        isOpen={false}
        projectKey="KAN"
        transition={{ from_state: 'In Review', to_state: 'Done' }}
        onClose={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('runs dry-run against sample ticket missing docs/qa/, rendering rejected validator and skipped_async agent hooks with copyable CLI command (Mandatory Test Case 4)', async () => {
    const mockResponse: DryRunResponse = {
      would_commit: false,
      steps: [
        {
          order: 1,
          name: 'require-qa-proof-link',
          hook_kind: 'sync_validator',
          result: 'rejected',
          reason: 'Verification proof rejected: missing docs/qa/ proof bundle in ticket description or comments',
          duration_us: 1200,
        },
        {
          order: 2,
          name: 'forensic-code-check',
          hook_kind: 'agent_interceptor',
          result: 'skipped_async',
          duration_us: 50,
          cli_command: 'uv run kanban-agent validate-transition --project KAN --transition "In Review -> Done" --agent forensic-code-check',
        },
        {
          order: 3,
          name: 'sec-invariant-scan',
          hook_kind: 'agent_interceptor',
          result: 'skipped_async',
          duration_us: 40,
          cli_command: 'uv run kanban-agent validate-transition --project KAN --transition "In Review -> Done" --agent sec-invariant-scan',
        },
      ],
    };

    const mockRunner = vi
      .fn<(projectKey: string, payload: DryRunPayload) => Promise<DryRunResponse>>()
      .mockResolvedValue(mockResponse);

    render(
      <DryRunDrawer
        isOpen={true}
        projectKey="KAN"
        transition={{ from_state: 'In Review', to_state: 'Done' }}
        onClose={vi.fn()}
        dryRunRunner={mockRunner}
      />,
    );

    expect(screen.getByText(/▶ Dry-Run: \[In Review\] ➔ \[Done\]/i)).toBeDefined();

    // Click Run Dry-Run
    fireEvent.click(screen.getByRole('button', { name: '▶ Run Dry-Run' }));

    await waitFor(() => {
      expect(mockRunner).toHaveBeenCalledTimes(1);
    });
    const callArgs = mockRunner.mock.calls[0];
    expect(callArgs?.[0]).toBe('KAN');
    expect(callArgs?.[1]?.from_state).toBe('In Review');
    expect(callArgs?.[1]?.to_state).toBe('Done');
    expect(callArgs?.[1]?.sample_ticket?.summary).toContain('Fix RLS policy');

    // Check step 1: rejected
    await waitFor(() => {
      expect(screen.getByTestId('dry-run-step-1').textContent).toContain('require-qa-proof-link');
      expect(screen.getByTestId('dry-run-reason-1').textContent).toContain(
        'Verification proof rejected: missing docs/qa/ proof bundle',
      );
    });

    // Check would_commit banner
    const wouldCommitBanner = screen.getByTestId('would-commit-banner');
    expect(wouldCommitBanner.textContent).toContain('would_commit: false');

    // Check step 2: skipped_async with CLI command
    const step2Cli = screen.getByTestId('dry-run-cli-2');
    expect(step2Cli.textContent).toContain('uv run kanban-agent validate-transition');

    // Click copy CLI button
    const copyBtn = screen.getByRole('button', { name: /Copy CLI command for forensic-code-check/i });
    fireEvent.click(copyBtn);
    expect(writeTextSpy).toHaveBeenCalledWith(
      expect.stringContaining('uv run kanban-agent validate-transition'),
    );
    await waitFor(() => {
      expect(screen.getByText('Copied!')).toBeDefined();
    });
  });

  it('switches between sample ticket and existing issue modes', async () => {
    const mockRunner = vi.fn().mockResolvedValue({
      would_commit: true,
      steps: [
        {
          order: 1,
          name: 'auto-label-mutator',
          hook_kind: 'sync_mutator',
          result: 'mutated',
          field_updates: { labels: ['security', 'verified'] },
          duration_us: 2500,
        },
      ],
    });

    render(
      <DryRunDrawer
        isOpen={true}
        projectKey="KAN"
        transition={{ from_state: null, to_state: 'Done' }}
        onClose={vi.fn()}
        dryRunRunner={mockRunner}
      />,
    );

    // Switch to existing issue
    fireEvent.click(screen.getByRole('tab', { name: 'Pick existing issue' }));
    expect(screen.getByLabelText('Issue Key')).toBeDefined();

    // Switch back to sample
    fireEvent.click(screen.getByRole('tab', { name: 'Sample ticket' }));
    expect(screen.getByLabelText(/Summary/i)).toBeDefined();
    fireEvent.click(screen.getByRole('tab', { name: 'Pick existing issue' }));

    // Trigger run with issue key
    fireEvent.change(screen.getByLabelText('Issue Key'), { target: { value: 'KAN-99' } });
    fireEvent.click(screen.getByRole('button', { name: '▶ Run Dry-Run' }));

    await waitFor(() => {
      expect(mockRunner).toHaveBeenCalledWith(
        'KAN',
        expect.objectContaining({
          from_state: null,
          to_state: 'Done',
          issue_key: 'KAN-99',
        }),
      );
    });

    // Verify mutated step updates
    await waitFor(() => {
      expect(screen.getByTestId('dry-run-updates-1').textContent).toContain('verified');
      expect(screen.getByTestId('would-commit-banner').textContent).toContain('Transition Allowed');
    });
  });

  it('validates empty issue key in issue mode', () => {
    render(
      <DryRunDrawer
        isOpen={true}
        projectKey="KAN"
        transition={{ from_state: 'In Review', to_state: 'Done' }}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('tab', { name: 'Pick existing issue' }));
    fireEvent.change(screen.getByLabelText('Issue Key'), { target: { value: '   ' } });
    fireEvent.submit(screen.getByRole('button', { name: '▶ Run Dry-Run' }));

    expect(screen.getByRole('alert').textContent).toContain('Issue key is required');
  });

  it('renders prominent simulation top banner and handles runner failure gracefully', async () => {
    const mockRunner = vi.fn().mockRejectedValue(new Error('Network timeout during dry-run'));

    render(
      <DryRunDrawer
        isOpen={true}
        projectKey="KAN"
        transition={{ from_state: 'In Review', to_state: 'Done' }}
        onClose={vi.fn()}
        dryRunRunner={mockRunner}
      />,
    );

    // Check prominent simulation banner
    const simBanner = screen.getByTestId('dry-run-simulation-banner');
    expect(simBanner).toBeDefined();
    expect(simBanner.textContent).toContain('DRY-RUN SIMULATION: No database changes were committed.');

    fireEvent.click(screen.getByRole('button', { name: '▶ Run Dry-Run' }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Network timeout during dry-run');
    });
  });

  it('renders diff table for sample mode field updates and handles error and allowed steps with sub-millisecond durations', async () => {
    const mockRunner = vi
      .fn<(projectKey: string, payload: DryRunPayload) => Promise<DryRunResponse>>()
      .mockResolvedValue({
        would_commit: true,
      steps: [
        {
          order: 1,
          name: 'fast-wasm-validator',
          hook_kind: 'sync_validator',
          result: 'allowed',
          duration_us: 400,
        },
        {
          order: 2,
          name: 'faulty-validator',
          hook_kind: 'sync_validator',
          result: 'error',
          reason: 'Wasm execution faulted with SIGSEGV',
          duration_us: 800,
        },
        {
          order: 3,
          name: 'metadata-mutator',
          hook_kind: 'sync_mutator',
          result: 'mutated',
          field_updates: {
            priority: 'HIGH',
            summary: 'Updated Summary Title',
          },
          duration_us: 1500,
        },
      ],
    });

    const handleClose = vi.fn();
    render(
      <DryRunDrawer
        isOpen={true}
        projectKey="KAN"
        transition={{ from_state: 'In Review', to_state: 'Done' }}
        onClose={handleClose}
        dryRunRunner={mockRunner}
      />,
    );

    // Edit sample inputs
    fireEvent.change(screen.getByLabelText(/Summary/i), { target: { value: 'Original Summary' } });
    fireEvent.change(screen.getByLabelText(/Description Markdown/i), { target: { value: 'New markdown body' } });
    fireEvent.change(screen.getByLabelText(/Priority/i), { target: { value: 'NORMAL' } });
    fireEvent.change(screen.getByLabelText(/Labels/i), { target: { value: 'frontend, security' } });

    // Click Run
    fireEvent.click(screen.getByRole('button', { name: '▶ Run Dry-Run' }));

    await waitFor(() => {
      expect(mockRunner).toHaveBeenCalled();
    });
    const lastCall = mockRunner.mock.calls[0];
    expect(lastCall?.[0]).toBe('KAN');
    expect(lastCall?.[1]?.sample_ticket?.summary).toBe('Original Summary');
    expect(lastCall?.[1]?.sample_ticket?.description_markdown).toBe('New markdown body');
    expect(lastCall?.[1]?.sample_ticket?.priority).toBe('NORMAL');
    expect(lastCall?.[1]?.sample_ticket?.labels).toEqual(['frontend', 'security']);

    // Check fast validator duration (<1ms)
    expect(screen.getByTestId('dry-run-step-1').textContent).toContain('<1ms');
    expect(screen.getByTestId('dry-run-step-1').textContent).toContain('Allowed');

    // Check faulty validator (error)
    expect(screen.getByTestId('dry-run-step-2').textContent).toContain('Error');
    expect(screen.getByTestId('dry-run-reason-2').textContent).toContain('SIGSEGV');

    // Check diff table for field updates in sample mode
    expect(screen.getByTestId('dry-run-diff-3')).toBeDefined();
    expect(screen.getByTestId('dry-run-diff-3').textContent).toContain('"Original Summary"');
    expect(screen.getByTestId('dry-run-diff-3').textContent).toContain('"Updated Summary Title"');

    // Test backdrop close and aside stopPropagation
    const drawerAside = screen.getByRole('dialog');
    fireEvent.click(drawerAside);
    expect(handleClose).not.toHaveBeenCalled();

    const backdrop = document.querySelector('.workflow-modal-backdrop');
    if (backdrop instanceof HTMLElement) {
      fireEvent.click(backdrop);
      expect(handleClose).toHaveBeenCalled();
    }
  });

  it('handles non-Error thrown during dry-run runner execution gracefully', async () => {
    const mockRunner = vi.fn().mockRejectedValue('String error failure');

    render(
      <DryRunDrawer
        isOpen={true}
        projectKey="KAN"
        transition={{ from_state: 'In Review', to_state: 'Done' }}
        onClose={vi.fn()}
        dryRunRunner={mockRunner}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '▶ Run Dry-Run' }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Dry-run request failed.');
    });
  });

  describe('StudioDocLink and FieldHelpHint Integrations (KAN-510)', () => {
    afterEach(() => {
      document.documentElement.removeAttribute('data-theme');
    });

    it('renders StudioDocLink in dry-run header with correct href, title, and label in Light and Dark themes', () => {
      for (const theme of ['light', 'dark'] as const) {
        document.documentElement.setAttribute('data-theme', theme);
        const { unmount } = render(
          <DryRunDrawer
            isOpen={true}
            projectKey="KAN"
            transition={{ from_state: 'In Review', to_state: 'Done' }}
            onClose={vi.fn()}
          />,
        );

        const docLink = screen.getByTestId('dry-run-doc-link');
        expect(docLink).toBeDefined();
        expect(docLink.getAttribute('href')).toBe(
          '/docs/scripted-workflows-and-transition-helpers#dry-run-simulation',
        );
        expect(docLink.getAttribute('aria-label')).toBe('Workflow Dry-Run Documentation');
        expect(docLink.textContent).toContain('Documentation ->');

        const headerActions = docLink.closest('.dry-run-header-actions');
        expect(headerActions).not.toBeNull();

        const header = docLink.closest('.dry-run-header');
        expect(header).not.toBeNull();
        expect(header?.querySelector('#dry-run-drawer-title')?.textContent).toContain('Dry-Run:');

        unmount();
      }
    });

    it('supports keyboard focus and opens in-app help panel via ShellPanelsProvider on click', async () => {
      const unregister = registerShellPanel('help', ({ arg }) => (
        <div data-testid="in-app-help-panel">
          Help Drawer for {(arg as { href?: string } | undefined)?.href}
        </div>
      ));

      try {
        render(
          <ShellPanelsProvider>
            <DryRunDrawer
              isOpen={true}
              projectKey="KAN"
              transition={{ from_state: 'In Review', to_state: 'Done' }}
              onClose={vi.fn()}
            />
          </ShellPanelsProvider>,
        );

        const docLink = screen.getByTestId('dry-run-doc-link');
        docLink.focus();
        expect(document.activeElement).toBe(docLink);

        fireEvent.click(docLink);

        await waitFor(() => {
          expect(screen.getByTestId('in-app-help-panel')).toBeDefined();
        });

        const panel = screen.getByTestId('in-app-help-panel');
        expect(panel.textContent).toContain(
          '/docs/scripted-workflows-and-transition-helpers#dry-run-simulation',
        );
      } finally {
        unregister();
      }
    });

    it('renders FieldHelpHint for Issue Key explaining simulated execution vs ephemeral synthetic payload', () => {
      render(
        <DryRunDrawer
          isOpen={true}
          projectKey="KAN"
          transition={{ from_state: 'In Review', to_state: 'Done' }}
          onClose={vi.fn()}
        />,
      );

      // Switch to existing issue mode
      fireEvent.click(screen.getByRole('tab', { name: 'Pick existing issue' }));

      // Locate label and trigger
      const label = screen.getByText('Issue Key');
      const trigger = screen.getByTestId('dry-run-issue-key-help');
      expect(trigger).toBeDefined();
      expect(trigger.getAttribute('aria-label')).toBe('Help for Issue Key');

      // MANDATORY INVARIANT: never nest FieldHelpHint inside label!
      expect(label.contains(trigger)).toBe(false);

      // They must be adjacent siblings inside .dry-run-label-row
      const labelRow = trigger.closest('.dry-run-label-row');
      expect(labelRow).not.toBeNull();
      expect(labelRow?.contains(label)).toBe(true);
      expect(labelRow?.contains(trigger)).toBe(true);

      // Focus opens the popover
      act(() => {
        trigger.focus();
      });

      const popover = screen.getByTestId('dry-run-issue-key-help-popover');
      expect(popover).toBeDefined();
      expect(popover.textContent).toContain('Issue Key');
      expect(popover.textContent).toContain(
        'Simulates workflow transition execution against an existing issue',
      );
      expect(popover.textContent).toContain('ephemeral synthetic payload');
      expect(popover.textContent).toContain('Example:');
      expect(popover.textContent).toContain('KAN-142');

      const docLink = popover.querySelector('a');
      expect(docLink).not.toBeNull();
      expect(docLink?.getAttribute('href')).toBe(
        '/docs/scripted-workflows-and-transition-helpers#dry-run-simulation',
      );
    });

    it('dismisses FieldHelpHint popover on Escape key and restores focus to trigger without closing drawer', () => {
      const handleClose = vi.fn();
      render(
        <DryRunDrawer
          isOpen={true}
          projectKey="KAN"
          transition={{ from_state: 'In Review', to_state: 'Done' }}
          onClose={handleClose}
        />,
      );

      fireEvent.click(screen.getByRole('tab', { name: 'Pick existing issue' }));

      const trigger = screen.getByTestId('dry-run-issue-key-help');
      act(() => {
        trigger.focus();
      });

      expect(screen.getByTestId('dry-run-issue-key-help-popover')).toBeDefined();

      // Escape dismisses popover without closing drawer
      act(() => {
        fireEvent.keyDown(trigger, { key: 'Escape' });
      });
      expect(handleClose).not.toHaveBeenCalled();
      expect(screen.queryByTestId('dry-run-issue-key-help-popover')).toBeNull();
      expect(document.activeElement).toBe(trigger);
    });
  });
});
