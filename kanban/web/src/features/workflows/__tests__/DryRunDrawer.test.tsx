// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { DryRunDrawer } from '../DryRunDrawer';
import type { DryRunResponse, DryRunPayload } from '../api';

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
    expect(screen.getByLabelText(/Issue Key/i)).toBeDefined();

    // Trigger run with issue key
    fireEvent.change(screen.getByLabelText(/Issue Key/i), { target: { value: 'KAN-99' } });
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
    fireEvent.change(screen.getByLabelText(/Issue Key/i), { target: { value: '   ' } });
    fireEvent.submit(screen.getByRole('button', { name: '▶ Run Dry-Run' }));

    expect(screen.getByRole('alert').textContent).toContain('Issue key is required');
  });

  it('handles runner failure gracefully', async () => {
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

    fireEvent.click(screen.getByRole('button', { name: '▶ Run Dry-Run' }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Network timeout during dry-run');
    });
  });
});
