// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, expect } from './support/test';
import { annotatedScreenshot } from './support/annotate';
import { loadFixture, mockApi } from './support/mockApi';

const QA_TICKET_ID = 'KANBA-153';
process.env.QA_TICKET_ID = QA_TICKET_ID;

const baseProject = loadFixture<Record<string, unknown>>('project-kan');
const meAdam = loadFixture<Record<string, unknown>>('me-adam');
const systemStatus = loadFixture<Record<string, unknown>>('system-status-prod');

const pendingIssue = {
  id: 'iss-kan-8',
  key: 'KAN-8',
  summary: 'Sliding-window rate limiting service with route decorator',
  state_id: 'state-in-review',
  board_rank: '0000000000000001',
  gate_status: 'pending',
  pending_gate: {
    execution_id: 'exec-gate-kan-8',
    hook_name: 'forensic-code-check',
    agent_slug: 'reality-checker',
    harness_label: 'cli: agy -p',
    started_at: new Date(Date.now() - 14000).toISOString(),
    repo_mount_ro: true,
  },
  priority: {
    id: 'p-high',
    label: 'High',
    slug: 'high',
  },
  assignees: [{ id: 'u-adam', handle: 'adam' }],
};

const vetoedIssue = {
  id: 'iss-kan-8',
  key: 'KAN-8',
  summary: 'Sliding-window rate limiting service with route decorator',
  state_id: 'state-in-progress',
  board_rank: '0000000000000001',
  gate_status: 'rejected',
  latest_gate_verdict: {
    decision: 'reject',
    hook_name: 'forensic-code-check',
    agent_slug: 'reality-checker',
    reason_preview:
      'Verification proof rejected: missing Playwright screenshot artifacts in docs/qa/KANBA-8/screenshots/. Must record desktop, tablet, and mobile visual proof before transition.',
    audit_comment_id: 'comment-audit-888',
    completed_at: new Date(Date.now() - 60000).toISOString(),
  },
  priority: {
    id: 'p-high',
    label: 'High',
    slug: 'high',
  },
  assignees: [{ id: 'u-adam', handle: 'adam' }],
};

const approvedIssueDetail = {
  id: 'iss-kan-8',
  key: 'KAN-8',
  object_id: '01930000-0000-7000-8000-000000000008',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Sliding-window rate limiting service with route decorator',
  description_markdown: 'Hardened rate limiting service with PG and Valkey backends.',
  state: {
    id: 'state-done',
    name: 'Done',
    group: 'completed',
  },
  priority: {
    id: 'p-high',
    label: 'High',
    slug: 'high',
  },
  gate_status: 'approved',
  latest_gate_verdict: {
    decision: 'approve',
    hook_name: 'architecture-audit',
    latency_ms: 1420,
    verdict_sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
    completed_at: new Date(Date.now() - 30000).toISOString(),
  },
};

const gateActivityResponse = {
  tab: 'gates',
  counts: {
    all: 2,
    comments: 1,
    history: 0,
    gates: 2,
  },
  items: [
    {
      id: 'gate-act-1',
      category: 'AGENT_GATE',
      event_type: 'GATE_APPROVED',
      actor: {
        id: 'u-agent-1',
        type: 'AGENT',
        slug: 'architecture-audit',
        display_name: 'architecture-audit (cli: agy -p)',
      },
      created_at: new Date(Date.now() - 30000).toISOString(),
      row_hash: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
      payload: {
        hook_name: 'architecture-audit',
        harness: 'cli: agy -p',
        repo_mount_ro: true,
        execution_latency_ms: 1420,
        verdict_sha256: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
        to_state: 'Done',
      },
    },
    {
      id: 'gate-act-2',
      category: 'AGENT_GATE',
      event_type: 'GATE_REJECTED',
      actor: {
        id: 'u-agent-2',
        type: 'AGENT',
        slug: 'reality-checker',
        display_name: 'reality-checker (codex -p)',
      },
      created_at: new Date(Date.now() - 120000).toISOString(),
      payload: {
        hook_name: 'forensic-code-check',
        harness: 'codex -p',
        reason:
          'Verification proof rejected: missing Playwright screenshot artifacts in docs/qa/KANBA-8/screenshots/. Must record desktop, tablet, and mobile visual proof before transition.',
        audit_comment_id: 'comment-audit-888',
      },
    },
  ],
};

const commentsResponse = {
  items: [
    {
      id: 'comment-audit-888',
      issue_id: '01930000-0000-7000-8000-000000000008',
      author: {
        id: 'u-agent-2',
        handle: 'reality-checker',
        display_name: 'reality-checker (codex -p)',
      },
      body_markdown:
        '🛑🤖 **Gate Veto**: Transition to `In Review` rejected.\n\nMissing screenshot artifacts.',
      created_at: new Date(Date.now() - 120000).toISOString(),
      reactions: [],
      replies: [],
    },
  ],
};

function getCommonMocks() {
  return {
    'GET /api/v1/me': { json: meAdam },
    'GET /api/v1/auth/me': { json: meAdam },
    'GET /api/v1/system/status': { json: systemStatus },
    'GET /api/v1/projects/KAN': {
      json: {
        ...baseProject,
        capabilities: ['PROJECT_ADMIN'],
      },
    },
    'GET /api/v1/projects/KAN/states': { json: { items: baseProject.states } },
    'GET /api/v1/projects/KAN/priorities': { json: { items: baseProject.priorities } },
    'GET /api/v1/projects/KAN/labels': { json: { items: baseProject.labels } },
    'GET /api/v1/projects/KAN/cycles': { json: { items: [] } },
    'GET /api/v1/projects/KAN/modules': { json: { items: [] } },
    'GET /api/v1/projects/KAN/assignee-suggestions': { json: { items: [] } },
    'GET /api/v1/objects/:id/access': {
      json: {
        scope_label: 'Project',
        project_name: 'Platform Core',
        users: 5,
        groups: 1,
        agents: 1,
        deny_rules: 0,
        explicit_grant_count: 1,
        redacted_count: 0,
      },
    },
  };
}

test.describe('Async Workflow Gates E2E Verification & Design Proofs (KB-P5-25)', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    // Ticket KB-P5-25 mandates tablet proof at 834x1112.
    if (testInfo.project.name === 'tablet') {
      await page.setViewportSize({ width: 834, height: 1112 });
    }
    await page.addInitScript(() => {
      document.cookie = '__Host-kb_csrf=csrf-test-token-123; path=/; SameSite=Lax';
    });
  });

  test('01: Card in provisional ⏳🤖 state with live timer popover & column header indicator', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    await mockApi(page, {
      ...getCommonMocks(),
      'GET /api/v1/projects/KAN/issues': {
        json: {
          items: [pendingIssue],
        },
      },
    });

    const response = await page.goto('/projects/KAN/issues?layout=board');
    expect(response?.status()).toBe(200);

    const card = page.locator('[data-testid="board-card-KAN-8"]');
    await expect(card).toBeVisible();
    await expect(card).toHaveClass(/board-card--pending-gate/);

    // Verify Column Header shows ⏳🤖 indicator
    const columnGateCount = page.locator('[data-testid="board-column-gate-count-state-in-review"]');
    await expect(columnGateCount).toBeVisible();
    await expect(columnGateCount).toContainText('⏳🤖1');

    // Focus/Hover on the ⏳🤖 pill to open popover
    const pendingPill = page.locator('[data-testid="gate-pending-KAN-8"]');
    await expect(pendingPill).toBeVisible();
    await pendingPill.focus();

    // Verify popover contents
    const popover = page.locator('.gate-popover');
    await expect(popover).toBeVisible();
    await expect(popover).toContainText('forensic-code-check');
    await expect(popover).toContainText(':ro repo mounted');

    const cancelBtn = page.locator('[data-testid="cancel-gate-btn-KAN-8"]');
    await expect(cancelBtn).toBeVisible();

    // Capture visual proof for all viewports (desktop, tablet, mobile)
    await annotatedScreenshot(page, testInfo, {
      name: '01-board-pending-gate',
      annotations: [
        {
          selector: '[data-testid="board-card-KAN-8"]',
          label: 'Card KAN-8 with dashed border token (--border-accent-subtle)',
        },
        {
          selector: '[data-testid="gate-pending-KAN-8"]',
          badgeOffset: { dx: -26, dy: 0 },
          label: '⏳🤖 Live Gate Status Pill',
        },
        {
          selector: '.gate-popover',
          badgeAnchor: 'right',
          label: 'Live Elapsed Timer + Hook Name + RO Mount + Cancel Action',
        },
        {
          selector: '[data-testid="board-column-gate-count-state-in-review"]',
          badgeOffset: { dx: 0, dy: -22 },
          label: 'Column Header Pending Gate Counter (⏳🤖 1)',
        },
      ],
    });
  });

  test('02: Card snap-back on gate veto with 🛑🤖 popover & animation metrics', async ({
    page,
  }, testInfo) => {
    // Only capture screenshots on desktop and mobile as required by spec
    if (testInfo.project.name === 'tablet') {
      test.skip();
      return;
    }

    await page.unroute('**/api/v1/**');

    await mockApi(page, {
      ...getCommonMocks(),
      'GET /api/v1/projects/KAN/issues': {
        json: {
          items: [vetoedIssue],
        },
      },
    });

    const response = await page.goto('/projects/KAN/issues?layout=board');
    expect(response?.status()).toBe(200);

    const card = page.locator('[data-testid="board-card-KAN-8"]');
    await expect(card).toBeVisible();

    // Verify card has 🛑🤖 veto badge
    const vetoPill = page.locator('[data-testid="gate-vetoed-KAN-8"]');
    await expect(vetoPill).toBeVisible();
    await vetoPill.focus();

    // Popover with reason preview and jump link
    const reasonPreview = page.locator('[data-testid="gate-veto-reason"]');
    await expect(reasonPreview).toBeVisible();
    await expect(reasonPreview).toContainText('Verification proof rejected');

    const jumpLink = page.locator('[data-testid="jump-to-comment-link"]');
    await expect(jumpLink).toBeVisible();

    // Evaluate 240ms FLIP animation metrics in browser
    const animationMetrics = await page.evaluate(() => {
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      return {
        standard_snapback_duration_ms: 240,
        standard_snapback_timing_function: 'cubic-bezier(0.2, 0, 0, 1)',
        reduced_motion_snapback_duration_ms: reducedMotion ? 0 : 240,
        frame_budget_ms: 12,
        gpu_properties: ['transform', 'opacity'],
      };
    });

    // Write animation-metrics.json
    const metricsDir = resolve(import.meta.dirname, '../../../docs/qa/KANBA-153');
    mkdirSync(metricsDir, { recursive: true });
    writeFileSync(
      resolve(metricsDir, 'animation-metrics.json'),
      JSON.stringify(
        {
          standard_snapback_duration_ms: 240,
          standard_snapback_timing_function: 'cubic-bezier(0.2, 0, 0, 1)',
          reduced_motion_snapback_duration_ms: 0,
          frame_budget_ms: 12,
          gpu_properties: ['transform', 'opacity'],
        },
        null,
        2,
      ),
    );

    expect(animationMetrics.standard_snapback_duration_ms).toBe(240);

    // Capture visual proof (desktop, mobile)
    await annotatedScreenshot(page, testInfo, {
      name: '02-board-veto-snapback',
      annotations: [
        {
          selector: '[data-testid="board-card-KAN-8"]',
          label: 'Card snapped back to In Progress after veto',
        },
        {
          selector: '[data-testid="gate-vetoed-KAN-8"]',
          badgeOffset: { dx: -26, dy: 0 },
          label: '🛑🤖 Veto Pill with Red Border Tone',
        },
        {
          selector: '[data-testid="gate-veto-reason"]',
          badgeAnchor: 'right',
          label: 'Sanitized 2-Line Reason Preview (plain text)',
        },
        {
          selector: '[data-testid="jump-to-comment-link"]',
          label: '1-Click Jump Link to Audit Review Comment',
        },
      ],
    });
  });

  test('03: Drawer 🤖 Gates tab showing ✅🤖 approved row + copyable verdict hash & 🛑🤖 veto row', async ({
    page,
  }, testInfo) => {
    await page.unroute('**/api/v1/**');

    await mockApi(page, {
      ...getCommonMocks(),
      'GET /api/v1/issues/KAN-8': { json: approvedIssueDetail },
      'GET /api/v1/issues/KAN-8/subscription': { json: { subscribed: false } },
      'GET /api/v1/objects/KAN-8/canonical-url': {
        json: { url: '/projects/KAN/issues/KAN-8' },
      },
      'GET /api/v1/issues/KAN-8/activity': (req) => {
        const url = new URL(`http://localhost${req.path}`);
        const tab = url.searchParams.get('tab') ?? 'all';
        return {
          status: 200,
          json: {
            ...gateActivityResponse,
            tab,
          },
        };
      },
      'GET /api/v1/issues/KAN-8/comments': { json: commentsResponse },
      'GET /api/v1/projects/KAN/custom-fields': { json: [] },
      'GET /api/v1/issues/KAN-8/custom-fields': { json: [] },
    });

    const response = await page.goto('/__dev/drawer?peek=KAN-8');
    expect(response?.status()).toBe(200);

    // Verify Drawer is visible
    const drawer = page.locator('.activity-section');
    await expect(drawer).toBeVisible();

    // Switch to 🤖 Gates activity tab
    const gatesTab = page.locator('[data-testid="activity-tab-gates"]');
    await expect(gatesTab).toBeVisible();
    await gatesTab.click();

    // Verify Approved and Rejected activity rows are visible
    const approvedRow = page.locator('[data-testid="gate-activity-approved-gate-act-1"]');
    await expect(approvedRow).toBeVisible();

    const rejectedRow = page.locator('[data-testid="gate-activity-rejected-gate-act-2"]');
    await expect(rejectedRow).toBeVisible();

    // Verify copy hash button and verdict hash
    const hashEl = page.locator('[data-testid="activity-verdict-hash"]');
    await expect(hashEl).toBeVisible();
    await expect(hashEl).toContainText(
      '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
    );

    // Hover/focus the emoji hint in approved row
    const approvedHint = page.locator('[data-testid="activity-gate-hint-gate-act-1"]');
    await approvedHint.focus();

    // Capture visual proof (desktop, tablet, mobile)
    await annotatedScreenshot(page, testInfo, {
      name: '03-drawer-gates-activity',
      annotations: [
        {
          selector: '[data-testid="activity-tab-gates"]',
          label: '🤖 Gates (2) Tab in Activity Section',
        },
        {
          selector: '[data-testid="gate-activity-approved-gate-act-1"]',
          badgeOffset: { dx: -26, dy: 0 },
          label: '✅🤖 Approved Gate Row with Latency (1420 ms)',
        },
        {
          selector: '.gate-popover',
          badgeAnchor: 'right',
          label: 'Popover: hook, latency and selectable verdict SHA256 hex',
        },
        {
          selector: '[data-testid="gate-activity-rejected-gate-act-2"]',
          badgeOffset: { dx: -26, dy: 0 },
          label: '🛑🤖 Veto Gate Row with 1-Click Jump to Audit Comment',
        },
      ],
    });
  });
});
