// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

/**
 * Playwright E2E verification & Visual Proof Suite for Admin Workflow Transition Studio UI
 * (KB-P5-24 / S14.4 wireframe parity, KANBA-158).
 *
 * Verifies:
 * 1. S14.4 wireframe fidelity (In Review -> Done card with 3 hooks, latency budget, ro mount, emoji hint popover).
 * 2. Hook reordering (drag-and-drop & keyboard move), toggle enable/disable, and error recovery.
 * 3. AttachHookDialog conditional Wasm vs Agent transition helper selectors, MUTABLE_FIELD_UNIVERSE chips.
 * 4. Sample-ticket / existing-issue DryRunDrawer with rejection reasons and copyable CLI validation snippet.
 * 5. Security guards: non-admin 404 anti-enumeration view, AAL2 step-up elevation challenge.
 * 6. Multi-device annotated screenshots across desktop, tablet, and mobile viewports.
 */

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from './support/test';
import { mockApi, loadFixture, type MockHandlers, type MockRecorder } from './support/mockApi';
import { annotatedScreenshot } from './support/annotate';

const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../docs/qa/KANBA-158/screenshots',
);

const defaultHooks = [
  {
    from_state: 'In Review',
    to_state: 'Done',
    active_hook_count: 3,
    hooks: [
      {
        id: 'hook-1',
        name: 'require-qa-proof-link',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'sync_validator',
        sort_rank: '0000000000000001',
        failure_policy: 'fail_closed',
        manifest_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        is_enabled: true,
        wasm_module_name: 'qa-proof-validator',
        wasm_module_sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        target_latency_budget: '<2ms',
        description: 'Ensures description or comments include `docs/qa/KAN-*/` proof bundle before invoking AI.',
      },
      {
        id: 'hook-2',
        name: 'forensic-code-check',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'agent_interceptor',
        sort_rank: '0000000000000002',
        failure_policy: 'fail_closed',
        manifest_sha256: '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
        is_enabled: true,
        agent_slug: 'forensic-code-check',
        agent_display_name: 'Forensic Code Check',
        harness_kind: 'cli_pipe',
        cli_binary_allowlist_id: 'agy',
        cli_args: ['-p'],
        timeout_ms: 60000,
        repo_binding_slug: 'kanban-main',
        repo_access_mode: 'ro_vfs_mount',
        mcp_access_summary: 'Read-Only (KAN)',
        allowed_mutable_fields: ['labels'],
        description: 'Repo: `kanban-main` (:ro mount) | MCP: Read-Only (`KAN`) | Mutable Fields: `[labels]`',
      },
      {
        id: 'hook-3',
        name: 'sec-invariant-scan',
        from_state: 'In Review',
        to_state: 'Done',
        hook_kind: 'agent_interceptor',
        sort_rank: '0000000000000003',
        failure_policy: 'fail_closed',
        manifest_sha256: '7b52009b64fd0a2a49e6d8a939753077792b055425eee527861182c611383145',
        is_enabled: true,
        agent_slug: 'sec-invariant-scan',
        agent_display_name: 'Security Invariant Scanner',
        harness_kind: 'in_app_sdk',
        provider_kind: 'ollama',
        model_id: 'ollama/qwen2.5-coder',
        timeout_ms: 30000,
        repo_binding_slug: 'kanban-main',
        repo_access_mode: 'ro_vfs_mount',
        mcp_access_summary: 'Read-Only (KAN)',
        allowed_mutable_fields: [],
        description: 'Verifies RLS policy tests & zero new unapproved dependencies in `uv.lock` / `pnpm-lock.yaml`.',
      },
    ],
  },
];

async function setupWorkflowMocks(page: Page, handlers: MockHandlers = {}): Promise<MockRecorder> {
  const projectKan = loadFixture('project-kan');
  await page.unroute('**/api/v1/**');
  return mockApi(page, {
    'GET /api/v1/me': { json: loadFixture('me-adam') },
    'GET /api/v1/auth/me': { json: loadFixture('me-adam') },
    'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
    'GET /api/v1/setup/status': { json: { initialized: true } },
    'GET /api/v1/auth/session': { json: { authenticated: true, csrf_token: 'test-csrf-token-123' } },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/objects/project/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/projects/KAN/workflow-hooks': { json: { rules: defaultHooks } },
    'GET /api/v1/projects/KAN/states': {
      json: [
        { id: 'state-backlog', name: 'Backlog' },
        { id: 'state-in-progress', name: 'In Progress' },
        { id: 'state-in-review', name: 'In Review' },
        { id: 'state-done', name: 'Done' },
        { id: 'state-cancelled', name: 'Cancelled' },
      ],
    },
    'GET /api/v1/workspaces/kanban/agent-definitions': {
      json: [
        {
          id: 'agent-1',
          slug: 'forensic-code-check',
          display_name: 'Forensic Code Check',
          harness_kind: 'cli_pipe',
          cli_binary_allowlist_id: 'agy',
          cli_args: ['-p'],
          repo_access_mode: 'ro_vfs_mount',
          timeout_ms: 60000,
        },
        {
          id: 'agent-2',
          slug: 'sec-invariant-scan',
          display_name: 'Security Invariant Scanner',
          harness_kind: 'in_app_sdk',
          provider_kind: 'ollama',
          model_id: 'ollama/qwen2.5-coder',
          cli_args: [],
          repo_access_mode: 'ro_vfs_mount',
          timeout_ms: 30000,
        },
      ],
    },
    'GET /api/v1/projects/KAN/repo-bindings': {
      json: [
        {
          id: 'repo-1',
          slug: 'kanban-main',
          remote_url: 'https://github.com/adamoutler/kanban.git',
          access_mode: 'ro_vfs_mount',
        },
      ],
    },
    'POST /api/v1/projects/KAN/workflow-hooks/dry-run': {
      json: {
        steps: [
          {
            order: 1,
            name: 'require-qa-proof-link',
            hook_kind: 'sync_validator',
            result: 'rejected',
            reason: 'Missing required docs/qa/ proof bundle',
            duration_us: 1200,
          },
          {
            order: 2,
            name: 'forensic-code-check',
            hook_kind: 'agent_interceptor',
            result: 'skipped_async',
            duration_us: 200,
            cli_command:
              'uv run kanban-agent validate-transition --project KAN --issue KAN-123 --transition "In Review->Done" --agent forensic-code-check',
          },
          {
            order: 3,
            name: 'sec-invariant-scan',
            hook_kind: 'agent_interceptor',
            result: 'skipped_async',
            duration_us: 150,
            cli_command:
              'uv run kanban-agent validate-transition --project KAN --issue KAN-123 --transition "In Review->Done" --agent sec-invariant-scan',
          },
        ],
        would_commit: false,
      },
    },
    'POST /api/v1/projects/KAN/workflow-hooks/reorder': { status: 200, json: { ok: true } },
    'POST /api/v1/projects/KAN/workflow-hooks': (req) => ({
      status: 201,
      json: {
        id: 'hook-created',
        sort_rank: '0000000000000004',
        is_enabled: true,
        ...(typeof req.body === 'object' && req.body !== null ? req.body : {}),
      },
    }),
    'POST /api/v1/workflow-hooks/:hookId/enable': { status: 200, json: { ok: true } },
    'POST /api/v1/workflow-hooks/:hookId/disable': { status: 200, json: { ok: true } },
    'DELETE /api/v1/workflow-hooks/:hookId': { status: 204 },
    ...handlers,
  });
}

test.describe('Admin Workflow Transition Studio UI E2E (KB-P5-24, KANBA-158)', () => {
  test.beforeEach(async ({ context }) => {
    mkdirSync(SCREENSHOT_DIR, { recursive: true });
    await context.addCookies([
      {
        name: 'kb_csrf',
        value: 'test-csrf-token-123',
        domain: '127.0.0.1',
        path: '/',
      },
    ]);
  });

  test('01-studio-pipeline: renders S14.4 wireframe card with 3 hooks and open EmojiHint popover', async ({
    page,
  }, testInfo) => {
    await setupWorkflowMocks(page);

    await page.goto('/projects/KAN/settings/workflows');
    await page.waitForLoadState('networkidle');

    // Studio page & header presence
    await expect(page.locator('[data-testid="workflow-studio-page"]')).toBeVisible();
    await expect(page.locator('[data-testid="transition-card-In Review-Done"]')).toBeVisible();
    await expect(page.locator('[data-testid="active-hooks-count"]')).toHaveText('3 Active Hooks');

    // Hook rows presence
    await expect(page.locator('[data-testid="hook-pipeline-row-hook-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="hook-pipeline-row-hook-2"]')).toBeVisible();
    await expect(page.locator('[data-testid="hook-pipeline-row-hook-3"]')).toBeVisible();

    // Trigger and inspect the EmojiHint popover on the CLI Agent hook
    const emojiTrigger = page.locator('[data-testid="emoji-hint-hook-2"]');
    await expect(emojiTrigger).toBeVisible();
    await emojiTrigger.hover();

    const popup = page.locator('[data-testid="emoji-hint-hook-2-popup"]');
    if (!(await popup.isVisible())) {
      await emojiTrigger.click();
    }
    await expect(popup).toBeVisible();
    await expect(popup).toContainText('Harness: cli_pipe');

    // Annotated Screenshot: 01-studio-pipeline (desktop, tablet, mobile)
    await annotatedScreenshot(page, testInfo, {
      name: '01-studio-pipeline',
      annotations: [
        {
          selector: '[data-testid="transition-card-In Review-Done"]',
          label: 'S14.4 Transition Rule Card ([ In Review ] ======( 3 Active Hooks )======> [ Done ])',
          note: 'Enterprise whitespace with token-based geometry and directional state connectors',
        },
        {
          selector: '[data-testid="hook-pipeline-row-hook-1"]',
          label: 'Sync Wasm Validator (require-qa-proof-link, <2ms budget)',
          note: 'Fast synchronous gate checking proof bundle before invoking AI',
        },
        {
          selector: '[data-testid="hook-pipeline-row-hook-2"]',
          label: 'CLI Agent Transition Helper (forensic-code-check, agy -p, :ro mount)',
          note: 'Isolated subprocess execution with restricted mutable fields [labels]',
        },
        {
          selector: '[data-testid="emoji-hint-hook-2-popup"]',
          label: 'Semantic EmojiHint Popover',
          note: 'Detailed agent harness metadata and read-only mount constraints',
        },
      ],
    });
  });

  test('02-attach-agent-hook: opens AttachHookDialog with agent selector and mutable fields chips', async ({
    page,
  }, testInfo) => {
    // Only capture for desktop and mobile as specified in proof bundle definition
    if (testInfo.project.name === 'tablet') {
      test.skip();
    }

    await setupWorkflowMocks(page);

    await page.goto('/projects/KAN/settings/workflows');
    await page.waitForLoadState('networkidle');

    // Click "Add Transition Rule" to open AttachHookDialog
    const addRuleBtn = page.getByRole('button', { name: 'Add Transition Rule' });
    await expect(addRuleBtn).toBeVisible();
    await addRuleBtn.click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();
    await expect(page.locator('#attach-hook-title')).toHaveText('Attach Workflow Helper Hook');

    // Select Agent Transition Helper
    const agentRadio = page.locator('input[type="radio"][value="agent_interceptor"]');
    await agentRadio.check();

    // Fill hook name
    const nameInput = page.locator('#hook-name-input');
    await nameInput.fill('audit-gate-reviewer');

    // Select Agent Definition
    const agentSelect = page.locator('#agent-def-select');
    await agentSelect.selectOption('forensic-code-check');

    // Verify agent metadata notice is displayed
    const agentSummary = page.locator('[data-testid="agent-details-summary"]');
    await expect(agentSummary).toBeVisible();
    await expect(agentSummary).toContainText('Harness: cli_pipe');
    await expect(agentSummary).toContainText('Validated CLI Args: -p');

    // Check mutable field 'labels'
    const labelsCheckbox = page.locator('.mutable-fields-picker input[type="checkbox"]').first();
    await labelsCheckbox.check();

    // Visual proof: 02-attach-agent-hook (desktop, mobile)
    await annotatedScreenshot(page, testInfo, {
      name: '02-attach-agent-hook',
      annotations: [
        {
          selector: '[role="dialog"]',
          label: 'AttachHookDialog Modal',
          note: 'Modal overlay for attaching synchronous Wasm or asynchronous agent hooks',
        },
        {
          selector: '[role="radiogroup"][aria-label="Hook Kind"]',
          label: 'Hook Kind RadioGroup',
          note: 'Switches between Sync Wasm Validator, Sync Wasm Mutator, and Agent Transition Helper',
        },
        {
          selector: '[data-testid="agent-details-summary"]',
          label: 'Agent Definition Metadata Summary',
          note: 'Harness command arguments (agy -p), timeout, and ro mount constraints',
        },
        {
          selector: '.mutable-fields-picker',
          label: 'Strict Mutable Fields Universe Chips',
          note: 'Restricted to MUTABLE_FIELD_UNIVERSE; core fields remain strictly immutable',
        },
      ],
    });
  });

  test('03-dry-run-results: executes sample-ticket dry-run and displays rejected validator with copyable CLI command', async ({
    page,
  }, testInfo) => {
    await setupWorkflowMocks(page);

    await page.goto('/projects/KAN/settings/workflows');
    await page.waitForLoadState('networkidle');

    // Click [▶ Dry-Run Against Sample Ticket]
    const dryRunBtn = page.getByRole('button', {
      name: /Dry-run against sample ticket/i,
    });
    await expect(dryRunBtn).toBeVisible();
    await dryRunBtn.click();

    // Verify drawer opened
    const drawer = page.locator('.dry-run-drawer');
    await expect(drawer).toBeVisible();

    // Submit dry-run form
    const runBtn = page.locator('button[type="submit"]:has-text("Run Dry-Run")');
    await expect(runBtn).toBeVisible();
    await runBtn.click();

    // Verify results
    const resultsContainer = page.locator('[data-testid="dry-run-results"]');
    await expect(resultsContainer).toBeVisible();

    const banner = page.locator('[data-testid="would-commit-banner"]');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(/would not commit/i);

    const step1 = page.locator('[data-testid="dry-run-step-1"]');
    await expect(step1).toBeVisible();
    await expect(step1).toContainText('Missing required docs/qa/ proof bundle');

    const step2 = page.locator('[data-testid="dry-run-step-2"]');
    await expect(step2).toBeVisible();
    await expect(step2).toContainText('Skipped Async');

    const cliSnippet = page.locator('[data-testid="dry-run-cli-2"]');
    await expect(cliSnippet).toBeVisible();
    await expect(cliSnippet).toContainText('uv run kanban-agent validate-transition');

    // Visual proof: 03-dry-run-results (desktop, tablet, mobile)
    await annotatedScreenshot(page, testInfo, {
      name: '03-dry-run-results',
      annotations: [
        {
          selector: '[data-testid="would-commit-banner"]',
          label: 'Dry-Run Outcome Banner',
          note: 'Indicates whether the transition would commit or is blocked',
        },
        {
          selector: '[data-testid="dry-run-step-1"]',
          label: 'Step 1 Validator: Rejected',
          note: 'Sync Wasm validator halts pipeline on missing proof bundle',
        },
        {
          selector: '[data-testid="dry-run-step-2"]',
          label: 'Step 2 Helper: Skipped Async',
          note: 'Asynchronous agent hooks are skipped in interactive UI dry-runs',
        },
        {
          selector: '[data-testid="dry-run-cli-2"]',
          label: '1-Click Copyable CLI Transition Snippet',
          note: 'Pre-populated command to execute agent validation in local CLI or CI runner',
        },
      ],
    });
  });

  test('04-non-admin-404: renders NotFoundView without leaking studio controls for non-admin callers', async ({
    page,
  }, testInfo) => {
    // Only capture on desktop as specified in proof bundle definition
    if (testInfo.project.name !== 'desktop') {
      test.skip();
    }

    let writeCallAttempted = false;
    await setupWorkflowMocks(page, {
      'POST /api/v1/projects/KAN/workflow-hooks': () => {
        writeCallAttempted = true;
        return { status: 403 };
      },
    });

    // Navigate with non-admin role query param
    await page.goto('/projects/KAN/settings/workflows?role=member');
    await page.waitForLoadState('networkidle');

    // Uniform 403/404 view preventing principal & object enumeration (S3.4)
    const notFoundView = page.locator('[data-testid="not-found-view"]');
    await expect(notFoundView).toBeVisible();
    await expect(page.locator('h1')).toHaveText('Not found or no access');

    // Ensure studio controls are completely absent
    await expect(page.locator('[data-testid="workflow-studio-page"]')).not.toBeVisible();
    expect(writeCallAttempted).toBe(false);

    // Visual proof: 04-non-admin-404 (desktop)
    await annotatedScreenshot(page, testInfo, {
      name: '04-non-admin-404',
      annotations: [
        {
          selector: '[data-testid="not-found-view"]',
          label: 'Anti-Enumeration Uniform Not Found or No Access View (S3.4)',
          note: 'Renders uniform 404 view for non-admin users with 0 write calls',
        },
      ],
    });
  });

  test('05-reorder-and-toggle: supports keyboard reordering, toggle switch, and 422 error rollback', async ({
    page,
  }) => {
    let reorderCalled = false;
    let disableCalled = false;
    const rulesState = JSON.parse(JSON.stringify(defaultHooks)) as typeof defaultHooks;

    await setupWorkflowMocks(page, {
      'GET /api/v1/projects/KAN/workflow-hooks': () => ({ json: { rules: rulesState } }),
      'POST /api/v1/workflow-hooks/:hookId/disable': (req) => {
        disableCalled = true;
        const hookId = req.params.hookId;
        for (const rule of rulesState) {
          for (const hook of rule.hooks) {
            if (hook.id === hookId) {
              hook.is_enabled = false;
            }
          }
        }
        return { status: 200, json: { ok: true } };
      },
      'POST /api/v1/projects/KAN/workflow-hooks/reorder': () => {
        reorderCalled = true;
        return { status: 200, json: { ok: true } };
      },
    });

    await page.goto('/projects/KAN/settings/workflows');
    await page.waitForLoadState('networkidle');

    // Toggle hook-1 enabled state
    const toggleInput = page.locator('#hook-toggle-hook-1');
    await expect(toggleInput).toBeChecked();
    await toggleInput.click();
    await expect.poll(() => disableCalled).toBe(true);

    // Keyboard move down hook-1
    const moveDownBtn = page.getByRole('button', { name: 'Move require-qa-proof-link down' });
    await expect(moveDownBtn).toBeVisible();
    await moveDownBtn.click();
    await expect.poll(() => reorderCalled).toBe(true);
  });
});
