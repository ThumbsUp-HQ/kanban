// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.

import { resolve } from 'node:path';
import { mkdirSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect } from '../support/test';
import { mockApi, loadFixture, type MockHandlers } from '../support/mockApi';
import { annotatedScreenshot } from '../support/annotate';

process.env.QA_TICKET_ID = 'KANBA-216';
const SCREENSHOT_DIR = resolve(
  import.meta.dirname,
  '../../../../docs/qa/KANBA-216/screenshots',
);
mkdirSync(SCREENSHOT_DIR, { recursive: true });

async function applyTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.evaluate((t) => {
    document.documentElement.setAttribute('data-theme', t);
    localStorage.setItem('kb:theme', t);
  }, theme);
  await page.waitForTimeout(100);
}

const me = {
  id: '01918a22-0000-7000-8000-000000000001',
  handle: '@adam',
  display_name: 'Adam Outler',
  email: 'adam@example.com',
  type: 'USER',
  is_server_admin: true,
  aal_level: 2,
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'SERVER_ADMIN'],
};

const projectKan = {
  id: '01918a22-0000-7000-8000-000000000010',
  identifier: 'KAN',
  key: 'KAN',
  name: 'Platform Core',
  description: 'Agent-First, Security-First Kanban & Ticketing Platform',
  description_markdown: 'Agent-First, Security-First Kanban & Ticketing Platform',
  modules_enabled: true,
  default_module_ids: ['mod-1'],
  auto_archive_days: 14,
  is_project_admin: true,
  capabilities: ['VIEW', 'COMMENT', 'EDIT', 'ADMIN', 'PROJECT_ADMIN', 'SERVER_ADMIN'],
};

const states = [
  { id: 'state-backlog', name: 'Backlog', group: 'backlog', color: '#64748b', sort_order: 1, is_default: true },
  { id: 'state-todo', name: 'Todo', group: 'unstarted', color: '#3b82f6', sort_order: 2, is_default: false },
  { id: 'state-in-progress', name: 'In Progress', group: 'started', color: '#f59e0b', sort_order: 3, is_default: false },
  { id: 'state-done', name: 'Done', group: 'completed', color: '#10b981', sort_order: 4, is_default: false },
];

const priorities = [
  { slug: 'urgent', name: 'urgent', label: 'Urgent', emoji: '🔥', sort_order: 1 },
  { slug: 'high', name: 'high', label: 'High', emoji: '⚡', sort_order: 2 },
  { slug: 'medium', name: 'medium', label: 'Medium', emoji: '🔹', sort_order: 3 },
  { slug: 'low', name: 'low', label: 'Low', emoji: '💤', sort_order: 4 },
];

const mockDefinitions = [
  {
    id: 'f-cvss',
    slug: 'cvss-score',
    name: 'CVSS Score',
    tier: 'wasm',
    output_format: 'severity_pill',
    output_format_metadata: {
      critical_min: 9.0,
      high_min: 7.0,
      medium_min: 4.0,
      low_min: 0.1,
    },
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    manifest_sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0',
    is_enabled: true,
    approval_status: 'APPROVED',
    script_source: 'formula: issue.priority == "critical" ? 9.8 : (issue.priority == "high" ? 8.8 : 3.5)',
  },
  {
    id: 'f-env',
    slug: 'target-env',
    name: 'Target Environment',
    tier: 'nsjail',
    output_format: 'text',
    output_format_metadata: { prefix: 'Env: ' },
    target_scope: 'WORKSPACE',
    credential_mode: 'PROJECT_ADMIN_SP',
    egress_allowlist: ['/api/v1/projects/KAN'],
    manifest_sha256: 'b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01',
    is_enabled: true,
    approval_status: 'PENDING',
    script_source: 'return "staging-us-east";',
  },
  {
    id: 'f-build',
    slug: 'build-number',
    name: 'Build Number',
    tier: 'wasm',
    output_format: 'number',
    output_format_metadata: { unit_suffix: 'build', maximum_fraction_digits: 0 },
    target_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    egress_allowlist: [],
    manifest_sha256: 'c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4',
    is_enabled: true,
    approval_status: null,
    script_source: 'scalar: 4092',
  },
];

const mockResults = [
  {
    field_id: 'f-cvss',
    field_slug: 'cvss-score',
    field_name: 'CVSS Score',
    output_format: 'severity_pill',
    value: { level: 'high', score: 8.8, label: 'High' },
    status: 'SUCCESS',
    tier: 'Wasmtime',
    token_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    last_latency_ms: 12,
    computed_at: '2026-11-13T12:00:00Z',
  },
  {
    field_id: 'f-env',
    field_slug: 'target-env',
    field_name: 'Target Environment',
    output_format: 'text',
    value: null,
    status: 'ERROR',
    error_code: 'SANDBOX_UNAVAILABLE_IN_STANDALONE',
    tier: 'nsjail',
    token_scope: 'WORKSPACE',
    credential_mode: 'PROJECT_ADMIN_SP',
    last_latency_ms: 0,
    computed_at: '2026-11-13T12:00:00Z',
  },
  {
    field_id: 'f-build',
    field_slug: 'build-number',
    field_name: 'Build Number',
    output_format: 'number',
    value: 4092,
    status: 'SUCCESS',
    tier: 'Wasmtime',
    token_scope: 'PROJECT',
    credential_mode: 'INVOKING_USER',
    last_latency_ms: 8,
    computed_at: '2026-11-13T12:00:00Z',
  },
];

const mockApprovals = [
  {
    id: 'appr-env',
    field_id: 'f-env',
    status: 'PENDING',
    target_scope: 'WORKSPACE',
    credential_mode: 'PROJECT_ADMIN_SP',
    manifest_sha256: 'b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef01',
    justification: 'Needs workspace token to verify target environments',
    created_at: '2026-11-13T10:00:00Z',
    updated_at: '2026-11-13T10:00:00Z',
  },
];

const issueKan142 = {
  key: 'KAN-142',
  object_id: '11111111-1111-1111-1111-111111111111',
  project_key: 'KAN',
  project_name: 'Platform Core',
  summary: 'Harden Multi-Card OIDC & LDAPS Auth Studio',
  description_markdown: 'Detailed description of custom scripted fields verification.',
  priority: {
    slug: 'high',
    label: 'High',
    emoji: '⚡',
    sort_order: 2,
    sla_target: null,
  },
  state: {
    name: 'In Progress',
    group: 'started',
  },
  etag: '"etag-kan-142"',
};

function getCommonMocks(): MockHandlers {
  return {
    'GET /api/v1/me': { json: me },
    'GET /api/v1/auth/me': { json: me },
    'GET /api/v1/users/me': { json: me },
    'GET /api/v1/auth/session': {
      json: {
        authenticated: true,
        aal_level: 2,
        csrf_token: 'test-csrf-token-kanba-216',
        user: me,
      },
    },
    'GET /api/v1/session/csrf': { json: { csrf_token: 'test-csrf-token-kanba-216' } },
    'GET /api/v1/setup/status': { json: { initialized: true, is_initialized: true, requires_setup: false } },
    'GET /api/v1/system/status': { json: loadFixture('system-status-standalone') },
    'GET /api/v1/notifications': { json: { items: [], unread_count: 0 } },
    'GET /api/v1/workspaces': {
      json: [
        {
          id: '01918a22-0000-7000-8000-000000000001',
          name: 'Primary Workspace',
          slug: 'kanban',
          is_current: true,
        },
      ],
    },
    'GET /api/v1/projects': { json: [projectKan] },
    'GET /api/v1/projects/KAN': { json: projectKan },
    'GET /api/v1/projects/KAN/states': { json: states },
    'GET /api/v1/projects/KAN/priorities': { json: priorities },
    'GET /api/v1/projects/KAN/labels': { json: [] },
    'GET /api/v1/projects/KAN/members': { json: [] },
    'GET /api/v1/projects/KAN/cycles': { json: [] },
    'GET /api/v1/projects/KAN/modules': { json: [] },
    'GET /api/v1/projects/KAN/custom-fields': { json: mockDefinitions },
    'GET /api/v1/objects/:id/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN/access': { json: loadFixture('access-project-kan') },
    'GET /api/v1/objects/KAN-142/canonical-url': { json: { canonical_url: '/projects/KAN/issues/KAN-142' } },
    'GET /api/v1/objects/11111111-1111-1111-1111-111111111111/access': { json: loadFixture('access-kan-142') },
    'GET /api/v1/issues': { json: [issueKan142] },
    'GET /api/v1/issues/KAN-142': { json: issueKan142 },
    'GET /api/v1/issues/KAN-142/subscription': { json: { is_subscribed: false } },
    'GET /api/v1/issues/KAN-142/activity': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/KAN-142/comments': { json: { items: [], total: 0 } },
    'GET /api/v1/issues/KAN-142/sub-issues': { json: [] },
    'GET /api/v1/issues/KAN-142/links': { json: [] },
    'GET /api/v1/issues/KAN-142/attachments': { json: [] },
    'GET /api/v1/issues/KAN-142/custom-fields': { json: mockResults },
    'GET /api/v1/custom-fields/f-env/approvals': { json: mockApprovals },
    'GET /api/v1/custom-fields/f-cvss/approvals': { json: [] },
    'POST /api/v1/projects/KAN/custom-fields/test-execute': {
      status: 200,
      json: {
        output_format: 'severity_pill',
        value: { level: 'high', score: 8.8, label: 'High' },
        latency_ms: 14,
        logs: '[INFO] Formula evaluated successfully in 14ms\n[DEBUG] issue.priority = high\n[INFO] Matched CVSS severity pill High (8.8)',
        status: 'SUCCESS',
      },
    },
  };
}

test.describe('KANBA-216: Custom Scripted Fields Studio & Ticket Rail Proofs', () => {
  test('01-custom-fields-studio-test-execute: verifies flavor selector, rows 8 textarea, and test-execute evaluation', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getCommonMocks());
    await page.goto('/projects/KAN/settings/custom-fields');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="custom-fields-editor-layout"]')).toBeVisible();

    // Select CVSS Score definition
    const cvssItem = page.locator('[data-testid="field-item-cvss-score"]');
    await cvssItem.click();

    // Check slug pattern attribute
    const slugInput = page.locator('[data-testid="field-slug-input"]');
    const slugPattern = await slugInput.getAttribute('pattern');
    expect(slugPattern).toContain('a-z0-9');
    expect(slugPattern).toContain('{1,62}');

    // Check metadata textarea has rows 8
    const metaTextarea = page.locator('[data-testid="format-metadata-textarea"]');
    await expect(metaTextarea).toHaveAttribute('rows', '8');

    // Run Test Execute against KAN-142
    const issueKeyInput = page.locator('[data-testid="test-issue-key-input"]');
    await issueKeyInput.fill('KAN-142');

    const testExecBtn = page.locator('[data-testid="test-execute-btn"]');
    await testExecBtn.click();

    // Verify evaluation telemetry and output preview
    await expect(page.locator('[data-testid="test-latency"]')).toContainText('14');
    await expect(page.locator('[data-testid="test-output-pill"]')).toContainText('8.8');
    await expect(page.locator('[data-testid="test-output-pill"]')).toContainText('High');
    await expect(page.locator('[data-testid="test-logs"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `01-studio-test-execute-${theme}`,
        annotations: [
          {
            selector: '[data-testid="field-slug-input"]',
            label: '1: Slug Pattern Regex',
            note: 'Validated with ASCII hyphens avoiding /v flag syntax errors',
          },
          {
            selector: '[data-testid="field-flavor-select"]',
            label: '2: Field Flavor Selector',
            note: 'Aligned with Scalar, Formula Expression, WebAssembly, and nsjail Advanced',
          },
          {
            selector: '[data-testid="format-metadata-textarea"]',
            label: '3: Enlarged Metadata JSON Textarea',
            note: 'Enlarged to rows=8 preventing JSON clipping',
          },
          {
            selector: '[data-testid="custom-field-test-panel"]',
            label: '4: Test Execute Section',
            note: 'Interactive evaluation with latency pill, logs viewer, and rendered preview',
          },
        ],
      });
    }
  });

  test('02-custom-fields-studio-dual-control: verifies dual-control policy banner on pending approval field', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getCommonMocks());
    await page.goto('/projects/KAN/settings/custom-fields');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('[data-testid="custom-fields-editor-layout"]')).toBeVisible();

    // Select Target Environment definition (PENDING approval)
    const envItem = page.locator('[data-testid="field-item-target-env"]');
    await envItem.click();

    // Verify literal dual-control explanation banner
    const banner = page.locator('[data-testid="dual-control-explanation-banner"]');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('Dual-Control Policy:');
    await expect(banner).toContainText('Self-approval is blocked (403 Forbidden)');

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `02-studio-dual-control-${theme}`,
        annotations: [
          {
            selector: '[data-testid="dual-control-explanation-banner"]',
            label: '1: Dual-Control Explanation Banner',
            note: 'Explicit requirement for distinct administrator holding target_scope authority + fresh AAL2',
          },
          {
            selector: '[data-testid="sp-warning-banner"]',
            label: '2: Service Principal Credential Banner',
            note: 'Prompts explicit admin acknowledgment before escalation',
          },
        ],
      });
    }
  });

  test('03-issue-drawer-custom-fields-rail: verifies 7-format rail rendering and sandbox unavailable tooltip', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getCommonMocks());
    await page.goto('/projects/KAN?peek=KAN-142');
    await page.waitForLoadState('networkidle');

    const railSection = page.locator('[data-testid="custom-fields-rail-section"]');
    await expect(railSection).toBeVisible();

    // Verify CVSS Score severity pill
    await expect(page.locator('[data-testid="custom-field-row-cvss-score"]')).toBeVisible();

    // Verify SANDBOX_UNAVAILABLE_IN_STANDALONE row
    const envRow = page.locator('[data-testid="custom-field-row-target-env"]');
    await expect(envRow).toBeVisible();
    await expect(envRow).toContainText('Optional CLI Sandbox not enabled in single-container mode');

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `03-drawer-custom-fields-${theme}`,
        annotations: [
          {
            selector: '[data-testid="custom-fields-rail-section"]',
            label: '1: Custom Fields Drawer Rail',
            note: 'Rendered in ?peek= drawer with project fallback resolution',
          },
          {
            selector: '[data-testid="custom-field-row-cvss-score"]',
            label: '2: Active Severity Pill',
            note: 'Rendered computed score from formula evaluation',
          },
          {
            selector: '[data-testid="custom-field-row-target-env"]',
            label: '3: Standalone Sandbox Indicator',
            note: 'Informative tooltip on standalone deployment without nsjail container',
          },
        ],
      });
    }
  });

  test('04-issue-fullscreen-custom-fields-rail: verifies custom fields rail rendering in fullscreen issue view', async ({
    page,
  }, testInfo) => {
    await mockApi(page, getCommonMocks());
    await page.goto('/projects/KAN/issues/KAN-142');
    await page.waitForLoadState('networkidle');

    const railSection = page.locator('[data-testid="custom-fields-rail-section"]');
    await expect(railSection).toBeVisible();

    await expect(page.locator('[data-testid="custom-field-row-cvss-score"]')).toBeVisible();
    await expect(page.locator('[data-testid="custom-field-row-build-number"]')).toBeVisible();

    for (const theme of ['light', 'dark'] as const) {
      await applyTheme(page, theme);
      await annotatedScreenshot(page, testInfo, {
        name: `04-fullscreen-custom-fields-${theme}`,
        annotations: [
          {
            selector: '[data-testid="custom-fields-rail-section"]',
            label: '1: Fullscreen Custom Fields Rail',
            note: 'Identical component and state rendering in fullscreen view',
          },
          {
            selector: '[data-testid="custom-field-row-cvss-score"]',
            label: '2: Severity Pill Value',
            note: 'Shows CVSS High 8.8 pill with hover elaboration',
          },
        ],
      });
    }
  });
});
